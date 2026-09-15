"""JPEG 페이지들을 무손실로 하나의 PDF에 병합한다."""
from pathlib import Path

import img2pdf

from .naming import parse_page_number, sort_pages

A4_PT = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))


def collect_pages(out_dir: Path, title: str) -> list[Path]:
    out_dir = Path(out_dir)
    candidates = [p for p in out_dir.glob(f"{title}_p*.jpg") if parse_page_number(p.name) is not None]
    return sort_pages(candidates)


def build_pdf(out_dir: Path, title: str, page_size: str | None = None) -> Path:
    """img2pdf는 JPEG을 /DCTDecode로 그대로 삽입한다. 재인코딩이 없어 화질 손실이 0이다."""
    pages = collect_pages(out_dir, title)
    if not pages:
        raise ValueError(f"'{title}'에 해당하는 페이지 이미지를 찾을 수 없습니다: {out_dir}")

    kwargs = {}
    if page_size == "a4":
        kwargs["layout_fun"] = img2pdf.get_layout_fun(A4_PT)

    pdf_path = Path(out_dir) / f"{title}.pdf"
    pdf_path.write_bytes(img2pdf.convert([str(p) for p in pages], **kwargs))
    return pdf_path
