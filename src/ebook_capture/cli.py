"""대화형 CLI 진입점."""
import argparse
import sys
import time
from pathlib import Path

from .capture import ScreenCapture
from .clicker import click
from .display import list_displays, require_permissions
from .geometry import Region
from .naming import sanitize_title
from .pdfbuild import build_pdf
from .picker import AbortWatcher, pick_point, pick_region
from .session import SessionConfig, StopReason, run_session

RESULT_DIR = Path(__file__).resolve().parents[2] / "result"


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
    p.add_argument("--resume", metavar="JSON", help="저장된 세션 설정으로 재개")
    return p


def save_previews(capturer, config: SessionConfig, out_dir: Path) -> list[Path]:
    """지정한 영역을 한 장씩 저장해 사용자가 눈으로 확인하게 한다.

    좌표를 잘못 잡은 채 수백 장을 캡처하는 사고를 막는 가장 싼 방법이다.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for label, region in (("capture", config.capture_region), ("progress", config.progress_region)):
        path = out_dir / f"_preview_{label}.png"
        capturer.grab(region).save(path)
        paths.append(path)
    return paths


def _choose_display() -> Region:
    displays = list_displays()
    print("\n캡처할 디스플레이를 고르세요:")
    for i, d in enumerate(displays):
        print(f"  [{i}] ({d.left},{d.top}) {d.width}x{d.height}  스케일 {d.scale:.2f}x")
    index = int(input("번호: ").strip())
    return Region.from_display(displays[index])


def _configure(args) -> SessionConfig:
    title = sanitize_title(args.title or input("PDF 제목: ").strip())
    interval = args.interval if args.interval is not None else float(input("캡처 간격(초): ").strip())

    print("\n영역과 클릭 지점을 지정합니다. 안내가 나오면 해당 위치를 클릭하세요.")
    capture_region = _choose_display() if args.fullscreen else pick_region("캡처 영역")
    click_point = pick_point("다음 페이지로 넘기는 버튼")
    progress_region = pick_region("진행률(%) 표시 영역")

    return SessionConfig(
        title=title,
        capture_region=capture_region,
        progress_region=progress_region,
        click_point=click_point,
        interval=interval,
        dpi=args.dpi,
        quality=args.quality,
        max_pages=args.max_pages,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    require_permissions()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    if args.resume:
        config = SessionConfig.load(Path(args.resume))
        print(f"세션을 재개합니다: {config.title}")
    else:
        config = _configure(args)

    with ScreenCapture() as capturer:
        for path in save_previews(capturer, config, RESULT_DIR):
            print(f"  미리보기 저장: {path}")
        if input("\n미리보기가 올바릅니까? 계속하려면 y: ").strip().lower() != "y":
            print("취소했습니다.")
            return 1

        session_path = RESULT_DIR / f"{config.title}.session.json"
        config.save(session_path)
        print(f"세션 설정 저장: {session_path}")

        print("\n5초 후 시작합니다. 대상 창을 맨 앞으로 띄워두세요. 중단하려면 ESC.")
        time.sleep(5)

        def report(page: int, percent: float | None) -> None:
            shown = f"{percent:.0f}%" if percent is not None else "판독 실패"
            print(f"  p{page:03d}  진행률 {shown}", flush=True)

        with AbortWatcher() as watcher:
            pages, reason = run_session(
                config, RESULT_DIR, capturer, lambda pt: click(*pt), watcher, on_page=report
            )

    print(f"\n캡처 종료: {pages}장 — {reason}")
    if pages == 0:
        print("캡처된 페이지가 없어 PDF를 만들지 않습니다.")
        return 1

    pdf_path = build_pdf(RESULT_DIR, config.title, page_size=args.page_size)
    size_mb = pdf_path.stat().st_size / 1e6
    print(f"PDF 생성 완료: {pdf_path}  ({pages}쪽, {size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
