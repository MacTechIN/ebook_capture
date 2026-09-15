from pathlib import Path

import pytest
from PIL import Image

from ebook_capture.capture import ScreenCapture, save_page
from ebook_capture.geometry import Region


def test_save_page_writes_300dpi_metadata(tmp_path):
    img = Image.new("RGB", (100, 200), "white")
    path = save_page(img, tmp_path, "테스트책", 3)
    assert path.name == "테스트책_p003.jpg"
    with Image.open(path) as reopened:
        assert reopened.info["dpi"] == (300, 300)
        assert reopened.size == (100, 200), "픽셀을 리샘플링하면 안 된다"


def test_save_page_custom_dpi(tmp_path):
    img = Image.new("RGB", (100, 200), "white")
    path = save_page(img, tmp_path, "책", 1, dpi=150)
    with Image.open(path) as reopened:
        assert reopened.info["dpi"] == (150, 150)


def test_save_page_creates_missing_directory(tmp_path):
    img = Image.new("RGB", (10, 10), "white")
    target = tmp_path / "result"
    path = save_page(img, target, "책", 1)
    assert path.exists()


def test_grab_returns_requested_size():
    """실제 화면을 잡되 결과 크기만 검증한다 (권한 필요)."""
    with ScreenCapture() as sc:
        img = sc.grab(Region(left=0, top=0, width=200, height=100))
    assert img.size == (200, 100)
    assert img.mode == "RGB"


def test_grab_detects_blank_capture():
    """권한이 없으면 전 픽셀이 동일하게 나온다. 그 신호를 감지할 수 있어야 한다."""
    with ScreenCapture() as sc:
        img = sc.grab(Region(left=0, top=0, width=200, height=100))
    assert len(img.getcolors(maxcolors=256 * 256)) > 1, (
        "캡처가 단색입니다. 화면 기록 권한을 확인하세요."
    )
