from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import atan2, hypot, radians, tan
from typing import Any


PIXELS_PER_METER = 40

WALL_MATERIALS = ["Газоблок 300 мм", "Кирпич керамический рядовой", "Пеноблок", "Каркас 150 мм"]
FOUNDATION_TYPES = ["Плита", "Лента", "Сваи"]
ROOF_TYPES = ["Плоская", "Односкатная", "Двускатная", "Вальмовая", "Полувальмовая", "Мансардная", "Шатровая"]
ROOFING_TYPES = ["Металлочерепица", "Профлист", "Мягкая кровля", "Фальцевая кровля"]
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
    height: float = 2.1
    opening_direction: str = "Внутрь"
    hinge_side: str = "Левая"
    price: float = 28000.0
    template_name: str = "Входная 0.9 x 2.1 м"
    distance_from_start: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "DoorItem":
        return DoorItem(
            wall_index=int(data["wall_index"]),
            position=float(data.get("position", 0.5)),
            width=float(data.get("width", 0.9)),
            height=float(data.get("height", 2.1)),
            opening_direction=str(data.get("opening_direction", "Внутрь")),
            hinge_side=str(data.get("hinge_side", "Левая")),
            price=float(data.get("price", 28000.0)),
            template_name=str(data.get("template_name", "Входная 0.9 x 2.1 м")),
            distance_from_start=(
                None
                if data.get("distance_from_start") is None
                else float(data.get("distance_from_start", 0.0))
            ),
        )


@dataclass
class WindowItem:
    wall_index: int
    position: float = 0.5
    width: float = 1.2
    height: float = 1.4
    install_height: float = 0.9
    glass_type: str = "двухкамерный"
    price: float = 18000.0
    price_per_m2: float = 0.0
    template_name: str = "Стандартное окно 1.5 x 1.4 м"
    distance_from_start: float | None = None
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
            install_height=float(data.get("install_height", data.get("sill_height", 0.9))),
            glass_type=str(data.get("glass_type", "двухкамерный")),
            price=float(data.get("price", 18000.0)),
            price_per_m2=float(data.get("price_per_m2", 0.0)),
            template_name=str(data.get("template_name", "Стандартное окно 1.5 x 1.4 м")),
            distance_from_start=(
                None
                if data.get("distance_from_start") is None
                else float(data.get("distance_from_start", 0.0))
            ),
            count=int(data.get("count", 1)),
        )


ROOM_TYPES = [
    "Кухня",
    "Гостиная",
    "Спальня",
    "Детская",
    "Кабинет",
    "Санузел",
    "Ванная",
    "Котельная",
    "Гардероб",
    "Коридор",
    "Прихожая",
    "Кладовая",
    "Постирочная",
    "Свободное помещение",
]

STAIR_TYPES = ["Прямая", "Г-образная", "П-образная"]


@dataclass
class RoomItem:
    name: str
    floor: int
    center: Point
    area: float
    perimeter: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "floor": self.floor,
            "center": self.center.to_dict(),
            "area": self.area,
            "perimeter": self.perimeter,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "RoomItem":
        return RoomItem(
            name=str(data.get("name", "Свободное помещение")),
            floor=int(data.get("floor", 1)),
            center=Point.from_dict(data.get("center", {"x": 0, "y": 0})),
            area=float(data.get("area", 0.0)),
            perimeter=float(data.get("perimeter", 0.0)),
        )


@dataclass
class StairItem:
    floor: int
    position: Point
    stair_type: str = "Прямая"
    width: float = 0.9
    length: float = 3.0
    rise_height: float = 3.1
    steps: int = 16
    price: float = 120000.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "floor": self.floor,
            "position": self.position.to_dict(),
            "stair_type": self.stair_type,
            "width": self.width,
            "length": self.length,
            "rise_height": self.rise_height,
            "steps": self.steps,
            "price": self.price,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "StairItem":
        return StairItem(
            floor=int(data.get("floor", 1)),
            position=Point.from_dict(data.get("position", {"x": 0, "y": 0})),
            stair_type=str(data.get("stair_type", "Прямая")),
            width=float(data.get("width", 0.9)),
            length=float(data.get("length", 3.0)),
            rise_height=float(data.get("rise_height", 3.1)),
            steps=int(data.get("steps", 16)),
            price=float(data.get("price", 120000.0)),
        )


@dataclass
class FloorPlan:
    level: int
    name: str
    walls: list[Wall] = field(default_factory=list)
    doors: list[DoorItem] = field(default_factory=list)
    windows: list[WindowItem] = field(default_factory=list)
    rooms: list[RoomItem] = field(default_factory=list)
    stairs: list[StairItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "name": self.name,
            "walls": [wall.to_dict() for wall in self.walls],
            "doors": [door.to_dict() for door in self.doors],
            "windows": [window.to_dict() for window in self.windows],
            "rooms": [room.to_dict() for room in self.rooms],
            "stairs": [stair.to_dict() for stair in self.stairs],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "FloorPlan":
        level = int(data.get("level", 1))
        return FloorPlan(
            level=level,
            name=str(data.get("name", f"План {level} этажа")),
            walls=[Wall.from_dict(item) for item in data.get("walls", [])],
            doors=[DoorItem.from_dict(item) for item in data.get("doors", [])],
            windows=[WindowItem.from_dict(item) for item in data.get("windows", [])],
            rooms=[RoomItem.from_dict(item) for item in data.get("rooms", [])],
            stairs=[StairItem.from_dict(item) for item in data.get("stairs", [])],
        )


@dataclass
class Project:
    walls: list[Wall] = field(default_factory=list)
    doors: list[DoorItem] = field(default_factory=list)
    windows: list[WindowItem] = field(default_factory=list)
    floor_plans: list[FloorPlan] = field(default_factory=list)
    wall_height: float = 2.8
    floors: int = 1
    floor_mode: str = "1 этаж"
    floor_1_height: float = 2.8
    floor_2_height: float = 2.8
    plinth_height: float = 0.4
    slab_height: float = 0.3
    wall_material: str = "Газоблок 300 мм"
    foundation_type: str = "Лента"
    roof_type: str = "Двускатная"
    roofing: str = "Металлочерепица"
    roof_ridge_direction: str = "по X"
    roof_angle: float = 30.0
    roof_ridge_height: float = 2.0
    roof_overhang: float = 0.5
    roof_gable_height: float = 1.6
    roof_complexity: float = 1.0
    auto_roof_ridge_height: bool = True
    show_roof: bool = False
    finishing: str = "Без отделки"
    insulation_type: str = "Без утепления"
    facade_finish: str = "Без отделки"

    def __post_init__(self) -> None:
        self.ensure_floor_count(max(1, self.floors))

    def ensure_floor_count(self, count: int) -> None:
        count = max(1, count)
        if not self.floor_plans:
            self.floor_plans = [
                FloorPlan(
                    level=1,
                    name="План 1 этажа",
                    walls=self.walls,
                    doors=self.doors,
                    windows=self.windows,
                )
            ]

        existing = {floor.level: floor for floor in self.floor_plans}
        for level in range(1, count + 1):
            if level not in existing:
                self.floor_plans.append(FloorPlan(level=level, name=f"План {level} этажа"))
        self.floor_plans.sort(key=lambda floor: floor.level)
        self._sync_legacy_lists()

    def visible_floor_levels(self) -> list[int]:
        if self.floor_mode == "2 этажа":
            self.ensure_floor_count(2)
            return [1, 2]
        return [1]

    def visible_floors(self) -> list[FloorPlan]:
        return [self.get_floor(level) for level in self.visible_floor_levels()]

    def all_floors(self) -> list[FloorPlan]:
        self.ensure_floor_count(max(1, self.floors, len(self.floor_plans)))
        return list(self.floor_plans)

    def get_floor(self, level: int) -> FloorPlan:
        self.ensure_floor_count(level)
        for floor in self.floor_plans:
            if floor.level == level:
                return floor
        floor = FloorPlan(level=level, name=f"План {level} этажа")
        self.floor_plans.append(floor)
        self.floor_plans.sort(key=lambda item: item.level)
        self._sync_legacy_lists()
        return floor

    def _sync_legacy_lists(self) -> None:
        first_floor = next((floor for floor in self.floor_plans if floor.level == 1), None)
        if first_floor is None:
            first_floor = FloorPlan(level=1, name="План 1 этажа")
            self.floor_plans.insert(0, first_floor)
        self.walls = first_floor.walls
        self.doors = first_floor.doors
        self.windows = first_floor.windows

    def all_walls(self) -> list[Wall]:
        return [wall for floor in self.visible_floors() for wall in floor.walls]

    def all_doors(self) -> list[DoorItem]:
        return [door for floor in self.visible_floors() for door in floor.doors]

    def all_windows(self) -> list[WindowItem]:
        return [window for floor in self.visible_floors() for window in floor.windows]

    def all_rooms(self) -> list[RoomItem]:
        return [room for floor in self.visible_floors() for room in floor.rooms]

    def all_stairs(self) -> list[StairItem]:
        return [stair for floor in self.visible_floors() for stair in floor.stairs]

    def create_second_floor_from_first(self) -> None:
        first = self.get_floor(1)
        second = self.get_floor(2)
        exterior_walls = self._exterior_walls(first.walls)
        second.walls = []
        for wall in exterior_walls:
            second.walls.append(
                Wall(
                    start=Point(wall.start.x, wall.start.y),
                    end=Point(wall.end.x, wall.end.y),
                    height=self.floor_2_height,
                    thickness=wall.thickness,
                    material=wall.material,
                    price_per_m2=wall.price_per_m2,
                    is_load_bearing=wall.is_load_bearing,
                )
            )
        second.doors = []
        second.windows = []
        second.rooms = []
        second.stairs = []
        self.floor_mode = "2 этажа"
        self.floors = 2
        self._sync_legacy_lists()

    def _exterior_walls(self, walls: list[Wall]) -> list[Wall]:
        if not walls:
            return []
        xs = [point.x for wall in walls for point in (wall.start, wall.end)]
        ys = [point.y for wall in walls for point in (wall.start, wall.end)]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        tolerance = PIXELS_PER_METER * 0.25
        exterior: list[Wall] = []
        for wall in walls:
            mid_x = (wall.start.x + wall.end.x) / 2
            mid_y = (wall.start.y + wall.end.y) / 2
            dx = abs(wall.end.x - wall.start.x)
            dy = abs(wall.end.y - wall.start.y)
            horizontal_edge = dx >= dy and (abs(mid_y - min_y) <= tolerance or abs(mid_y - max_y) <= tolerance)
            vertical_edge = dy > dx and (abs(mid_x - min_x) <= tolerance or abs(mid_x - max_x) <= tolerance)
            if horizontal_edge or vertical_edge:
                exterior.append(wall)
        return exterior or [wall for wall in walls if wall.is_load_bearing] or list(walls)

    def total_wall_length_m(self) -> float:
        return sum(wall.length_m for wall in self.all_walls())

    def wall_area_m2(self) -> float:
        area = sum(wall.area_m2() for wall in self.all_walls())
        if self.floor_mode == "1 этаж + мансарда":
            return area * 1.35
        return area

    def approximate_house_area_m2(self) -> float:
        if self.floor_mode == "1 этаж + мансарда":
            return self.floor_area_m2(1) * 1.5
        return sum(self.floor_area_m2(level) for level in self.visible_floor_levels())

    def floor_area_m2(self, level: int) -> float:
        return self._walls_area_m2(self.get_floor(level).walls)

    def floor_perimeter_m(self, level: int) -> float:
        return sum(wall.length_m for wall in self.get_floor(level).walls if wall.is_load_bearing)

    def floor_area_multiplier(self) -> float:
        if self.floor_mode == "2 этажа":
            return 2.0
        if self.floor_mode == "1 этаж + мансарда":
            return 1.5
        return 1.0

    def wall_storey_multiplier(self) -> float:
        if self.floor_mode == "2 этажа":
            return 2.0
        if self.floor_mode == "1 этаж + мансарда":
            return 1.35
        return 1.0

    def total_wall_height_m(self) -> float:
        if self.floor_mode == "2 этажа":
            return self.floor_1_height + self.slab_height + self.floor_2_height
        if self.floor_mode == "1 этаж + мансарда":
            return self.floor_1_height + self.slab_height + max(1.2, self.roof_ridge_height * 0.55)
        return self.floor_1_height

    def roof_span_width_m(self) -> float:
        width_m, depth_m = self.footprint_bounds_m()
        return width_m if self.roof_ridge_direction == "по Y" else depth_m

    def roof_ridge_length_m(self) -> float:
        width_m, depth_m = self.footprint_bounds_m()
        if self.roof_type == "Плоская":
            return 0.0
        if self.roof_type in ("Односкатная", "Шатровая"):
            return 0.0
        length = depth_m if self.roof_ridge_direction == "по Y" else width_m
        if self.roof_type in ("Вальмовая", "Полувальмовая"):
            length *= 0.65
        return max(0.0, length)

    def roof_slope_count(self) -> int:
        if self.roof_type in ("Плоская", "Односкатная"):
            return 1
        if self.roof_type == "Двускатная":
            return 2
        return 4

    def update_auto_roof_height(self) -> None:
        if not self.auto_roof_ridge_height or self.roof_type != "Двускатная":
            return
        span = self.roof_span_width_m()
        if span <= 0:
            return
        angle = max(1.0, min(60.0, self.roof_angle))
        self.roof_ridge_height = (span / 2) * tan(radians(angle))

    def footprint_area_m2(self) -> float:
        return self.floor_area_m2(1)

    def _walls_area_m2(self, walls: list[Wall]) -> float:
        if len(walls) < 3:
            return 0.0

        points: list[Point] = []
        seen: set[tuple[float, float]] = set()
        for wall in walls:
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
        xs = [point.x for wall in walls for point in (wall.start, wall.end)]
        ys = [point.y for wall in walls for point in (wall.start, wall.end)]
        width_m = (max(xs) - min(xs)) / PIXELS_PER_METER
        height_m = (max(ys) - min(ys)) / PIXELS_PER_METER
        return max(0.0, width_m * height_m)

    def footprint_bounds_m(self) -> tuple[float, float]:
        walls = self.get_floor(1).walls
        if not walls:
            return 0.0, 0.0
        xs = [point.x for wall in walls for point in (wall.start, wall.end)]
        ys = [point.y for wall in walls for point in (wall.start, wall.end)]
        width_m = (max(xs) - min(xs)) / PIXELS_PER_METER
        height_m = (max(ys) - min(ys)) / PIXELS_PER_METER
        return max(0.0, width_m), max(0.0, height_m)

    def to_dict(self) -> dict[str, Any]:
        self._sync_legacy_lists()
        return {
            "walls": [wall.to_dict() for wall in self.walls],
            "doors": [door.to_dict() for door in self.doors],
            "windows": [window.to_dict() for window in self.windows],
            "floor_plans": [floor.to_dict() for floor in self.floor_plans],
            "wall_height": self.wall_height,
            "floors": self.floors,
            "floor_mode": self.floor_mode,
            "floor_1_height": self.floor_1_height,
            "floor_2_height": self.floor_2_height,
            "plinth_height": self.plinth_height,
            "slab_height": self.slab_height,
            "wall_material": self.wall_material,
            "foundation_type": self.foundation_type,
            "roof_type": self.roof_type,
            "roofing": self.roofing,
            "roof_ridge_direction": self.roof_ridge_direction,
            "roof_angle": self.roof_angle,
            "roof_ridge_height": self.roof_ridge_height,
            "roof_overhang": self.roof_overhang,
            "roof_gable_height": self.roof_gable_height,
            "roof_complexity": self.roof_complexity,
            "auto_roof_ridge_height": self.auto_roof_ridge_height,
            "show_roof": self.show_roof,
            "finishing": self.finishing,
            "insulation_type": self.insulation_type,
            "facade_finish": self.facade_finish,
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

        if data.get("floor_plans"):
            floor_plans = [FloorPlan.from_dict(item) for item in data.get("floor_plans", [])]
            first = next((floor for floor in floor_plans if floor.level == 1), FloorPlan(level=1, name="План 1 этажа"))
            legacy_walls = first.walls
            legacy_doors = first.doors
            legacy_windows = first.windows
        else:
            legacy_walls = [Wall.from_dict(item) for item in data.get("walls", [])]
            legacy_doors = doors
            legacy_windows = windows
            floor_plans = [
                FloorPlan(
                    level=1,
                    name="План 1 этажа",
                    walls=legacy_walls,
                    doors=legacy_doors,
                    windows=legacy_windows,
                )
            ]

        project = Project(
            walls=legacy_walls,
            doors=legacy_doors,
            windows=legacy_windows,
            floor_plans=floor_plans,
            wall_height=float(data.get("wall_height", 2.8)),
            floors=int(data.get("floors", 1)),
            floor_mode=str(data.get("floor_mode", "2 этажа" if int(data.get("floors", 1)) == 2 else "1 этаж")),
            floor_1_height=float(data.get("floor_1_height", data.get("wall_height", 2.8))),
            floor_2_height=float(data.get("floor_2_height", data.get("wall_height", 2.8))),
            plinth_height=float(data.get("plinth_height", 0.4)),
            slab_height=float(data.get("slab_height", 0.3)),
            wall_material=str(data.get("wall_material", "Газоблок 300 мм")),
            foundation_type=str(data.get("foundation_type", "Лента")),
            roof_type=str(data.get("roof_type", "Двускатная")),
            roofing=str(data.get("roofing", "Металлочерепица")),
            roof_ridge_direction=str(data.get("roof_ridge_direction", "по X")),
            roof_angle=float(data.get("roof_angle", 30.0)),
            roof_ridge_height=float(data.get("roof_ridge_height", 2.0)),
            roof_overhang=float(data.get("roof_overhang", 0.5)),
            roof_gable_height=float(data.get("roof_gable_height", data.get("gable_height", 1.6))),
            roof_complexity=float(data.get("roof_complexity", 1.0)),
            auto_roof_ridge_height=bool(data.get("auto_roof_ridge_height", True)),
            show_roof=bool(data.get("show_roof", False)),
            finishing=str(data.get("finishing", "Без отделки")),
            insulation_type=str(data.get("insulation_type", "Без утепления")),
            facade_finish=str(data.get("facade_finish", data.get("finishing", "Без отделки"))),
        )

        # Для старых стен без параметров подставляем общие настройки проекта.
        material_aliases = {
            "Газоблок": "Газоблок 300 мм",
            "Кирпич": "Кирпич керамический рядовой",
            "Каркас": "Каркас 150 мм",
        }
        project.wall_material = material_aliases.get(project.wall_material, project.wall_material)
        project.floors = 2 if project.floor_mode == "2 этажа" else 1
        project.ensure_floor_count(max(1, project.floors))
        for wall in project.all_walls():
            wall.material = material_aliases.get(wall.material, wall.material)
            if not wall.material:
                wall.material = project.wall_material
            if wall.height <= 0:
                wall.height = project.wall_height
        return project
