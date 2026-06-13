from __future__ import annotations

from math import hypot

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QMenu, QWidget

from models import Point, Project, SiteElement


SITE_ELEMENT_PRESETS: dict[str, dict[str, object]] = {
    "fence": {"name": "Забор", "width": 1.0, "length": 1.0, "unit": "м", "price": 2500},
    "gate": {"name": "Ворота", "width": 4.0, "length": 0.4, "unit": "шт", "price": 65000},
    "wicket": {"name": "Калитка", "width": 1.0, "length": 0.4, "unit": "шт", "price": 18000},
    "parking": {"name": "Парковка", "width": 6.0, "length": 5.0, "unit": "м²", "price": 1600},
    "path": {"name": "Дорожка", "width": 1.2, "length": 8.0, "unit": "м²", "price": 1400},
    "septic": {
        "name": "Септик",
        "width": 2.0,
        "length": 2.0,
        "unit": "шт",
        "price": 120000,
        "parameters": {"type": "Станция биоочистки", "volume_m3": 3.0, "delivery": 12000, "installation": 35000},
    },
    "well": {"name": "Скважина", "width": 1.2, "length": 1.2, "unit": "шт", "price": 180000},
    "electric_input": {"name": "Электрический ввод", "width": 1.0, "length": 1.0, "unit": "шт", "price": 35000},
    "electric_panel": {"name": "Электрощит", "width": 0.8, "length": 0.8, "unit": "шт", "price": 28000},
    "outlet": {"name": "Розетка", "width": 0.5, "length": 0.5, "unit": "шт", "price": 1200},
    "switch": {"name": "Выключатель", "width": 0.5, "length": 0.5, "unit": "шт", "price": 900},
    "light": {"name": "Светильник", "width": 0.6, "length": 0.6, "unit": "шт", "price": 2500},
    "electric_line": {"name": "Линия электрики", "width": 0.3, "length": 8.0, "unit": "м", "price": 180},
    "water_input": {"name": "Ввод воды", "width": 1.0, "length": 1.0, "unit": "шт", "price": 18000},
    "water_pipe": {"name": "Водопровод", "width": 0.3, "length": 10.0, "unit": "м", "price": 450},
    "plumbing_point": {"name": "Сантехническая точка", "width": 0.7, "length": 0.7, "unit": "шт", "price": 6500},
    "sewer_output": {"name": "Канализационный вывод", "width": 0.8, "length": 0.8, "unit": "шт", "price": 12000},
    "shower": {"name": "Душевая", "width": 1.0, "length": 1.0, "unit": "шт", "price": 18000},
    "kitchen_water": {"name": "Кухня", "width": 0.8, "length": 0.8, "unit": "шт", "price": 9000},
    "landscaping": {"name": "Зона озеленения", "width": 6.0, "length": 4.0, "unit": "м²", "price": 600},
}


class SiteCanvas(QWidget):
    """Простой план участка с условными объектами и коммуникациями."""

    project_changed = Signal()
    warning_requested = Signal(str)

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.tool = "site"
        self.selected_index = -1
        self.setMinimumSize(720, 520)
        self.setMouseTracking(True)

    def set_project(self, project: Project) -> None:
        self.project = project
        self.selected_index = -1
        self.update()

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f7f8f4"))
        plot = self._plot_rect()
        painter.fillRect(plot, QColor("#edf5e8"))
        painter.setPen(QPen(QColor("#405047"), 2))
        painter.drawRoundedRect(plot, 6, 6)
        self._draw_setbacks(painter, plot)
        self._draw_house(painter, plot)
        if self.project.show_site_layer:
            self._draw_site_elements(painter, plot)
        self._draw_hint(painter)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() != Qt.LeftButton:
            return
        pos_m = self._screen_to_site_m(event.position())
        if pos_m is None:
            return
        if self.tool in SITE_ELEMENT_PRESETS:
            if self.tool == "fence":
                self._add_fence()
            else:
                self._add_element(self.tool, pos_m)
            self.project_changed.emit()
            self.update()
            return
        self.selected_index = self._element_at(pos_m)
        self.update()

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt API
        pos_m = self._screen_to_site_m(QPointF(event.pos()))
        if pos_m is None:
            return
        index = self._element_at(pos_m)
        if index < 0:
            return
        self.selected_index = index
        menu = QMenu(self)
        delete_action = menu.addAction("Удалить")
        action = menu.exec(event.globalPos())
        if action == delete_action:
            del self.project.site_elements[index]
            self.selected_index = -1
            self.project_changed.emit()
            self.update()

    def _add_fence(self) -> None:
        site = self.project.site
        perimeter = 2 * (site.width_m + site.length_m)
        existing = next((item for item in self.project.site_elements if item.kind == "fence"), None)
        if existing is not None:
            existing.quantity = perimeter
            return
        preset = SITE_ELEMENT_PRESETS["fence"]
        self.project.site_elements.append(
            SiteElement(
                kind="fence",
                name=str(preset["name"]),
                position=Point(site.width_m / 2, site.length_m / 2),
                quantity=perimeter,
                unit=str(preset["unit"]),
                price=float(preset["price"]),
            )
        )

    def _add_element(self, kind: str, pos_m: QPointF) -> None:
        preset = SITE_ELEMENT_PRESETS[kind]
        width = float(preset.get("width", 1.0))
        length = float(preset.get("length", 1.0))
        quantity = max(1.0, width * length) if str(preset.get("unit")) == "м²" else 1.0
        if str(preset.get("unit")) == "м":
            quantity = length
        element = SiteElement(
            kind=kind,
            name=str(preset.get("name", "Элемент участка")),
            position=Point(pos_m.x(), pos_m.y()),
            width_m=width,
            length_m=length,
            quantity=quantity,
            unit=str(preset.get("unit", "шт")),
            price=float(preset.get("price", 0) or 0),
            parameters=dict(preset.get("parameters", {})),
        )
        self.project.site_elements.append(element)
        self.selected_index = len(self.project.site_elements) - 1
        self._update_septic_distances()

    def _draw_setbacks(self, painter: QPainter, plot: QRectF) -> None:
        site = self.project.site
        scale = self._scale()
        rect = QRectF(
            plot.left() + site.left_setback_m * scale,
            plot.top() + site.front_setback_m * scale,
            max(1, plot.width() - (site.left_setback_m + site.right_setback_m) * scale),
            max(1, plot.height() - (site.front_setback_m + site.rear_setback_m) * scale),
        )
        pen = QPen(QColor("#7e9388"), 1, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)
        painter.setPen(QColor("#5f6f68"))
        painter.setFont(QFont("Arial", 9))
        painter.drawText(rect.adjusted(6, 6, -6, -6), Qt.AlignTop | Qt.AlignLeft, "Допустимая зона дома")

    def _draw_house(self, painter: QPainter, plot: QRectF) -> None:
        scale = self._scale()
        house_w, house_d = self.project.footprint_bounds_m()
        house_w = house_w or 8.0
        house_d = house_d or 10.0
        site = self.project.site
        x = min(max(site.left_setback_m, 0.5), max(0.5, site.width_m - house_w - site.right_setback_m))
        y = min(max(site.front_setback_m, 0.5), max(0.5, site.length_m - house_d - site.rear_setback_m))
        rect = QRectF(plot.left() + x * scale, plot.top() + y * scale, house_w * scale, house_d * scale)
        if self.project.show_architecture_layer:
            painter.setPen(QPen(QColor("#28313a"), 2))
            painter.setBrush(QColor(255, 255, 255, 230))
        else:
            painter.setPen(QPen(QColor("#aeb8b1"), 1))
            painter.setBrush(QColor(255, 255, 255, 110))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(QColor("#263238"))
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        painter.drawText(rect, Qt.AlignCenter, "Дом")

    def _draw_site_elements(self, painter: QPainter, plot: QRectF) -> None:
        for index, item in enumerate(self.project.site_elements):
            if not self._element_visible(item):
                continue
            self._draw_element(painter, plot, item, index == self.selected_index)

    def _draw_element(self, painter: QPainter, plot: QRectF, item: SiteElement, selected: bool) -> None:
        scale = self._scale()
        center = QPointF(plot.left() + item.position.x * scale, plot.top() + item.position.y * scale)
        width = max(18.0, item.width_m * scale)
        height = max(18.0, item.length_m * scale)
        rect = QRectF(center.x() - width / 2, center.y() - height / 2, width, height)
        colors = {
            "septic": "#8d6e63",
            "well": "#2887c8",
            "parking": "#8f9aa3",
            "path": "#c7b8a0",
            "gate": "#795548",
            "wicket": "#7b5e57",
            "electric_input": "#f2b632",
            "electric_panel": "#f2b632",
            "outlet": "#f2b632",
            "switch": "#f2b632",
            "light": "#f2b632",
            "electric_line": "#f2b632",
            "water_input": "#2589d0",
            "water_pipe": "#2589d0",
            "plumbing_point": "#2589d0",
            "sewer_output": "#607d8b",
            "landscaping": "#7ca982",
        }
        color = QColor(colors.get(item.kind, "#7ca982"))
        pen = QPen(QColor("#e0822d") if selected else color.darker(130), 3 if selected else 2)
        painter.setPen(pen)
        if item.kind in {"electric_line", "water_pipe", "path"}:
            painter.drawLine(rect.left(), rect.center().y(), rect.right(), rect.center().y())
        elif item.kind in {"parking", "landscaping"}:
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 80))
            painter.drawRoundedRect(rect, 5, 5)
        else:
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 120))
            painter.drawEllipse(rect)
        painter.setPen(QColor("#1d2a2a"))
        painter.setFont(QFont("Arial", 9))
        painter.drawText(rect.adjusted(-42, rect.height() / 2 + 3, 42, 28), Qt.AlignCenter, item.name)

    def _draw_hint(self, painter: QPainter) -> None:
        site = self.project.site
        painter.setPen(QColor("#53635c"))
        painter.setFont(QFont("Arial", 10))
        painter.drawText(
            QRectF(14, self.height() - 38, self.width() - 28, 28),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"Участок: {site.area_sotka:.1f} сот. ({site.width_m:.1f} x {site.length_m:.1f} м). Выберите элемент справа и кликните на плане.",
        )

    def _element_visible(self, item: SiteElement) -> bool:
        if item.kind.startswith("electric") or item.kind in {"outlet", "switch", "light"}:
            return self.project.show_electric_layer
        if item.kind in {"water_input", "water_pipe", "plumbing_point", "sewer_output", "shower", "kitchen_water"}:
            return self.project.show_plumbing_layer
        return self.project.show_site_layer

    def _plot_rect(self) -> QRectF:
        margin = 46.0
        site = self.project.site
        scale = self._scale()
        width = site.width_m * scale
        height = site.length_m * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height).adjusted(0, 0, 0, 0).intersected(
            QRectF(margin, margin, max(1, self.width() - margin * 2), max(1, self.height() - margin * 2))
        )

    def _scale(self) -> float:
        site = self.project.site
        return max(4.0, min((self.width() - 92) / max(1.0, site.width_m), (self.height() - 92) / max(1.0, site.length_m)))

    def _screen_to_site_m(self, pos: QPointF) -> QPointF | None:
        plot = self._plot_rect()
        if not plot.contains(pos):
            return None
        scale = self._scale()
        return QPointF((pos.x() - plot.left()) / scale, (pos.y() - plot.top()) / scale)

    def _element_at(self, pos_m: QPointF) -> int:
        for index, item in enumerate(self.project.site_elements):
            radius = max(item.width_m, item.length_m, 1.0) * 0.75
            if hypot(pos_m.x() - item.position.x, pos_m.y() - item.position.y) <= radius:
                return index
        return -1

    def _update_septic_distances(self) -> None:
        house_w, house_d = self.project.footprint_bounds_m()
        site = self.project.site
        house_center = QPointF(site.left_setback_m + (house_w or 8.0) / 2, site.front_setback_m + (house_d or 10.0) / 2)
        wells = [item for item in self.project.site_elements if item.kind == "well"]
        for septic in (item for item in self.project.site_elements if item.kind == "septic"):
            septic_pos = QPointF(septic.position.x, septic.position.y)
            septic.parameters["distance_to_house_m"] = round(hypot(septic_pos.x() - house_center.x(), septic_pos.y() - house_center.y()), 1)
            if wells:
                nearest = min(hypot(septic_pos.x() - well.position.x, septic_pos.y() - well.position.y) for well in wells)
                septic.parameters["distance_to_well_m"] = round(nearest, 1)
                if nearest < 8.0:
                    self.warning_requested.emit("Проверьте расстояние между септиком и скважиной.")
