from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import atan2, hypot
from typing import Any


PIXELS_PER_METER = 40

WALL_MATERIALS = ["Газоблок", "Кирпич", "Пеноблок", "Каркас"]
FOUNDATION_TYPES = ["Плита", "Лента", "Сваи"]
ROOF_TYPES = ["Плоская", "Односкатная", "Двускатная", "Вальмовая"]
ROOFING_TYPES = ["Металлочерепица", "Профлист", "Мягкая кровля"]
FINISHING_TYPES = ["Без отделки", "Черновая", "Чистовая"]


@dataclass
class Point:
    x: float
    y: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Point":
        return Point(float(data["x"]), float(data["y"]))


@dataclass
class Wall:
    start: Point
    end: Point
    height: float = 2.8
    thickness: float = 0.3
    material: str = "Газоблок"
    price_per_m2: float = 0.0
    is_load_bearing: bool = True

    @property
    def length_m(self) -> float:
        # Один метр на плане равен PIXELS_PER_METER пикселям.
        return hypot(self.end.x - self.start.x, self.end.y - self.start.y) / PIXELS_PER_METER

    def area_m2(self) -> float:
        return self.length_m * self.height

    def move(self, dx: float, dy: float) -> None:
        self.start.x += dx
        self.start.y += dy
        self.end.x += dx
        self.end.y += dy

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "height": self.height,
            "thickness": self.thickness,
            "material": self.material,
            "price_per_m2": self.price_per_m2,
            "is_load_bearing": self.is_load_bearing,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Wall":
        return Wall(
            start=Point.from_dict(data["start"]),
            end=Point.from_dict(data["end"]),
            height=float(data.get("height", 2.8)),
            thickness=float(data.get("thickness", 0.3)),
            material=str(data.get("material", "Газоблок")),
            price_per_m2=float(data.get("price_per_m2", 0.0)),
            is_load_bearing=bool(data.get("is_load_bearing", True)),
        )


@dataclass
class DoorItem:
    wall_index: int
    position: float = 0.5
    width: float = 0.9
    opening_direction: str = "Внутрь"
    hinge_side: str = "Левая"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "DoorItem":
        return DoorItem(
            wall_index=int(data["wall_index"]),
            position=float(data.get("position", 0.5)),
            width=float(data.get("width", 0.9)),
            opening_direction=str(data.get("opening_direction", "Внутрь")),
            hinge_side=str(data.get("hinge_side", "Левая")),
        )


@dataclass
class WindowItem:
    wall_index: int
    position: float = 0.5
    width: float = 1.2
    height: float = 1.4
    count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "WindowItem":
        return WindowItem(
            wall_index=int(data["wall_index"]),
            position=float(data.get("position", 0.5)),
            width=float(data.get("width", 1.2)),
            height=float(data.get("height", 1.4)),
            count=int(data.get("count", 1)),
        )


@dataclass
class Project:
    walls: list[Wall] = field(default_factory=list)
    doors: list[DoorItem] = field(default_factory=list)
    windows: list[WindowItem] = field(default_factory=list)
    wall_height: float = 2.8
    floors: int = 1
    wall_material: str = "Газоблок"
    foundation_type: str = "Лента"
    roof_type: str = "Двускатная"
    roofing: str = "Металлочерепица"
    roof_ridge_direction: str = "по X"
    roof_angle: float = 30.0
    roof_ridge_height: float = 2.0
    roof_overhang: float = 0.5
    roof_complexity: float = 1.0
    show_roof: bool = False
    finishing: str = "Без отделки"

    def total_wall_length_m(self) -> float:
        return sum(wall.length_m for wall in self.walls)

    def wall_area_m2(self) -> float:
        return sum(wall.area_m2() for wall in self.walls) * self.floors

    def approximate_house_area_m2(self) -> float:
        return self.footprint_area_m2() * self.floors

    def footprint_area_m2(self) -> float:
        if len(self.walls) < 3:
            return 0.0

        points: list[Point] = []
        seen: set[tuple[float, float]] = set()
        for wall in self.walls:
            for point in (wall.start, wall.end):
                key = (round(point.x, 3), round(point.y, 3))
                if key not in seen:
                    points.append(point)
                    seen.add(key)

        if len(points) >= 3:
            # Для простого замкнутого контура сортируем углы вокруг центра и считаем площадь.
            center_x = sum(point.x for point in points) / len(points)
            center_y = sum(point.y for point in points) / len(points)
            ordered = sorted(points, key=lambda point: atan2(point.y - center_y, point.x - center_x))
            area_px = 0.0
            for index, point in enumerate(ordered):
                next_point = ordered[(index + 1) % len(ordered)]
                area_px += point.x * next_point.y - next_point.x * point.y
            area_m2 = abs(area_px) / 2 / (PIXELS_PER_METER * PIXELS_PER_METER)
            if area_m2 > 0:
                return area_m2

        # Если контур ещё не замкнут, используем габарит как понятную приблизительную оценку.
        xs = [point.x for wall in self.walls for point in (wall.start, wall.end)]
        ys = [point.y for wall in self.walls for point in (wall.start, wall.end)]
        width_m = (max(xs) - min(xs)) / PIXELS_PER_METER
        height_m = (max(ys) - min(ys)) / PIXELS_PER_METER
        return max(0.0, width_m * height_m)

    def footprint_bounds_m(self) -> tuple[float, float]:
        if not self.walls:
            return 0.0, 0.0
        xs = [point.x for wall in self.walls for point in (wall.start, wall.end)]
        ys = [point.y for wall in self.walls for point in (wall.start, wall.end)]
        width_m = (max(xs) - min(xs)) / PIXELS_PER_METER
        height_m = (max(ys) - min(ys)) / PIXELS_PER_METER
        return max(0.0, width_m), max(0.0, height_m)

    def to_dict(self) -> dict[str, Any]:
        return {
            "walls": [wall.to_dict() for wall in self.walls],
            "doors": [door.to_dict() for door in self.doors],
            "windows": [window.to_dict() for window in self.windows],
            "wall_height": self.wall_height,
            "floors": self.floors,
            "wall_material": self.wall_material,
            "foundation_type": self.foundation_type,
            "roof_type": self.roof_type,
            "roofing": self.roofing,
            "roof_ridge_direction": self.roof_ridge_direction,
            "roof_angle": self.roof_angle,
            "roof_ridge_height": self.roof_ridge_height,
            "roof_overhang": self.roof_overhang,
            "roof_complexity": self.roof_complexity,
            "show_roof": self.show_roof,
            "finishing": self.finishing,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Project":
        doors = [DoorItem.from_dict(item) for item in data.get("doors", [])]
        windows = [WindowItem.from_dict(item) for item in data.get("windows", [])]

        # Старые проекты хранили двери и окна в общем списке openings.
        for opening in data.get("openings", []):
            kind = str(opening.get("kind", "")).strip().lower()
            if kind in ("дверь", "door"):
                doors.append(DoorItem(int(opening["wall_index"]), float(opening.get("position", 0.5))))
            elif kind in ("окно", "window"):
                windows.append(WindowItem(int(opening["wall_index"]), float(opening.get("position", 0.5))))

        project = Project(
            walls=[Wall.from_dict(item) for item in data.get("walls", [])],
            doors=doors,
            windows=windows,
            wall_height=float(data.get("wall_height", 2.8)),
            floors=int(data.get("floors", 1)),
            wall_material=str(data.get("wall_material", "Газоблок")),
            foundation_type=str(data.get("foundation_type", "Лента")),
            roof_type=str(data.get("roof_type", "Двускатная")),
            roofing=str(data.get("roofing", "Металлочерепица")),
            roof_ridge_direction=str(data.get("roof_ridge_direction", "по X")),
            roof_angle=float(data.get("roof_angle", 30.0)),
            roof_ridge_height=float(data.get("roof_ridge_height", 2.0)),
            roof_overhang=float(data.get("roof_overhang", 0.5)),
            roof_complexity=float(data.get("roof_complexity", 1.0)),
            show_roof=bool(data.get("show_roof", False)),
            finishing=str(data.get("finishing", "Без отделки")),
        )

        # Для старых стен без параметров подставляем общие настройки проекта.
        for wall in project.walls:
            if not wall.material:
                wall.material = project.wall_material
            if wall.height <= 0:
                wall.height = project.wall_height
        return project
