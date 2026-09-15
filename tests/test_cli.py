from pathlib import Path

import pytest
from PIL import Image

from ebook_capture import cli as cli_mod
from ebook_capture.cli import _ask_float, _ask_index, build_parser, main, save_previews
from ebook_capture.geometry import Region
from ebook_capture.session import SessionConfig, StopReason


def test_parser_defaults_to_region_mode():
    args = build_parser().parse_args([])
    assert args.fullscreen is False, "기본은 영역 지정이다 (research.md 6.3)"
    assert args.dpi == 300
    assert args.max_pages == 2000
    assert args.page_size is None


def test_parser_accepts_options():
    args = build_parser().parse_args(
        ["--title", "내책", "--interval", "2.5", "--page-size", "a4", "--fullscreen"]
    )
    assert args.title == "내책"
    assert args.interval == 2.5
    assert args.page_size == "a4"
    assert args.fullscreen is True


def test_parser_rejects_bad_page_size():
    import pytest

    with pytest.raises(SystemExit):
        build_parser().parse_args(["--page-size", "letter"])


class StubCapturer:
    def grab(self, region):
        return Image.new("RGB", (region.width, region.height), "white")


def test_save_previews_writes_both_regions(tmp_path):
    config = SessionConfig(
        title="책",
        capture_region=Region(0, 0, 40, 40),
        progress_region=Region(0, 100, 30, 20),
        click_point=(10, 10),
        interval=1.0,
    )
    previews = save_previews(StubCapturer(), config, tmp_path)
    assert len(previews) == 2
    assert all(p.exists() for p in previews)
    assert any("capture" in p.name for p in previews)
    assert any("progress" in p.name for p in previews)


def _install_fakes(monkeypatch, tmp_path, *, confirm="y", pages=3):
    """main()의 OS 의존 협력자를 전부 가짜로 바꾸고 호출 순서를 기록한다."""
    events: list[str] = []

    class FakeCapturer:
        def grab(self, region):
            return Image.new("RGB", (region.width, region.height), "white")

        def __enter__(self):
            events.append("capture_open")
            return self

        def __exit__(self, *exc):
            events.append("capture_close")

    class FakeWatcher:
        aborted = False

        def __init__(self):
            events.append("watcher_init")

        def __enter__(self):
            events.append("watcher_enter")
            return self

        def __exit__(self, *exc):
            events.append("watcher_exit")

    def fake_run_session(config, out_dir, capturer, clicker_fn, watcher, on_page=None, start_page=0):
        saved = (Path(out_dir) / f"{config.title}.session.json").exists()
        events.append(f"run_session(session_saved={saved})")
        events.append(f"start_page={start_page}")
        return start_page + pages, StopReason.COMPLETE

    def fake_build_pdf(out_dir, title, page_size=None):
        events.append("build_pdf")
        path = Path(out_dir) / f"{title}.pdf"
        path.write_bytes(b"%PDF-1.4\n")
        return path

    answers = iter(confirm if isinstance(confirm, list) else [confirm])
    monkeypatch.setattr(cli_mod, "RESULT_DIR", tmp_path)
    monkeypatch.setattr(cli_mod, "require_permissions", lambda: events.append("perms"))
    monkeypatch.setattr(cli_mod, "ScreenCapture", FakeCapturer)
    monkeypatch.setattr(cli_mod, "AbortWatcher", FakeWatcher)
    monkeypatch.setattr(cli_mod, "run_session", fake_run_session)
    monkeypatch.setattr(cli_mod, "build_pdf", fake_build_pdf)
    monkeypatch.setattr(cli_mod, "pick_region", lambda label: Region(0, 0, 40, 40))
    monkeypatch.setattr(cli_mod, "pick_point", lambda prompt: (10, 10))
    monkeypatch.setattr("time.sleep", lambda s: events.append(f"sleep({s})"))
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    return events


def test_main_happy_path_keeps_safety_ordering(monkeypatch, tmp_path):
    events = _install_fakes(monkeypatch, tmp_path)
    assert main(["--title", "책", "--interval", "0"]) == 0
    assert events.count("watcher_enter") == 1, "AbortWatcher는 실행당 정확히 한 번만 진입해야 한다"
    assert events.index("watcher_enter") > events.index("capture_open")
    assert "run_session(session_saved=True)" in events, "세션 JSON은 루프 시작 전에 저장되어야 한다"
    assert events.index("build_pdf") > events.index("capture_close")


def test_main_declining_preview_never_starts_keyboard_hook(monkeypatch, tmp_path):
    events = _install_fakes(monkeypatch, tmp_path, confirm="n")
    assert main(["--title", "책", "--interval", "0"]) == 1
    assert "watcher_init" not in events, "취소했는데 전역 키보드 훅을 만들면 안 된다"
    assert "watcher_enter" not in events
    assert "capture_close" in events, "취소해도 캡처 자원은 정리되어야 한다"


def test_main_zero_pages_skips_pdf(monkeypatch, tmp_path):
    events = _install_fakes(monkeypatch, tmp_path, pages=0)
    assert main(["--title", "책", "--interval", "0"]) == 1
    assert "build_pdf" not in events


def test_ask_float_retries_until_valid(monkeypatch, capsys):
    answers = iter(["abc", "-1", "2.5"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert _ask_float("간격: ") == 2.5
    assert "숫자를 입력하세요" in capsys.readouterr().out


def test_ask_index_retries_until_in_range(monkeypatch, capsys):
    answers = iter(["9", "x", "1"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert _ask_index("번호: ", 3) == 1
    assert "0 부터 2 사이" in capsys.readouterr().out


def test_ask_float_aborts_cleanly_on_eof(monkeypatch):
    """stdin이 터미널이 아니면 트레이스백 대신 한국어 안내로 끝나야 한다."""
    def raise_eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    with pytest.raises(SystemExit):
        _ask_float("간격: ")


def test_choose_display_without_displays_exits(monkeypatch):
    """디스플레이가 없으면 무한 반복 대신 즉시 중단해야 한다."""
    monkeypatch.setattr(cli_mod, "list_displays", lambda: [])
    with pytest.raises(SystemExit):
        cli_mod._choose_display()


def test_main_treats_eof_at_confirmation_as_decline(monkeypatch, tmp_path):
    """자동 실행 환경에서 EOF가 '진행'으로 해석되면 멋대로 클릭을 시작한다."""
    events = _install_fakes(monkeypatch, tmp_path)

    def raise_eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    assert main(["--title", "책", "--interval", "0"]) == 1
    assert "watcher_init" not in events


def test_main_resume_continues_after_existing_pages(monkeypatch, tmp_path):
    """--resume 은 기존 페이지 다음 번호부터 이어가야 한다."""
    for i in (1, 2, 3):
        (tmp_path / f"책_p{i:03d}.jpg").write_bytes(b"x")
    cfg = SessionConfig(
        title="책",
        capture_region=Region(0, 0, 40, 40),
        progress_region=Region(0, 100, 30, 20),
        click_point=(10, 10),
        interval=0.0,
    )
    session_file = tmp_path / "책.session.json"
    cfg.save(session_file)
    events = _install_fakes(monkeypatch, tmp_path)
    assert main(["--resume", str(session_file)]) == 0
    assert "start_page=3" in events, f"start_page가 전달되지 않았다: {events}"


def test_main_refuses_to_overwrite_existing_pages(monkeypatch, tmp_path):
    """--resume 없이 같은 제목으로 재실행하면 덮어쓰기 전에 막아야 한다."""
    project = tmp_path / "책"
    project.mkdir()
    (project / "책_p001.jpg").write_bytes(b"x")
    events = _install_fakes(monkeypatch, tmp_path, confirm="n")
    assert main(["--title", "책", "--interval", "0"]) == 1
    assert "watcher_init" not in events
    assert (project / "책_p001.jpg").exists(), "취소했는데 파일을 지우면 안 된다"


def test_main_deletes_existing_pages_only_after_preview_confirmed(monkeypatch, tmp_path):
    """d로 동의해도 미리보기 확인 전에는 지우지 않는다."""
    project = tmp_path / "책"
    project.mkdir()
    old = project / "책_p001.jpg"
    old.write_bytes(b"x")
    keep_pdf = project / "책.pdf"
    keep_pdf.write_bytes(b"%PDF-1.4\n")
    events = _install_fakes(monkeypatch, tmp_path, confirm=["d", "n"])
    assert main(["--title", "책", "--interval", "0"]) == 1
    assert old.exists(), "미리보기에서 취소했는데 기존 페이지를 지우면 안 된다"


def test_main_deletes_existing_pages_after_full_confirmation(monkeypatch, tmp_path):
    """d + y 를 모두 거친 뒤에만 기존 페이지를 지우고 처음부터 시작한다."""
    project = tmp_path / "책"
    project.mkdir()
    old = project / "책_p001.jpg"
    old.write_bytes(b"x")
    keep = project / "책.session.json"
    keep.write_text("{}", encoding="utf-8")
    events = _install_fakes(monkeypatch, tmp_path, confirm=["d", "y"])
    assert main(["--title", "책", "--interval", "0"]) == 0
    assert not old.exists(), "확인까지 마쳤으면 기존 페이지는 지워져야 한다"
    assert keep.exists(), "페이지 이미지가 아닌 파일은 건드리면 안 된다"
    assert "start_page=0" in events


def test_main_esc_during_countdown_aborts_before_run_session(monkeypatch, tmp_path):
    """카운트다운 중 ESC가 눌리면(watcher.aborted) 클릭 루프를 아예 시작하면 안 된다."""
    events = _install_fakes(monkeypatch, tmp_path)

    class AbortedWatcher:
        aborted = True

        def __init__(self):
            events.append("watcher_init")

        def __enter__(self):
            events.append("watcher_enter")
            return self

        def __exit__(self, *exc):
            events.append("watcher_exit")

    monkeypatch.setattr(cli_mod, "AbortWatcher", AbortedWatcher)
    assert main(["--title", "책", "--interval", "0"]) == 1
    assert not any(e.startswith("run_session") for e in events), "ESC로 중단됐으면 run_session을 호출하면 안 된다"
    assert "sleep(5)" in events, "카운트다운은 AbortWatcher 안에서 여전히 일어나야 한다"


def test_main_reports_unexpected_exception_in_korean(monkeypatch, tmp_path, capsys):
    """run_session에서 예기치 못한 예외가 나면 영어 트레이스백 대신 한국어 안내로 끝나야 한다."""
    events = _install_fakes(monkeypatch, tmp_path)

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(cli_mod, "run_session", boom)
    assert main(["--title", "책", "--interval", "0"]) == 1
    out = capsys.readouterr().out
    assert "disk full" not in out or "오류" in out
    assert "--resume" in out


def test_main_reports_actual_merged_page_count(monkeypatch, tmp_path, capsys):
    """PDF 완료 메시지는 build_pdf가 실제로 병합한 장수를 보고해야 한다 (last_page가 아니라)."""
    events = _install_fakes(monkeypatch, tmp_path, pages=3)

    def fake_build_pdf(out_dir, title, page_size=None):
        events.append("build_pdf")
        # 실제로는 한 장이 손으로 지워진 상황을 흉내낸다: last_page(3)보다 적게 병합됨.
        for i in (1, 2):
            (Path(out_dir) / f"{title}_p{i:03d}.jpg").write_bytes(b"x")
        path = Path(out_dir) / f"{title}.pdf"
        path.write_bytes(b"%PDF-1.4\n")
        return path

    monkeypatch.setattr(cli_mod, "build_pdf", fake_build_pdf)
    assert main(["--title", "책", "--interval", "0"]) == 0
    out = capsys.readouterr().out
    assert "2쪽" in out


def test_resolve_session_path_accepts_a_direct_path(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_mod, "RESULT_DIR", tmp_path)
    direct = tmp_path / "어딘가.json"
    direct.write_text("{}", encoding="utf-8")
    assert cli_mod._resolve_session_path(str(direct)) == direct


def test_resolve_session_path_accepts_a_plain_title(tmp_path, monkeypatch):
    """제목만 줘도 프로젝트 폴더에서 세션 파일을 찾아야 한다."""
    monkeypatch.setattr(cli_mod, "RESULT_DIR", tmp_path)
    project = tmp_path / "책"
    project.mkdir()
    session = project / "책.session.json"
    session.write_text("{}", encoding="utf-8")
    assert cli_mod._resolve_session_path("책") == session


def test_resolve_session_path_finds_legacy_flat_layout(tmp_path, monkeypatch):
    """폴더 구조가 생기기 전에 저장된 세션도 찾아야 한다."""
    monkeypatch.setattr(cli_mod, "RESULT_DIR", tmp_path)
    legacy = tmp_path / "책.session.json"
    legacy.write_text("{}", encoding="utf-8")
    assert cli_mod._resolve_session_path("책") == legacy


def test_main_saves_into_a_per_title_directory(monkeypatch, tmp_path):
    """제목마다 result/<제목>/ 폴더가 생기고 모든 산출물이 그 안에 들어가야 한다."""
    events = _install_fakes(monkeypatch, tmp_path)
    assert main(["--title", "책", "--interval", "0"]) == 0
    project = tmp_path / "책"
    assert project.is_dir(), "프로젝트 폴더가 만들어져야 한다"
    assert (project / "책.session.json").exists()
    assert (project / "_preview_capture.png").exists()
    assert (project / "책.pdf").exists()
    assert not (tmp_path / "책.session.json").exists(), "result/ 바로 아래에 쓰면 안 된다"


def test_main_resume_continues_inside_the_session_directory(monkeypatch, tmp_path):
    """재개는 세션 파일이 있는 폴더에서 이어가야 한다 (제목만 줘도 동작)."""
    project = tmp_path / "책"
    project.mkdir()
    for i in (1, 2):
        (project / f"책_p{i:03d}.jpg").write_bytes(b"x")
    SessionConfig(
        title="책",
        capture_region=Region(0, 0, 40, 40),
        progress_region=Region(0, 100, 30, 20),
        click_point=(10, 10),
        interval=0.0,
    ).save(project / "책.session.json")
    events = _install_fakes(monkeypatch, tmp_path)
    assert main(["--resume", "책"]) == 0
    assert "start_page=2" in events, f"세션 폴더의 기존 2쪽을 못 찾았다: {events}"
