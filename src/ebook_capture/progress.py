"""진행률 OCR과 화면 정지 감지. research.md 3.2의 종료 판정 1·2번."""
import re

import pytesseract
from PIL import Image, ImageChops, ImageStat

_NUM_RE = re.compile(r"\d{1,3}(?:\.\d+)?")
_WHITELIST = "0123456789.%/"


def _ocr(img: Image.Image, psm: int) -> str:
    cfg = f"--psm {psm} -c tessedit_char_whitelist={_WHITELIST}"
    return pytesseract.image_to_string(img, config=cfg).strip()


def read_percent(img: Image.Image, upscale: int = 4) -> float | None:
    """진행률을 0~100 사이 실수로 반환한다. 읽지 못하면 None.

    실제 뷰어의 11px 글리프도 ×4 업스케일이면 정확히 읽힌다 (research.md 6.2).
    이진화·대비 보정은 불필요한 것으로 검증되어 넣지 않는다.
    """
    big = img.resize((img.width * upscale, img.height * upscale), Image.LANCZOS)
    for psm in (7, 8):
        match = _NUM_RE.search(_ocr(big, psm))
        if match:
            value = float(match.group(0))
            if 0.0 <= value <= 100.0:
                return value
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
