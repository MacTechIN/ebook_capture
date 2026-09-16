"""진행률 OCR과 화면 정지 감지. research.md 3.2의 종료 판정 1·2번."""
import re

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
