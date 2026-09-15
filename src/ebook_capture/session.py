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
    start_page: int = 0,
) -> tuple[int, StopReason]:
    """캡처 -> 저장 -> 진행률 판정 -> 클릭 -> 대기를 반복한다.

    종료 조건은 세 겹이다 (research.md 3.2):
      1. OCR이 100% 이상을 읽음          -> COMPLETE
      2. 화면이 N회 연속 동일            -> STILL   (OCR 실패 대비 폴백)
      3. max_pages 도달                  -> MAX_PAGES
    여기에 ESC 중단(ABORTED)이 더해진다.

    start_page 는 이미 디스크에 저장되어 있는 페이지 수다. 캡처는
    start_page + 1 번부터 이어진다. max_pages 는 항상 페이지 번호의
    절대 상한이므로, 재개 시에도 그대로 적용된다.
    """
    stillness = StillnessDetector(required=config.stillness_required)
    page = start_page

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
