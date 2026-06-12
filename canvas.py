from __future__ import annotations

from math import atan2, hypot

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from models import DoorItem, PIXELS_PER_METER, Point, Project, Wall, WindowItem


class PlanCanvas(QWidget):
    project_changed = Signal()
    selection_changed = Signal(str, int)

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.tool = "select"
        self.grid_size = 20
        self.selected_kind = "project"
        self.selected_index = -1
        self.hover_wall = -1
        self.hover_ratio = 0.5
        self.door_template: dict[str, object] = {}
        self.window_template: dict[str, object] = {}
        self._draft_start: QPointF | None = None
        self._draft_end: QPointF | None = None
        self._last_mouse_pos: QPointF | None = None
        self.setMinimumSize(720, 520)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_project(self, project: Project) -> None:
        self.project = project
        self._select("project", -1)
        self.update()
        self.project_changed.emit()

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self._draft_start = None
        self._draft_end = None
        if tool == "roof":
            self.project.show_roof = True
            self._select("project", -1)
            self.project_changed.emit()
        self.update()

    def set_door_template(self, template: dict[str, object]) -> None:
        self.door_template = dict(template)

    def set_window_template(self, template: dict[str, object]) -> None:
        self.window_template = dict(template)

    def delete_selected_element(self) -> None:
        if self.selected_kind == "wall" and self.selected_index >= 0:
            self._delete_wall(self.selected_index)
        elif self.selected_kind == "door" and self.selected_index >= 0:
            del self.project.doors[self.selected_index]
            self._select("project", -1)
        elif self.selected_kind == "window" and self.selected_index >= 0:
            del self.project.windows[self.selected_index]
            self._select("project", -1)
        else:
            return
        self.project_changed.emit()
        self.update()

    def delete_selected_wall(self) -> None:
        # Метод оставлен для совместимости со старым интерфейсом.
        if self.selected_kind == "wall":
            self.delete_selected_element()

    def resize_selected_wall(self, length_m: float) -> None:
        if self.selected_kind != "wall" or self.selected_index < 0 or length_m <= 0:
            return
        wall = self.project.walls[self.selected_index]
        dx = wall.end.x - wall.start.x
        dy = wall.end.y - wall.start.y
        current = hypot(dx, dy)
        if current == 0:
            wall.end.x = wall.start.x + length_m * PIXELS_PER_METER
        else:
            scale = length_m * PIXELS_PER_METER / current
            wall.end.x = wall.start.x + dx * scale
            wall.end.y = wall.start.y + dy * scale
        self.project_changed.emit()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fbfbf8"))
        self._draw_grid(painter)
        self._draw_walls(painter)
        self._draw_windows(painter)
        self._draw_doors(painter)
        self._draw_roof_overlay(painter)
        self._draw_draft(painter)
        self._draw_hover_preview(painter)
        self._draw_hint(painter)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        pos = self._snap(event.position())
        if event.button() != Qt.LeftButton:
            return
        self.setFocus()

        if self.tool == "wall":
            self._draft_start = pos
            self._draft_end = pos
        elif self.tool == "door":
            index, ratio = self._wall_at(pos)
            if index >= 0:
                self.project.doors.append(self._door_from_template(index, ratio))
                self._select("door", len(self.project.doors) - 1)
                self.project_changed.emit()
                self.update()
        elif self.tool == "window":
            index, ratio = self._wall_at(pos)
            if index >= 0:
                self.project.windows.append(self._window_from_template(index, ratio))
                self._select("window", len(self.project.windows) - 1)
                self.project_changed.emit()
                self.update()
        else:
            kind, index = self._element_at(pos)
            self._select(kind, index)
            self._last_mouse_pos = pos if kind == "wall" else None
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        pos = self._snap(event.position())
        if self.tool == "wall" and self._draft_start is not None:
            self._draft_end = pos
            self.update()
            return

        if self.tool in ("door", "window"):
            self.hover_wall, self.hover_ratio = self._wall_at(pos)
            self.update()
            return

        if self.tool == "select" and self.selected_kind == "wall" and self.selected_index >= 0 and self._last_mouse_pos is not None:
            if event.buttons() & Qt.LeftButton:
                dx = pos.x() - self._last_mouse_pos.x()
                dy = pos.y() - self._last_mouse_pos.y()
                self.project.walls[self.selected_index].move(dx, dy)
                self._last_mouse_pos = pos
                self.project_changed.emit()
                self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.tool == "wall" and self._draft_start is not None and self._draft_end is not None:
            if hypot(self._draft_end.x() - self._draft_start.x(), self._draft_end.y() - self._draft_start.y()) >= 20:
                wall = Wall(
                    Point(self._draft_start.x(), self._draft_start.y()),
                    Point(self._draft_end.x(), self._draft_end.y()),
                    height=self.project.wall_height,
                    material=self.project.wall_material,
                )
                self.project.walls.append(wall)
                self._select("wall", len(self.project.walls) - 1)
                self.project_changed.emit()
            self._draft_start = None
            self._draft_end = None
            self.update()
        self._last_mouse_pos = None

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected_element()

    def _select(self, kind: str, index: int) -> None:
        self.selected_kind = kind
        self.selected_index = index
        self.selection_changed.emit(kind, index)

    def _delete_wall(self, wall_index: int) -> None:
        del self.project.walls[wall_index]
        self.project.doors = [door for door in self.project.doors if door.wall_index != wall_index]
        self.project.windows = [window for window in self.project.windows if window.wall_index != wall_index]
        for door in self.project.doors:
            if door.wall_index > wall_index:
                door.wall_index -= 1
        for window in self.project.windows:
            if window.wall_index > wall_index:
                window.wall_index -= 1
        self._select("project", -1)

    def _draw_grid(self, painter: QPainter) -> None:
        thin = QPen(QColor("#e7e2d7"), 1)
        thick = QPen(QColor("#d2c8b8"), 1)
        for x in range(0, self.width(), self.grid_size):
            painter.setPen(thick if x % 100 == 0 else thin)
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), self.grid_size):
            painter.setPen(thick if y % 100 == 0 else thin)
            painter.drawLine(0, y, self.width(), y)

    def _draw_walls(self, painter: QPainter) -> None:
        for index, wall in enumerate(self.project.walls):
            color = QColor("#1f2427")
            if self.selected_kind == "wall" and index == self.selected_index:
                color = QColor("#197a68")
            thickness_px = max(6, min(32, wall.thickness * PIXELS_PER_METER))
            if self.selected_kind == "wall" and index == self.selected_index:
                thickness_px += 2
            painter.setPen(QPen(color, thickness_px, Qt.SolidLine, Qt.RoundCap))
            for start_ratio, end_ratio in self._wall_visible_spans(index):
                start = self._point_on_wall(wall, start_ratio)
                end = self._point_on_wall(wall, end_ratio)
                painter.drawLine(start, end)

            mid = self._point_on_wall(wall, 0.5)
            painter.setPen(QPen(QColor("#1f2a2e"), 1))
            painter.setFont(QFont("Arial", 9))
            painter.drawText(mid + QPointF(8, -8), f"{wall.length_m:.1f} м")

    def _draw_doors(self, painter: QPainter) -> None:
        for index, door in enumerate(self.project.doors):
            if door.wall_index >= len(self.project.walls):
                continue
            selected = self.selected_kind == "door" and index == self.selected_index
            self._draw_door_symbol(painter, self.project.walls[door.wall_index], door, selected)

    def _draw_windows(self, painter: QPainter) -> None:
        for index, window in enumerate(self.project.windows):
            if window.wall_index >= len(self.project.walls):
                continue
            selected = self.selected_kind == "window" and index == self.selected_index
            self._draw_window_symbol(painter, self.project.walls[window.wall_index], window, selected)

    def _draw_door_symbol(self, painter: QPainter, wall: Wall, door: DoorItem, selected: bool) -> None:
        center, tangent, normal = self._wall_basis(wall, door.position)
        width_px = door.width * PIXELS_PER_METER
        left = center - tangent * (width_px / 2)
        right = center + tangent * (width_px / 2)
        hinge = left if door.hinge_side == "Левая" else right
        closed_end = right if door.hinge_side == "Левая" else left
        open_normal = normal if door.opening_direction == "Внутрь" else -normal
        open_end = hinge + open_normal * width_px

        door_color = QColor("#cf7628")
        painter.setPen(QPen(door_color, 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(hinge, open_end)

        path = QPainterPath()
        path.moveTo(closed_end)
        path.quadTo(hinge + (closed_end - hinge + open_end - hinge) * 0.72, open_end)
        painter.setPen(QPen(door_color, 3))
        painter.drawPath(path)

        painter.setBrush(door_color)
        painter.drawEllipse(hinge, 4, 4)

        if selected:
            painter.setPen(QPen(QColor("#ffb35c"), 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(center.x() - width_px / 2 - 8, center.y() - width_px / 2 - 8, width_px + 16, width_px + 16))

    def _draw_window_symbol(self, painter: QPainter, wall: Wall, window: WindowItem, selected: bool) -> None:
        center, tangent, normal = self._wall_basis(wall, window.position)
        width_px = window.width * PIXELS_PER_METER
        half = width_px / 2
        blue = QColor("#1f8fce")
        painter.setPen(QPen(blue, 4, Qt.SolidLine, Qt.RoundCap))
        for offset in (-3, 3):
            start = center - tangent * half + normal * offset
            end = center + tangent * half + normal * offset
            painter.drawLine(start, end)

        if selected:
            painter.setPen(QPen(QColor("#4ab3e8"), 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(center.x() - half - 7, center.y() - 14, width_px + 14, 28))

    def _draw_draft(self, painter: QPainter) -> None:
        if self._draft_start is None or self._draft_end is None:
            return
        painter.setPen(QPen(QColor("#5a8f7b"), 4, Qt.DashLine, Qt.RoundCap))
        painter.drawLine(self._draft_start, self._draft_end)
        length_m = self._distance(self._draft_start, self._draft_end) / PIXELS_PER_METER
        mid = QPointF((self._draft_start.x() + self._draft_end.x()) / 2, (self._draft_start.y() + self._draft_end.y()) / 2)
        text = f"{length_m:.1f} м"
        text_rect = QRectF(mid.x() + 10, mid.y() - 28, 64, 24)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.drawRoundedRect(text_rect, 5, 5)
        painter.setPen(QPen(QColor("#17483f"), 1))
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.drawText(text_rect, Qt.AlignCenter, text)

    def _draw_roof_overlay(self, painter: QPainter) -> None:
        if not self.project.show_roof or not self.project.walls:
            return
        roof_points = self._roof_polygon_points()
        if len(roof_points) < 3:
            return

        polygon = QPolygonF(roof_points)
        painter.setPen(QPen(QColor(118, 83, 41, 190), 2, Qt.DashLine))
        painter.setBrush(QBrush(QColor(184, 125, 63, 55)))
        painter.drawPolygon(polygon)

        roof_type = self.project.roof_type
        left = min(point.x() for point in roof_points)
        right = max(point.x() for point in roof_points)
        top = min(point.y() for point in roof_points)
        bottom = max(point.y() for point in roof_points)
        center_x = (left + right) / 2
        center_y = (top + bottom) / 2
        painter.setPen(QPen(QColor(136, 76, 28, 210), 2))

        if roof_type in ("Двускатная", "Полувальмовая", "Мансардная"):
            if self.project.roof_ridge_direction == "по Y":
                painter.drawLine(QPointF(center_x, top + 12), QPointF(center_x, bottom - 12))
            else:
                painter.drawLine(QPointF(left + 12, center_y), QPointF(right - 12, center_y))
            if roof_type == "Мансардная":
                painter.setPen(QPen(QColor(136, 76, 28, 150), 1, Qt.DashLine))
                painter.drawLine(QPointF(left + 18, center_y - 18), QPointF(right - 18, center_y - 18))
                painter.drawLine(QPointF(left + 18, center_y + 18), QPointF(right - 18, center_y + 18))
        elif roof_type == "Односкатная":
            if self.project.roof_ridge_direction == "по Y":
                start = QPointF(left + 18, center_y)
                end = QPointF(right - 18, center_y)
            else:
                start = QPointF(center_x, bottom - 18)
                end = QPointF(center_x, top + 18)
            painter.drawLine(start, end)
            painter.drawLine(end, QPointF(end.x() - 18, end.y() + 2))
            painter.drawLine(end, QPointF(end.x() - 4, end.y() + 18))
        elif roof_type in ("Вальмовая", "Шатровая"):
            if self.project.roof_ridge_direction == "по Y":
                ridge_a = QPointF(center_x, top + 22)
                ridge_b = QPointF(center_x, bottom - 22)
            else:
                ridge_a = QPointF(left + 22, center_y)
                ridge_b = QPointF(right - 22, center_y)
            if roof_type == "Вальмовая":
                painter.drawLine(ridge_a, ridge_b)
                targets = (ridge_a, ridge_b)
            else:
                targets = (QPointF(center_x, center_y),)
            for corner in (QPointF(left, top), QPointF(right, top), QPointF(right, bottom), QPointF(left, bottom)):
                target = min(targets, key=lambda item: self._distance(corner, item))
                painter.drawLine(corner, target)

    def _draw_hover_preview(self, painter: QPainter) -> None:
        if self.tool not in ("door", "window") or self.hover_wall < 0:
            return
        wall = self.project.walls[self.hover_wall]
        if self.tool == "door":
            preview = self._door_from_template(self.hover_wall, self.hover_ratio)
            self._draw_door_symbol(painter, wall, preview, True)
        else:
            preview = self._window_from_template(self.hover_wall, self.hover_ratio)
            self._draw_window_symbol(painter, wall, preview, True)

    def _door_from_template(self, wall_index: int, ratio: float) -> DoorItem:
        wall = self.project.walls[wall_index]
        return DoorItem(
            wall_index=wall_index,
            position=ratio,
            width=float(self.door_template.get("width", 0.9) or 0.9),
            height=float(self.door_template.get("height", 2.1) or 2.1),
            opening_direction=str(self.door_template.get("opening_direction", "Внутрь")),
            hinge_side=str(self.door_template.get("hinge_side", "Левая")),
            price=float(self.door_template.get("price", 28000) or 0),
            template_name=str(self.door_template.get("template_name", "Свой размер")),
            distance_from_start=ratio * wall.length_m,
        )

    def _window_from_template(self, wall_index: int, ratio: float) -> WindowItem:
        wall = self.project.walls[wall_index]
        return WindowItem(
            wall_index=wall_index,
            position=ratio,
            width=float(self.window_template.get("width", 1.2) or 1.2),
            height=float(self.window_template.get("height", 1.4) or 1.4),
            install_height=float(self.window_template.get("sill_height", self.window_template.get("install_height", 0.9)) or 0.9),
            glass_type=str(self.window_template.get("glass_type", "двухкамерный")),
            price=float(self.window_template.get("price", 18000) or 0),
            price_per_m2=float(self.window_template.get("price_per_m2", 0) or 0),
            template_name=str(self.window_template.get("template_name", "Свой размер")),
            distance_from_start=ratio * wall.length_m,
            count=1,
        )

    def _draw_hint(self, painter: QPainter) -> None:
        painter.setPen(QColor("#5f6f78"))
        painter.setFont(QFont("Arial", 10))
        text = "Сетка: 1 м = 40 px. Стены привязаны к шагу 0,5 м."
        painter.drawText(QRectF(12, self.height() - 32, self.width() - 24, 24), Qt.AlignLeft, text)

    def _wall_visible_spans(self, wall_index: int) -> list[tuple[float, float]]:
        wall = self.project.walls[wall_index]
        if wall.length_m <= 0:
            return []

        gaps: list[tuple[float, float]] = []
        for door in self.project.doors:
            if door.wall_index == wall_index:
                half_ratio = door.width / wall.length_m / 2
                gaps.append((door.position - half_ratio, door.position + half_ratio))
        for window in self.project.windows:
            if window.wall_index == wall_index:
                half_ratio = window.width / wall.length_m / 2
                gaps.append((window.position - half_ratio, window.position + half_ratio))

        spans: list[tuple[float, float]] = []
        cursor = 0.0
        for start, end in sorted((max(0.0, a), min(1.0, b)) for a, b in gaps):
            if start > cursor:
                spans.append((cursor, start))
            cursor = max(cursor, end)
        if cursor < 1.0:
            spans.append((cursor, 1.0))
        return spans

    def _element_at(self, pos: QPointF) -> tuple[str, int]:
        for index, door in enumerate(self.project.doors):
            if door.wall_index < len(self.project.walls):
                center = self._point_on_wall(self.project.walls[door.wall_index], door.position)
                if self._distance(pos, center) <= max(16, door.width * PIXELS_PER_METER):
                    return "door", index
        for index, window in enumerate(self.project.windows):
            if window.wall_index < len(self.project.walls):
                center = self._point_on_wall(self.project.walls[window.wall_index], window.position)
                if self._distance(pos, center) <= max(16, window.width * PIXELS_PER_METER / 2):
                    return "window", index

        wall_index, _ = self._wall_at(pos)
        if wall_index >= 0:
            return "wall", wall_index
        return "project", -1

    def _snap(self, pos: QPointF) -> QPointF:
        return QPointF(round(pos.x() / self.grid_size) * self.grid_size, round(pos.y() / self.grid_size) * self.grid_size)

    def _roof_polygon_points(self) -> list[QPointF]:
        points: list[QPointF] = []
        seen: set[tuple[float, float]] = set()
        for wall in self.project.walls:
            for point in (wall.start, wall.end):
                key = (round(point.x, 3), round(point.y, 3))
                if key not in seen:
                    points.append(QPointF(point.x, point.y))
                    seen.add(key)
        if len(points) < 3:
            return []

        center_x = sum(point.x() for point in points) / len(points)
        center_y = sum(point.y() for point in points) / len(points)
        center = QPointF(center_x, center_y)
        ordered = sorted(points, key=lambda point: atan2(point.y() - center_y, point.x() - center_x))
        overhang_px = self.project.roof_overhang * PIXELS_PER_METER
        expanded: list[QPointF] = []
        for point in ordered:
            dx = point.x() - center.x()
            dy = point.y() - center.y()
            length = hypot(dx, dy) or 1
            expanded.append(QPointF(point.x() + dx / length * overhang_px, point.y() + dy / length * overhang_px))
        return expanded

    def _wall_at(self, pos: QPointF) -> tuple[int, float]:
        best_index = -1
        best_distance = 14.0
        best_ratio = 0.5
        for index, wall in enumerate(self.project.walls):
            distance, ratio = self._point_to_segment_distance(pos, wall)
            if distance < best_distance:
                best_index = index
                best_distance = distance
                best_ratio = ratio
        return best_index, best_ratio

    def _wall_basis(self, wall: Wall, ratio: float) -> tuple[QPointF, QPointF, QPointF]:
        center = self._point_on_wall(wall, ratio)
        dx = wall.end.x - wall.start.x
        dy = wall.end.y - wall.start.y
        length = hypot(dx, dy) or 1
        tangent = QPointF(dx / length, dy / length)
        normal = QPointF(-tangent.y(), tangent.x())
        return center, tangent, normal

    @staticmethod
    def _point_on_wall(wall: Wall, ratio: float) -> QPointF:
        return QPointF(
            wall.start.x + (wall.end.x - wall.start.x) * ratio,
            wall.start.y + (wall.end.y - wall.start.y) * ratio,
        )

    @staticmethod
    def _point_to_segment_distance(pos: QPointF, wall: Wall) -> tuple[float, float]:
        ax, ay = wall.start.x, wall.start.y
        bx, by = wall.end.x, wall.end.y
        px, py = pos.x(), pos.y()
        dx = bx - ax
        dy = by - ay
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            return hypot(px - ax, py - ay), 0.0
        ratio = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
        nearest_x = ax + ratio * dx
        nearest_y = ay + ratio * dy
        return hypot(px - nearest_x, py - nearest_y), ratio

    @staticmethod
    def _distance(a: QPointF, b: QPointF) -> float:
        return hypot(a.x() - b.x(), a.y() - b.y())


class RoofPreviewWidget(QWidget):
    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.setMinimumHeight(210)

    def set_project(self, project: Project) -> None:
        self.project = project
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f8faf7"))

        if not self.project.walls:
            painter.setPen(QColor("#6b7872"))
            painter.drawText(self.rect(), Qt.AlignCenter, "3D-просмотр крыши появится после стен")
            return

        width_m, depth_m = self.project.footprint_bounds_m()
        width_m = max(1.0, width_m + self.project.roof_overhang * 2)
        depth_m = max(1.0, depth_m + self.project.roof_overhang * 2)
        scale = min((self.width() - 60) / (width_m + depth_m), (self.height() - 40) / (width_m * 0.25 + depth_m * 0.25 + self.project.roof_ridge_height + 2))
        scale = max(18, min(48, scale))
        origin = QPointF(self.width() / 2, self.height() * 0.72)

        def iso(x: float, y: float, z: float = 0.0) -> QPointF:
            return QPointF(origin.x() + (x - y) * scale, origin.y() + (x + y) * scale * 0.42 - z * scale)

        x0, x1 = -width_m / 2, width_m / 2
        y0, y1 = -depth_m / 2, depth_m / 2
        h = max(0.1, self.project.roof_ridge_height)
        base = [iso(x0, y0), iso(x1, y0), iso(x1, y1), iso(x0, y1)]

        painter.setPen(QPen(QColor("#8a6a45"), 1))
        roof_pen = QPen(QColor("#7a4e25"), 2)
        painter.setPen(roof_pen)

        if self.project.roof_type == "Плоская":
            self._draw_face(painter, base, QColor(165, 112, 69, 160))
        elif self.project.roof_type == "Односкатная":
            if self.project.roof_ridge_direction == "по Y":
                pts = [iso(x0, y0, 0), iso(x1, y0, h), iso(x1, y1, h), iso(x0, y1, 0)]
            else:
                pts = [iso(x0, y0, h), iso(x1, y0, h), iso(x1, y1, 0), iso(x0, y1, 0)]
            self._draw_face(painter, pts, QColor(184, 125, 63, 175))
        elif self.project.roof_type in ("Двускатная", "Полувальмовая", "Мансардная"):
            if self.project.roof_ridge_direction == "по Y":
                ridge_a, ridge_b = iso(0, y0, h), iso(0, y1, h)
                self._draw_face(painter, [iso(x0, y0), ridge_a, ridge_b, iso(x0, y1)], QColor(184, 125, 63, 180))
                self._draw_face(painter, [ridge_a, iso(x1, y0), iso(x1, y1), ridge_b], QColor(151, 93, 45, 185))
            else:
                ridge_a, ridge_b = iso(x0, 0, h), iso(x1, 0, h)
                self._draw_face(painter, [iso(x0, y0), iso(x1, y0), ridge_b, ridge_a], QColor(184, 125, 63, 180))
                self._draw_face(painter, [ridge_a, ridge_b, iso(x1, y1), iso(x0, y1)], QColor(151, 93, 45, 185))
            painter.setPen(QPen(QColor("#5f391c"), 2))
            painter.drawLine(ridge_a, ridge_b)
        else:
            top = iso(0, 0, h)
            faces = [
                [iso(x0, y0), iso(x1, y0), top],
                [iso(x1, y0), iso(x1, y1), top],
                [iso(x1, y1), iso(x0, y1), top],
                [iso(x0, y1), iso(x0, y0), top],
            ]
            colors = [QColor(184, 125, 63, 180), QColor(166, 105, 52, 180), QColor(145, 86, 41, 180), QColor(196, 139, 78, 170)]
            for face, color in zip(faces, colors):
                self._draw_face(painter, face, color)

        painter.setPen(QColor("#31413a"))
        painter.setFont(QFont("Arial", 9))
        painter.drawText(12, 22, f"3D: {self.project.roof_type}, {self.project.roof_ridge_direction}")

    def _draw_face(self, painter: QPainter, points: list[QPointF], color: QColor) -> None:
        painter.setBrush(QBrush(color))
        painter.drawPolygon(QPolygonF(points))
