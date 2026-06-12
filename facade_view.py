from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from models import PIXELS_PER_METER, Project, Wall


class FacadeView(QWidget):
    """Простой 2D-вид фасада без инженерной детализации."""

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.side = "север"
        self.setMinimumSize(720, 520)

    def set_project(self, project: Project) -> None:
        self.project = project
        self.update()

    def set_side(self, side: str) -> None:
        self.side = side
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f8faf7"))

        if not self.project.get_floor(1).walls:
            painter.setPen(QColor("#5f6f78"))
            painter.setFont(QFont("Arial", 14, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, "Фасад появится после рисования стен")
            return

        bounds = self._bounds()
        facade_width_m = self._facade_width(bounds)
        wall_height_m = max(2.0, self.project.total_wall_height_m())
        roof_height_m = max(0.2, self.project.roof_ridge_height)
        total_height_m = wall_height_m + roof_height_m + self.project.plinth_height + 0.8

        scale = min((self.width() - 100) / max(1.0, facade_width_m), (self.height() - 90) / total_height_m)
        scale = max(20.0, min(85.0, scale))

        left = (self.width() - facade_width_m * scale) / 2
        ground_y = self.height() - 46
        floor_y = ground_y - self.project.plinth_height * scale
        wall_top = floor_y - wall_height_m * scale
        right = left + facade_width_m * scale

        self._draw_ground(painter, left, right, ground_y, floor_y)
        self._draw_wall(painter, left, right, wall_top, floor_y)
        self._draw_floor_levels(painter, left, right, floor_y, scale)
        self._draw_openings(painter, bounds, left, floor_y, scale)
        self._draw_roof(painter, left, right, wall_top, scale)

        painter.setPen(QColor("#24343a"))
        painter.setFont(QFont("Arial", 12, QFont.Bold))
        painter.drawText(18, 28, f"Фасад: {self.side}")

    def _draw_ground(self, painter: QPainter, left: float, right: float, ground_y: float, floor_y: float) -> None:
        painter.setPen(QPen(QColor("#7b8a80"), 2))
        painter.drawLine(QPointF(left - 35, ground_y), QPointF(right + 35, ground_y))
        painter.setBrush(QColor("#d9dfd8"))
        painter.setPen(QPen(QColor("#aeb9b0"), 1))
        painter.drawRect(QRectF(left, floor_y, right - left, ground_y - floor_y))
        painter.setPen(QColor("#4d6258"))
        painter.setFont(QFont("Arial", 9))
        painter.drawText(QPointF(left + 8, ground_y - 8), "уровень земли / цоколь")

    def _draw_wall(self, painter: QPainter, left: float, right: float, top: float, bottom: float) -> None:
        painter.setPen(QPen(QColor("#364147"), 2))
        painter.setBrush(QColor("#eef1ed"))
        painter.drawRect(QRectF(left, top, right - left, bottom - top))

    def _draw_floor_levels(self, painter: QPainter, left: float, right: float, floor_y: float, scale: float) -> None:
        painter.setPen(QPen(QColor("#aeb8b2"), 1, Qt.DashLine))
        first_top = floor_y - self.project.floor_1_height * scale
        painter.drawLine(QPointF(left, first_top), QPointF(right, first_top))
        painter.setFont(QFont("Arial", 9))
        painter.setPen(QColor("#52635d"))
        painter.drawText(QPointF(right - 92, first_top - 6), "1 этаж")

        if self.project.floor_mode in ("2 этажа", "1 этаж + мансарда"):
            slab_top = first_top - self.project.slab_height * scale
            painter.setPen(QPen(QColor("#9ea9a3"), 2))
            painter.drawLine(QPointF(left, slab_top), QPointF(right, slab_top))
            painter.setPen(QColor("#52635d"))
            label = "2 этаж" if self.project.floor_mode == "2 этажа" else "мансарда"
            painter.drawText(QPointF(right - 92, slab_top - 6), label)

    def _draw_openings(self, painter: QPainter, bounds: tuple[float, float, float, float], left: float, floor_y: float, scale: float) -> None:
        for floor in self.project.visible_floors():
            floor_base_y = floor_y
            if floor.level == 2:
                floor_base_y = floor_y - self.project.floor_1_height * scale - self.project.slab_height * scale
            visible_walls = {index for index, wall in enumerate(floor.walls) if self._wall_matches_side(wall, bounds)}
            if not visible_walls:
                visible_walls = set(range(len(floor.walls)))

            for window in floor.windows:
                if window.wall_index not in visible_walls or window.wall_index >= len(floor.walls):
                    continue
                x = left + self._opening_offset_m(floor.walls[window.wall_index], window.position, bounds) * scale
                width = window.width * scale
                height = window.height * scale
                bottom = floor_base_y - window.install_height * scale
                rect = QRectF(x - width / 2, bottom - height, width, height)
                painter.setBrush(QColor("#b9ddf3"))
                painter.setPen(QPen(QColor("#1779b7"), 2))
                painter.drawRect(rect)
                painter.drawLine(rect.topLeft(), rect.bottomRight())
                painter.drawLine(rect.bottomLeft(), rect.topRight())
                self._draw_size_label(painter, rect, f"{window.width:.1f} x {window.height:.1f} м")

            for door in floor.doors:
                if door.wall_index not in visible_walls or door.wall_index >= len(floor.walls):
                    continue
                x = left + self._opening_offset_m(floor.walls[door.wall_index], door.position, bounds) * scale
                width = door.width * scale
                height = door.height * scale
                rect = QRectF(x - width / 2, floor_base_y - height, width, height)
                painter.setBrush(QColor("#d79a55"))
                painter.setPen(QPen(QColor("#9a5a21"), 2))
                painter.drawRect(rect)
                painter.drawLine(rect.topLeft(), rect.bottomRight())
                self._draw_size_label(painter, rect, f"{door.width:.1f} x {door.height:.1f} м")

    def _draw_size_label(self, painter: QPainter, rect: QRectF, text: str) -> None:
        painter.setPen(QColor("#1f2a2e"))
        painter.setFont(QFont("Arial", 8))
        label_rect = QRectF(rect.left() - 10, rect.top() - 18, rect.width() + 20, 16)
        painter.drawText(label_rect, Qt.AlignCenter, text)

    def _draw_roof(self, painter: QPainter, left: float, right: float, wall_top: float, scale: float) -> None:
        overhang = self.project.roof_overhang * scale
        roof_left = left - overhang
        roof_right = right + overhang
        roof_base = wall_top
        ridge_y = roof_base - self.project.roof_ridge_height * scale
        center_x = (roof_left + roof_right) / 2
        roof_type = self.project.roof_type

        painter.setPen(QPen(QColor("#7a4e25"), 2))
        painter.setBrush(QBrush(QColor(184, 125, 63, 145)))

        if roof_type == "Плоская":
            painter.drawRect(QRectF(roof_left, roof_base - 12, roof_right - roof_left, 12))
            return

        if roof_type == "Односкатная":
            polygon = QPolygonF([QPointF(roof_left, roof_base), QPointF(roof_right, ridge_y), QPointF(roof_right, ridge_y + 12), QPointF(roof_left, roof_base + 12)])
            painter.drawPolygon(polygon)
            painter.drawLine(QPointF(roof_left + 12, roof_base - 10), QPointF(roof_right - 12, ridge_y + 6))
            return

        if roof_type in ("Вальмовая", "Полувальмовая"):
            top_left = QPointF(left + (right - left) * 0.22, ridge_y)
            top_right = QPointF(right - (right - left) * 0.22, ridge_y)
            polygon = QPolygonF([QPointF(roof_left, roof_base), top_left, top_right, QPointF(roof_right, roof_base)])
            painter.drawPolygon(polygon)
            painter.drawLine(top_left, top_right)
            painter.drawLine(QPointF(roof_left, roof_base), top_left)
            painter.drawLine(QPointF(roof_right, roof_base), top_right)
        elif roof_type == "Шатровая":
            polygon = QPolygonF([QPointF(roof_left, roof_base), QPointF(center_x, ridge_y), QPointF(roof_right, roof_base)])
            painter.drawPolygon(polygon)
            painter.drawLine(QPointF(center_x, ridge_y), QPointF(center_x, roof_base))
        else:
            polygon = QPolygonF([QPointF(roof_left, roof_base), QPointF(center_x, ridge_y), QPointF(roof_right, roof_base)])
            painter.drawPolygon(polygon)
            painter.drawLine(QPointF(center_x, ridge_y), QPointF(center_x, roof_base))
            if roof_type == "Мансардная":
                painter.setPen(QPen(QColor("#7a4e25"), 1, Qt.DashLine))
                painter.drawLine(QPointF(roof_left + 22, roof_base - 24), QPointF(roof_right - 22, roof_base - 24))

        painter.setPen(QColor("#49301d"))
        painter.setFont(QFont("Arial", 9))
        painter.drawText(QPointF(center_x + 8, ridge_y + 16), f"конёк {self.project.roof_ridge_height:.1f} м")

    def _bounds(self) -> tuple[float, float, float, float]:
        walls = self.project.get_floor(1).walls
        xs = [point.x for wall in walls for point in (wall.start, wall.end)]
        ys = [point.y for wall in walls for point in (wall.start, wall.end)]
        return min(xs), min(ys), max(xs), max(ys)

    def _facade_width(self, bounds: tuple[float, float, float, float]) -> float:
        min_x, min_y, max_x, max_y = bounds
        if self.side in ("север", "юг"):
            return max(1.0, (max_x - min_x) / PIXELS_PER_METER)
        return max(1.0, (max_y - min_y) / PIXELS_PER_METER)

    def _wall_matches_side(self, wall: Wall, bounds: tuple[float, float, float, float]) -> bool:
        min_x, min_y, max_x, max_y = bounds
        mid_x = (wall.start.x + wall.end.x) / 2
        mid_y = (wall.start.y + wall.end.y) / 2
        dx = abs(wall.end.x - wall.start.x)
        dy = abs(wall.end.y - wall.start.y)
        tolerance = PIXELS_PER_METER * 0.35
        if self.side == "север":
            return dx >= dy and abs(mid_y - min_y) <= tolerance
        if self.side == "юг":
            return dx >= dy and abs(mid_y - max_y) <= tolerance
        if self.side == "запад":
            return dy >= dx and abs(mid_x - min_x) <= tolerance
        return dy >= dx and abs(mid_x - max_x) <= tolerance

    def _opening_offset_m(self, wall: Wall, ratio: float, bounds: tuple[float, float, float, float]) -> float:
        min_x, min_y, max_x, max_y = bounds
        x = wall.start.x + (wall.end.x - wall.start.x) * ratio
        y = wall.start.y + (wall.end.y - wall.start.y) * ratio
        if self.side in ("север", "юг"):
            return max(0.0, (x - min_x) / PIXELS_PER_METER)
        return max(0.0, (y - min_y) / PIXELS_PER_METER)
