from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from models import Project


class SectionView(QWidget):
    """Простой строительный разрез дома: фундамент, этажи, перекрытие и крыша."""

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.setMinimumSize(720, 520)

    def set_project(self, project: Project) -> None:
        self.project = project
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f8faf7"))

        width_m, depth_m = self.project.footprint_bounds_m()
        span_m = max(1.0, self.project.roof_span_width_m() or min(width_m or 6.0, depth_m or 6.0))
        wall_height = max(2.0, self.project.total_wall_height_m())
        ridge_height = 0.0 if self.project.roof_type == "Плоская" else max(0.1, self.project.roof_ridge_height)
        total_height = self.project.plinth_height + wall_height + ridge_height + 0.8
        scale = min((self.width() - 150) / span_m, (self.height() - 100) / total_height)
        scale = max(22.0, min(80.0, scale))

        left = (self.width() - span_m * scale) / 2
        right = left + span_m * scale
        ground_y = self.height() - 48
        plinth_top = ground_y - self.project.plinth_height * scale
        wall_top = plinth_top - wall_height * scale
        center_x = (left + right) / 2
        ridge_y = wall_top - ridge_height * scale

        self._draw_foundation(painter, left, right, ground_y, scale)
        self._draw_plinth(painter, left, right, ground_y, plinth_top)
        self._draw_walls_and_floors(painter, left, right, plinth_top, wall_top, scale)
        self._draw_stairs(painter, left, right, plinth_top, scale)
        self._draw_roof(painter, left, right, wall_top, ridge_y, center_x)
        self._draw_dimensions(painter, right, ground_y, plinth_top, wall_top, ridge_y, scale)

        painter.setPen(QColor("#24343a"))
        painter.setFont(QFont("Arial", 12, QFont.Bold))
        painter.drawText(18, 28, "Разрез дома")

    def _draw_foundation(self, painter: QPainter, left: float, right: float, ground_y: float, scale: float) -> None:
        painter.setBrush(QColor("#b8b0a4"))
        painter.setPen(QPen(QColor("#82796f"), 2))
        height = max(14, 0.35 * scale)
        painter.drawRect(QRectF(left - 16, ground_y, right - left + 32, height))
        painter.setPen(QColor("#4f5f58"))
        painter.setFont(QFont("Arial", 9))
        painter.drawText(QPointF(left - 12, ground_y + height + 18), f"фундамент: {self.project.foundation_type}")

    def _draw_plinth(self, painter: QPainter, left: float, right: float, ground_y: float, plinth_top: float) -> None:
        painter.setBrush(QColor("#d8ded7"))
        painter.setPen(QPen(QColor("#a8b3ad"), 1))
        painter.drawRect(QRectF(left, plinth_top, right - left, ground_y - plinth_top))
        painter.setPen(QColor("#52635d"))
        painter.drawText(QPointF(left + 8, plinth_top + 18), "цоколь")

    def _draw_walls_and_floors(self, painter: QPainter, left: float, right: float, plinth_top: float, wall_top: float, scale: float) -> None:
        painter.setBrush(QColor("#eef1ed"))
        painter.setPen(QPen(QColor("#344047"), 2))
        painter.drawRect(QRectF(left, wall_top, right - left, plinth_top - wall_top))

        first_top = plinth_top - self.project.floor_1_height * scale
        painter.setPen(QPen(QColor("#899791"), 1, Qt.DashLine))
        painter.drawLine(QPointF(left, first_top), QPointF(right, first_top))
        painter.setPen(QColor("#52635d"))
        painter.drawText(QPointF(left + 8, first_top - 8), "1 этаж")

        if self.project.floor_mode in ("2 этажа", "1 этаж + мансарда"):
            slab_top = first_top - self.project.slab_height * scale
            painter.setPen(QPen(QColor("#6c7a73"), 4))
            painter.drawLine(QPointF(left, slab_top), QPointF(right, slab_top))
            painter.setPen(QColor("#52635d"))
            painter.setFont(QFont("Arial", 9))
            painter.drawText(QPointF(left + 8, slab_top - 8), "перекрытие")
            label = "2 этаж" if self.project.floor_mode == "2 этажа" else "мансарда"
            painter.drawText(QPointF(left + 8, wall_top + 20), label)

    def _draw_roof(self, painter: QPainter, left: float, right: float, wall_top: float, ridge_y: float, center_x: float) -> None:
        roof_type = self.project.roof_type
        overhang = self.project.roof_overhang * (right - left) / max(1.0, self.project.roof_span_width_m())
        roof_left = left - overhang
        roof_right = right + overhang
        painter.setPen(QPen(QColor("#7a4e25"), 2))
        painter.setBrush(QBrush(QColor(184, 125, 63, 155)))

        if roof_type == "Плоская":
            painter.drawRect(QRectF(roof_left, wall_top - 14, roof_right - roof_left, 14))
            return
        if roof_type == "Односкатная":
            painter.drawPolygon(QPolygonF([QPointF(roof_left, wall_top), QPointF(roof_right, ridge_y), QPointF(roof_right, ridge_y + 12), QPointF(roof_left, wall_top + 12)]))
            return

        painter.drawPolygon(QPolygonF([QPointF(roof_left, wall_top), QPointF(center_x, ridge_y), QPointF(roof_right, wall_top)]))
        painter.setPen(QPen(QColor("#50321a"), 4))
        painter.drawPoint(QPointF(center_x, ridge_y))
        painter.setPen(QColor("#50321a"))
        painter.setFont(QFont("Arial", 9, QFont.Bold))
        painter.drawText(QPointF(center_x + 8, ridge_y + 18), f"конёк {self.project.roof_ridge_height:.1f} м")

        if roof_type in ("Двускатная", "Полувальмовая", "Мансардная"):
            painter.setPen(QPen(QColor("#9c5f28"), 2))
            painter.drawLine(QPointF(roof_left, wall_top), QPointF(left, wall_top))
            painter.drawLine(QPointF(roof_right, wall_top), QPointF(right, wall_top))

    def _draw_stairs(self, painter: QPainter, left: float, right: float, plinth_top: float, scale: float) -> None:
        if not self.project.all_stairs() or self.project.floor_mode != "2 этажа":
            return
        stair = self.project.all_stairs()[0]
        stair_left = left + (right - left) * 0.18
        stair_right = stair_left + max(1.8, stair.length) * scale * 0.52
        stair_bottom = plinth_top - 0.12 * scale
        stair_top = plinth_top - (self.project.floor_1_height + self.project.slab_height) * scale
        painter.setPen(QPen(QColor("#8b5a2b"), 2))
        painter.setBrush(QColor(225, 185, 126, 95))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(stair_left, stair_bottom),
                    QPointF(stair_right, stair_top),
                    QPointF(stair_right, stair_top + 12),
                    QPointF(stair_left, stair_bottom + 12),
                ]
            )
        )
        steps = max(4, min(22, stair.steps))
        for index in range(steps + 1):
            t = index / steps
            x = stair_left + (stair_right - stair_left) * t
            y = stair_bottom + (stair_top - stair_bottom) * t
            painter.drawLine(QPointF(x, y), QPointF(x + 18, y))
        painter.setPen(QColor("#4f3320"))
        painter.setFont(QFont("Arial", 9, QFont.Bold))
        painter.drawText(QPointF(stair_left, stair_top - 10), f"лестница: {stair.stair_type}")

    def _draw_dimensions(self, painter: QPainter, right: float, ground_y: float, plinth_top: float, wall_top: float, ridge_y: float, scale: float) -> None:
        x = right + 34
        painter.setPen(QPen(QColor("#4d6258"), 1))
        painter.drawLine(QPointF(x, ground_y), QPointF(x, ridge_y))
        first_top = plinth_top - self.project.floor_1_height * scale
        slab_top = first_top - self.project.slab_height * scale
        ticks = [ground_y, plinth_top, first_top, wall_top, ridge_y]
        if self.project.floor_mode == "2 этажа":
            ticks.insert(3, slab_top)
        for y in ticks:
            painter.drawLine(QPointF(x - 6, y), QPointF(x + 6, y))
        painter.setFont(QFont("Arial", 9))
        painter.drawText(QPointF(x + 10, (ground_y + plinth_top) / 2), f"цоколь {self.project.plinth_height:.1f} м")
        painter.drawText(QPointF(x + 10, (plinth_top + first_top) / 2), f"1 этаж {self.project.floor_1_height:.1f} м")
        if self.project.floor_mode == "2 этажа":
            painter.drawText(QPointF(x + 10, (first_top + slab_top) / 2), f"перекрытие {self.project.slab_height:.1f} м")
            painter.drawText(QPointF(x + 10, (slab_top + wall_top) / 2), f"2 этаж {self.project.floor_2_height:.1f} м")
        if self.project.roof_type != "Плоская":
            painter.drawText(QPointF(x + 10, (wall_top + ridge_y) / 2), f"конёк {self.project.roof_ridge_height:.1f} м")
        total_height = self.project.plinth_height + self.project.total_wall_height_m() + max(0.0, self.project.roof_ridge_height)
        painter.setFont(QFont("Arial", 9, QFont.Bold))
        painter.drawText(QPointF(x + 10, ridge_y - 8), f"общая {total_height:.1f} м")
