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
