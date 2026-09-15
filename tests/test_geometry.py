import pytest
from ebook_capture.geometry import Region


def test_from_points_normal_order():
    r = Region.from_points((10, 20), (110, 220))
    assert (r.left, r.top, r.width, r.height) == (10, 20, 100, 200)


def test_from_points_reversed_order():
    """우하단을 먼저 클릭해도 같은 사각형이 나와야 한다."""
    r = Region.from_points((110, 220), (10, 20))
    assert (r.left, r.top, r.width, r.height) == (10, 20, 100, 200)


def test_from_points_negative_coordinates():
    """왼쪽 보조 모니터는 x가 음수다 (research.md 2.1)."""
    r = Region.from_points((-3800, -400), (-3000, 100))
    assert (r.left, r.top, r.width, r.height) == (-3800, -400, 800, 500)


def test_from_points_zero_area_raises():
    with pytest.raises(ValueError, match="영역"):
        Region.from_points((50, 50), (50, 200))


def test_to_mss_shape():
    r = Region(left=-100, top=-50, width=800, height=600)
    assert r.to_mss() == {"left": -100, "top": -50, "width": 800, "height": 600}


def test_region_is_frozen():
    r = Region(0, 0, 10, 10)
    with pytest.raises(Exception):
        r.left = 5


def test_from_display_converts_display_bounds():
    """DisplayInfo의 경계를 그대로 Region으로 옮긴다. 왼쪽 모니터는 원점이 음수다."""

    class FakeDisplay:
        left, top, width, height = -3840, -467, 3840, 2160

    r = Region.from_display(FakeDisplay())
    assert (r.left, r.top, r.width, r.height) == (-3840, -467, 3840, 2160)
