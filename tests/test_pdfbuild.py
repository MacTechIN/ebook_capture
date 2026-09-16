import pikepdf
import pytest
from PIL import Image

from ebook_capture.capture import save_page
from ebook_capture.pdfbuild import build_pdf, collect_pages, trailing_duplicates


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


def _make_varied(tmp_path, title, shades):
    """지정한 밝기대로 페이지를 만든다. 같은 값이면 같은 페이지가 된다."""
    for i, shade in enumerate(shades, 1):
        save_page(Image.new("RGB", (120, 160), (shade, shade, shade)), tmp_path, title, i)


def test_trailing_duplicates_finds_the_run_at_the_end(tmp_path):
    """책이 끝난 뒤 정지 감지가 확인하느라 찍은 여분 장을 골라낸다."""
    _make_varied(tmp_path, "책", [10, 60, 110, 110, 110])
    dupes = trailing_duplicates(collect_pages(tmp_path, "책"))
    assert [p.name for p in dupes] == ["책_p004.jpg", "책_p005.jpg"]


def test_trailing_duplicates_ignores_duplicates_in_the_middle(tmp_path):
    """중간의 동일 페이지는 진짜 빈 페이지일 수 있다. 건드리면 안 된다."""
    _make_varied(tmp_path, "책", [10, 60, 60, 110, 160])
    assert trailing_duplicates(collect_pages(tmp_path, "책")) == []


def test_trailing_duplicates_is_empty_when_every_page_differs(tmp_path):
    _make_varied(tmp_path, "책", [10, 60, 110, 160])
    assert trailing_duplicates(collect_pages(tmp_path, "책")) == []


def test_trailing_duplicates_keeps_at_least_one_page(tmp_path):
    """전부 같은 화면이어도 한 장은 남겨야 PDF 를 만들 수 있다."""
    _make_varied(tmp_path, "책", [90, 90, 90])
    dupes = trailing_duplicates(collect_pages(tmp_path, "책"))
    assert len(dupes) == 2


def test_build_pdf_excludes_trailing_duplicates_by_default(tmp_path):
    _make_varied(tmp_path, "책", [10, 60, 110, 110, 110])
    pdf = build_pdf(tmp_path, "책")
    with pikepdf.open(pdf) as doc:
        assert len(doc.pages) == 3
    assert len(list(tmp_path.glob("책_p*.jpg"))) == 5, "JPG 원본은 그대로 남겨야 한다"


def test_build_pdf_can_keep_trailing_duplicates(tmp_path):
    _make_varied(tmp_path, "책", [10, 60, 110, 110, 110])
    pdf = build_pdf(tmp_path, "책", drop_trailing_duplicates=False)
    with pikepdf.open(pdf) as doc:
        assert len(doc.pages) == 5


def test_trailing_duplicates_survives_an_unreadable_file(tmp_path):
    """파일 하나가 깨졌다고 PDF 생성 전체가 죽으면 안 된다."""
    _make_varied(tmp_path, "책", [10, 60, 110])
    (tmp_path / "책_p004.jpg").write_bytes(b"not an image")
    pages = collect_pages(tmp_path, "책")
    assert len(pages) == 4
    assert trailing_duplicates(pages) == [], "확인 못 한 페이지는 지우지 않는다"
