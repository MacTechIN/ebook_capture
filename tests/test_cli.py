from pathlib import Path

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

    def fake_run_session(config, out_dir, capturer, clicker_fn, watcher, on_page=None):
        saved = (Path(out_dir) / f"{config.title}.session.json").exists()
        events.append(f"run_session(session_saved={saved})")
        return pages, StopReason.COMPLETE

    def fake_build_pdf(out_dir, title, page_size=None):
        events.append("build_pdf")
        path = Path(out_dir) / f"{title}.pdf"
        path.write_bytes(b"%PDF-1.4\n")
        return path

    answers = iter([confirm])
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
