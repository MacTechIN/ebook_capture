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
