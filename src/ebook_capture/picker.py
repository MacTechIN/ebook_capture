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
