"""디스플레이 정보 조회와 macOS 권한 프리플라이트."""
import sys
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
