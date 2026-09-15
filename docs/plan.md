# 화면 캡처 → PDF 생성기 구현 계획 (plan.md)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 화면의 지정 영역을 일정 간격으로 자동 캡처하고 다음 페이지 버튼을 클릭해 나가다가 진행률 100%에서 멈춘 뒤, 모은 JPG를 무손실로 하나의 PDF에 병합하는 macOS 전용 CLI 도구를 만든다.

**Architecture:** 순수 함수(좌표 계산·파일명·정렬)와 OS 의존 계층(캡처·클릭·입력 수집)을 파일 단위로 분리한다. OS 의존 모듈은 얇게 유지해 단위 테스트 가능한 코어를 최대화한다. 메인 루프는 `session.py` 하나에 모으고, 나머지 모듈은 상태를 갖지 않는다.

**Tech Stack:** Python 3.12 / mss(캡처) / pyobjc-Quartz(클릭·디스플레이) / pynput(좌표 수집·ESC) / Pillow / pytesseract + tesseract 5.5.2 / img2pdf / uv / pytest

**Spec:** [`docs/research.md`](./research.md) — 기술 선정 근거와 실측값. [`docs/project_requirement.md`](./project_requirement.md) — 원본 요구사항.

## Global Constraints

모든 Task의 요구사항에 아래가 암묵적으로 포함된다.

- **Python**: 3.12 이상. 패키지 관리는 `uv`.
- **런타임 의존성은 정확히 6개**. 추가 금지:
  `mss>=10.2`, `pynput>=1.8`, `pyobjc-framework-Quartz>=12.2`, `Pillow>=12.3`, `pytesseract>=0.3.13`, `img2pdf>=0.6.3`
- **개발 의존성**: `pytest>=8`, `pikepdf>=10` (PDF 검증용)
- **`pyautogui` 사용 절대 금지.** 보조 모니터의 음수 좌표를 주소 지정할 수 없다 (research.md 2.3).
- **`numpy` 사용 금지.** 이미지 비교는 `PIL.ImageChops` + `PIL.ImageStat`으로 처리한다.
- **시스템 의존성**: `tesseract` 5.5.2 (Homebrew 설치 완료)
- **좌표는 항상 전역 좌표계**이며 **음수가 될 수 있다** (왼쪽 모니터는 `x = -3840`부터). 모든 좌표 코드는 음수를 전제한다.
- **출력 경로**: `result/` 고정. 이미지 `result/<제목>_p{n:03d}.jpg`, 최종 `result/<제목>.pdf`
- **JPEG 저장 파라미터**: `quality=95`, `dpi=(300, 300)`
- **OCR 설정**: 업스케일 ×4 LANCZOS, `--psm 7` 우선 후 실패 시 `--psm 8` 1회 재시도,
  화이트리스트 `0123456789.%/`
- **기본 캡처 모드는 영역 지정.** 전체 화면은 `--fullscreen` 명시 플래그로만 (research.md 6.3: 전체 캡처 시 70% 낭비).
- **ESC 전역 중단키는 필수 기능**이다. 생략하거나 나중으로 미루지 않는다.
- **안전 상한** `--max-pages` 기본 2000.
- 모든 사용자 대면 메시지는 **한국어**로 작성한다.
- 각 Task는 `git commit`으로 끝낸다.

## File Structure

| 파일 | 책임 | OS 의존 |
|---|---|---|
| `src/ebook_capture/geometry.py` | `Region` 값 객체. 두 점 → 정규화 사각형 | 없음 (순수) |
| `src/ebook_capture/naming.py` | 페이지 파일명 생성·파싱·번호순 정렬 | 없음 (순수) |
| `src/ebook_capture/capture.py` | mss 캡처, JPEG 300dpi 저장 | mss |
| `src/ebook_capture/pdfbuild.py` | img2pdf 무손실 병합, 페이지 박스 옵션 | 없음 |
| `src/ebook_capture/progress.py` | 진행률 OCR, 화면 정지 감지 | tesseract |
| `src/ebook_capture/display.py` | 디스플레이 열거, 스케일 팩터, 권한 프리플라이트 | Quartz |
| `src/ebook_capture/clicker.py` | `CGEventPost` 클릭 | Quartz |
| `src/ebook_capture/picker.py` | 클릭 좌표 수집, ESC 감시 | pynput |
| `src/ebook_capture/session.py` | 설정 dataclass, JSON 저장/복원, 메인 루프 | 조합 |
| `src/ebook_capture/cli.py` | argparse + 대화형 진입점 | 조합 |

순수 모듈(`geometry`, `naming`, `pdfbuild`)을 먼저 만들어 테스트 기반을 깔고,
OS 의존 모듈을 얹은 뒤, 마지막에 루프와 CLI로 조립한다.

---

### Task 1: 프로젝트 부트스트랩과 권한 프리플라이트

가장 먼저 **research.md 6.5의 미검증 항목 1번(클릭이 실제로 먹히는가)** 을 해소한다.
이것이 실패하면 이후 모든 작업이 무의미하므로 맨 앞에 둔다.

**Files:**
- Create: `pyproject.toml`
- Create: `src/ebook_capture/__init__.py`
- Create: `src/ebook_capture/display.py`
- Create: `tests/test_display.py`
- Create: `.gitignore`

**Interfaces:**
- Consumes: 없음 (최초 Task)
- Produces:
  - `display.check_permissions() -> tuple[bool, bool]` — `(화면기록, 손쉬운사용)`
  - `display.require_permissions() -> None` — 미충족 시 안내 메시지 출력 후 `SystemExit(1)`
  - `display.list_displays() -> list[DisplayInfo]`
  - `DisplayInfo` dataclass: `id: int, left: int, top: int, width: int, height: int, scale: float`

- [ ] **Step 1: git 저장소와 디렉터리 초기화**

```bash
cd /Users/sl/Workspace/eBOOK/generator
git init
mkdir -p src/ebook_capture tests result
touch src/ebook_capture/__init__.py
printf '.venv/\n__pycache__/\n*.pyc\nresult/*.jpg\nresult/*.pdf\nresult/*.session.json\n.pytest_cache/\n' > .gitignore
```

- [ ] **Step 2: `pyproject.toml` 작성**

```toml
[project]
name = "ebook-capture"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "mss>=10.2",
    "pynput>=1.8",
    "pyobjc-framework-Quartz>=12.2",
    "Pillow>=12.3",
    "pytesseract>=0.3.13",
    "img2pdf>=0.6.3",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pikepdf>=10"]

[project.scripts]
ebook-capture = "ebook_capture.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ebook_capture"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
markers = ["manual: 실제 화면 조작이 필요해 자동 실행에서 제외되는 테스트"]
addopts = "-m 'not manual'"
```

- [ ] **Step 3: 환경 생성 및 설치**

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
```

기대: 6개 런타임 + pytest, pikepdf 설치. **pyautogui가 목록에 없어야 한다.**

- [ ] **Step 4: 실패하는 테스트 작성**

```python
# tests/test_display.py
import pytest
from ebook_capture import display


def test_check_permissions_returns_two_bools():
    screen, accessibility = display.check_permissions()
    assert isinstance(screen, bool)
    assert isinstance(accessibility, bool)


def test_list_displays_finds_at_least_one():
    displays = display.list_displays()
    assert len(displays) >= 1


def test_display_scale_is_positive():
    for d in display.list_displays():
        assert d.scale > 0, f"디스플레이 {d.id}의 스케일이 0 이하입니다"


def test_display_dimensions_are_positive():
    for d in display.list_displays():
        assert d.width > 0 and d.height > 0
```

- [ ] **Step 5: 테스트 실패 확인**

```bash
uv run pytest tests/test_display.py -v
```

기대: `ModuleNotFoundError` 또는 `AttributeError`로 4개 모두 FAIL

- [ ] **Step 6: `display.py` 구현**

```python
"""디스플레이 정보 조회와 macOS 권한 프리플라이트."""
from dataclasses import dataclass

import Quartz
from ApplicationServices import AXIsProcessTrusted


@dataclass(frozen=True)
class DisplayInfo:
    id: int
    left: int
    top: int
    width: int
    height: int
    scale: float


def check_permissions() -> tuple[bool, bool]:
    """(화면 기록 허용 여부, 손쉬운 사용 허용 여부)를 반환한다."""
    return bool(Quartz.CGPreflightScreenCaptureAccess()), bool(AXIsProcessTrusted())


def require_permissions() -> None:
    """권한이 없으면 안내 후 종료한다."""
    screen, accessibility = check_permissions()
    if screen and accessibility:
        return
    print("필요한 권한이 없습니다. 시스템 설정에서 아래 항목을 허용해 주세요.\n")
    if not screen:
        print("  [ ] 개인정보 보호 및 보안 > 화면 기록")
        print("      없으면 캡처가 검은 화면이나 배경화면만 반환합니다.")
    if not accessibility:
        print("  [ ] 개인정보 보호 및 보안 > 손쉬운 사용")
        print("      없으면 자동 클릭과 ESC 중단키가 동작하지 않습니다.")
    print("\n권한은 python이 아니라 '이 프로그램을 실행한 앱'(터미널 / VS Code)에 부여해야 합니다.")
    print("허용 후 앱을 완전히 종료했다가 다시 실행하세요.")
    raise SystemExit(1)


def list_displays() -> list[DisplayInfo]:
    """연결된 모든 디스플레이를 전역 좌표와 스케일 팩터와 함께 반환한다."""
    _, ids, _ = Quartz.CGGetActiveDisplayList(16, None, None)
    out = []
    for did in ids:
        bounds = Quartz.CGDisplayBounds(did)
        pixels_wide = Quartz.CGDisplayPixelsWide(did)
        # 스케일은 하드코딩하지 않고 실행 시점에 측정한다 (research.md 2.1)
        scale = pixels_wide / bounds.size.width if bounds.size.width else 1.0
        out.append(
            DisplayInfo(
                id=int(did),
                left=int(bounds.origin.x),
                top=int(bounds.origin.y),
                width=int(bounds.size.width),
                height=int(bounds.size.height),
                scale=scale,
            )
        )
    return out
```

- [ ] **Step 7: 테스트 통과 확인**

```bash
uv run pytest tests/test_display.py -v
```

기대: 4개 PASS

- [ ] **Step 8: 권한과 클릭 실증 (research.md 6.5 항목 1 해소)**

`scripts/preflight.py`를 만들어 실제로 클릭이 먹히는지 확인한다.

```python
# scripts/preflight.py
"""실행 전 1회: 권한 상태와 CGEventPost 클릭 동작을 눈으로 확인한다."""
import time

import Quartz

from ebook_capture.display import check_permissions, list_displays

screen, accessibility = check_permissions()
print(f"화면 기록   : {screen}")
print(f"손쉬운 사용 : {accessibility}")
for d in list_displays():
    print(f"  디스플레이 {d.id}: ({d.left},{d.top}) {d.width}x{d.height} scale={d.scale:.2f}x")

x, y = map(float, input("\n클릭을 테스트할 좌표를 'x y'로 입력 (5초 뒤 클릭): ").split())
print("5초 후 클릭합니다. 대상 창을 띄워두세요...")
time.sleep(5)
for kind in (Quartz.kCGEventMouseMoved, Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
    Quartz.CGEventPost(
        Quartz.kCGHIDEventTap,
        Quartz.CGEventCreateMouseEvent(None, kind, (x, y), Quartz.kCGMouseButtonLeft),
    )
    time.sleep(0.05)
print("클릭을 보냈습니다. 대상 앱이 반응했는지 확인하세요.")
```

```bash
uv run python scripts/preflight.py
```

기대: 두 권한 모두 `True`, 입력한 좌표에서 대상 앱이 실제로 반응.
**반응하지 않으면 여기서 멈추고 원인을 해결한다.** 이후 Task는 이 전제 위에 있다.

- [ ] **Step 9: 커밋**

```bash
git add pyproject.toml .gitignore src/ebook_capture/__init__.py src/ebook_capture/display.py tests/test_display.py scripts/preflight.py
git commit -m "feat: 프로젝트 부트스트랩과 macOS 권한 프리플라이트

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Region 값 객체

**Files:**
- Create: `src/ebook_capture/geometry.py`
- Create: `tests/test_geometry.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `Region` frozen dataclass: `left: int, top: int, width: int, height: int`
  - `Region.from_points(p1: tuple[int, int], p2: tuple[int, int]) -> Region`
  - `Region.from_display(d: DisplayInfo) -> Region`
  - `Region.to_mss() -> dict[str, int]`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_geometry.py
import pytest
from ebook_capture.geometry import Region


def test_from_points_normal_order():
    r = Region.from_points((10, 20), (110, 220))
    assert (r.left, r.top, r.width, r.height) == (10, 20, 100, 200)


def test_from_points_reversed_order():
    """우하단을 먼저 클릭해도 같은 사각형이 나와야 한다."""
    r = Region.from_points((110, 220), (10, 20))
    assert (r.left, r.top, r.width, r.height) == (10, 20, 100, 200)


def test_from_points_negative_coordinates():
    """왼쪽 보조 모니터는 x가 음수다 (research.md 2.1)."""
    r = Region.from_points((-3800, -400), (-3000, 100))
    assert (r.left, r.top, r.width, r.height) == (-3800, -400, 800, 500)


def test_from_points_zero_area_raises():
    with pytest.raises(ValueError, match="영역"):
        Region.from_points((50, 50), (50, 200))


def test_to_mss_shape():
    r = Region(left=-100, top=-50, width=800, height=600)
    assert r.to_mss() == {"left": -100, "top": -50, "width": 800, "height": 600}


def test_region_is_frozen():
    r = Region(0, 0, 10, 10)
    with pytest.raises(Exception):
        r.left = 5
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/test_geometry.py -v
```

기대: `ModuleNotFoundError: No module named 'ebook_capture.geometry'`로 6개 FAIL

- [ ] **Step 3: `geometry.py` 구현**

```python
"""화면 영역 값 객체. 전역 좌표계를 쓰며 음수 좌표를 허용한다."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    left: int
    top: int
    width: int
    height: int

    @classmethod
    def from_points(cls, p1: tuple[int, int], p2: tuple[int, int]) -> "Region":
        """두 점으로 사각형을 만든다. 클릭 순서는 상관없다."""
        left, right = sorted((int(p1[0]), int(p2[0])))
        top, bottom = sorted((int(p1[1]), int(p2[1])))
        width, height = right - left, bottom - top
        if width <= 0 or height <= 0:
            raise ValueError(f"영역의 너비나 높이가 0입니다: {width}x{height}")
        return cls(left=left, top=top, width=width, height=height)

    @classmethod
    def from_display(cls, d) -> "Region":
        return cls(left=d.left, top=d.top, width=d.width, height=d.height)

    def to_mss(self) -> dict[str, int]:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/test_geometry.py -v
```

기대: 6개 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/ebook_capture/geometry.py tests/test_geometry.py
git commit -m "feat: 음수 좌표를 지원하는 Region 값 객체

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: 페이지 파일명 규칙

PDF 병합 시 `_p2.jpg`가 `_p10.jpg`보다 먼저 와야 한다. 사전순 정렬은 이를 깨뜨리므로
**번호를 파싱해 수치순으로 정렬**한다. 이 규칙을 순수 모듈로 분리해 확실히 테스트한다.

**Files:**
- Create: `src/ebook_capture/naming.py`
- Create: `tests/test_naming.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `page_filename(title: str, page: int) -> str`
  - `parse_page_number(name: str) -> int | None`
  - `sort_pages(paths: list[Path]) -> list[Path]`
  - `sanitize_title(title: str) -> str`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_naming.py
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
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/test_naming.py -v
```

기대: `ModuleNotFoundError`로 7개 FAIL

- [ ] **Step 3: `naming.py` 구현**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/test_naming.py -v
```

기대: 7개 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/ebook_capture/naming.py tests/test_naming.py
git commit -m "feat: 수치순 정렬을 보장하는 페이지 파일명 규칙

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: 화면 캡처와 JPEG 저장

**Files:**
- Create: `src/ebook_capture/capture.py`
- Create: `tests/test_capture.py`

**Interfaces:**
- Consumes: `geometry.Region`, `naming.page_filename`
- Produces:
  - `ScreenCapture` 컨텍스트 매니저, 메서드 `grab(region: Region) -> PIL.Image.Image`
  - `save_page(img, out_dir: Path, title: str, page: int, quality: int = 95, dpi: int = 300) -> Path`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_capture.py
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
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/test_capture.py -v
```

기대: `ModuleNotFoundError`로 5개 FAIL

- [ ] **Step 3: `capture.py` 구현**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/test_capture.py -v
```

기대: 5개 PASS. `test_grab_detects_blank_capture`가 실패하면 화면 기록 권한 문제다.

- [ ] **Step 5: 커밋**

```bash
git add src/ebook_capture/capture.py tests/test_capture.py
git commit -m "feat: 화면 캡처와 300dpi JPEG 저장

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: PDF 무손실 병합

**Files:**
- Create: `src/ebook_capture/pdfbuild.py`
- Create: `tests/test_pdfbuild.py`

**Interfaces:**
- Consumes: `naming.sort_pages`, `naming.parse_page_number`
- Produces:
  - `collect_pages(out_dir: Path, title: str) -> list[Path]`
  - `build_pdf(out_dir: Path, title: str, page_size: str | None = None) -> Path`
    - `page_size`는 `None`(이미지 DPI 기준) 또는 `"a4"`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_pdfbuild.py
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
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/test_pdfbuild.py -v
```

기대: `ModuleNotFoundError`로 7개 FAIL

- [ ] **Step 3: `pdfbuild.py` 구현**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/test_pdfbuild.py -v
```

기대: 7개 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/ebook_capture/pdfbuild.py tests/test_pdfbuild.py
git commit -m "feat: JPEG 무손실 PDF 병합

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: 진행률 OCR과 정지 감지

research.md 3.2의 삼중 종료 판정 중 1번(OCR)과 2번(정지 감지)을 만든다.

**Files:**
- Create: `src/ebook_capture/progress.py`
- Create: `tests/test_progress.py`

**Interfaces:**
- Consumes: 없음 (PIL 이미지를 인자로 받는다)
- Produces:
  - `read_percent(img: Image.Image, upscale: int = 4) -> float | None`
  - `StillnessDetector(threshold: float = 2.0, required: int = 3)`, 메서드 `update(img) -> bool`
    (`True`면 화면이 `required`회 연속 동일 — 더 넘길 페이지가 없다는 신호)

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_progress.py
import pytest
from PIL import Image, ImageDraw, ImageFont

from ebook_capture.progress import StillnessDetector, read_percent

FONT = "/System/Library/Fonts/Helvetica.ttc"


def _label(text: str, size: int = 11) -> Image.Image:
    """실제 뷰어와 같은 조건: 진회색 글자 + 흰 배경 (research.md 6.2)."""
    img = Image.new("RGB", (120, 34), "white")
    ImageDraw.Draw(img).text((8, 8), text, fill=(68, 68, 68), font=ImageFont.truetype(FONT, size))
    return img


@pytest.mark.parametrize("text,expected", [("0%", 0.0), ("47%", 47.0), ("100%", 100.0)])
def test_read_percent_parses_labels(text, expected):
    assert read_percent(_label(text)) == expected


def test_read_percent_returns_none_on_blank():
    assert read_percent(Image.new("RGB", (120, 34), "white")) is None


def test_read_percent_rejects_out_of_range():
    """오인식으로 999 같은 값이 나오면 None이어야 한다."""
    assert read_percent(_label("999")) is None


def test_stillness_detector_fires_after_required_repeats():
    same = Image.new("RGB", (60, 60), (10, 20, 30))
    d = StillnessDetector(required=3)
    assert d.update(same) is False  # 첫 프레임: 비교 대상 없음
    assert d.update(same) is False  # 1회 연속
    assert d.update(same) is False  # 2회 연속
    assert d.update(same) is True   # 3회 연속 -> 정지


def test_stillness_detector_resets_on_change():
    a = Image.new("RGB", (60, 60), (10, 20, 30))
    b = Image.new("RGB", (60, 60), (200, 40, 60))
    d = StillnessDetector(required=2)
    d.update(a)
    d.update(a)
    assert d.update(b) is False, "화면이 바뀌면 카운터가 초기화되어야 한다"
    assert d.update(b) is False


def test_stillness_detector_tolerates_tiny_noise():
    """안티에일리어싱 수준의 미세한 차이는 '동일'로 봐야 한다."""
    a = Image.new("RGB", (60, 60), (100, 100, 100))
    b = Image.new("RGB", (60, 60), (101, 100, 100))
    d = StillnessDetector(threshold=2.0, required=2)
    d.update(a)
    d.update(b)
    assert d.update(a) is True
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/test_progress.py -v
```

기대: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: `progress.py` 구현**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/test_progress.py -v
```

기대: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/ebook_capture/progress.py tests/test_progress.py
git commit -m "feat: 진행률 OCR과 화면 정지 감지

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Quartz 클릭 제어

**Files:**
- Create: `src/ebook_capture/clicker.py`
- Create: `tests/test_clicker.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `click(x: int, y: int, settle: float = 0.05) -> None`
  - `build_click_events(x: float, y: float) -> list` — 포스팅 없이 이벤트만 만든다 (테스트용)

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_clicker.py
import pytest
import Quartz

from ebook_capture.clicker import build_click_events, click


def test_build_click_events_has_move_down_up():
    events = build_click_events(100.0, 200.0)
    assert len(events) == 3


@pytest.mark.parametrize("x,y", [(-2000.0, 500.0), (100.0, 100.0), (3000.0, 800.0)])
def test_build_click_events_preserve_global_coordinates(x, y):
    """음수 좌표(왼쪽 모니터)가 보존되어야 한다. pyautogui는 이걸 못 한다 (research.md 2.3)."""
    for event in build_click_events(x, y):
        loc = Quartz.CGEventGetLocation(event)
        assert abs(loc.x - x) < 1.0
        assert abs(loc.y - y) < 1.0


@pytest.mark.manual
def test_click_actually_works():
    """실제 화면을 클릭하므로 수동 실행 전용: pytest -m manual"""
    click(100, 100)
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/test_clicker.py -v
```

기대: `ModuleNotFoundError`로 FAIL (manual 표시 테스트는 수집만 되고 실행 제외)

- [ ] **Step 3: `clicker.py` 구현**

```python
"""Quartz CGEventPost 기반 클릭. 전역 좌표계의 음수 값을 정확히 처리한다."""
import time

import Quartz

_KINDS = (
    Quartz.kCGEventMouseMoved,
    Quartz.kCGEventLeftMouseDown,
    Quartz.kCGEventLeftMouseUp,
)


def build_click_events(x: float, y: float) -> list:
    """이동·누름·뗌 이벤트를 만든다. 포스팅은 하지 않는다."""
    point = (float(x), float(y))
    return [
        Quartz.CGEventCreateMouseEvent(None, kind, point, Quartz.kCGMouseButtonLeft)
        for kind in _KINDS
    ]


def click(x: int, y: int, settle: float = 0.05) -> None:
    """지정한 전역 좌표를 클릭한다. 손쉬운 사용 권한이 필요하다."""
    for event in build_click_events(x, y):
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(settle)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/test_clicker.py -v
uv run pytest tests/test_clicker.py -m manual -v   # 실제 클릭 확인 (화면이 클릭됨)
```

기대: 자동 테스트 4개 PASS. manual 테스트는 실행 시 좌표 (100,100)이 실제로 클릭됨.

- [ ] **Step 5: 커밋**

```bash
git add src/ebook_capture/clicker.py tests/test_clicker.py
git commit -m "feat: 음수 전역 좌표를 지원하는 Quartz 클릭

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: 클릭 좌표 수집과 ESC 중단

자동 클릭 루프가 도는 동안 사용자는 마우스를 쓸 수 없다. **ESC 중단 수단이 없으면 위험하므로
이 Task는 생략 불가다** (research.md 3.2).

**Files:**
- Create: `src/ebook_capture/picker.py`
- Create: `tests/test_picker.py`

**Interfaces:**
- Consumes: `geometry.Region`
- Produces:
  - `pick_point(prompt: str) -> tuple[int, int]` — 안내 출력 후 사용자의 클릭 1회를 가로채 좌표 반환
  - `pick_region(label: str) -> Region` — 두 점을 받아 `Region` 생성
  - `AbortWatcher()` 컨텍스트 매니저, 속성 `aborted: bool` — ESC 감시

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_picker.py
import pytest

from ebook_capture.geometry import Region
from ebook_capture.picker import AbortWatcher, pick_point, pick_region


def test_abort_watcher_starts_not_aborted():
    with AbortWatcher() as watcher:
        assert watcher.aborted is False


def test_abort_watcher_can_be_triggered_programmatically():
    """ESC 키를 실제로 누르지 않고 내부 플래그 경로를 검증한다."""
    with AbortWatcher() as watcher:
        watcher.trigger()
        assert watcher.aborted is True


def test_pick_region_builds_region_from_two_points(monkeypatch):
    points = iter([(10, 20), (110, 220)])
    monkeypatch.setattr("ebook_capture.picker.pick_point", lambda prompt: next(points))
    region = pick_region("캡처 영역")
    assert region == Region(left=10, top=20, width=100, height=200)


def test_pick_region_handles_reversed_clicks(monkeypatch):
    points = iter([(110, 220), (10, 20)])
    monkeypatch.setattr("ebook_capture.picker.pick_point", lambda prompt: next(points))
    assert pick_region("캡처 영역") == Region(left=10, top=20, width=100, height=200)


@pytest.mark.manual
def test_pick_point_real_click():
    """수동 실행 전용: 실제로 화면을 클릭해야 통과한다."""
    x, y = pick_point("아무 곳이나 클릭하세요")
    assert isinstance(x, int) and isinstance(y, int)
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/test_picker.py -v
```

기대: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: `picker.py` 구현**

```python
"""pynput 기반 클릭 좌표 수집과 ESC 전역 중단 감시."""
import threading

from pynput import keyboard, mouse

from .geometry import Region


def pick_point(prompt: str) -> tuple[int, int]:
    """안내를 출력하고 사용자의 다음 클릭 좌표를 가로채 반환한다."""
    print(f"  {prompt} — 지금 클릭하세요...")
    captured: dict[str, tuple[int, int]] = {}

    def on_click(x, y, button, pressed):
        if pressed and button == mouse.Button.left:
            captured["point"] = (int(x), int(y))
            return False  # 리스너 종료
        return True

    with mouse.Listener(on_click=on_click) as listener:
        listener.join()

    point = captured["point"]
    print(f"    -> ({point[0]}, {point[1]})")
    return point


def pick_region(label: str) -> Region:
    """좌상단과 우하단을 순서대로 받아 Region을 만든다. 클릭 순서가 뒤바뀌어도 동작한다."""
    first = pick_point(f"{label}: 좌상단")
    second = pick_point(f"{label}: 우하단")
    return Region.from_points(first, second)


class AbortWatcher:
    """ESC 키를 전역 감시한다. 자동 클릭 루프 중 유일한 중단 수단이다."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._listener: keyboard.Listener | None = None

    @property
    def aborted(self) -> bool:
        return self._event.is_set()

    def trigger(self) -> None:
        self._event.set()

    def _on_press(self, key) -> None:
        if key == keyboard.Key.esc:
            self.trigger()

    def __enter__(self) -> "AbortWatcher":
        self._listener = keyboard.Listener(on_press=self._on_press)
        self._listener.start()
        return self

    def __exit__(self, *exc) -> None:
        if self._listener is not None:
            self._listener.stop()
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/test_picker.py -v
```

기대: 자동 테스트 4개 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/ebook_capture/picker.py tests/test_picker.py
git commit -m "feat: 클릭 좌표 수집과 ESC 전역 중단 감시

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: 세션 설정과 메인 루프

**Files:**
- Create: `src/ebook_capture/session.py`
- Create: `tests/test_session.py`

**Interfaces:**
- Consumes: `geometry.Region`, `capture.ScreenCapture`/`save_page`, `clicker.click`,
  `progress.read_percent`/`StillnessDetector`, `picker.AbortWatcher`, `naming.sanitize_title`
- Produces:
  - `SessionConfig` dataclass: `title, capture_region: Region, progress_region: Region,
    click_point: tuple[int, int], interval: float, dpi: int, quality: int, max_pages: int,
    stillness_required: int`
  - `SessionConfig.save(path) / SessionConfig.load(path)` — JSON 왕복
  - `StopReason` str enum: `COMPLETE`, `STILL`, `MAX_PAGES`, `ABORTED`
  - `run_session(config, out_dir, capturer, clicker_fn, watcher, on_page=None) -> tuple[int, StopReason]`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_session.py
import json

import pytest
from PIL import Image, ImageDraw, ImageFont

from ebook_capture.geometry import Region
from ebook_capture.session import SessionConfig, StopReason, run_session

FONT = "/System/Library/Fonts/Helvetica.ttc"


def _config(**over):
    base = dict(
        title="테스트책",
        capture_region=Region(0, 0, 60, 60),
        progress_region=Region(0, 900, 120, 34),
        click_point=(500, 500),
        interval=0.0,
        dpi=300,
        quality=95,
        max_pages=50,
        stillness_required=3,
    )
    base.update(over)
    return SessionConfig(**base)


def _pct_image(text: str) -> Image.Image:
    img = Image.new("RGB", (120, 34), "white")
    ImageDraw.Draw(img).text((8, 8), text, fill=(68, 68, 68), font=ImageFont.truetype(FONT, 11))
    return img


class FakeCapturer:
    """캡처 영역과 진행률 영역에 서로 다른 스크립트된 이미지를 돌려준다."""

    def __init__(self, percents, pages=None):
        self.percents = list(percents)
        self.pages = pages
        self.calls = 0

    def grab(self, region):
        if region.height == 34:  # 진행률 영역
            return _pct_image(self.percents[min(self.calls - 1, len(self.percents) - 1)])
        self.calls += 1
        if self.pages is not None:
            shade = self.pages[min(self.calls - 1, len(self.pages) - 1)]
        else:
            shade = self.calls * 7 % 256
        return Image.new("RGB", (60, 60), (shade, 60, 90))


class FakeWatcher:
    def __init__(self, abort_after=None):
        self.abort_after = abort_after
        self.checks = 0

    @property
    def aborted(self):
        self.checks += 1
        return self.abort_after is not None and self.checks > self.abort_after


def test_config_json_roundtrip(tmp_path):
    cfg = _config()
    path = tmp_path / "s.json"
    cfg.save(path)
    assert SessionConfig.load(path) == cfg


def test_config_json_is_human_readable(tmp_path):
    path = tmp_path / "s.json"
    _config().save(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["title"] == "테스트책"
    assert data["capture_region"]["width"] == 60


def test_session_stops_at_100_percent(tmp_path):
    clicks = []
    capturer = FakeCapturer(percents=["10%", "50%", "100%"])
    pages, reason = run_session(
        _config(), tmp_path, capturer, clicks.append, FakeWatcher()
    )
    assert reason == StopReason.COMPLETE
    assert pages == 3
    assert len(list(tmp_path.glob("테스트책_p*.jpg"))) == 3


def test_session_does_not_click_after_final_page(tmp_path):
    """100%를 읽은 뒤에는 더 클릭하지 않아야 한다."""
    clicks = []
    capturer = FakeCapturer(percents=["50%", "100%"])
    run_session(_config(), tmp_path, capturer, clicks.append, FakeWatcher())
    assert len(clicks) == 1


def test_session_stops_on_stillness_when_ocr_never_reaches_100(tmp_path):
    """OCR이 100%를 못 읽어도 화면이 멈추면 종료해야 한다 (research.md 3.2 폴백)."""
    capturer = FakeCapturer(percents=["50%"], pages=[10, 10, 10, 10, 10])
    pages, reason = run_session(
        _config(stillness_required=3), tmp_path, capturer, lambda p: None, FakeWatcher()
    )
    assert reason == StopReason.STILL
    assert pages < 50


def test_session_respects_max_pages(tmp_path):
    capturer = FakeCapturer(percents=["50%"])  # 계속 50%, 화면은 매번 바뀜
    pages, reason = run_session(
        _config(max_pages=5), tmp_path, capturer, lambda p: None, FakeWatcher()
    )
    assert reason == StopReason.MAX_PAGES
    assert pages == 5


def test_session_aborts_on_esc(tmp_path):
    capturer = FakeCapturer(percents=["50%"])
    pages, reason = run_session(
        _config(max_pages=100), tmp_path, capturer, lambda p: None, FakeWatcher(abort_after=2)
    )
    assert reason == StopReason.ABORTED
    assert pages < 100
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/test_session.py -v
```

기대: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: `session.py` 구현**

```python
"""세션 설정과 캡처 메인 루프."""
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from .capture import save_page
from .geometry import Region
from .progress import StillnessDetector, read_percent


class StopReason(StrEnum):
    COMPLETE = "진행률 100% 도달"
    STILL = "화면 변화 없음 (마지막 페이지로 판단)"
    MAX_PAGES = "최대 페이지 수 도달"
    ABORTED = "사용자가 ESC로 중단"


@dataclass(frozen=True)
class SessionConfig:
    title: str
    capture_region: Region
    progress_region: Region
    click_point: tuple[int, int]
    interval: float
    dpi: int = 300
    quality: int = 95
    max_pages: int = 2000
    stillness_required: int = 3

    def save(self, path: Path) -> None:
        data = asdict(self)
        data["click_point"] = list(self.click_point)
        Path(path).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> "SessionConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        data["capture_region"] = Region(**data["capture_region"])
        data["progress_region"] = Region(**data["progress_region"])
        data["click_point"] = tuple(data["click_point"])
        return cls(**data)


def run_session(
    config: SessionConfig,
    out_dir: Path,
    capturer,
    clicker_fn: Callable[[tuple[int, int]], None],
    watcher,
    on_page: Callable[[int, float | None], None] | None = None,
) -> tuple[int, StopReason]:
    """캡처 -> 저장 -> 진행률 판정 -> 클릭 -> 대기를 반복한다.

    종료 조건은 세 겹이다 (research.md 3.2):
      1. OCR이 100% 이상을 읽음          -> COMPLETE
      2. 화면이 N회 연속 동일            -> STILL   (OCR 실패 대비 폴백)
      3. max_pages 도달                  -> MAX_PAGES
    여기에 ESC 중단(ABORTED)이 더해진다.
    """
    stillness = StillnessDetector(required=config.stillness_required)
    page = 0

    while True:
        if watcher.aborted:
            return page, StopReason.ABORTED

        page += 1
        image = capturer.grab(config.capture_region)
        save_page(image, out_dir, config.title, page, quality=config.quality, dpi=config.dpi)

        percent = read_percent(capturer.grab(config.progress_region))
        if on_page is not None:
            on_page(page, percent)

        if percent is not None and percent >= 100.0:
            return page, StopReason.COMPLETE
        if stillness.update(image):
            return page, StopReason.STILL
        if page >= config.max_pages:
            return page, StopReason.MAX_PAGES

        clicker_fn(config.click_point)
        if config.interval > 0:
            time.sleep(config.interval)
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/test_session.py -v
```

기대: 7개 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/ebook_capture/session.py tests/test_session.py
git commit -m "feat: 삼중 종료 판정을 갖춘 캡처 메인 루프

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: CLI 조립

**Files:**
- Create: `src/ebook_capture/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: 모든 모듈
- Produces:
  - `build_parser() -> argparse.ArgumentParser`
  - `save_previews(capturer, config, out_dir) -> list[Path]`
  - `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_cli.py
from PIL import Image

from ebook_capture.cli import build_parser, save_previews
from ebook_capture.geometry import Region
from ebook_capture.session import SessionConfig


def test_parser_defaults_to_region_mode():
    args = build_parser().parse_args([])
    assert args.fullscreen is False, "기본은 영역 지정이다 (research.md 6.3)"
    assert args.dpi == 300
    assert args.max_pages == 2000
    assert args.page_size is None


def test_parser_accepts_options():
    args = build_parser().parse_args(
        ["--title", "내책", "--interval", "2.5", "--page-size", "a4", "--fullscreen"]
    )
    assert args.title == "내책"
    assert args.interval == 2.5
    assert args.page_size == "a4"
    assert args.fullscreen is True


def test_parser_rejects_bad_page_size():
    import pytest

    with pytest.raises(SystemExit):
        build_parser().parse_args(["--page-size", "letter"])


class StubCapturer:
    def grab(self, region):
        return Image.new("RGB", (region.width, region.height), "white")


def test_save_previews_writes_both_regions(tmp_path):
    config = SessionConfig(
        title="책",
        capture_region=Region(0, 0, 40, 40),
        progress_region=Region(0, 100, 30, 20),
        click_point=(10, 10),
        interval=1.0,
    )
    previews = save_previews(StubCapturer(), config, tmp_path)
    assert len(previews) == 2
    assert all(p.exists() for p in previews)
    assert any("capture" in p.name for p in previews)
    assert any("progress" in p.name for p in previews)
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
uv run pytest tests/test_cli.py -v
```

기대: `ModuleNotFoundError`로 FAIL

- [ ] **Step 3: `cli.py` 구현**

```python
"""대화형 CLI 진입점."""
import argparse
import sys
import time
from pathlib import Path

from .capture import ScreenCapture
from .clicker import click
from .display import list_displays, require_permissions
from .geometry import Region
from .naming import sanitize_title
from .pdfbuild import build_pdf
from .picker import AbortWatcher, pick_point, pick_region
from .session import SessionConfig, StopReason, run_session

RESULT_DIR = Path(__file__).resolve().parents[2] / "result"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ebook-capture",
        description="화면을 자동 캡처해 PDF로 묶습니다. 루프 중 ESC로 언제든 중단됩니다.",
    )
    p.add_argument("--title", help="PDF 제목 (생략 시 대화형으로 물어봅니다)")
    p.add_argument("--interval", type=float, help="캡처 간격(초)")
    p.add_argument("--fullscreen", action="store_true", help="영역 지정 대신 디스플레이 전체 캡처")
    p.add_argument("--dpi", type=int, default=300, help="JPEG DPI 메타데이터 (기본 300)")
    p.add_argument("--quality", type=int, default=95, help="JPEG 품질 (기본 95)")
    p.add_argument("--page-size", choices=["a4"], default=None, help="PDF 페이지 박스를 A4로 배치")
    p.add_argument("--max-pages", type=int, default=2000, help="안전 상한 (기본 2000)")
    p.add_argument("--resume", metavar="JSON", help="저장된 세션 설정으로 재개")
    return p


def save_previews(capturer, config: SessionConfig, out_dir: Path) -> list[Path]:
    """지정한 영역을 한 장씩 저장해 사용자가 눈으로 확인하게 한다.

    좌표를 잘못 잡은 채 수백 장을 캡처하는 사고를 막는 가장 싼 방법이다.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for label, region in (("capture", config.capture_region), ("progress", config.progress_region)):
        path = out_dir / f"_preview_{label}.png"
        capturer.grab(region).save(path)
        paths.append(path)
    return paths


def _choose_display() -> Region:
    displays = list_displays()
    print("\n캡처할 디스플레이를 고르세요:")
    for i, d in enumerate(displays):
        print(f"  [{i}] ({d.left},{d.top}) {d.width}x{d.height}  스케일 {d.scale:.2f}x")
    index = int(input("번호: ").strip())
    return Region.from_display(displays[index])


def _configure(args) -> SessionConfig:
    title = sanitize_title(args.title or input("PDF 제목: ").strip())
    interval = args.interval if args.interval is not None else float(input("캡처 간격(초): ").strip())

    print("\n영역과 클릭 지점을 지정합니다. 안내가 나오면 해당 위치를 클릭하세요.")
    capture_region = _choose_display() if args.fullscreen else pick_region("캡처 영역")
    click_point = pick_point("다음 페이지로 넘기는 버튼")
    progress_region = pick_region("진행률(%) 표시 영역")

    return SessionConfig(
        title=title,
        capture_region=capture_region,
        progress_region=progress_region,
        click_point=click_point,
        interval=interval,
        dpi=args.dpi,
        quality=args.quality,
        max_pages=args.max_pages,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    require_permissions()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    if args.resume:
        config = SessionConfig.load(Path(args.resume))
        print(f"세션을 재개합니다: {config.title}")
    else:
        config = _configure(args)

    with ScreenCapture() as capturer:
        for path in save_previews(capturer, config, RESULT_DIR):
            print(f"  미리보기 저장: {path}")
        if input("\n미리보기가 올바릅니까? 계속하려면 y: ").strip().lower() != "y":
            print("취소했습니다.")
            return 1

        session_path = RESULT_DIR / f"{config.title}.session.json"
        config.save(session_path)
        print(f"세션 설정 저장: {session_path}")

        print("\n5초 후 시작합니다. 대상 창을 맨 앞으로 띄워두세요. 중단하려면 ESC.")
        time.sleep(5)

        def report(page: int, percent: float | None) -> None:
            shown = f"{percent:.0f}%" if percent is not None else "판독 실패"
            print(f"  p{page:03d}  진행률 {shown}", flush=True)

        with AbortWatcher() as watcher:
            pages, reason = run_session(
                config, RESULT_DIR, capturer, lambda pt: click(*pt), watcher, on_page=report
            )

    print(f"\n캡처 종료: {pages}장 — {reason}")
    if pages == 0:
        print("캡처된 페이지가 없어 PDF를 만들지 않습니다.")
        return 1

    pdf_path = build_pdf(RESULT_DIR, config.title, page_size=args.page_size)
    size_mb = pdf_path.stat().st_size / 1e6
    print(f"PDF 생성 완료: {pdf_path}  ({pages}쪽, {size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
uv run pytest tests/test_cli.py -v
uv run pytest -v            # 전체 회귀
```

기대: `test_cli.py` 5개 PASS, 전체 스위트 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/ebook_capture/cli.py tests/test_cli.py
git commit -m "feat: 미리보기 확인과 세션 저장을 갖춘 대화형 CLI

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: 실사용 검증과 README

research.md 6.5의 남은 미검증 항목 2·3번을 실제 뷰어로 해소하고 문서를 남긴다.

**Files:**
- Create: `README.md`
- Modify: `docs/research.md` (6.5절 검증 결과 반영)

**Interfaces:**
- Consumes: 완성된 CLI
- Produces: 없음 (문서)

- [ ] **Step 1: 짧은 구간으로 실사용 테스트**

뷰어를 4K 모니터에 띄우고 3~5쪽만 돌려본다.

```bash
uv run ebook-capture --title "테스트" --interval 2 --max-pages 5
```

확인 사항:
1. 미리보기 2장이 의도한 영역과 일치하는가
2. `result/테스트_p001.jpg` ~ `p005.jpg`가 생성되는가
3. 진행률이 매 쪽 콘솔에 출력되는가 (판독 실패가 섞이지 않는가)
4. **중간에 ESC를 눌러 즉시 멈추는가**
5. `result/테스트.pdf`가 5쪽으로 생성되는가

- [ ] **Step 2: 간격 튜닝 (research.md 6.5 항목 2)**

`--interval`을 1초부터 올려가며 **중복 페이지가 사라지는 최소값**을 찾는다.
동일 이미지가 연속 저장되면 간격이 렌더링보다 짧은 것이다.

```bash
uv run python - <<'EOF'
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from ebook_capture.naming import sort_pages
pages = sort_pages(list(Path("result").glob("테스트_p*.jpg")))
for a, b in zip(pages, pages[1:]):
    with Image.open(a) as x, Image.open(b) as y:
        diff = ImageStat.Stat(ImageChops.difference(x.convert("L"), y.convert("L"))).mean[0]
        print(f"{a.name} -> {b.name}: 평균 차이 {diff:.2f}", "중복 의심!" if diff < 2 else "")
EOF
```

찾은 값을 README에 권장 간격으로 기록한다.

- [ ] **Step 3: 끝까지 1회 완주 (research.md 6.5 항목 3)**

실제 책 한 권을 끝까지 돌려 **진행률이 100%에 도달해 COMPLETE로 끝나는지**,
아니면 99%에 머물러 STILL 폴백으로 끝나는지 확인하고 research.md 6.5에 결과를 적는다.

- [ ] **Step 4: `README.md` 작성**

````markdown
# ebook-capture

화면의 지정 영역을 일정 간격으로 자동 캡처하고, 다음 페이지 버튼을 클릭해 나가다가
진행률 100%에서 멈춘 뒤, 모은 JPG를 무손실로 하나의 PDF에 묶습니다. macOS 전용입니다.

## 사전 준비

**시스템 설정 > 개인정보 보호 및 보안**에서 두 항목을 허용해야 합니다.

- **화면 기록** — 없으면 캡처가 검은 화면만 반환합니다
- **손쉬운 사용** — 없으면 자동 클릭과 ESC 중단이 동작하지 않습니다

권한은 python이 아니라 **이 프로그램을 실행하는 앱**(터미널 / VS Code)에 부여합니다.
허용 후 앱을 완전히 종료했다 다시 여세요.

```bash
brew install tesseract
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run python scripts/preflight.py   # 권한과 클릭 동작 확인
```

## 사용법

```bash
uv run ebook-capture
```

제목과 간격을 물어본 뒤, 순서대로 클릭해서 지정합니다.

1. 캡처 영역 좌상단 → 우하단
2. 다음 페이지 버튼
3. 진행률(%) 표시 영역 좌상단 → 우하단

미리보기 2장이 `result/`에 저장됩니다. **확인 후 y를 눌러야 시작**합니다.
5초 카운트다운 뒤 자동 캡처가 시작되며, **ESC를 누르면 즉시 중단**됩니다.

결과물은 `result/<제목>_p001.jpg` ... 와 `result/<제목>.pdf`입니다.
설정은 `result/<제목>.session.json`에 저장되어 `--resume`으로 재개할 수 있습니다.

## 옵션

| 옵션 | 기본 | 설명 |
|---|---|---|
| `--title` | 대화형 | PDF 제목 |
| `--interval` | 대화형 | 캡처 간격(초) |
| `--fullscreen` | 꺼짐 | 영역 지정 대신 디스플레이 전체 캡처 |
| `--dpi` | 300 | JPEG DPI 메타데이터 |
| `--quality` | 95 | JPEG 품질 |
| `--page-size` | 없음 | `a4` 지정 시 PDF 페이지 박스를 A4로 배치 |
| `--max-pages` | 2000 | 안전 상한 |
| `--resume` | — | 저장된 세션 JSON으로 재개 |

## 화질에 대해

화면 캡처는 화면에 있는 픽셀 수만큼만 존재합니다. `--dpi 300`은 **픽셀을 늘리지 않고
DPI 메타데이터만 기록**하므로 화질 손실도 없고 파일이 커지지도 않습니다.

**실제 화질을 높이는 유일한 방법은 캡처 전에 뷰어 창을 최대한 크게 키우는 것입니다.**
4K 모니터에서 세로로 꽉 채우면 페이지 픽셀이 크게 늘어납니다.

`--dpi`와 `--page-size`는 PDF 페이지의 표기 크기만 바꿉니다. 셋 다 화질은 동일합니다.

## 종료 조건

1. 진행률 OCR이 100% 이상을 읽음
2. 화면이 3회 연속 동일 (OCR 실패 대비 폴백)
3. `--max-pages` 도달
4. ESC

## 테스트

```bash
uv run pytest              # 자동 테스트
uv run pytest -m manual    # 실제 화면을 클릭하는 수동 테스트
```
````

- [ ] **Step 5: 커밋**

```bash
git add README.md docs/research.md
git commit -m "docs: README와 실사용 검증 결과 반영

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

---

### Task 12: 사용자 가이드 매뉴얼

README는 설치·옵션 레퍼런스다. 이 Task는 **도구를 처음 쓰는 사람이 순서대로 따라 하기만 하면
되는 실사용 매뉴얼**을 따로 만든다. 독자는 개발자가 아니라 이 도구의 사용자다.

**Files:**
- Create: `docs/사용자_가이드.md`

**Interfaces:**
- Consumes: Task 11에서 실사용 검증으로 확정된 권장 간격과 종료 동작
- Produces: 없음 (문서)

- [ ] **Step 1: Task 11의 실측값 수집**

가이드에 넣을 실제 수치를 Task 11 결과에서 가져온다. 추정값을 쓰지 않는다.

- Task 11 Step 2에서 찾은 **권장 `--interval` 값**
- Task 11 Step 3에서 확인한 **실제 종료 사유** (`COMPLETE` 인지 `STILL` 폴백인지)
- 실제 한 권을 돌렸을 때의 **소요 시간과 결과 PDF 용량**

- [ ] **Step 2: `docs/사용자_가이드.md` 작성**

아래 목차를 모두 채운다. 각 절은 "무엇을 하는지"가 아니라 **"무엇을 누르면 되는지"**를 쓴다.

1. **이 도구로 할 수 있는 일** — 3문장 이내. 결과물이 무엇인지(`result/` 안의 JPG들과 PDF 1개)
2. **처음 한 번만 하는 준비**
   - 시스템 설정에서 화면 기록·손쉬운 사용 켜기 — **스크린샷 대신 클릭 경로를 글로** 적는다
   - 권한을 켠 뒤 **앱을 완전히 종료했다 다시 열어야 한다**는 점을 굵게
   - `brew install tesseract`, `uv pip install -e ".[dev]"`
   - `uv run python scripts/preflight.py`로 확인하는 법과, 성공했을 때 보이는 화면
3. **캡처 전 준비 (화질을 결정하는 단계)**
   - 뷰어를 **가장 큰 모니터에 띄우고 창을 최대한 크게** — 실제 화질을 높이는 유일한 방법
   - 첫 페이지로 이동해 두기
   - 진행률 표시가 화면에 보이는 상태인지 확인
4. **실행 순서** — 번호를 매겨 그대로 따라 하게 쓴다
   1. `uv run ebook-capture` 실행
   2. 제목 입력 (파일 이름이 된다)
   3. 간격 입력 — **Task 11에서 찾은 권장값을 명시**
   4. 캡처 영역 좌상단 클릭 → 우하단 클릭 (책 페이지의 네 귀퉁이 중 두 곳)
   5. 다음 페이지 버튼 클릭
   6. 진행률(%) 표시 영역 좌상단 클릭 → 우하단 클릭 — **여유 있게 크게 잡으라**고 안내
   7. `result/_preview_capture.png`와 `_preview_progress.png`를 열어 확인
   8. `y` 입력 → 5초 뒤 시작
   9. 끝날 때까지 **마우스와 키보드를 건드리지 않는다**
5. **중간에 멈추고 싶을 때** — `ESC` 한 번. 그때까지 캡처된 이미지는 `result/`에 남는다
6. **결과물 확인** — `result/<제목>.pdf`, 쪽수와 용량 확인법
7. **다시 이어서 하기** — `--resume result/<제목>.session.json`
8. **자주 겪는 문제** — 아래 표를 그대로 포함한다

| 증상 | 원인 | 해결 |
|---|---|---|
| 캡처가 전부 검은 화면 | 화면 기록 권한 없음 | 설정에서 켠 뒤 **앱 재시작** |
| 클릭해도 페이지가 안 넘어감 | 손쉬운 사용 권한 없음 | 설정에서 켠 뒤 **앱 재시작** |
| 같은 페이지가 여러 장 저장됨 | 간격이 렌더링보다 짧음 | `--interval` 값을 늘린다 |
| 진행률이 "판독 실패"로 뜸 | 진행률 영역을 너무 좁게 잡음 | 다시 실행해 여유 있게 잡는다 |
| 끝났는데 마지막 몇 쪽이 없음 | 진행률이 100% 전에 정지 감지로 종료 | `--resume`으로 이어서 진행 |
| PDF 페이지가 너무 작게 나옴 | 300dpi 메타데이터 기준 페이지 크기 | `--page-size a4` 사용 (화질은 동일) |
| 좌표를 잘못 잡았다 | — | 미리보기 확인 단계에서 `y` 대신 아무 키나 눌러 취소 |

9. **화질에 대해 알아둘 것** — 업스케일로는 화질이 오르지 않는다는 점, `--dpi`와 `--page-size`는
   표기만 바꾼다는 점, 창을 크게 키우는 것이 유일한 방법이라는 점을 3문장으로

- [ ] **Step 3: 문서 검토**

직접 처음부터 끝까지 따라 하며 확인한다.

- 4절의 번호 순서대로만 따라 해도 PDF가 나오는가
- 개발자만 아는 용어(전역 좌표, OCR, DPI 메타데이터 등)를 설명 없이 쓰지 않았는가
- 8절의 표가 Task 11에서 실제로 겪은 문제를 반영하는가

- [ ] **Step 4: 커밋**

```bash
git add docs/사용자_가이드.md
git commit -m "docs: 사용자 가이드 매뉴얼

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

## Self-Review

**1. 요구사항 커버리지** — `project_requirement.md`의 7개 요구를 Task에 매핑했다.

| 요구 | 구현 Task |
|---|---|
| R1 화면 인식 | Task 1 (`display.list_displays`) |
| R2 전체/영역 선택 | Task 2 (`Region`) + Task 8 (`pick_region`) + Task 10 (`--fullscreen`) |
| R3 스크롤 클릭 지점 지정 | Task 8 (`pick_point`) |
| R4 지정 간격 캡처 | Task 4 + Task 9 (`interval`) |
| R5 `<제목>_p[n].jpg` 300dpi 저장 | Task 3 (`naming`) + Task 4 (`save_page`) |
| R6 진행률 100% 판정 후 중단 | Task 6 (`read_percent`) + Task 9 (`StopReason.COMPLETE`) |
| R7 전체 PDF 병합 | Task 5 (`build_pdf`) |

**2. 플레이스홀더 점검** — "TBD", "적절히 처리", "위와 비슷하게" 같은 표현 없음.
모든 코드 단계에 실제 코드 블록이 들어 있다.

**3. 타입 일관성 확인**

- `Region`: Task 2에서 정의, Task 4·8·9·10에서 동일 필드명(`left/top/width/height`) 사용
- `page_filename`: Task 3에서 정의, Task 4 `save_page`가 소비
- `sort_pages`: Task 3에서 정의, Task 5 `collect_pages`가 소비
- `read_percent` / `StillnessDetector.update`: Task 6에서 정의, Task 9 루프가 소비
- `click(x, y)`: Task 7에서 정의, Task 10이 `lambda pt: click(*pt)`로 어댑팅
- `AbortWatcher.aborted`: Task 8에서 정의, Task 9가 소비 (테스트는 `FakeWatcher`로 대체)
- `SessionConfig` 필드는 Task 9 정의와 Task 10 생성부가 일치

**4. 설계 원칙 준수**

- **DRY**: 파일명 규칙이 `naming.py` 한 곳에만 있다. 캡처·병합 양쪽이 이를 참조한다.
- **YAGNI**: OCR 이진화·대비 보정을 research.md 6.2에서 불필요로 검증하고 제외했다.
  GUI, 병렬 처리, 진행률 바 라이브러리도 넣지 않았다.
- **TDD**: 모든 Task가 실패 테스트 → 실패 확인 → 최소 구현 → 통과 확인 순이다.
- **격리**: OS 의존은 `capture`/`clicker`/`picker`/`display` 4개 파일에 갇혀 있고,
  `session.run_session`은 의존성을 인자로 받아 전부 가짜 객체로 테스트된다.
