import pytest
from PIL import Image, ImageDraw, ImageFont

from ebook_capture.progress import (
    StillnessDetector,
    load_loading_references,
    read_percent,
    wait_for_loading,
)

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
    assert read_percent(_label("150%")) is None


def test_read_percent_ignores_bare_numbers_without_a_marker():
    """'%'도 '/'도 없는 숫자는 진행률이 아니다."""
    assert read_percent(_label("350")) is None
    assert read_percent(_label("128")) is None


@pytest.mark.parametrize(
    "text,expected",
    [("1/762", 0.13), ("381/762", 50.0), ("762/762", 100.0), ("1 / 762", 0.13)],
)
def test_read_percent_understands_page_fractions(text, expected):
    """'1/762' 처럼 쪽/전체로 표시하는 뷰어도 진행률로 읽어야 한다."""
    value = read_percent(_label(text))
    assert value is not None
    assert abs(value - expected) < 0.1


def test_fraction_reaching_total_is_exactly_100():
    """n/n 은 정확히 100.0 이어야 종료 판정이 걸린다."""
    assert read_percent(_label("762/762")) == 100.0


def test_percent_wins_over_a_fraction_when_both_are_present():
    """'%' 표시가 있으면 그것이 진행률이다. 옆의 쪽 번호에 흔들리면 안 된다."""
    assert read_percent(_label("50% 100/200")) == 50.0


@pytest.mark.parametrize("text", ["800/762", "762/0"])
def test_read_percent_rejects_impossible_fractions(text):
    """분자가 분모보다 크거나 분모가 0이면 진행률이 아니다."""
    assert read_percent(_label(text)) is None


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


class _ScriptedCapturer:
    """지정한 순서대로 이미지를 돌려주는 가짜 캡처기. 마지막 이미지는 계속 반복한다."""

    def __init__(self, images):
        self.images = list(images)
        self.calls = 0

    def grab(self, region):
        img = self.images[min(self.calls, len(self.images) - 1)]
        self.calls += 1
        return img


def _solid(shade):
    return Image.new("RGB", (40, 40), (shade, shade, shade))


def test_wait_for_loading_returns_immediately_when_nothing_animates():
    """로딩 표시가 없으면 기다리지 않고 바로 진행해야 한다."""
    cap = _ScriptedCapturer([_solid(200)])
    waited = wait_for_loading(cap, None, poll=0.0, timeout=5.0)
    assert waited == 0.0 or waited < 0.5
    assert cap.calls <= 3, "정지 상태인데 여러 번 들여다볼 이유가 없다"


def test_wait_for_loading_waits_while_the_region_keeps_changing():
    """도는 표시가 있는 동안은 기다리고, 멈추면 진행해야 한다."""
    spinning = [_solid(s) for s in (10, 60, 110, 160)]
    settled = [_solid(200), _solid(200), _solid(200)]
    cap = _ScriptedCapturer(spinning + settled)
    wait_for_loading(cap, None, poll=0.0, timeout=5.0)
    assert cap.calls >= len(spinning), "애니메이션이 끝나기 전에 진행하면 안 된다"


def test_wait_for_loading_gives_up_after_the_timeout():
    """영영 안 멈추면 무한 대기하지 말고 포기하고 진행한다."""
    forever = _ScriptedCapturer([_solid(s) for s in range(0, 250, 40)])
    waited = wait_for_loading(forever, None, poll=0.0, timeout=0.3)
    assert waited <= 1.0


def test_wait_for_loading_stops_when_the_user_aborts():
    """대기 중에도 ESC가 먹혀야 한다. 로딩이 길면 여기서 갇힐 수 있다."""

    class Watcher:
        aborted = True

    cap = _ScriptedCapturer([_solid(s) for s in range(0, 250, 40)])
    wait_for_loading(cap, None, poll=0.0, timeout=10.0, watcher=Watcher())
    assert cap.calls <= 3, "중단을 눌렀는데 계속 들여다보면 안 된다"


def _ring(shade, size=(40, 40)):
    """로딩 표시를 흉내낸 그림. 회전 각도가 다른 프레임을 만들 때 shade 를 바꾼다."""
    img = Image.new("RGB", size, "white")
    ImageDraw.Draw(img).ellipse((6, 6, size[0] - 6, size[1] - 6), outline=(shade, shade, shade), width=4)
    return img


def test_load_loading_references_reads_every_registered_image(tmp_path):
    """앱마다 로딩 표시가 달라 여러 장을 등록할 수 있어야 한다."""
    for i in range(3):
        _ring(40 + i * 30).save(tmp_path / f"loading{i}.png")
    refs = load_loading_references(sorted(tmp_path.glob("*.png")))
    assert len(refs) == 3


def test_wait_for_loading_waits_while_a_registered_image_matches(tmp_path):
    """등록한 로딩 그림과 같으면, 화면이 멈춰 있어도 로딩 중으로 보고 기다린다."""
    ref_path = tmp_path / "spin.png"
    _ring(60).save(ref_path)
    refs = load_loading_references([ref_path])

    loading_frames = [_ring(60)] * 4          # 멈춘 로딩 표시
    page = Image.new("RGB", (40, 40), (230, 230, 230))
    cap = _ScriptedCapturer(loading_frames + [page, page, page])
    wait_for_loading(cap, None, references=refs, poll=0.0, timeout=5.0)
    assert cap.calls > len(loading_frames), "등록된 로딩 그림이 보이는 동안은 기다려야 한다"


def test_wait_for_loading_proceeds_when_no_registered_image_matches(tmp_path):
    """등록한 그림과 다르면 로딩이 아니므로 바로 진행한다."""
    ref_path = tmp_path / "spin.png"
    _ring(60).save(ref_path)
    refs = load_loading_references([ref_path])

    page = Image.new("RGB", (40, 40), (230, 230, 230))
    cap = _ScriptedCapturer([page])
    wait_for_loading(cap, None, references=refs, poll=0.0, timeout=5.0)
    assert cap.calls <= 3


def _spinner(angle, size=(120, 120)):
    """실제 로딩 표시를 흉내낸 그림. 회색 링 위에서 청록색 호가 돈다."""
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    box = (14, 14, size[0] - 14, size[1] - 14)
    draw.arc(box, 0, 360, fill=(224, 224, 224), width=8)
    draw.arc(box, angle, angle + 80, fill=(34, 188, 212), width=8)
    return img


def test_wait_for_loading_catches_a_thin_spinner_rotating():
    """얇은 표시가 도는 것도 잡아야 한다.

    영역 전체 평균으로 재면 넓은 흰 배경이 차이를 희석해 15도 회전이 평균차이
    1.00 에 그친다. 그대로 두면 로딩 중인데 진행해 로딩 화면을 저장하게 된다.
    """
    spinning = [_spinner(a) for a in range(0, 360, 15)]
    settled = [Image.new("RGB", (120, 120), (250, 250, 250))] * 3
    cap = _ScriptedCapturer(spinning + settled)
    wait_for_loading(cap, None, poll=0.0, timeout=5.0)
    assert cap.calls > len(spinning), "도는 표시를 정지로 오인하면 안 된다"


def test_registered_image_does_not_match_a_blank_screen(tmp_path):
    """로딩 표시는 대부분이 흰 배경이다. 빈 흰 화면까지 로딩으로 보면
    매 페이지마다 타임아웃만큼 헛기다린다."""
    path = tmp_path / "spin.png"
    _spinner(0).save(path)
    refs = load_loading_references([path])
    blank = Image.new("RGB", (120, 120), "white")
    cap = _ScriptedCapturer([blank])
    wait_for_loading(cap, None, references=refs, poll=0.0, timeout=5.0)
    assert cap.calls <= 3
