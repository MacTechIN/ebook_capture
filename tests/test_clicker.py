import pytest
import Quartz

from ebook_capture.clicker import build_click_events, click


def test_build_click_events_has_move_down_up():
    events = build_click_events(100.0, 200.0)
    assert len(events) == 3


@pytest.mark.parametrize("x,y", [(-2000.0, 500.0), (100.0, 100.0), (3000.0, 800.0)])
def test_build_click_events_preserve_global_coordinates(x, y):
    """음수 좌표(왼쪽 모니터)가 보존되어야 한다. pyautogui는 이걸 못 한다 (research.md 2.3)."""
    for event in build_click_events(x, y):
        loc = Quartz.CGEventGetLocation(event)
        assert abs(loc.x - x) < 1.0
        assert abs(loc.y - y) < 1.0


@pytest.mark.manual
def test_click_actually_works():
    """실제 화면을 클릭하므로 수동 실행 전용: pytest -m manual"""
    click(100, 100)
