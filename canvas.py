from __future__ import annotations

from math import atan2, cos, hypot, sin

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from models import DoorItem, PIXELS_PER_METER, Point, Project, RoomItem, StairItem, Wall, WindowItem


class PlanCanvas(QWidget):
    project_changed = Signal()
    selection_changed = Signal(str, int)
    room_place_requested = Signal(float, float, int)

    def __init__(self, project: Project, floor_level: int = 1) -> None:
        super().__init__()
        self.project = project
        self.floor_level = floor_level
        self.tool = "select"
        self.grid_size = 20
        self.selected_kind = "project"
        self.selected_index = -1
        self.hover_wall = -1
        self.hover_ratio = 0.5
        self.view_scale = 1.0
        self.view_offset = QPointF(0, 0)
        self.door_template: dict[str, object] = {}
        self.window_template: dict[str, object] = {}
        self.stair_template: dict[str, object] = {
            "stair_type": "Прямая",
            "width": 0.9,
            "length": 3.0,
            "rise_height": 3.1,
            "steps": 16,
            "price": 120000.0,
        }
        self._draft_start: QPointF | None = None
        self._draft_end: QPointF | None = None
        self._last_mouse_pos: QPointF | None = None
        self._panning = False
        self._last_pan_pos: QPointF | None = None
        self.setMinimumSize(720, 520)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def current_floor(self):
        return self.project.get_floor(self.floor_level)

    def set_floor_level(self, level: int) -> None:
        self.floor_level = level
        self._select("project", -1)
        self.update()

    def set_project(self, project: Project) -> None:
        self.project = project
        self.project.ensure_floor_count(max(1, self.floor_level))
        self._select("project", -1)
        self.fit_project_to_view()
        self.update()
        self.project_changed.emit()

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self._draft_start = None
        self._draft_end = None
        if tool == "roof":
            self.project.show_roof = True
            self._select("roof", -1)
            self.project_changed.emit()
        self.update()

    def set_door_template(self, template: dict[str, object]) -> None:
        self.door_template = dict(template)

    def set_window_template(self, template: dict[str, object]) -> None:
        self.window_template = dict(template)

    def set_stair_template(self, template: dict[str, object]) -> None:
        self.stair_template = dict(template)

    def fit_project_to_view(self) -> None:
        bounds = self._project_bounds()
        if bounds is None or bounds.width() <= 0 or bounds.height() <= 0:
            self.view_scale = 1.0
            self.view_offset = QPointF(self.width() * 0.12, self.height() * 0.12)
            self.update()
            return

        target_w = max(1.0, self.width() * 0.82)
        target_h = max(1.0, self.height() * 0.82)
        scale = min(target_w / bounds.width(), target_h / bounds.height())
        self.view_scale = max(0.25, min(5.0, scale))
        center = bounds.center()
        self.view_offset = QPointF(
            self.width() / 2 - center.x() * self.view_scale,
            self.height() / 2 - center.y() * self.view_scale,
        )
        self.update()

    def delete_selected_element(self) -> None:
        floor = self.current_floor()
        if self.selected_kind == "wall" and self.selected_index >= 0:
            self._delete_wall(self.selected_index)
        elif self.selected_kind == "door" and self.selected_index >= 0:
            del floor.doors[self.selected_index]
            self.project._sync_legacy_lists()
            self._select("project", -1)
        elif self.selected_kind == "window" and self.selected_index >= 0:
            del floor.windows[self.selected_index]
            self.project._sync_legacy_lists()
            self._select("project", -1)
        elif self.selected_kind == "room" and self.selected_index >= 0:
            del floor.rooms[self.selected_index]
            self._select("project", -1)
        elif self.selected_kind == "stair" and self.selected_index >= 0:
            del floor.stairs[self.selected_index]
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
        wall = self.current_floor().walls[self.selected_index]
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
        painter.save()
        painter.translate(self.view_offset)
        painter.scale(self.view_scale, self.view_scale)
        self._draw_grid(painter)
        if self.project.show_rooms:
            self._draw_rooms(painter)
        self._draw_walls(painter)
        self._draw_stairs(painter)
        if self.project.show_windows:
            self._draw_windows(painter)
        if self.project.show_doors:
            self._draw_doors(painter)
        self._draw_roof_overlay(painter)
        self._draw_draft(painter)
        self._draw_hover_preview(painter)
        painter.restore()
        self._draw_hint(painter)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._last_pan_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            return

        pos = self._snap(self._screen_to_world(event.position()))
        floor = self.current_floor()
        if event.button() != Qt.LeftButton:
            return
        self.setFocus()

        if self.tool == "wall":
            self._draft_start = pos
            self._draft_end = pos
        elif self.tool == "door":
            index, ratio = self._wall_at(pos)
            if index >= 0:
                floor.doors.append(self._door_from_template(index, ratio))
                self.project._sync_legacy_lists()
                self._select("door", len(floor.doors) - 1)
                self.project_changed.emit()
                self.update()
        elif self.tool == "window":
            index, ratio = self._wall_at(pos)
            if index >= 0:
                floor.windows.append(self._window_from_template(index, ratio))
                self.project._sync_legacy_lists()
                self._select("window", len(floor.windows) - 1)
                self.project_changed.emit()
                self.update()
        elif self.tool == "stair":
            floor.stairs.append(self._stair_from_template(pos))
            self._select("stair", len(floor.stairs) - 1)
            self.project_changed.emit()
            self.update()
        elif self.tool == "room":
            self.room_place_requested.emit(pos.x(), pos.y(), self.floor_level)
        elif self.tool == "roof":
            self.project.show_roof = True
            self._select("roof", -1)
            self.project_changed.emit()
            self.update()
        else:
            kind, index = self._element_at(pos)
            self._select(kind, index)
            self._last_mouse_pos = pos if kind == "wall" else None
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._panning and self._last_pan_pos is not None:
            delta = event.position() - self._last_pan_pos
            self.view_offset += delta
            self._last_pan_pos = event.position()
            self.update()
            return

        pos = self._snap(self._screen_to_world(event.position()))
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
                self.current_floor().walls[self.selected_index].move(dx, dy)
                self._last_mouse_pos = pos
                self.project_changed.emit()
                self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MiddleButton:
            self._panning = False
            self._last_pan_pos = None
            self.unsetCursor()
            return

        if self.tool == "wall" and self._draft_start is not None and self._draft_end is not None:
            if hypot(self._draft_end.x() - self._draft_start.x(), self._draft_end.y() - self._draft_start.y()) >= 20:
                floor_height = self.project.floor_2_height if self.floor_level == 2 else self.project.floor_1_height
                wall = Wall(
                    Point(self._draft_start.x(), self._draft_start.y()),
                    Point(self._draft_end.x(), self._draft_end.y()),
                    height=floor_height,
                    material=self.project.wall_material,
                )
                self.current_floor().walls.append(wall)
                self.project._sync_legacy_lists()
                self._select("wall", len(self.current_floor().walls) - 1)
                self.project_changed.emit()
            self._draft_start = None
            self._draft_end = None
            self.update()
        self._last_mouse_pos = None

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MiddleButton:
            self.fit_project_to_view()

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API
        cursor = event.position()
        before = self._screen_to_world(cursor)
        factor = 1.0018 ** event.angleDelta().y()
        self.view_scale = max(0.2, min(6.0, self.view_scale * factor))
        self.view_offset = QPointF(cursor.x() - before.x() * self.view_scale, cursor.y() - before.y() * self.view_scale)
        self.update()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected_element()

    def _select(self, kind: str, index: int) -> None:
        self.selected_kind = kind
        self.selected_index = index
        self.selection_changed.emit(kind, index)

    def _delete_wall(self, wall_index: int) -> None:
        floor = self.current_floor()
        del floor.walls[wall_index]
        floor.doors = [door for door in floor.doors if door.wall_index != wall_index]
        floor.windows = [window for window in floor.windows if window.wall_index != wall_index]
        for door in floor.doors:
            if door.wall_index > wall_index:
                door.wall_index -= 1
        for window in floor.windows:
            if window.wall_index > wall_index:
                window.wall_index -= 1
        self.project._sync_legacy_lists()
        self._select("project", -1)

    def _draw_grid(self, painter: QPainter) -> None:
        thin = QPen(QColor("#e7e2d7"), 1)
        thick = QPen(QColor("#d2c8b8"), 1)
        top_left = self._screen_to_world(QPointF(0, 0))
        bottom_right = self._screen_to_world(QPointF(self.width(), self.height()))
        left = int(top_left.x() // self.grid_size * self.grid_size) - self.grid_size
        right = int(bottom_right.x() // self.grid_size * self.grid_size) + self.grid_size
        top = int(top_left.y() // self.grid_size * self.grid_size) - self.grid_size
        bottom = int(bottom_right.y() // self.grid_size * self.grid_size) + self.grid_size
        for x in range(left, right + 1, self.grid_size):
            painter.setPen(thick if x % 100 == 0 else thin)
            painter.drawLine(x, top, x, bottom)
        for y in range(top, bottom + 1, self.grid_size):
            painter.setPen(thick if y % 100 == 0 else thin)
            painter.drawLine(left, y, right, y)

    def _draw_walls(self, painter: QPainter) -> None:
        for index, wall in enumerate(self.current_floor().walls):
            color = QColor("#1f2427")
            if self.selected_kind == "wall" and index == self.selected_index:
                color = QColor("#d97a2b")
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
        floor = self.current_floor()
        for index, door in enumerate(floor.doors):
            if door.wall_index >= len(floor.walls):
                continue
            selected = self.selected_kind == "door" and index == self.selected_index
            self._draw_door_symbol(painter, floor.walls[door.wall_index], door, selected)

    def _draw_windows(self, painter: QPainter) -> None:
        floor = self.current_floor()
        for index, window in enumerate(floor.windows):
            if window.wall_index >= len(floor.walls):
                continue
            selected = self.selected_kind == "window" and index == self.selected_index
            self._draw_window_symbol(painter, floor.walls[window.wall_index], window, selected)

    def _draw_rooms(self, painter: QPainter) -> None:
        for index, room in enumerate(self.current_floor().rooms):
            selected = self.selected_kind == "room" and index == self.selected_index
            text = f"{room.name}\n{room.area:.1f} м²"
            rect = QRectF(room.center.x - 66, room.center.y - 25, 132, 50)
            painter.setPen(QPen(QColor("#5d8f77" if selected else "#9fb8aa"), 2 if selected else 1))
            painter.setBrush(QColor(209, 235, 223, 165 if selected else 105))
            painter.drawRoundedRect(rect, 10, 10)
            painter.setPen(QColor("#173b33"))
            painter.setFont(QFont("Arial", 9, QFont.Bold))
            painter.drawText(rect, Qt.AlignCenter, text)

    def _draw_stairs(self, painter: QPainter) -> None:
        for index, stair in enumerate(self.current_floor().stairs):
            selected = self.selected_kind == "stair" and index == self.selected_index
            x = stair.position.x
            y = stair.position.y
            width = max(28.0, stair.width * PIXELS_PER_METER)
            length = max(60.0, stair.length * PIXELS_PER_METER)
            rect = QRectF(x - width / 2, y - length / 2, width, length)
            painter.setPen(QPen(QColor("#8b5a2b" if not selected else "#2f9f72"), 2 if not selected else 4))
            painter.setBrush(QColor(225, 185, 126, 135 if not selected else 170))

            if stair.stair_type == "Г-образная":
                painter.drawRect(QRectF(rect.left(), rect.top(), width, length * 0.62))
                painter.drawRect(QRectF(rect.left(), rect.center().y(), width * 1.55, width))
            elif stair.stair_type == "П-образная":
                painter.drawRect(QRectF(rect.left(), rect.top(), width, length))
                painter.drawRect(QRectF(rect.left() + width * 1.15, rect.top(), width, length))
                painter.drawRect(QRectF(rect.left(), rect.center().y() - width / 2, width * 2.15, width))
            else:
                painter.drawRect(rect)

            steps = max(3, min(28, stair.steps))
            painter.setPen(QPen(QColor("#7a4b22"), 1))
            for step in range(1, steps):
                yy = rect.top() + rect.height() * step / steps
                painter.drawLine(QPointF(rect.left(), yy), QPointF(rect.right(), yy))
            self._draw_arrow(painter, QPointF(rect.center().x(), rect.bottom() - 8), QPointF(rect.center().x(), rect.top() + 8))
            painter.setPen(QColor("#3a2617"))
            painter.setFont(QFont("Arial", 8, QFont.Bold))
            painter.drawText(rect.adjusted(-40, -22, 40, 0), Qt.AlignHCenter | Qt.AlignTop, "Лестница")

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
            painter.setPen(QPen(QColor("#f28b38"), 3, Qt.DashLine))
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
            painter.setPen(QPen(QColor("#2aa6df"), 3, Qt.DashLine))
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
        if not self.project.show_roof or not self.project.get_floor(1).walls:
            return
        base_points = self._roof_base_polygon_points()
        roof_points = self._expanded_polygon_points(base_points, self.project.roof_overhang * PIXELS_PER_METER)
        if len(roof_points) < 3:
            return

        detail_mode = self.tool == "roof" or self.selected_kind == "roof"
        outline_width = 4 if detail_mode else 2
        ridge_width = 6 if detail_mode else 4
        polygon = QPolygonF(roof_points)

        # В обычном плане крыша не перекрывает помещения: видны только свес,
        # конёк, стрелки и размеры. Заливка включается только в режиме "Крыша".
        if detail_mode and self.project.show_roof_slopes:
            painter.setPen(QPen(QColor(118, 83, 41, 210), 1))
            painter.setBrush(QBrush(QColor(184, 125, 63, 58)))
            painter.drawPolygon(polygon)

        if self.project.show_roof_overhangs or detail_mode:
            painter.setPen(QPen(QColor(118, 83, 41, 230), outline_width, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(polygon)

        if detail_mode and self.project.show_roof_overhangs:
            # Внутренний контур помогает сравнить стены и свес только в режиме крыши.
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#5f6f78"), 1, Qt.DotLine))
            painter.drawPolygon(QPolygonF(base_points))

        roof_type = self.project.roof_type
        left = min(point.x() for point in roof_points)
        right = max(point.x() for point in roof_points)
        top = min(point.y() for point in roof_points)
        bottom = max(point.y() for point in roof_points)
        center_x = (left + right) / 2
        center_y = (top + bottom) / 2
        painter.setPen(QPen(QColor(136, 76, 28, 230), ridge_width, Qt.SolidLine, Qt.RoundCap))

        ridge_start: QPointF | None = None
        ridge_end: QPointF | None = None

        if roof_type in ("Двускатная", "Полувальмовая", "Мансардная"):
            if self.project.roof_ridge_direction == "по Y":
                ridge_start = QPointF(center_x, top + 18)
                ridge_end = QPointF(center_x, bottom - 18)
            else:
                ridge_start = QPointF(left + 18, center_y)
                ridge_end = QPointF(right - 18, center_y)
            if self.project.show_roof_ridge:
                painter.drawLine(ridge_start, ridge_end)
                if self.project.show_roof_dimensions:
                    self._draw_roof_ridge_labels(painter, ridge_start, ridge_end)
            if self.project.show_roof_slopes:
                self._draw_slope_arrows(painter, ridge_start, ridge_end, left, right, top, bottom)
            if detail_mode:
                self._draw_gables(painter, left, right, top, bottom)
            if roof_type == "Мансардная":
                if detail_mode:
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
            if self.project.show_roof_slopes:
                painter.setPen(QPen(QColor(136, 76, 28, 230), 3, Qt.SolidLine, Qt.RoundCap))
                self._draw_arrow(painter, start, end)
            if self.project.show_roof_dimensions:
                slope_mid = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
                self._label_box(painter, slope_mid + QPointF(10, -28), f"уклон {self.project.roof_angle:.0f}°")
        elif roof_type in ("Вальмовая", "Шатровая"):
            if self.project.roof_ridge_direction == "по Y":
                ridge_a = QPointF(center_x, top + 22)
                ridge_b = QPointF(center_x, bottom - 22)
            else:
                ridge_a = QPointF(left + 22, center_y)
                ridge_b = QPointF(right - 22, center_y)
            if roof_type == "Вальмовая":
                ridge_start, ridge_end = ridge_a, ridge_b
                if self.project.show_roof_ridge:
                    painter.drawLine(ridge_a, ridge_b)
                if self.project.show_roof_dimensions:
                    self._draw_roof_ridge_labels(painter, ridge_a, ridge_b)
                targets = (ridge_a, ridge_b)
            else:
                targets = (QPointF(center_x, center_y),)
                if detail_mode and self.project.show_roof_dimensions:
                    self._label_box(painter, QPointF(center_x + 10, center_y - 28), f"конёк {self.project.roof_ridge_height:.1f} м")
            if self.project.show_roof_slopes:
                painter.setPen(QPen(QColor("#8d5a2d"), 2, Qt.SolidLine, Qt.RoundCap))
                for corner in (QPointF(left, top), QPointF(right, top), QPointF(right, bottom), QPointF(left, bottom)):
                    target = min(targets, key=lambda item: self._distance(corner, item))
                    if detail_mode:
                        painter.drawLine(corner, target)
                        self._draw_arrow(painter, target, corner)
                    else:
                        start = QPointF(
                            target.x() + (corner.x() - target.x()) * 0.38,
                            target.y() + (corner.y() - target.y()) * 0.38,
                        )
                        end = QPointF(
                            target.x() + (corner.x() - target.x()) * 0.58,
                            target.y() + (corner.y() - target.y()) * 0.58,
                        )
                        self._draw_arrow(painter, start, end)

        if self.project.show_roof_overhangs and self.project.show_roof_dimensions:
            self._draw_overhang_labels(painter, base_points, roof_points)

    def _draw_roof_ridge_labels(self, painter: QPainter, start: QPointF, end: QPointF) -> None:
        length_m = self.project.roof_ridge_length_m()
        mid = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
        self._label_box(painter, mid + QPointF(12, -34), f"конёк {length_m:.1f} м")
        self._label_box(painter, mid + QPointF(12, -8), f"высота {self.project.roof_ridge_height:.1f} м")

    def _draw_slope_arrows(self, painter: QPainter, ridge_start: QPointF, ridge_end: QPointF, left: float, right: float, top: float, bottom: float) -> None:
        painter.setPen(QPen(QColor("#8d5a2d"), 2, Qt.SolidLine, Qt.RoundCap))
        if self.project.roof_ridge_direction == "по Y":
            for y in (top + (bottom - top) * 0.35, top + (bottom - top) * 0.65):
                self._draw_arrow(painter, QPointF((ridge_start.x() + ridge_end.x()) / 2, y), QPointF(left + 24, y))
                self._draw_arrow(painter, QPointF((ridge_start.x() + ridge_end.x()) / 2, y), QPointF(right - 24, y))
        else:
            for x in (left + (right - left) * 0.35, left + (right - left) * 0.65):
                self._draw_arrow(painter, QPointF(x, (ridge_start.y() + ridge_end.y()) / 2), QPointF(x, top + 24))
                self._draw_arrow(painter, QPointF(x, (ridge_start.y() + ridge_end.y()) / 2), QPointF(x, bottom - 24))

    def _draw_gables(self, painter: QPainter, left: float, right: float, top: float, bottom: float) -> None:
        painter.setPen(QPen(QColor("#a3452a"), 4, Qt.SolidLine, Qt.RoundCap))
        if self.project.roof_ridge_direction == "по Y":
            painter.drawLine(QPointF(left + 8, top), QPointF(right - 8, top))
            painter.drawLine(QPointF(left + 8, bottom), QPointF(right - 8, bottom))
            if self.project.show_roof_dimensions:
                self._label_box(painter, QPointF(left + 12, top + 12), f"фронтон {self.project.roof_gable_height:.1f} м")
        else:
            painter.drawLine(QPointF(left, top + 8), QPointF(left, bottom - 8))
            painter.drawLine(QPointF(right, top + 8), QPointF(right, bottom - 8))
            if self.project.show_roof_dimensions:
                self._label_box(painter, QPointF(left + 12, top + 12), f"фронтон {self.project.roof_gable_height:.1f} м")

    def _draw_overhang_labels(self, painter: QPainter, base_points: list[QPointF], roof_points: list[QPointF]) -> None:
        if not base_points or not roof_points or self.project.roof_overhang <= 0:
            return
        base_left = min(point.x() for point in base_points)
        base_top = min(point.y() for point in base_points)
        roof_left = min(point.x() for point in roof_points)
        roof_top = min(point.y() for point in roof_points)
        painter.setPen(QPen(QColor("#6f7a73"), 1, Qt.SolidLine))
        self._draw_arrow(painter, QPointF(roof_left, roof_top - 14), QPointF(base_left, base_top - 14))
        self._label_box(painter, QPointF(roof_left + 6, roof_top - 44), f"свес {self.project.roof_overhang:.1f} м")

    def _draw_arrow(self, painter: QPainter, start: QPointF, end: QPointF) -> None:
        painter.drawLine(start, end)
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = hypot(dx, dy) or 1
        ux, uy = dx / length, dy / length
        left = QPointF(end.x() - ux * 12 - uy * 6, end.y() - uy * 12 + ux * 6)
        right = QPointF(end.x() - ux * 12 + uy * 6, end.y() - uy * 12 - ux * 6)
        painter.drawLine(end, left)
        painter.drawLine(end, right)

    def _label_box(self, painter: QPainter, pos: QPointF, text: str) -> None:
        width = max(84, len(text) * 7)
        rect = QRectF(pos.x(), pos.y(), width, 22)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 225))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(QPen(QColor("#46321f"), 1))
        painter.setFont(QFont("Arial", 8, QFont.Bold))
        painter.drawText(rect, Qt.AlignCenter, text)

    def _draw_hover_preview(self, painter: QPainter) -> None:
        if self.tool not in ("door", "window") or self.hover_wall < 0:
            return
        wall = self.current_floor().walls[self.hover_wall]
        if self.tool == "door":
            preview = self._door_from_template(self.hover_wall, self.hover_ratio)
            self._draw_door_symbol(painter, wall, preview, True)
        else:
            preview = self._window_from_template(self.hover_wall, self.hover_ratio)
            self._draw_window_symbol(painter, wall, preview, True)

    def _door_from_template(self, wall_index: int, ratio: float) -> DoorItem:
        wall = self.current_floor().walls[wall_index]
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
        wall = self.current_floor().walls[wall_index]
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

    def _stair_from_template(self, pos: QPointF) -> StairItem:
        return StairItem(
            floor=self.floor_level,
            position=Point(pos.x(), pos.y()),
            stair_type=str(self.stair_template.get("stair_type", "Прямая")),
            width=float(self.stair_template.get("width", 0.9) or 0.9),
            length=float(self.stair_template.get("length", 3.0) or 3.0),
            rise_height=float(self.stair_template.get("rise_height", 3.1) or 3.1),
            steps=int(self.stair_template.get("steps", 16) or 16),
            price=float(self.stair_template.get("price", 120000) or 0),
        )

    def _draw_hint(self, painter: QPainter) -> None:
        painter.setPen(QColor("#5f6f78"))
        painter.setFont(QFont("Arial", 10))
        text = "Сетка: 1 м = 40 px. Стены привязаны к шагу 0,5 м."
        painter.drawText(QRectF(12, self.height() - 32, self.width() - 24, 24), Qt.AlignLeft, text)

    def _wall_visible_spans(self, wall_index: int) -> list[tuple[float, float]]:
        floor = self.current_floor()
        wall = floor.walls[wall_index]
        if wall.length_m <= 0:
            return []

        gaps: list[tuple[float, float]] = []
        if self.project.show_doors:
            for door in floor.doors:
                if door.wall_index == wall_index:
                    half_ratio = door.width / wall.length_m / 2
                    gaps.append((door.position - half_ratio, door.position + half_ratio))
        if self.project.show_windows:
            for window in floor.windows:
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
        floor = self.current_floor()
        for index, stair in enumerate(floor.stairs):
            width = max(28.0, stair.width * PIXELS_PER_METER)
            length = max(60.0, stair.length * PIXELS_PER_METER)
            rect = QRectF(stair.position.x - width / 2, stair.position.y - length / 2, width, length)
            if rect.adjusted(-8, -8, 8, 8).contains(pos):
                return "stair", index
        for index, room in enumerate(floor.rooms):
            if self._distance(pos, QPointF(room.center.x, room.center.y)) <= 70:
                return "room", index
        for index, door in enumerate(floor.doors):
            if door.wall_index < len(floor.walls):
                center = self._point_on_wall(floor.walls[door.wall_index], door.position)
                if self._distance(pos, center) <= max(16, door.width * PIXELS_PER_METER):
                    return "door", index
        for index, window in enumerate(floor.windows):
            if window.wall_index < len(floor.walls):
                center = self._point_on_wall(floor.walls[window.wall_index], window.position)
                if self._distance(pos, center) <= max(16, window.width * PIXELS_PER_METER / 2):
                    return "window", index

        wall_index, _ = self._wall_at(pos)
        if wall_index >= 0:
            return "wall", wall_index
        if self.project.show_roof:
            roof_points = self._roof_polygon_points()
            if len(roof_points) >= 3 and QPolygonF(roof_points).containsPoint(pos, Qt.OddEvenFill):
                return "roof", -1
        return "project", -1

    def _snap(self, pos: QPointF) -> QPointF:
        return QPointF(round(pos.x() / self.grid_size) * self.grid_size, round(pos.y() / self.grid_size) * self.grid_size)

    def _roof_polygon_points(self) -> list[QPointF]:
        return self._expanded_polygon_points(self._roof_base_polygon_points(), self.project.roof_overhang * PIXELS_PER_METER)

    def _roof_base_polygon_points(self) -> list[QPointF]:
        points: list[QPointF] = []
        seen: set[tuple[float, float]] = set()
        for wall in self.project.get_floor(1).walls:
            for point in (wall.start, wall.end):
                key = (round(point.x, 3), round(point.y, 3))
                if key not in seen:
                    points.append(QPointF(point.x, point.y))
                    seen.add(key)
        if len(points) < 3:
            return []

        center_x = sum(point.x() for point in points) / len(points)
        center_y = sum(point.y() for point in points) / len(points)
        return sorted(points, key=lambda point: atan2(point.y() - center_y, point.x() - center_x))

    def _expanded_polygon_points(self, ordered: list[QPointF], overhang_px: float) -> list[QPointF]:
        if len(ordered) < 3:
            return []
        center_x = sum(point.x() for point in ordered) / len(ordered)
        center_y = sum(point.y() for point in ordered) / len(ordered)
        center = QPointF(center_x, center_y)
        expanded: list[QPointF] = []
        for point in ordered:
            dx = point.x() - center.x()
            dy = point.y() - center.y()
            length = hypot(dx, dy) or 1
            expanded.append(QPointF(point.x() + dx / length * overhang_px, point.y() + dy / length * overhang_px))
        return expanded

    def _wall_at(self, pos: QPointF) -> tuple[int, float]:
        best_index = -1
        best_distance = max(8.0, 14.0 / max(0.4, self.view_scale))
        best_ratio = 0.5
        for index, wall in enumerate(self.current_floor().walls):
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

    def _screen_to_world(self, pos: QPointF) -> QPointF:
        scale = self.view_scale or 1.0
        return QPointF((pos.x() - self.view_offset.x()) / scale, (pos.y() - self.view_offset.y()) / scale)

    def _project_bounds(self) -> QRectF | None:
        points: list[QPointF] = []
        floor = self.current_floor()
        for wall in floor.walls:
            points.append(QPointF(wall.start.x, wall.start.y))
            points.append(QPointF(wall.end.x, wall.end.y))
        for room in floor.rooms:
            points.append(QPointF(room.center.x - 80, room.center.y - 40))
            points.append(QPointF(room.center.x + 80, room.center.y + 40))
        for stair in floor.stairs:
            width = max(28.0, stair.width * PIXELS_PER_METER)
            length = max(60.0, stair.length * PIXELS_PER_METER)
            points.append(QPointF(stair.position.x - width, stair.position.y - length))
            points.append(QPointF(stair.position.x + width, stair.position.y + length))
        if self.project.show_roof and self.floor_level == 1:
            points.extend(self._roof_polygon_points())
        if not points:
            return None
        left = min(point.x() for point in points)
        right = max(point.x() for point in points)
        top = min(point.y() for point in points)
        bottom = max(point.y() for point in points)
        padding = 45
        return QRectF(left - padding, top - padding, max(1.0, right - left + padding * 2), max(1.0, bottom - top + padding * 2))


class RoofPreviewWidget(QWidget):
    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.yaw = 0.0
        self.preview_zoom = 1.0
        self._drag_pos: QPointF | None = None
        self.setMinimumHeight(210)
        self.setMouseTracking(True)

    def set_project(self, project: Project) -> None:
        self.project = project
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f8faf7"))

        if not self.project.get_floor(1).walls:
            painter.setPen(QColor("#6b7872"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Схема крыши появится после стен")
            return

        width_m, depth_m = self.project.footprint_bounds_m()
        width_m = max(1.0, width_m + self.project.roof_overhang * 2)
        depth_m = max(1.0, depth_m + self.project.roof_overhang * 2)
        scale = min((self.width() - 60) / (width_m + depth_m), (self.height() - 40) / (width_m * 0.25 + depth_m * 0.25 + self.project.roof_ridge_height + 2))
        scale = max(18, min(80, scale)) * self.preview_zoom
        origin = QPointF(self.width() / 2, self.height() * 0.72)

        def iso(x: float, y: float, z: float = 0.0) -> QPointF:
            rx = x * cos(self.yaw) - y * sin(self.yaw)
            ry = x * sin(self.yaw) + y * cos(self.yaw)
            return QPointF(origin.x() + (rx - ry) * scale, origin.y() + (rx + ry) * scale * 0.42 - z * scale)

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
        painter.drawText(12, 22, f"Схема: {self.project.roof_type}, {self.project.roof_ridge_direction}")
        painter.drawText(12, 42, "ЛКМ - вращение, колесо - масштаб")

    def _draw_face(self, painter: QPainter, points: list[QPointF], color: QColor) -> None:
        painter.setBrush(QBrush(color))
        painter.drawPolygon(QPolygonF(points))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.position()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._drag_pos is None or not (event.buttons() & Qt.LeftButton):
            return
        delta = event.position() - self._drag_pos
        self.yaw += delta.x() * 0.01
        self._drag_pos = event.position()
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.LeftButton:
            self._drag_pos = None

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API
        factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        self.preview_zoom = max(0.45, min(2.8, self.preview_zoom * factor))
        self.update()
