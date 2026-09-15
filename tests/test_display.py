import pytest
from ebook_capture import display


def test_check_permissions_returns_two_bools():
    screen, accessibility = display.check_permissions()
    assert isinstance(screen, bool)
    assert isinstance(accessibility, bool)


def test_list_displays_finds_at_least_one():
    displays = display.list_displays()
    assert len(displays) >= 1


def test_display_scale_is_positive():
    for d in display.list_displays():
        assert d.scale > 0, f"디스플레이 {d.id}의 스케일이 0 이하입니다"


def test_display_dimensions_are_positive():
    for d in display.list_displays():
        assert d.width > 0 and d.height > 0
