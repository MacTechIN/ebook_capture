import json

import pytest
from PIL import Image, ImageDraw, ImageFont

from ebook_capture.geometry import Region
from ebook_capture.session import SessionConfig, StopReason, run_session

FONT = "/System/Library/Fonts/Helvetica.ttc"


def _config(**over):
    base = dict(
        title="테스트책",
        capture_region=Region(0, 0, 60, 60),
        progress_region=Region(0, 900, 120, 34),
        click_point=(500, 500),
        interval=0.0,
        dpi=300,
        quality=95,
        max_pages=50,
        stillness_required=3,
    )
    base.update(over)
    return SessionConfig(**base)


def _pct_image(text: str) -> Image.Image:
    img = Image.new("RGB", (120, 34), "white")
    ImageDraw.Draw(img).text((8, 8), text, fill=(68, 68, 68), font=ImageFont.truetype(FONT, 11))
    return img


class FakeCapturer:
    """캡처 영역과 진행률 영역에 서로 다른 스크립트된 이미지를 돌려준다."""

    def __init__(self, percents, pages=None):
        self.percents = list(percents)
        self.pages = pages
        self.calls = 0

    def grab(self, region):
        if region.height == 34:  # 진행률 영역
            return _pct_image(self.percents[min(self.calls - 1, len(self.percents) - 1)])
        self.calls += 1
        if self.pages is not None:
            shade = self.pages[min(self.calls - 1, len(self.pages) - 1)]
        else:
            # 단계를 53으로 둔다. 7로 두면 RGB->L 변환에서 휘도 차이가 정확히 2.0이
            # 되어 StillnessDetector의 threshold 2.0에 걸려 "화면이 멈췄다"로
            # 오판한다. 53이면 휘도 차이가 16 이상이라 확실히 구분된다.
            shade = self.calls * 53 % 256
        return Image.new("RGB", (60, 60), (shade, 60, 90))


class FakeWatcher:
    def __init__(self, abort_after=None):
        self.abort_after = abort_after
        self.checks = 0

    @property
    def aborted(self):
        self.checks += 1
        return self.abort_after is not None and self.checks > self.abort_after


def test_config_json_roundtrip(tmp_path):
    cfg = _config()
    path = tmp_path / "s.json"
    cfg.save(path)
    assert SessionConfig.load(path) == cfg


def test_config_json_is_human_readable(tmp_path):
    path = tmp_path / "s.json"
    _config().save(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["title"] == "테스트책"
    assert data["capture_region"]["width"] == 60


def test_session_stops_at_100_percent(tmp_path):
    clicks = []
    capturer = FakeCapturer(percents=["10%", "50%", "100%"])
    pages, reason = run_session(
        _config(), tmp_path, capturer, clicks.append, FakeWatcher()
    )
    assert reason == StopReason.COMPLETE
    assert pages == 3
    assert len(list(tmp_path.glob("테스트책_p*.jpg"))) == 3


def test_session_does_not_click_after_final_page(tmp_path):
    """100%를 읽은 뒤에는 더 클릭하지 않아야 한다."""
    clicks = []
    capturer = FakeCapturer(percents=["50%", "100%"])
    run_session(_config(), tmp_path, capturer, clicks.append, FakeWatcher())
    assert len(clicks) == 1


def test_session_stops_on_stillness_when_ocr_never_reaches_100(tmp_path):
    """OCR이 100%를 못 읽어도 화면이 멈추면 종료해야 한다 (research.md 3.2 폴백)."""
    clicks = []
    capturer = FakeCapturer(percents=["50%"], pages=[10, 10, 10, 10, 10])
    pages, reason = run_session(
        _config(stillness_required=3), tmp_path, capturer, clicks.append, FakeWatcher()
    )
    assert reason == StopReason.STILL
    assert pages < 50
    assert len(clicks) == pages - 1, "멈추기로 한 회차에서는 클릭하지 않아야 한다"


def test_session_respects_max_pages(tmp_path):
    clicks = []
    capturer = FakeCapturer(percents=["50%"])  # 계속 50%, 화면은 매번 바뀜
    pages, reason = run_session(
        _config(max_pages=5), tmp_path, capturer, clicks.append, FakeWatcher()
    )
    assert reason == StopReason.MAX_PAGES
    assert pages == 5
    assert len(clicks) == 4, "상한에 닿은 회차에서는 클릭하지 않아야 한다"


def test_session_aborts_on_esc(tmp_path):
    clicks = []
    capturer = FakeCapturer(percents=["50%"])
    pages, reason = run_session(
        _config(max_pages=100), tmp_path, capturer, clicks.append, FakeWatcher(abort_after=2)
    )
    assert reason == StopReason.ABORTED
    assert pages == 2
    # ESC는 이미 클릭한 뒤 다음 회차 시작에서 감지되므로 클릭 수가 쪽 수와 같다.
    # 다른 종료 사유(clicks == pages - 1)와 다른 이 차이가 정상 동작이다.
    assert len(clicks) == 2
