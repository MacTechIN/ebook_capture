"""진행률 OCR, 화면 정지 감지, 로딩 대기."""
import re
import time

import pytesseract
from PIL import Image, ImageChops, ImageStat

_PCT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
# '1/762' 처럼 쪽/전체로 표시하는 뷰어를 위한 형식. 1000쪽이 넘는 책도 있어 5자리까지 받는다.
_FRACTION_RE = re.compile(r"(\d{1,5})\s*/\s*(\d{1,5})")
_WHITELIST = "0123456789.%/"


def _ocr(img: Image.Image, psm: int) -> str:
    cfg = f"--psm {psm} -c tessedit_char_whitelist={_WHITELIST}"
    return pytesseract.image_to_string(img, config=cfg).strip()


def read_percent(img: Image.Image, upscale: int = 4) -> float | None:
    """진행률을 0~100 사이 실수로 반환한다. 읽지 못하면 None.

    실제 뷰어의 11px 글리프도 ×4 업스케일이면 정확히 읽힌다 (research.md 6.2).
    이진화·대비 보정은 불필요한 것으로 검증되어 넣지 않는다.

    두 가지 표기를 읽는다. '6%' 같은 백분율과 '123/762' 같은 쪽/전체 표기다.
    쪽/전체는 백분율로 환산하므로 n/n 이면 100.0 이 되어 종료 판정이 그대로 걸린다.

    맨 숫자는 진행률로 보지 않는다. 숫자만 찾으면 OCR 영역에 쪽 번호가 섞였을 때
    'p 100 / 350'에서 100을 읽어 350쪽짜리 책을 100쪽에서 조기 종료시킨다.
    '%' 를 분수보다 먼저 보는 것도 같은 이유다. '%' 로 표시하는 뷰어에서 영역에
    쪽 번호가 함께 잡혀도 '%' 쪽을 쓴다.
    """
    big = img.resize((img.width * upscale, img.height * upscale), Image.LANCZOS)
    for psm in (7, 8):
        text = _ocr(big, psm)

        # '%' 가 있으면 그것이 진행률이다. 옆에 쪽 번호가 섞여도 흔들리지 않는다.
        match = _PCT_RE.search(text)
        if match:
            value = float(match.group(1))
            if 0.0 <= value <= 100.0:
                return value

        # '%' 가 전혀 없을 때만 '1/762' 형식으로 읽는다.
        fraction = _FRACTION_RE.search(text)
        if fraction:
            current, total = int(fraction.group(1)), int(fraction.group(2))
            if total > 0 and 0 <= current <= total:
                return current / total * 100.0
    return None


class StillnessDetector:
    """연속으로 같은 화면이 나오면 True를 반환한다. OCR이 실패해도 루프를 멈추는 안전장치."""

    def __init__(self, threshold: float = 2.0, required: int = 3) -> None:
        self.threshold = threshold
        self.required = required
        self._previous: Image.Image | None = None
        self._streak = 0

    def update(self, img: Image.Image) -> bool:
        current = img.convert("L")
        if self._previous is None:
            self._previous = current
            return False
        diff = ImageChops.difference(self._previous, current)
        mean_diff = ImageStat.Stat(diff).mean[0]
        self._streak = self._streak + 1 if mean_diff <= self.threshold else 0
        self._previous = current
        return self._streak >= self.required

    def reset(self) -> None:
        self._previous = None
        self._streak = 0


# 로딩 그림을 맞춰볼 때 쓰는 크기. 작게 줄여서 비교하면 미세한 위치 차이에 둔감해진다.
_MATCH_SIZE = (48, 48)
# 배경으로 볼 밝기 차이. 이보다 밝기가 떨어지는 픽셀만 '그림'으로 친다.
_INK_MARGIN = 24
# 픽셀이 '변했다'고 볼 밝기 차이.
_MOTION_TOLERANCE = 24


def _fingerprint(img: Image.Image) -> Image.Image:
    """대조용 지문. 색을 살린다.

    실제 로딩 표시는 회색 링에 청록색 호가 도는 모양이라, 흑백으로 줄이면
    가장 특징적인 색 정보가 사라져 본문 화면과 구분이 흐려진다.
    """
    return img.convert("RGB").resize(_MATCH_SIZE, Image.LANCZOS)


def _ink_mask(fingerprint: Image.Image) -> Image.Image:
    """그림이 실제로 그려진 픽셀만 남긴 마스크.

    로딩 표시는 대부분이 흰 배경이고 링은 얇다. 화면 전체 평균으로 비교하면
    배경이 차이를 삼켜버려서 '아무것도 없는 흰 화면'까지 로딩으로 오인한다.
    그래서 링과 호가 그려진 픽셀만 골라 그 자리끼리 비교한다.
    """
    gray = fingerprint.convert("L")
    background = gray.getextrema()[1]
    return gray.point(lambda v: 255 if background - v > _INK_MARGIN else 0)


def _changed_fraction(a: Image.Image, b: Image.Image) -> float:
    """두 화면 사이에서 뚜렷하게 변한 픽셀의 비율.

    평균 차이로 재면 얇은 로딩 표시가 도는 것을 놓친다. 넓은 흰 배경이 차이를
    희석하기 때문이다(15도 회전이 평균차이 1.00 에 그친다). 변한 픽셀의 비율은
    같은 회전이 1.26%로 잡혀 정지 상태 0.00%와 뚜렷이 갈린다.
    """
    diff = ImageChops.difference(a, b)
    changed = diff.point(lambda v: 255 if v > _MOTION_TOLERANCE else 0)
    return ImageStat.Stat(changed).mean[0] / 255.0


def load_loading_references(paths) -> list[tuple]:
    """등록된 로딩 표시 그림들을 비교용으로 읽어들인다.

    앱마다, 상황마다 로딩 표시가 다르므로 여러 장을 등록할 수 있다.
    회전하는 표시라면 각도가 다른 프레임을 여러 장 등록해 두면 더 잘 걸린다.
    """
    references = []
    for path in paths:
        with Image.open(path) as img:
            fingerprint = _fingerprint(img.convert("RGB"))
        references.append((fingerprint, _ink_mask(fingerprint)))
    return references


def _matches_any(img: Image.Image, references, threshold: float) -> bool:
    if not references:
        return False
    current = _fingerprint(img)
    for ref_fingerprint, ink in references:
        if ink.getextrema()[1] == 0:
            continue
        diff = ImageChops.difference(current, ref_fingerprint)
        channels = ImageStat.Stat(diff, ink).mean
        if sum(channels) / len(channels) <= threshold:
            return True
    return False


def wait_for_loading(
    capturer,
    region,
    *,
    references=None,
    match_threshold: float = 12.0,
    poll: float = 0.25,
    stable_needed: int = 2,
    motion_threshold: float = 0.003,
    timeout: float = 30.0,
    watcher=None,
) -> float:
    """지정한 영역이 더 이상 변하지 않을 때까지 기다린다. 기다린 시간(초)을 반환한다.

    페이지를 넘긴 직후 뜨는 로딩 표시는 빙글빙글 도는 애니메이션이라 매 순간
    그림이 달라진다. 그래서 '이 영역이 계속 바뀌는 동안'을 로딩 중으로 본다.
    회전 각도가 매번 달라도 되고, 로딩 그림을 미리 등록해 둘 필요도 없다.

    여기에 더해 등록된 로딩 그림(references)과도 대조한다. 둘을 같이 쓰는 이유는
    서로 다른 경우를 잡기 때문이다. 등록 그림은 '멈춰 있는 로딩 표시'를 잡고,
    변화 감지는 '등록해 두지 않은 회전 각도'를 잡는다. 둘 중 하나라도 걸리면 기다린다.

    로딩 표시가 없으면 첫 두어 번만 들여다보고 바로 돌아오므로 비용이 거의 없다.
    영영 멈추지 않으면 timeout 에서 포기하고 진행한다 — 여기서 갇히는 것보다는
    한 장 잘못 찍고 정지 감지에 맡기는 편이 낫다.
    """
    start = time.monotonic()
    previous = None
    stable = 0

    while True:
        # 로딩이 길어질 수 있으므로 대기 중에도 ESC가 먹혀야 한다.
        if watcher is not None and watcher.aborted:
            return time.monotonic() - start

        frame = capturer.grab(region)

        # 등록된 로딩 그림과 같으면, 화면이 멈춰 있어도 로딩 중이다.
        if _matches_any(frame, references, match_threshold):
            stable = 0
            previous = frame.convert("L")
            if time.monotonic() - start >= timeout:
                return time.monotonic() - start
            if poll > 0:
                time.sleep(poll)
            continue

        current = frame.convert("L")
        if previous is not None:
            moved = _changed_fraction(previous, current)
            stable = stable + 1 if moved <= motion_threshold else 0
            if stable >= stable_needed:
                return time.monotonic() - start
        previous = current

        if time.monotonic() - start >= timeout:
            return time.monotonic() - start
        if poll > 0:
            time.sleep(poll)
