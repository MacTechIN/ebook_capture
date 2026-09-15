from pathlib import Path

import pytest

from ebook_capture.naming import page_filename, parse_page_number, sanitize_title, sort_pages


def test_page_filename_zero_padded():
    assert page_filename("내책", 1) == "내책_p001.jpg"
    assert page_filename("내책", 42) == "내책_p042.jpg"


def test_page_filename_beyond_padding():
    """1000쪽을 넘어도 잘리지 않아야 한다."""
    assert page_filename("내책", 1234) == "내책_p1234.jpg"


def test_parse_page_number():
    assert parse_page_number("내책_p001.jpg") == 1
    assert parse_page_number("내책_p1234.jpg") == 1234


def test_parse_page_number_rejects_non_page():
    assert parse_page_number("내책.pdf") is None
    assert parse_page_number("random.jpg") is None


def test_sort_pages_is_numeric_not_lexical():
    """사전순이면 p10이 p2보다 앞서는 버그가 난다."""
    paths = [Path("t_p10.jpg"), Path("t_p2.jpg"), Path("t_p1.jpg")]
    assert [p.name for p in sort_pages(paths)] == ["t_p1.jpg", "t_p2.jpg", "t_p10.jpg"]


def test_sanitize_title_removes_path_separators():
    assert "/" not in sanitize_title("a/b")
    assert ":" not in sanitize_title("a:b")


def test_sanitize_title_rejects_empty():
    with pytest.raises(ValueError):
        sanitize_title("   ")


def test_sort_pages_drops_non_page_files_without_crashing():
    """result/ 에는 .pdf 등이 섞여 있다. 걸러내기가 정렬보다 먼저여야 한다."""
    paths = [Path("t_p10.jpg"), Path("t.pdf"), Path("t_p2.jpg"), Path("random.jpg")]
    assert [p.name for p in sort_pages(paths)] == ["t_p2.jpg", "t_p10.jpg"]
