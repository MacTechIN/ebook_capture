"""JPEG 페이지들을 무손실로 하나의 PDF에 병합한다."""
import glob
from pathlib import Path

import img2pdf
from PIL import Image, ImageChops, ImageStat

from .naming import parse_page_number, sort_pages

A4_PT = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))


def collect_pages(out_dir: Path, title: str) -> list[Path]:
    """제목을 glob 패턴으로 escape 한다.

    glob에서 `[...]`는 문자 클래스라, 대괄호가 든 제목(흔한 한국어 전자책
    제목 표기, 예: '입문[개정판]')은 escape 없이는 자기 자신의 파일을 한
    장도 찾지 못한다.
    """
    out_dir = Path(out_dir)
    pattern = glob.escape(title) + "_p*.jpg"
    candidates = [p for p in out_dir.glob(pattern) if parse_page_number(p.name) is not None]
    return sort_pages(candidates)


# 두 페이지를 같다고 볼 평균 밝기 차이. 실측상 서로 다른 본문 페이지는 14~20,
# 정지 감지가 찍은 여분 장은 0.00~0.27 로 뚜렷이 갈린다.
_DUPLICATE_THRESHOLD = 3.0
_COMPARE_SIZE = (200, 260)


def _page_thumb(path: Path) -> Image.Image | None:
    """비교용 축소판. 열 수 없는 파일이면 None 을 돌려준다.

    파일이 깨져 있다고 PDF 생성 전체가 죽으면 안 된다. 확인하지 못한 페이지는
    '다르다'로 보고 그냥 둔다 — 지우는 쪽으로 기울면 멀쩡한 페이지를 잃는다.
    """
    try:
        with Image.open(path) as img:
            return img.convert("L").resize(_COMPARE_SIZE)
    except (OSError, ValueError):
        return None


def trailing_duplicates(pages: list[Path]) -> list[Path]:
    """맨 뒤에 연달아 붙은 동일 페이지들을 골라낸다.

    책이 끝나면 정지 감지가 '3회 연속 동일'을 확인하느라 같은 화면을 몇 장 더 찍는다.
    설계대로의 동작이지만 PDF 에 들어갈 이유는 없다.

    맨 뒤만 본다. 중간에 있는 동일 페이지는 진짜 빈 페이지일 수 있어 건드리지 않는다.
    한 장은 반드시 남긴다.
    """
    if len(pages) < 2:
        return []

    thumbs = {}

    def thumb(path):
        if path not in thumbs:
            thumbs[path] = _page_thumb(path)
        return thumbs[path]

    duplicates = []
    for i in range(len(pages) - 1, 0, -1):
        current, previous = thumb(pages[i]), thumb(pages[i - 1])
        if current is None or previous is None:
            break
        diff = ImageStat.Stat(ImageChops.difference(current, previous)).mean[0]
        if diff > _DUPLICATE_THRESHOLD:
            break
        duplicates.append(pages[i])
    return list(reversed(duplicates))


def build_pdf(
    out_dir: Path,
    title: str,
    page_size: str | None = None,
    drop_trailing_duplicates: bool = True,
) -> Path:
    """img2pdf는 JPEG을 /DCTDecode로 그대로 삽입한다. 재인코딩이 없어 화질 손실이 0이다."""
    pages = collect_pages(out_dir, title)
    if not pages:
        raise ValueError(f"'{title}'에 해당하는 페이지 이미지를 찾을 수 없습니다: {out_dir}")

    if drop_trailing_duplicates:
        # JPG 원본은 지우지 않는다. PDF 에서만 뺀다.
        excluded = set(trailing_duplicates(pages))
        if excluded:
            pages = [p for p in pages if p not in excluded]

    kwargs = {}
    if page_size == "a4":
        kwargs["layout_fun"] = img2pdf.get_layout_fun(A4_PT)

    pdf_path = Path(out_dir) / f"{title}.pdf"
    pdf_path.write_bytes(img2pdf.convert([str(p) for p in pages], **kwargs))
    return pdf_path
