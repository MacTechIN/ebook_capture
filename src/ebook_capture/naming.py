"""페이지 이미지 파일명 생성·파싱·정렬."""
import re
from pathlib import Path

_PAGE_RE = re.compile(r"_p(\d+)\.jpg$", re.IGNORECASE)
_UNSAFE_RE = re.compile(r'[/\\:*?"<>|]')


def sanitize_title(title: str) -> str:
    """파일명에 쓸 수 없는 문자를 제거한다."""
    cleaned = _UNSAFE_RE.sub("_", title).strip()
    if not cleaned:
        raise ValueError("제목이 비어 있습니다.")
    return cleaned


def page_filename(title: str, page: int) -> str:
    """3자리 0 패딩. 1000쪽 이상이면 자연히 늘어난다."""
    return f"{title}_p{page:03d}.jpg"


def parse_page_number(name: str) -> int | None:
    m = _PAGE_RE.search(name)
    return int(m.group(1)) if m else None


def sort_pages(paths: list[Path]) -> list[Path]:
    """페이지 번호 수치순 정렬. 사전순 정렬은 p10 < p2 버그를 만든다."""
    numbered = [(parse_page_number(p.name), p) for p in paths]
    return [p for n, p in sorted(numbered, key=lambda t: t[0]) if n is not None]
