import pikepdf
import pytest
from PIL import Image

from ebook_capture.capture import save_page
from ebook_capture.pdfbuild import build_pdf, collect_pages


def _make_pages(tmp_path, title, count, dpi=300):
    for i in range(1, count + 1):
        img = Image.new("RGB", (300, 500), (i * 20 % 256, 100, 150))
        save_page(img, tmp_path, title, i, dpi=dpi)


def test_collect_pages_numeric_order(tmp_path):
    _make_pages(tmp_path, "책", 12)
    names = [p.name for p in collect_pages(tmp_path, "책")]
    assert names[:3] == ["책_p001.jpg", "책_p002.jpg", "책_p003.jpg"]
    assert names[-1] == "책_p012.jpg"


def test_collect_pages_ignores_other_titles(tmp_path):
    _make_pages(tmp_path, "책A", 2)
    _make_pages(tmp_path, "책B", 3)
    assert len(collect_pages(tmp_path, "책A")) == 2


def test_build_pdf_page_count(tmp_path):
    _make_pages(tmp_path, "책", 5)
    pdf = build_pdf(tmp_path, "책")
    assert pdf.name == "책.pdf"
    with pikepdf.open(pdf) as doc:
        assert len(doc.pages) == 5


def test_build_pdf_embeds_jpeg_losslessly(tmp_path):
    """/DCTDecode면 원본 JPEG이 재인코딩 없이 삽입된 것이다 (research.md 2.5)."""
    _make_pages(tmp_path, "책", 2)
    pdf = build_pdf(tmp_path, "책")
    with pikepdf.open(pdf) as doc:
        image = next(iter(doc.pages[0].get_images().values()))
        assert str(image.Filter) == "/DCTDecode"
        assert int(image.Width) == 300 and int(image.Height) == 500


def test_build_pdf_page_geometry_from_dpi(tmp_path):
    """300x500px @300dpi -> 1.0in x 1.667in -> 72pt x 120pt."""
    _make_pages(tmp_path, "책", 1)
    pdf = build_pdf(tmp_path, "책")
    with pikepdf.open(pdf) as doc:
        box = doc.pages[0].MediaBox
        assert abs(float(box[2]) - 72.0) < 1.0
        assert abs(float(box[3]) - 120.0) < 1.0


def test_build_pdf_a4_layout(tmp_path):
    """A4 옵션은 픽셀은 그대로 두고 페이지 박스만 바꾼다 (research.md 6.4 C안)."""
    _make_pages(tmp_path, "책", 1)
    pdf = build_pdf(tmp_path, "책", page_size="a4")
    with pikepdf.open(pdf) as doc:
        box = doc.pages[0].MediaBox
        assert abs(float(box[2]) - 595.28) < 2.0
        assert abs(float(box[3]) - 841.89) < 2.0
        image = next(iter(doc.pages[0].get_images().values()))
        assert int(image.Width) == 300, "A4 옵션이 픽셀을 리샘플링하면 안 된다"


def test_build_pdf_with_no_pages_raises(tmp_path):
    with pytest.raises(ValueError, match="이미지"):
        build_pdf(tmp_path, "없는책")


def test_collect_pages_with_brackets_in_title(tmp_path):
    """glob에서 []는 문자 클래스다. 이스케이프하지 않으면 한 장도 못 찾는다."""
    _make_pages(tmp_path, "책[개정판]", 3)
    assert len(collect_pages(tmp_path, "책[개정판]")) == 3


def test_build_pdf_with_brackets_in_title(tmp_path):
    _make_pages(tmp_path, "책[개정판]", 2)
    pdf = build_pdf(tmp_path, "책[개정판]")
    with pikepdf.open(pdf) as doc:
        assert len(doc.pages) == 2
