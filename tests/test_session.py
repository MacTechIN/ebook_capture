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


def test_session_continues_from_start_page(tmp_path):
    """재개 시 기존 페이지를 덮어쓰지 않고 다음 번호부터 저장해야 한다."""
    capturer = FakeCapturer(percents=["50%", "100%"])
    last_page, reason = run_session(
        _config(), tmp_path, capturer, lambda p: None, FakeWatcher(), start_page=7
    )
    assert reason == StopReason.COMPLETE
    assert last_page == 9
    names = sorted(p.name for p in tmp_path.glob("테스트책_p*.jpg"))
    assert names == ["테스트책_p008.jpg", "테스트책_p009.jpg"]


def test_session_stops_when_page_fraction_reaches_total(tmp_path):
    """'1/762' 형식 뷰어에서도 n/n 에 도달하면 정상 종료해야 한다."""
    capturer = FakeCapturer(percents=["1/3", "2/3", "3/3"])
    last_page, reason = run_session(
        _config(), tmp_path, capturer, lambda p: None, FakeWatcher()
    )
    assert reason == StopReason.COMPLETE
    assert last_page == 3


def test_config_roundtrip_without_a_loading_region(tmp_path):
    """로딩 영역을 지정하지 않아도 저장·복원이 되어야 한다."""
    cfg = _config()
    assert cfg.loading_region is None
    path = tmp_path / "s.json"
    cfg.save(path)
    assert SessionConfig.load(path) == cfg


def test_config_roundtrip_with_a_loading_region(tmp_path):
    cfg = _config(loading_region=Region(-3800, 500, 60, 60))
    path = tmp_path / "s.json"
    cfg.save(path)
    restored = SessionConfig.load(path)
    assert restored == cfg
    assert restored.loading_region == Region(-3800, 500, 60, 60)


def test_session_checks_loading_after_click_and_before_next_capture(tmp_path):
    """다음 페이지를 누른 뒤 로딩이 끝날 때까지 캡처하지 않아야 한다."""
    events = []

    class Capturer:
        def __init__(self):
            self.n = 0

        def grab(self, region):
            if region.height == 34:
                events.append("progress")
                return _pct_image("50%")
            if region.height == 20:
                events.append("loading")
                return Image.new("RGB", (20, 20), "white")
            self.n += 1
            events.append("capture")
            return Image.new("RGB", (60, 60), (self.n * 53 % 256, 60, 90))

    cfg = _config(loading_region=Region(0, 500, 20, 20), max_pages=2)
    run_session(cfg, tmp_path, Capturer(), lambda pt: events.append("click"), FakeWatcher())

    first_click = events.index("click")
    assert events[first_click + 1] == "loading", f"클릭 직후 로딩을 확인해야 한다: {events}"
    assert "capture" in events[first_click + 1 :], "로딩 확인 뒤 캡처가 이어져야 한다"


def test_session_without_a_loading_region_never_checks_loading(tmp_path):
    """로딩 영역을 지정하지 않았으면 기존 동작 그대로여야 한다."""
    heights = []

    class Capturer:
        def __init__(self):
            self.n = 0

        def grab(self, region):
            heights.append(region.height)
            if region.height == 34:
                return _pct_image("100%")
            self.n += 1
            return Image.new("RGB", (60, 60), (self.n * 53 % 256, 60, 90))

    run_session(_config(), tmp_path, Capturer(), lambda pt: None, FakeWatcher())
    assert set(heights) == {60, 34}
