import pytest

from ebook_capture.geometry import Region
from ebook_capture.picker import AbortWatcher, pick_point, pick_region


def test_abort_watcher_starts_not_aborted():
    with AbortWatcher() as watcher:
        assert watcher.aborted is False


def test_abort_watcher_can_be_triggered_programmatically():
    """ESC 키를 실제로 누르지 않고 내부 플래그 경로를 검증한다."""
    with AbortWatcher() as watcher:
        watcher.trigger()
        assert watcher.aborted is True


def test_pick_region_builds_region_from_two_points(monkeypatch):
    points = iter([(10, 20), (110, 220)])
    monkeypatch.setattr("ebook_capture.picker.pick_point", lambda prompt: next(points))
    region = pick_region("캡처 영역")
    assert region == Region(left=10, top=20, width=100, height=200)


def test_pick_region_handles_reversed_clicks(monkeypatch):
    points = iter([(110, 220), (10, 20)])
    monkeypatch.setattr("ebook_capture.picker.pick_point", lambda prompt: next(points))
    assert pick_region("캡처 영역") == Region(left=10, top=20, width=100, height=200)


@pytest.mark.manual
def test_pick_point_real_click():
    """수동 실행 전용: 실제로 화면을 클릭해야 통과한다."""
    x, y = pick_point("아무 곳이나 클릭하세요")
    assert isinstance(x, int) and isinstance(y, int)
