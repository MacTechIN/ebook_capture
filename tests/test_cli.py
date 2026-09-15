from PIL import Image

from ebook_capture.cli import build_parser, save_previews
from ebook_capture.geometry import Region
from ebook_capture.session import SessionConfig


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
