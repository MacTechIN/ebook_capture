"""Quartz CGEventPost 기반 클릭. 전역 좌표계의 음수 값을 정확히 처리한다."""
import time

import Quartz

_KINDS = (
    Quartz.kCGEventMouseMoved,
    Quartz.kCGEventLeftMouseDown,
    Quartz.kCGEventLeftMouseUp,
)


def build_click_events(x: float, y: float) -> list:
    """이동·누름·뗌 이벤트를 만든다. 포스팅은 하지 않는다."""
    point = (float(x), float(y))
    return [
        Quartz.CGEventCreateMouseEvent(None, kind, point, Quartz.kCGMouseButtonLeft)
        for kind in _KINDS
    ]


def click(x: int, y: int, settle: float = 0.05) -> None:
    """지정한 전역 좌표를 클릭한다. 손쉬운 사용 권한이 필요하다."""
    for event in build_click_events(x, y):
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(settle)
