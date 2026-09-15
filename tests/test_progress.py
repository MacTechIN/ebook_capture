import pytest
from PIL import Image, ImageDraw, ImageFont

from ebook_capture.progress import StillnessDetector, read_percent

FONT = "/System/Library/Fonts/Helvetica.ttc"


def _label(text: str, size: int = 11) -> Image.Image:
    """실제 뷰어와 같은 조건: 진회색 글자 + 흰 배경 (research.md 6.2)."""
    img = Image.new("RGB", (120, 34), "white")
    ImageDraw.Draw(img).text((8, 8), text, fill=(68, 68, 68), font=ImageFont.truetype(FONT, size))
    return img


@pytest.mark.parametrize("text,expected", [("0%", 0.0), ("47%", 47.0), ("100%", 100.0)])
def test_read_percent_parses_labels(text, expected):
    assert read_percent(_label(text)) == expected


def test_read_percent_returns_none_on_blank():
    assert read_percent(Image.new("RGB", (120, 34), "white")) is None


def test_read_percent_rejects_out_of_range():
    """오인식으로 999 같은 값이 나오면 None이어야 한다."""
    assert read_percent(_label("999")) is None


def test_stillness_detector_fires_after_required_repeats():
    same = Image.new("RGB", (60, 60), (10, 20, 30))
    d = StillnessDetector(required=3)
    assert d.update(same) is False  # 첫 프레임: 비교 대상 없음
    assert d.update(same) is False  # 1회 연속
    assert d.update(same) is False  # 2회 연속
    assert d.update(same) is True   # 3회 연속 -> 정지


def test_stillness_detector_resets_on_change():
    a = Image.new("RGB", (60, 60), (10, 20, 30))
    b = Image.new("RGB", (60, 60), (200, 40, 60))
    d = StillnessDetector(required=2)
    d.update(a)
    d.update(a)
    assert d.update(b) is False, "화면이 바뀌면 카운터가 초기화되어야 한다"
    assert d.update(b) is False


def test_stillness_detector_tolerates_tiny_noise():
    """안티에일리어싱 수준의 미세한 차이는 '동일'로 봐야 한다."""
    a = Image.new("RGB", (60, 60), (100, 100, 100))
    b = Image.new("RGB", (60, 60), (101, 100, 100))
    d = StillnessDetector(threshold=2.0, required=2)
    d.update(a)
    d.update(b)
    assert d.update(a) is True
