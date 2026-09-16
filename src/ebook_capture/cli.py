"""대화형 CLI 진입점."""
import argparse
import sys
import time
from pathlib import Path

from .capture import ScreenCapture
from .clicker import click
from .display import list_displays, require_permissions
from .geometry import Region
from .naming import latest_page_number, sanitize_title
from .pdfbuild import build_pdf, collect_pages, trailing_duplicates
from .picker import AbortWatcher, pick_point, pick_region
from .progress import load_loading_references, wait_for_loading
from .session import SessionConfig, run_session

# 실행 위치 기준의 상대 경로다. 소스 위치를 기준으로 삼으면 전역 설치했을 때
# 도구 내부 venv 안에 저장하려 들고, 어디서 실행하든 같은 곳이라 책이 섞인다.
RESULT_DIR = Path("result")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ebook-capture",
        description="화면을 자동 캡처해 PDF로 묶습니다. 루프 중 ESC로 언제든 중단됩니다.",
    )
    p.add_argument("--title", help="PDF 제목 (생략 시 대화형으로 물어봅니다)")
    p.add_argument("--interval", type=float, help="캡처 간격(초)")
    p.add_argument("--fullscreen", action="store_true", help="영역 지정 대신 디스플레이 전체 캡처")
    p.add_argument("--dpi", type=int, default=300, help="JPEG DPI 메타데이터 (기본 300)")
    p.add_argument("--quality", type=int, default=95, help="JPEG 품질 (기본 95)")
    p.add_argument("--page-size", choices=["a4"], default=None, help="PDF 페이지 박스를 A4로 배치")
    p.add_argument("--max-pages", type=int, default=2000, help="안전 상한 (기본 2000)")
    p.add_argument("--resume", metavar="제목|경로", help="저장된 세션으로 재개 (제목만 줘도 됩니다)")
    p.add_argument("--out", metavar="폴더", default=None,
                   help="결과를 저장할 폴더 (기본: 현재 폴더의 result)")
    p.add_argument("--loading-image", metavar="이미지", action="append", default=[],
                   help="로딩 표시 그림 (여러 번 줄 수 있습니다)")
    p.add_argument("--loading-region", action="store_true",
                   help="로딩 표시가 뜨는 영역을 클릭으로 지정합니다")
    p.add_argument("--record-loading", action="store_true",
                   help="로딩 표시를 직접 촬영해 등록합니다 (여러 장)")
    p.add_argument("--load-timeout", type=float, default=30.0, metavar="초",
                   help="로딩을 기다리는 최대 시간 (기본 30)")
    p.add_argument("--keep-duplicates", action="store_true",
                   help="끝에 연달아 찍힌 동일 페이지도 PDF 에 넣습니다")
    return p


def _is_single_color(image) -> bool:
    """이미지 전체가 단색인지 확인한다.

    CGPreflightScreenCaptureAccess()가 True를 반환해도 실제로는 권한이 아직
    적용되지 않아 캡처가 단색(검은 화면 등)으로 나오는 경우가 있다. TCC
    플래그만으로는 이 상황을 잡을 수 없다.
    """
    colors = image.getcolors(maxcolors=1)
    return colors is not None and len(colors) == 1


def save_previews(capturer, config: SessionConfig, out_dir: Path) -> list[Path]:
    """지정한 영역을 한 장씩 저장해 사용자가 눈으로 확인하게 한다.

    좌표를 잘못 잡은 채 수백 장을 캡처하는 사고를 막는 가장 싼 방법이다.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    regions = [("capture", config.capture_region), ("progress", config.progress_region)]
    if config.loading_region is not None:
        regions.append(("loading", config.loading_region))

    paths = []
    for label, region in regions:
        image = capturer.grab(region)
        path = out_dir / f"_preview_{label}.png"
        image.save(path)
        paths.append(path)
        # 로딩 영역은 로딩이 아닐 때 빈 화면인 것이 정상이라 단색 경고를 내지 않는다.
        if label != "loading" and _is_single_color(image):
            print(f"\n경고: '{label}' 미리보기가 완전한 단색 이미지입니다.")
            print("  화면 기록 권한이 실제로는 아직 적용되지 않았을 가능성이 높습니다")
            print("  (진짜로 빈 화면일 수도 있습니다 — 아래 미리보기를 직접 확인하세요).")
            print("  권한이 의심되면 이 프로그램을 실행한 앱(터미널 등)을 완전히 종료했다가")
            print("  다시 실행해 보세요.")
    return paths


def _ask(prompt: str) -> str:
    """빈 입력을 허용하지 않는 문자열 입력."""
    while True:
        try:
            raw = input(prompt).strip()
        except EOFError:
            raise SystemExit("\n입력이 종료되어 중단합니다.")
        if raw:
            return raw
        print("  값을 입력하세요.")


def _ask_float(prompt: str, minimum: float = 0.0) -> float:
    """숫자가 나올 때까지 되묻는다. 잘못 입력했다고 처음부터 다시 하게 만들지 않는다."""
    while True:
        raw = _ask(prompt)
        try:
            value = float(raw)
        except ValueError:
            print("  숫자를 입력하세요. 예: 2 또는 2.5")
            continue
        if value < minimum:
            print(f"  {minimum} 이상이어야 합니다.")
            continue
        return value


def _ask_index(prompt: str, count: int) -> int:
    """0 이상 count 미만의 번호가 나올 때까지 되묻는다."""
    while True:
        raw = _ask(prompt)
        try:
            index = int(raw)
        except ValueError:
            index = -1
        if 0 <= index < count:
            return index
        print(f"  0 부터 {count - 1} 사이의 번호를 입력하세요.")


def _resolve_session_path(value: str, root: Path | None = None) -> Path:
    """--resume 인자를 세션 파일 경로로 바꾼다.

    경로를 그대로 줘도 되고 제목만 줘도 된다. 제목이면 프로젝트 폴더
    result/<제목>/<제목>.session.json 을 먼저 보고, 없으면 폴더 구조가 생기기 전에
    저장된 result/<제목>.session.json 을 본다.
    """
    root = RESULT_DIR if root is None else root
    direct = Path(value)
    if direct.is_file():
        return direct
    for candidate in (
        root / value / f"{value}.session.json",
        root / f"{value}.session.json",
    ):
        if candidate.is_file():
            return candidate
    return direct


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


def _loading_reference_paths(result_root: Path, explicit: list[str]) -> list[Path]:
    """등록된 로딩 표시 그림을 모은다.

    --loading-image 로 직접 준 것과, 결과 폴더 아래 loading/ 에 넣어둔 것을 합친다.
    앱마다 로딩 표시가 다르므로 여러 장을 등록할 수 있다.
    """
    paths = [Path(value) for value in explicit]
    folder = Path(result_root) / "loading"
    if folder.is_dir():
        paths += [p for p in sorted(folder.iterdir())
                  if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES]
    seen, unique = set(), []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def _choose_display() -> Region:
    displays = list_displays()
    if not displays:
        raise SystemExit("연결된 디스플레이를 찾을 수 없습니다.")
    print("\n캡처할 디스플레이를 고르세요:")
    for i, d in enumerate(displays):
        print(f"  [{i}] ({d.left},{d.top}) {d.width}x{d.height}  스케일 {d.scale:.2f}x")
    index = _ask_index("번호: ", len(displays))
    return Region.from_display(displays[index])


def _configure(args) -> SessionConfig:
    raw_title = args.title if args.title is not None else _ask("PDF 제목: ")
    try:
        title = sanitize_title(raw_title)
    except ValueError as exc:
        raise SystemExit(f"제목이 올바르지 않습니다: {exc}")
    interval = args.interval if args.interval is not None else _ask_float("캡처 간격(초): ")

    print("\n영역과 클릭 지점을 지정합니다. 안내가 나오면 해당 위치를 클릭하세요.")
    capture_region = _choose_display() if args.fullscreen else pick_region("캡처 영역")
    click_point = pick_point("다음 페이지로 넘기는 버튼")
    progress_region = pick_region("진행률(%) 표시 영역")

    loading_region = None
    if args.loading_region:
        loading_region = pick_region("로딩 표시 영역")

    return SessionConfig(
        title=title,
        capture_region=capture_region,
        progress_region=progress_region,
        click_point=click_point,
        interval=interval,
        dpi=args.dpi,
        quality=args.quality,
        max_pages=args.max_pages,
        loading_region=loading_region,
        load_timeout=args.load_timeout,
    )


_RECORD_SECONDS = 3.0
_RECORD_POLL = 0.15
_RECORD_MAX_FRAMES = 8
_RECORD_MIN_DIFF = 6.0


def _record_loading(result_root: Path) -> int:
    """다음 페이지를 직접 눌러 로딩 표시를 여러 장 찍어 등록한다.

    로딩 표시는 도는 그림이라 한 장만으로는 각도가 다를 때 못 알아본다.
    서로 다른 프레임만 골라 저장한다.
    """
    print("로딩 표시를 등록합니다. 먼저 영역과 버튼을 지정하세요.")
    region = pick_region("로딩 표시 영역")
    point = pick_point("다음 페이지로 넘기는 버튼")

    folder = result_root / "loading"
    folder.mkdir(parents=True, exist_ok=True)

    print(f"\n3초 후 다음 페이지를 누르고 {_RECORD_SECONDS:.0f}초 동안 촬영합니다. 손대지 마세요.")
    time.sleep(3)

    kept: list = []
    with ScreenCapture() as capturer:
        click(*point)
        deadline = time.monotonic() + _RECORD_SECONDS
        while time.monotonic() < deadline and len(kept) < _RECORD_MAX_FRAMES:
            frame = capturer.grab(region)
            if all(_frame_difference(frame, seen) > _RECORD_MIN_DIFF for seen in kept):
                kept.append(frame)
            time.sleep(_RECORD_POLL)

    if not kept:
        print("촬영된 화면이 없습니다.")
        return 1
    for i, frame in enumerate(kept, 1):
        path = folder / f"loading_{i:02d}.png"
        frame.save(path)
        print(f"  저장: {path}")
    print(f"\n{len(kept)}장을 등록했습니다. 다음 실행부터 자동으로 사용됩니다.")
    return 0


def _frame_difference(a, b) -> float:
    from PIL import ImageChops, ImageStat

    small_a = a.convert("RGB").resize((64, 64))
    small_b = b.convert("RGB").resize((64, 64))
    channels = ImageStat.Stat(ImageChops.difference(small_a, small_b)).mean
    return sum(channels) / len(channels)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    require_permissions()
    result_root = Path(args.out).expanduser() if args.out else RESULT_DIR
    result_root.mkdir(parents=True, exist_ok=True)

    if args.record_loading:
        return _record_loading(result_root)

    if args.resume:
        session_path = _resolve_session_path(args.resume, result_root)
        try:
            config = SessionConfig.load(session_path)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            print(f"세션 파일을 읽을 수 없습니다: {args.resume}")
            print(f"  {exc}")
            return 1
        print(f"세션을 재개합니다: {config.title}")
        if any(d.scale != 1.0 for d in list_displays()):
            print("경고: 현재 디스플레이 배율이 1.00x가 아닙니다.")
            print("  세션 저장 당시와 화면 설정이 다르면 저장된 좌표가 지금 화면과 맞지 않을 수 있습니다.")
        # 세션 파일이 있는 곳에서 이어간다. 폴더 구조 이전에 저장된 세션도 그대로 동작한다.
        project_dir = session_path.parent
    else:
        config = _configure(args)
        project_dir = result_root / config.title

    # 제목마다 별도 폴더를 둔다. 여러 권을 캡처해도 result/ 가 섞이지 않는다.
    project_dir.mkdir(parents=True, exist_ok=True)

    existing = collect_pages(project_dir, config.title)
    start_page = latest_page_number(existing)
    pending_delete: list[Path] = []

    reference_paths = _loading_reference_paths(result_root, args.loading_image)
    loading_references = load_loading_references(reference_paths) if reference_paths else None

    print("\n=== 시작 준비 ===")
    print(f"  제목        : {config.title}")
    print(f"  저장 위치   : {project_dir}")
    print(f"  기존 캡처   : {len(existing)}장" + (f" (마지막 p{start_page:03d})" if start_page else ""))
    print(f"  캡처 간격   : {config.interval:g}초")
    print(f"  안전 상한   : {config.max_pages}장")
    if config.loading_region is None:
        print("  로딩 대기   : 사용 안 함")
    elif reference_paths:
        print(f"  로딩 대기   : 등록 그림 {len(reference_paths)}장 + 변화 감지, 최대 {config.load_timeout:g}초")
    else:
        print(f"  로딩 대기   : 변화 감지만, 최대 {config.load_timeout:g}초")
        print("     등록된 로딩 그림이 없습니다. 아래로 먼저 등록하면 더 정확해집니다:")
        print("       ebook-capture --record-loading")


    if args.resume and start_page:
        print(f"기존 {start_page}쪽을 찾았습니다. p{start_page + 1:03d} 부터 이어서 캡처합니다.")
    elif existing:
        print(f"\n경고: '{config.title}' 이름으로 이미 {len(existing)}쪽이 저장되어 있습니다.")
        print("  이대로 진행하면 앞쪽부터 덮어써서 이전에 캡처한 것과 뒤섞입니다.")
        print("  이어서 캡처하려면 --resume 을 사용하세요.")
        try:
            answer = input("  기존 파일을 지우고 처음부터 시작하려면 d, 취소하려면 다른 키: ").strip().lower()
        except EOFError:
            answer = ""
        if answer != "d":
            print("취소했습니다.")
            return 1
        # 미리보기 확인 전까지는 지우지 않는다 (I3). 여기서는 '동의'만 기록한다.
        pending_delete = existing

    with ScreenCapture() as capturer:
        previews = save_previews(capturer, config, project_dir)
        for path in previews:
            print(f"  미리보기 저장: {path}")
        try:
            answer = input("\n미리보기가 올바릅니까? 계속하려면 y: ").strip().lower()
        except EOFError:
            answer = ""
        if answer != "y":
            # 취소했으면 무엇이 잘못됐는지 볼 수 있게 미리보기를 남겨둔다.
            print("취소했습니다.")
            return 1

        # 확인이 끝났으면 미리보기는 역할을 다했다. 결과 폴더를 깨끗하게 둔다.
        for path in previews:
            path.unlink(missing_ok=True)

        # 미리보기 확인이 끝났으니 이제 실제로 기존 페이지를 지운다.
        if pending_delete:
            for path in pending_delete:
                path.unlink()
            start_page = 0

        session_path = project_dir / f"{config.title}.session.json"
        config.save(session_path)
        print(f"세션 설정 저장: {session_path}")

        def report(page: int, percent: float | None) -> None:
            shown = f"{percent:.0f}%" if percent is not None else "판독 실패"
            print(f"  p{page:03d}  진행률 {shown}", flush=True)

        with AbortWatcher() as watcher:
            print("\n5초 후 시작합니다. 대상 창을 맨 앞으로 띄워두세요. 중단하려면 ESC.")
            time.sleep(5)
            if watcher.aborted:
                print("취소했습니다.")
                return 1
            try:
                last_page, reason = run_session(
                    config, project_dir, capturer, lambda pt: click(*pt), watcher,
                    loading_references=loading_references,
                    on_page=report, start_page=start_page,
                )
            except KeyboardInterrupt:
                print("\n사용자가 강제로 중단했습니다 (Ctrl+C).")
                print(f"  캡처한 이미지와 세션 설정은 {project_dir} 에 그대로 있습니다. --resume 으로 이어서 계속할 수 있습니다.")
                return 1
            except Exception as exc:  # noqa: BLE001 - 예상 못 한 오류도 한국어로 안내해야 한다
                print(f"\n캡처 중 예상치 못한 오류가 발생했습니다: {exc}")
                print(f"  캡처한 이미지와 세션 설정은 {project_dir} 에 그대로 있습니다. --resume 으로 이어서 계속할 수 있습니다.")
                return 1

    captured = last_page - start_page
    print(f"\n캡처 종료: 이번에 {captured}장, 총 {last_page}쪽 — {reason}")
    if last_page == 0:
        print("캡처된 페이지가 없어 PDF를 만들지 않습니다.")
        return 1

    try:
        pdf_path = build_pdf(project_dir, config.title, page_size=args.page_size,
                             drop_trailing_duplicates=not args.keep_duplicates)
    except (ValueError, OSError) as exc:
        print(f"PDF 생성에 실패했습니다: {exc}")
        print(f"캡처한 이미지는 {project_dir} 에 그대로 있습니다. 문제를 고친 뒤 다시 시도하세요.")
        return 1
    all_pages = collect_pages(project_dir, config.title)
    skipped = [] if args.keep_duplicates else trailing_duplicates(all_pages)
    merged_pages = len(all_pages) - len(skipped)
    if skipped:
        print(f"끝에 연달아 찍힌 동일 페이지 {len(skipped)}장은 PDF 에서 제외했습니다"
              f" (p{skipped[0].stem.split('_p')[-1]} 부터). 이미지 파일은 그대로 있습니다.")
        print("  모두 넣으려면 --keep-duplicates 를 쓰세요.")
    size_mb = pdf_path.stat().st_size / 1e6
    print(f"PDF 생성 완료: {pdf_path}  ({merged_pages}쪽, {size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
