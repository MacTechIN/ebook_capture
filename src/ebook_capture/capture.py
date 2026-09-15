"""mss 기반 화면 캡처와 JPEG 저장."""
from pathlib import Path

import mss
from PIL import Image

from .geometry import Region
from .naming import page_filename


class ScreenCapture:
    """mss 인스턴스를 재사용한다. 첫 grab은 약 79ms, 이후 약 12ms (research.md 2.2)."""

    def __init__(self) -> None:
        self._sct = mss.mss()

    def grab(self, region: Region) -> Image.Image:
        shot = self._sct.grab(region.to_mss())
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def close(self) -> None:
        self._sct.close()

    def __enter__(self) -> "ScreenCapture":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def save_page(
    img: Image.Image,
    out_dir: Path,
    title: str,
    page: int,
    quality: int = 95,
    dpi: int = 300,
) -> Path:
    """픽셀은 그대로 두고 DPI 메타데이터만 기록한다 (research.md 3.1 A안)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / page_filename(title, page)
    img.save(path, "JPEG", quality=quality, dpi=(dpi, dpi))
    return path
