from __future__ import annotations

from html import escape
from typing import Any

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSettings, QSize, Qt
from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QApplication,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from canvas import PlanCanvas, RoofPreviewWidget
from facade_view import FacadeView
from models import DoorItem, ExtraCostItem, PIXELS_PER_METER, Point, Project, ROOM_TYPES, RoomItem, SiteElement, Wall, WindowItem
from pricing import (
    calculate_estimate,
    estimate_to_text,
    format_money,
    load_materials,
    material_price_label,
    wall_catalog,
    wall_material_info,
)
from storage import export_text, load_project, save_project
from section_view import SectionView
from site_canvas import SITE_ELEMENT_PRESETS, SiteCanvas
from updater import APP_VERSION, check_for_updates, download_update, run_installer


class OpeningTemplateDialog(QDialog):
    """Небольшая форма выбора шаблона окна или двери перед установкой на стену."""

    def __init__(self, title: str, templates: dict[str, dict[str, Any]], kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.templates = templates
        self.kind = kind
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.template_combo = QComboBox()
        for name, data in templates.items():
            price = float(data.get("price", 0) or 0)
            label = f"{name} — {format_money(price)}" if price else name
            self.template_combo.addItem(label, name)
        form.addRow("Шаблон", self.template_combo)

        self.width_spin = self._meter_spin(0.3, 6.0, 0.1)
        self.height_spin = self._meter_spin(0.3, 3.5, 0.1)
        self.price_spin = self._money_spin()
        form.addRow("Ширина", self.width_spin)
        form.addRow("Высота", self.height_spin)

        self.sill_spin: QDoubleSpinBox | None = None
        self.price_m2_spin: QDoubleSpinBox | None = None
        self.glass_combo: QComboBox | None = None
        self.direction_combo: QComboBox | None = None
        self.hinge_combo: QComboBox | None = None

        if kind == "window":
            self.sill_spin = self._meter_spin(0.0, 2.5, 0.1)
            self.glass_combo = QComboBox()
            self.glass_combo.addItems(["однокамерный", "двухкамерный", "энергосберегающий", "панорамный"])
            self.price_m2_spin = self._money_spin()
            self.price_m2_spin.setSuffix(" ₽/м²")
            form.addRow("Высота от пола", self.sill_spin)
            form.addRow("Стеклопакет", self.glass_combo)
            form.addRow("Цена вручную", self.price_spin)
            form.addRow("Цена за м²", self.price_m2_spin)
        else:
            self.direction_combo = QComboBox()
            self.direction_combo.addItems(["Внутрь", "Наружу"])
            self.hinge_combo = QComboBox()
            self.hinge_combo.addItems(["Левая", "Правая"])
            form.addRow("Открывание", self.direction_combo)
            form.addRow("Петли", self.hinge_combo)
            form.addRow("Цена", self.price_spin)

        layout.addWidget(box)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.template_combo.currentIndexChanged.connect(self._load_template)
        self._load_template()

    def values(self) -> dict[str, Any]:
        name = self.template_combo.currentData()
        result: dict[str, Any] = {
            "template_name": name,
            "width": float(self.width_spin.value()),
            "height": float(self.height_spin.value()),
            "price": float(self.price_spin.value()),
        }
        if self.kind == "window":
            result["sill_height"] = float(self.sill_spin.value() if self.sill_spin else 0.9)
            result["install_height"] = result["sill_height"]
            result["glass_type"] = self.glass_combo.currentText() if self.glass_combo else "двухкамерный"
            result["price_per_m2"] = float(self.price_m2_spin.value() if self.price_m2_spin else 0)
        else:
            result["opening_direction"] = self.direction_combo.currentText() if self.direction_combo else "Внутрь"
            result["hinge_side"] = self.hinge_combo.currentText() if self.hinge_combo else "Левая"
        return result

    def _load_template(self) -> None:
        name = self.template_combo.currentData()
        data = self.templates.get(name, {})
        self.width_spin.setValue(float(data.get("width", 1.0) or 1.0))
        self.height_spin.setValue(float(data.get("height", 1.0) or 1.0))
        self.price_spin.setValue(float(data.get("price", 0) or 0))
        if self.kind == "window":
            if self.sill_spin is not None:
                self.sill_spin.setValue(float(data.get("sill_height", 0.9) or 0.9))
            if self.glass_combo is not None:
                self.glass_combo.setCurrentText(str(data.get("glass_type", "двухкамерный")))
            if self.price_m2_spin is not None:
                self.price_m2_spin.setValue(float(data.get("price_per_m2", 0) or 0))
        else:
            if self.direction_combo is not None:
                self.direction_combo.setCurrentText(str(data.get("opening_direction", "Внутрь")))
            if self.hinge_combo is not None:
                self.hinge_combo.setCurrentText(str(data.get("hinge_side", "Левая")))

    def _meter_spin(self, minimum: float, maximum: float, step: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setDecimals(1)
        spin.setSuffix(" м")
        return spin

    def _money_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0, 1000000)
        spin.setSingleStep(1000)
        spin.setDecimals(0)
        spin.setSuffix(" ₽")
        return spin


class StartDialog(QDialog):
    """Стартовый экран для быстрого начала работы без поиска нужной кнопки."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.action: str | None = None
        self.setWindowTitle("Начало работы")
        self.setMinimumSize(620, 420)
        self.setModal(True)
        self.setObjectName("LightDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(14)

        title = QLabel("С чего начать?")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        hint = QLabel("Создайте новый дом, откройте сохранённый проект или выберите простой шаблон.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        for caption, action in (
            ("Создать новый дом", "one_floor"),
            ("Открыть шаблон", "template"),
            ("Открыть проект", "open"),
        ):
            button = QPushButton(caption)
            button.setMinimumHeight(52)
            button.clicked.connect(lambda checked=False, value=action: self._finish(value))
            layout.addWidget(button)

        close_button = QPushButton("Продолжить с пустого проекта")
        close_button.clicked.connect(self.reject)
        layout.addWidget(close_button)

    def _finish(self, action: str) -> None:
        self.action = action
        self.accept()


class WelcomeDialog(QDialog):
    """Первое дружелюбное объяснение для пользователя без опыта CAD."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.action: str | None = None
        self.setWindowTitle("Добро пожаловать")
        self.setMinimumSize(700, 450)
        self.resize(700, 450)
        self.setModal(True)
        self.setObjectName("LightDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 30, 34, 30)
        layout.setSpacing(16)

        title = QLabel("Добро пожаловать в программу планировки дома.")
        title.setObjectName("PanelTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        text = QLabel(
            "Создание проекта занимает всего несколько шагов:\n\n"
            "1. Нарисуйте наружные стены.\n"
            "2. Добавьте внутренние перегородки.\n"
            "3. Установите окна и двери.\n"
            "4. Настройте материалы и крышу.\n"
            "5. Получите автоматическую смету."
        )
        text.setWordWrap(True)
        layout.addWidget(text)

        self.hide_check = QCheckBox("Больше не показывать")
        layout.addWidget(self.hide_check)

        buttons = [
            ("Создать новый дом", "new"),
            ("Открыть шаблон", "template"),
            ("Открыть демо-дом", "demo"),
            ("Начать обучение", "tutorial"),
            ("Открыть проект", "open"),
        ]
        for caption, action in buttons:
            button = QPushButton(caption)
            button.setMinimumHeight(50)
            button.clicked.connect(lambda checked=False, value=action: self._finish(value))
            layout.addWidget(button)

    def _finish(self, action: str) -> None:
        self.action = action
        self.accept()


class TutorialOverlay(QWidget):
    """Полупрозрачная маска и белое обучающее облачко со стрелкой к кнопке."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.target: QWidget | None = None
        self.text = ""
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()

    def show_tip(self, target: QWidget | None, text: str) -> None:
        self.target = target
        self.text = text
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(15, 24, 28, 95))

        target_rect = self._target_rect()
        if target_rect is not None:
            painter.setPen(QPen(QColor("#f0a24a"), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(target_rect, 10, 10)

        bubble = self._bubble_rect(target_rect)
        shadow = QPainterPath()
        shadow.addRoundedRect(bubble.adjusted(0, 4, 0, 4), 14, 14)
        painter.fillPath(shadow, QColor(0, 0, 0, 45))

        path = QPainterPath()
        path.addRoundedRect(bubble, 14, 14)
        painter.fillPath(path, QColor("#ffffff"))
        painter.setPen(QPen(QColor("#d7e0dc"), 1))
        painter.drawPath(path)

        if target_rect is not None:
            arrow = QPolygonF(
                [
                    QPointF(bubble.left(), bubble.center().y() - 10),
                    QPointF(bubble.left() - 18, bubble.center().y()),
                    QPointF(bubble.left(), bubble.center().y() + 10),
                ]
            )
            if bubble.center().x() < target_rect.center().x():
                arrow = QPolygonF(
                    [
                        QPointF(bubble.right(), bubble.center().y() - 10),
                        QPointF(bubble.right() + 18, bubble.center().y()),
                        QPointF(bubble.right(), bubble.center().y() + 10),
                    ]
                )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#ffffff"))
            painter.drawPolygon(arrow)

        painter.setPen(QColor("#172126"))
        painter.setFont(QFont("Segoe UI", 14))
        painter.drawText(bubble.adjusted(22, 18, -22, -18), Qt.AlignLeft | Qt.TextWordWrap, self.text)

    def _target_rect(self) -> QRectF | None:
        if self.target is None or not self.target.isVisible():
            return None
        top_left = self.target.mapToGlobal(QPoint(0, 0))
        local = self.mapFromGlobal(top_left)
        return QRectF(local, self.target.size()).adjusted(-8, -8, 8, 8)

    def _bubble_rect(self, target_rect: QRectF | None) -> QRectF:
        width = min(430.0, max(320.0, self.width() * 0.30))
        height = 150.0
        if target_rect is None:
            return QRectF((self.width() - width) / 2, 80, width, height)
        x = target_rect.right() + 34
        y = max(28.0, min(target_rect.top() - 18, self.height() - height - 28))
        if x + width > self.width() - 24:
            x = target_rect.left() - width - 34
        if x < 24:
            x = (self.width() - width) / 2
            y = min(target_rect.bottom() + 26, self.height() - height - 28)
        return QRectF(x, y, width, height)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Простая планировка дома и смета")
        self.resize(1680, 980)
        self.setMinimumSize(1280, 760)

        self.project = Project()
        self.materials = load_materials()
        self.canvas1 = PlanCanvas(self.project, floor_level=1)
        self.canvas2 = PlanCanvas(self.project, floor_level=2)
        self.canvas = self.canvas1
        self.facade_view = FacadeView(self.project)
        self.section_view = SectionView(self.project)
        self.site_canvas = SiteCanvas(self.project)
        self.roof_preview: RoofPreviewWidget | None = None
        self.center_tabs: QTabWidget | None = None
        self.explanation_table: QTableWidget | None = None
        self.current_project_path: str | None = None
        self.estimate: dict[str, float] = {}
        self._updating_controls = False
        self._start_screen_shown = False
        self.settings = QSettings("HousePlanner", "PlannerEstimate")
        self._tutorial_active = False
        self._tutorial_stage = ""
        self.tool_buttons: dict[str, QPushButton] = {}

        for canvas in self._all_canvases():
            canvas.set_window_template(self._template_payload("window_templates", "Стандартное окно 1.5 x 1.4 м"))
            canvas.set_door_template(self._template_payload("door_templates", "Входная 0.9 x 2.1 м"))
            canvas.set_stair_template(self._current_stair_template())

        self._build_menu()
        self._build_layout()
        self.tutorial_overlay = TutorialOverlay(self)
        self._connect_signals()
        self._sync_controls_from_project()
        self._refresh_selection_panel("project", -1)
        self._refresh_estimate()
        QTimer.singleShot(0, self._fit_current_project)
        QTimer.singleShot(150, self._show_welcome_or_start)
        QTimer.singleShot(2500, lambda: self._check_updates(manual=False))

    def _all_canvases(self) -> tuple[PlanCanvas, PlanCanvas]:
        return self.canvas1, self.canvas2

    def _active_floor(self):
        return self.canvas.current_floor()

    def _set_project_for_views(self, project: Project) -> None:
        self.project = project
        for canvas in self._all_canvases():
            canvas.set_project(project)
            canvas.set_window_template(self._template_payload("window_templates", "Стандартное окно 1.5 x 1.4 м"))
            canvas.set_door_template(self._template_payload("door_templates", "Входная 0.9 x 2.1 м"))
            canvas.set_stair_template(self._current_stair_template())
        self.facade_view.set_project(project)
        self.section_view.set_project(project)
        self.site_canvas.set_project(project)
        if self.roof_preview is not None:
            self.roof_preview.set_project(project)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if hasattr(self, "tutorial_overlay") and self.tutorial_overlay.isVisible():
            self.tutorial_overlay.setGeometry(self.rect())
            self.tutorial_overlay.update()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Файл")

        actions = [
            ("Новый проект", self._new_project),
            ("Новый из шаблона...", self._choose_house_template),
            ("Открыть JSON...", self._open_project),
            ("Сохранить JSON...", self._save_project),
            ("Экспорт сметы TXT...", self._export_txt),
            ("Экспорт сметы PDF...", self._export_pdf),
        ]
        for caption, handler in actions:
            action = QAction(caption, self)
            action.triggered.connect(handler)
            file_menu.addAction(action)

        help_menu = self.menuBar().addMenu("Помощь")
        quick_tutorial_action = QAction("Быстрое обучение", self)
        quick_tutorial_action.triggered.connect(self._start_tutorial)
        reset_tips_action = QAction("Сбросить подсказки", self)
        reset_tips_action.triggered.connect(self._reset_tips)
        demo_action = QAction("Открыть демонстрационный дом", self)
        demo_action.triggered.connect(self._open_demo_project)
        check_updates_action = QAction("Проверить обновления", self)
        check_updates_action.triggered.connect(lambda: self._check_updates(manual=True))
        help_menu.addAction(quick_tutorial_action)
        help_menu.addAction(reset_tips_action)
        help_menu.addAction(demo_action)
        help_menu.addSeparator()
        help_menu.addAction(check_updates_action)

    def _build_layout(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Планировка дома и смета")
        title.setObjectName("AppTitle")
        layout.addWidget(title)
        layout.addWidget(self._build_top_bar())

        work_area = QHBoxLayout()
        work_area.setSpacing(10)
        work_area.addWidget(self._build_tools_panel())
        work_area.addWidget(self._build_center_tabs(), stretch=1)
        work_area.addWidget(self._build_right_panel())
        layout.addLayout(work_area, stretch=1)
        self.setCentralWidget(root)

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        self._add_soft_shadow(bar)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        layout.addWidget(
            self._menu_button(
                "Проект",
                [
                    ("Новый", self._new_project),
                    ("Новый из шаблона", self._choose_house_template),
                    ("Открыть", self._open_project),
                    ("Сохранить", self._save_project),
                    ("Сохранить как", self._save_project_as),
                ],
            )
        )
        layout.addWidget(self._menu_button("Конструкции", [("Стена", lambda: self._activate_tool("wall")), ("Крыша", lambda: self._activate_tool("roof")), ("Лестница", lambda: self._activate_tool("stair"))]))
        layout.addWidget(self._menu_button("Планировки", [("Помещение", lambda: self._activate_tool("room")), ("Участок", lambda: self._activate_tool("site")), ("Вписать проект", self._fit_current_project)]))
        layout.addWidget(self._menu_button("Смета", [("Открыть смету", lambda: self.right_tabs.setCurrentIndex(8)), ("Экспорт TXT", self._export_txt)]))
        layout.addWidget(self._menu_button("Экспорт", [("PDF", self._export_pdf), ("Изображение", self._export_image), ("Коммерческое предложение", self._export_commercial_offer)]))

        self.fit_button = QPushButton("Вписать проект в экран")
        self.fit_button.setObjectName("TopActionButton")
        self.fit_button.clicked.connect(self._fit_current_project)
        layout.addWidget(self.fit_button)
        layout.addStretch()
        return bar

    def _menu_button(self, caption: str, actions: list[tuple[str, Any]]) -> QToolButton:
        button = QToolButton()
        button.setText(caption)
        button.setPopupMode(QToolButton.InstantPopup)
        button.setObjectName("TopMenuButton")
        menu = QMenu(button)
        for text, handler in actions:
            action = QAction(text, self)
            action.triggered.connect(lambda checked=False, callback=handler: callback())
            menu.addAction(action)
        button.setMenu(menu)
        return button

    def _build_center_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        self.center_tabs = tabs
        self.plan1_tab_index = tabs.addTab(self.canvas1, "План 1 этажа")
        self.plan2_tab_index = tabs.addTab(self.canvas2, "План 2 этажа")

        facade_tab = QWidget()
        facade_layout = QVBoxLayout(facade_tab)
        facade_layout.setContentsMargins(0, 0, 0, 0)
        facade_controls = QHBoxLayout()
        facade_controls.addWidget(QLabel("Сторона фасада"))
        self.facade_side_combo = QComboBox()
        self.facade_side_combo.addItems(["север", "юг", "запад", "восток"])
        facade_controls.addWidget(self.facade_side_combo)
        facade_controls.addStretch()
        facade_layout.addLayout(facade_controls)
        facade_layout.addWidget(self.facade_view, stretch=1)
        tabs.addTab(facade_tab, "Фасад")
        tabs.addTab(self.section_view, "Разрез")
        tabs.addTab(self._build_explanation_tab(), "Экспликация")
        self.site_tab_index = tabs.addTab(self.site_canvas, "Участок")
        self._sync_floor_tabs()
        tabs.currentChanged.connect(self._center_tab_changed)
        return tabs

    def _build_explanation_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        title = QLabel("Экспликация помещений")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)
        self.explanation_table = QTableWidget(0, 4)
        self.explanation_table.setHorizontalHeaderLabels(["Этаж", "Помещение", "Площадь", "Периметр"])
        self.explanation_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.explanation_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.explanation_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.explanation_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.explanation_table.verticalHeader().setVisible(False)
        self.explanation_table.setAlternatingRowColors(True)
        layout.addWidget(self.explanation_table, stretch=1)
        self.explanation_total_label = QLabel("Итого площадь: 0.0 м²")
        self.explanation_total_label.setObjectName("TotalLabel")
        self.explanation_total_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self.explanation_total_label)
        return tab

    def _build_tools_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFixedWidth(270)
        panel.setFrameShape(QFrame.StyledPanel)
        self._add_soft_shadow(panel)
        layout = QVBoxLayout(panel)

        title = QLabel("Инструменты")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        self.tool_group = QButtonGroup(self)
        tools = [
            ("select", "Выбрать / двигать"),
            ("wall", "Добавить стену"),
            ("door", "Добавить дверь"),
            ("window", "Добавить окно"),
            ("room", "Помещение"),
            ("stair", "Лестница"),
            ("roof", "Крыша"),
            ("site", "Участок"),
            ("delete", "Удалить объект"),
        ]
        for tool_id, caption in tools:
            button = QPushButton(caption)
            button.setCheckable(True)
            button.setMinimumHeight(56)
            self.tool_group.addButton(button)
            self.tool_buttons[tool_id] = button
            button.clicked.connect(lambda checked=False, value=tool_id: self._activate_tool(value))
            layout.addWidget(button)
            if tool_id == "select":
                button.setChecked(True)

        self.delete_button = QPushButton("Удалить выбранное")
        self.delete_button.setMinimumHeight(54)
        self.delete_button.clicked.connect(self._delete_selected)
        layout.addWidget(self.delete_button)

        self.fit_canvas_button = QPushButton("Вписать проект в экран")
        self.fit_canvas_button.setMinimumHeight(50)
        self.fit_canvas_button.clicked.connect(self._fit_current_project)
        layout.addWidget(self.fit_canvas_button)

        layout.addSpacing(12)
        self.copy_second_floor_button = QPushButton("Создать 2 этаж на основе 1 этажа")
        self.copy_second_floor_button.setMinimumHeight(56)
        self.copy_second_floor_button.clicked.connect(self._create_second_floor_from_first)
        layout.addWidget(self.copy_second_floor_button)

        self.new_project_button = QPushButton("Новый проект")
        self.open_button = QPushButton("Открыть")
        self.save_button = QPushButton("Сохранить")
        self.export_button = QPushButton("Экспорт сметы")
        for button in (self.new_project_button, self.open_button, self.save_button, self.export_button):
            button.setMinimumHeight(46)
            layout.addWidget(button)
        self.new_project_button.clicked.connect(self._new_project)
        self.open_button.clicked.connect(self._open_project)
        self.save_button.clicked.connect(self._save_project)
        self.export_button.clicked.connect(self._export_txt)

        layout.addStretch()
        self.roof_mode_box = QGroupBox("Режим крыши")
        roof_mode_layout = QFormLayout(self.roof_mode_box)
        roof_mode_layout.setVerticalSpacing(6)
        self.roof_mode_labels: dict[str, QLabel] = {}
        for key, caption in {
            "type": "Тип",
            "angle": "Угол",
            "ridge": "Конёк",
            "area": "Площадь",
            "slope": "Скат",
            "cost": "Стоимость",
        }.items():
            label = QLabel("0")
            label.setAlignment(Qt.AlignRight)
            self.roof_mode_labels[key] = label
            roof_mode_layout.addRow(caption, label)
        self.roof_mode_box.setVisible(False)
        layout.addWidget(self.roof_mode_box)

        self.help_label = QLabel("Окна и двери выбираются по шаблону и ставятся кликом по существующей стене.")
        self.help_label.setWordWrap(True)
        layout.addWidget(self.help_label)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFixedWidth(540)
        panel.setFrameShape(QFrame.StyledPanel)
        self._add_soft_shadow(panel)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.right_nav = QListWidget()
        self.right_nav.setObjectName("RightNav")
        self.right_nav.setFixedWidth(150)
        self.right_nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.right_nav.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.right_nav.setFocusPolicy(Qt.NoFocus)

        self.right_tabs = QStackedWidget()
        self.right_tabs.setObjectName("RightStack")
        self.right_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        sections = [
            ("🏠 Дом", self._build_project_panel()),
            ("🧱 Стены", self._build_wall_panel()),
            ("🏗 Крыша", self._build_roof_panel()),
            ("🪟 Окна", self._build_window_panel()),
            ("🚪 Двери", self._build_door_panel()),
            ("🏠 Помещения", self._build_rooms_panel()),
            ("🪜 Лестница", self._build_stair_panel()),
            ("🌿 Участок", self._build_site_panel()),
            ("💰 Смета", self._build_estimate_box()),
        ]
        for title, widget in sections:
            item = QListWidgetItem(title)
            item.setSizeHint(QSize(132, 46))
            self.right_nav.addItem(item)
            self.right_tabs.addWidget(self._scroll_panel(widget))

        self.right_nav.currentRowChanged.connect(self.right_tabs.setCurrentIndex)
        self.right_tabs.currentChanged.connect(self._sync_right_nav)
        self.right_nav.setCurrentRow(0)

        layout.addWidget(self.right_nav)
        layout.addWidget(self.right_tabs, stretch=1)
        return panel

    def _sync_right_nav(self, index: int) -> None:
        if not hasattr(self, "right_nav") or self.right_nav.currentRow() == index:
            return
        self.right_nav.blockSignals(True)
        self.right_nav.setCurrentRow(index)
        self.right_nav.blockSignals(False)

    def _build_project_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.no_selection_label = QLabel("Ничего не выбрано.\n\nВыберите объект на плане\nили создайте новый.")
        self.no_selection_label.setWordWrap(True)
        self.no_selection_label.setAlignment(Qt.AlignCenter)
        self.no_selection_label.setMinimumHeight(120)
        layout.addWidget(self.no_selection_label)

        box = QGroupBox("Дом")
        form = QFormLayout(box)
        self._setup_form(form)

        self.floor_mode_combo = QComboBox()
        self.floor_mode_combo.addItems(["1 этаж", "1 этаж + мансарда", "2 этажа"])
        form.addRow("Этажность", self.floor_mode_combo)

        self.floor_1_height_spin = self._meter_spin(2.0, 6.0, 0.1, 1)
        self.floor_2_height_spin = self._meter_spin(2.0, 6.0, 0.1, 1)
        self.plinth_height_spin = self._meter_spin(0.0, 2.0, 0.1, 1)
        self.slab_height_spin = self._meter_spin(0.0, 1.0, 0.05, 2)
        form.addRow("Высота 1 этажа", self.floor_1_height_spin)
        form.addRow("Высота 2 этажа", self.floor_2_height_spin)
        form.addRow("Высота цоколя", self.plinth_height_spin)
        form.addRow("Высота перекрытия", self.slab_height_spin)
        self.floor_2_height_label = form.labelForField(self.floor_2_height_spin)
        self.slab_height_label = form.labelForField(self.slab_height_spin)

        self.height_spin = self.floor_1_height_spin
        self.project_wall_material_combo = self._wall_combo()
        self.foundation_combo = self._section_combo("foundation_types", "price_per_m2")
        self.insulation_combo = self._section_combo("insulation_types", "price_per_m2")
        self.facade_finish_combo = self._section_combo("facade_finish", "price_per_m2")

        form.addRow("Материал новых стен", self.project_wall_material_combo)
        form.addRow("Фундамент", self.foundation_combo)
        form.addRow("Утепление", self.insulation_combo)
        form.addRow("Фасадная отделка", self.facade_finish_combo)

        layout.addWidget(box)
        layout.addStretch()
        return container

    def _build_roof_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox("Крыша")
        form = QFormLayout(box)
        self._setup_form(form)
        self.show_roof_check = QCheckBox("Показать крышу на плане")
        self.auto_roof_height_check = QCheckBox("Автоматически рассчитывать конёк")
        self.auto_build_roof_button = QPushButton("Автоматически построить крышу")
        self.open_roof_view_button = QPushButton("Схема крыши")
        self.roof_type_combo = self._section_combo("roof_types")
        self.roof_direction_combo = QComboBox()
        self.roof_direction_combo.addItems(["по X", "по Y"])
        self.roofing_combo = self._section_combo("roofing_materials", "price_per_m2")
        self.roof_angle_spin = self._plain_spin(1, 60, 1, 0, "°")
        self.roof_ridge_height_spin = self._meter_spin(0.1, 8.0, 0.1, 1)
        self.roof_overhang_spin = self._meter_spin(0.0, 2.0, 0.1, 1)
        self.roof_gable_height_spin = self._meter_spin(0.0, 5.0, 0.1, 1)
        self.roof_complexity_spin = self._plain_spin(0.5, 3.0, 0.05, 2, "")
        form.addRow("", self.show_roof_check)
        form.addRow("Тип крыши", self.roof_type_combo)
        form.addRow("Материал кровли", self.roofing_combo)
        form.addRow("Направление конька", self.roof_direction_combo)
        form.addRow("Угол наклона", self.roof_angle_spin)
        form.addRow("", self.auto_roof_height_check)
        form.addRow("Высота конька", self.roof_ridge_height_spin)
        form.addRow("Свес крыши", self.roof_overhang_spin)
        form.addRow("Высота фронтона", self.roof_gable_height_spin)
        form.addRow("Сложность", self.roof_complexity_spin)
        form.addRow("", self.auto_build_roof_button)
        form.addRow("", self.open_roof_view_button)

        display_box = QGroupBox("Отображение на плане")
        display_layout = QVBoxLayout(display_box)
        self.show_roof_ridge_check = QCheckBox("Конёк")
        self.show_roof_slopes_check = QCheckBox("Направление скатов")
        self.show_roof_overhangs_check = QCheckBox("Свесы")
        self.show_roof_dimensions_check = QCheckBox("Размеры")
        self.show_rooms_check = QCheckBox("Помещения")
        self.show_windows_check = QCheckBox("Окна")
        self.show_doors_check = QCheckBox("Двери")
        for checkbox in (
            self.show_roof_ridge_check,
            self.show_roof_slopes_check,
            self.show_roof_overhangs_check,
            self.show_roof_dimensions_check,
            self.show_rooms_check,
            self.show_windows_check,
            self.show_doors_check,
        ):
            checkbox.setChecked(True)
            display_layout.addWidget(checkbox)

        summary_box = QGroupBox("Расчёт крыши")
        summary_form = QFormLayout(summary_box)
        self._setup_form(summary_form)
        self.roof_labels: dict[str, QLabel] = {}
        for key, caption in {
            "type": "Тип крыши",
            "angle": "Угол",
            "ridge_height": "Высота конька",
            "ridge_length": "Длина конька",
            "overhang": "Свес",
            "roof_area": "Площадь кровли",
            "slope_area": "Площадь ската",
            "material": "Материал",
            "weight": "Вес кровли",
            "roofing_cost": "Стоимость кровли",
            "gable_area": "Площадь фронтонов",
            "gable_cost": "Стоимость фронтонов",
            "service_life": "Срок службы",
            "cost": "Общая стоимость крыши",
        }.items():
            label = QLabel("0")
            label.setAlignment(Qt.AlignRight)
            if key == "cost":
                label.setObjectName("TotalLabel")
            self.roof_labels[key] = label
            summary_form.addRow(caption, label)

        self.roof_preview = None

        legend_box = QGroupBox("Легенда")
        legend_layout = QVBoxLayout(legend_box)
        for text in (
            "Сплошная линия = конёк",
            "Пунктир = свес",
            "Стрелка = направление ската",
            "Заливка и вальмы = только в режиме Крыша",
        ):
            legend_layout.addWidget(QLabel(text))

        layout.addWidget(box)
        layout.addWidget(display_box)
        layout.addWidget(summary_box)
        layout.addWidget(legend_box)
        layout.addStretch()
        return container

    def _build_wall_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        self.wall_empty_label = QLabel("Ничего не выбрано.\n\nВыберите стену на плане\nили нажмите «Добавить стену».")
        self.wall_empty_label.setWordWrap(True)
        self.wall_empty_label.setAlignment(Qt.AlignCenter)
        self.wall_empty_label.setMinimumHeight(160)

        box = QGroupBox("Стена")
        self.wall_details_box = box
        form = QFormLayout(box)
        self._setup_form(form)

        self.wall_length_spin = self._meter_spin(0.2, 100.0, 0.1, 1)
        self.wall_height_spin = self._meter_spin(2.0, 8.0, 0.1, 1)
        self.wall_thickness_spin = self._meter_spin(0.05, 1.0, 0.05, 2)
        self.wall_material_combo = self._wall_combo()
        self.wall_price_spin = self._money_spin(" ₽/м²")
        self.load_bearing_check = QCheckBox("Несущая стена")

        form.addRow("Длина стены", self.wall_length_spin)
        form.addRow("Высота стены", self.wall_height_spin)
        form.addRow("Толщина стены", self.wall_thickness_spin)
        form.addRow("Материал стены", self.wall_material_combo)
        form.addRow("Цена материала", self.wall_price_spin)
        form.addRow("", self.load_bearing_check)
        layout.addWidget(self.wall_empty_label)
        layout.addWidget(box)
        layout.addStretch()
        return container

    def _build_door_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        self.door_empty_label = QLabel("Ничего не выбрано.\n\nВыберите дверь на плане\nили нажмите «Добавить дверь».")
        self.door_empty_label.setWordWrap(True)
        self.door_empty_label.setAlignment(Qt.AlignCenter)
        self.door_empty_label.setMinimumHeight(160)

        box = QGroupBox("Дверь")
        self.door_details_box = box
        form = QFormLayout(box)
        self._setup_form(form)

        self.door_template_combo = self._section_combo("door_templates", "price")
        self.door_width_spin = self._meter_spin(0.5, 4.0, 0.1, 1)
        self.door_height_spin = self._meter_spin(1.6, 3.2, 0.1, 1)
        self.door_direction_combo = QComboBox()
        self.door_direction_combo.addItems(["Внутрь", "Наружу"])
        self.door_hinge_combo = QComboBox()
        self.door_hinge_combo.addItems(["Левая", "Правая"])
        self.door_price_spin = self._money_spin(" ₽")

        form.addRow("Шаблон", self.door_template_combo)
        form.addRow("Ширина двери", self.door_width_spin)
        form.addRow("Высота двери", self.door_height_spin)
        form.addRow("Открывание", self.door_direction_combo)
        form.addRow("Петли", self.door_hinge_combo)
        form.addRow("Цена", self.door_price_spin)
        layout.addWidget(self.door_empty_label)
        layout.addWidget(box)
        layout.addStretch()
        return container

    def _build_window_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        self.window_empty_label = QLabel("Ничего не выбрано.\n\nВыберите окно на плане\nили нажмите «Добавить окно».")
        self.window_empty_label.setWordWrap(True)
        self.window_empty_label.setAlignment(Qt.AlignCenter)
        self.window_empty_label.setMinimumHeight(160)

        box = QGroupBox("Окно")
        self.window_details_box = box
        form = QFormLayout(box)
        self._setup_form(form)

        self.window_template_combo = self._section_combo("window_templates", "price")
        self.window_width_spin = self._meter_spin(0.4, 5.0, 0.1, 1)
        self.window_height_spin = self._meter_spin(0.4, 3.0, 0.1, 1)
        self.window_install_height_spin = self._meter_spin(0.0, 2.5, 0.1, 1)
        self.window_glass_combo = QComboBox()
        self.window_glass_combo.addItems(["однокамерный", "двухкамерный", "энергосберегающий", "панорамный"])
        self.window_price_spin = self._money_spin(" ₽")
        self.window_price_m2_spin = self._money_spin(" ₽/м²")
        self.window_count_spin = QSpinBox()
        self.window_count_spin.setRange(1, 100)

        form.addRow("Шаблон", self.window_template_combo)
        form.addRow("Ширина окна", self.window_width_spin)
        form.addRow("Высота окна", self.window_height_spin)
        form.addRow("Высота от пола", self.window_install_height_spin)
        form.addRow("Стеклопакет", self.window_glass_combo)
        form.addRow("Цена", self.window_price_spin)
        form.addRow("Цена за м²", self.window_price_m2_spin)
        form.addRow("Количество в смете", self.window_count_spin)
        layout.addWidget(self.window_empty_label)
        layout.addWidget(box)
        layout.addStretch()
        return container

    def _build_rooms_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        room_box = QGroupBox("Помещение")
        room_form = QFormLayout(room_box)
        self._setup_form(room_form)
        self.room_name_combo = QComboBox()
        self.room_name_combo.addItems(ROOM_TYPES)
        self.room_area_label = QLabel("0.0 м²")
        self.room_area_label.setAlignment(Qt.AlignRight)
        self.room_perimeter_label = QLabel("0.0 м")
        self.room_perimeter_label.setAlignment(Qt.AlignRight)
        self.room_floor_label = QLabel("1 этаж")
        self.room_floor_label.setAlignment(Qt.AlignRight)
        room_form.addRow("Название", self.room_name_combo)
        room_form.addRow("Этаж", self.room_floor_label)
        room_form.addRow("Площадь", self.room_area_label)
        room_form.addRow("Периметр", self.room_perimeter_label)

        hint = QLabel("Помещение ставится кликом внутри замкнутого контура. Подпись и площадь появятся на плане.")
        hint.setWordWrap(True)

        layout.addWidget(room_box)
        layout.addWidget(hint)
        layout.addStretch()
        return container

    def _build_stair_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        stair_box = QGroupBox("Лестница")
        stair_form = QFormLayout(stair_box)
        self._setup_form(stair_form)
        self.stair_type_combo = QComboBox()
        self.stair_type_combo.addItems(["Прямая", "Г-образная", "П-образная"])
        self.stair_width_spin = self._meter_spin(0.6, 2.5, 0.1, 1)
        self.stair_length_spin = self._meter_spin(1.5, 8.0, 0.1, 1)
        self.stair_rise_spin = self._meter_spin(2.0, 6.0, 0.1, 1)
        self.stair_steps_spin = QSpinBox()
        self.stair_steps_spin.setRange(3, 40)
        self.stair_steps_spin.setValue(16)
        self.stair_price_spin = self._money_spin(" ₽")
        self.stair_price_spin.setValue(120000)
        stair_form.addRow("Тип", self.stair_type_combo)
        stair_form.addRow("Ширина", self.stair_width_spin)
        stair_form.addRow("Длина", self.stair_length_spin)
        stair_form.addRow("Высота подъёма", self.stair_rise_spin)
        stair_form.addRow("Ступеней", self.stair_steps_spin)
        stair_form.addRow("Цена", self.stair_price_spin)

        hint = QLabel("Настройте лестницу, нажмите инструмент `Лестница` и кликните на плане в месте установки.")
        hint.setWordWrap(True)

        layout.addWidget(stair_box)
        layout.addWidget(hint)
        layout.addStretch()
        return container

    def _build_site_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        site_box = QGroupBox("Участок")
        site_form = QFormLayout(site_box)
        self._setup_form(site_form)
        self.site_area_spin = self._plain_spin(1.0, 50.0, 0.5, 1, " сот.")
        self.site_width_spin = self._meter_spin(5.0, 120.0, 0.5, 1)
        self.site_length_spin = self._meter_spin(5.0, 200.0, 0.5, 1)
        self.site_shape_combo = QComboBox()
        self.site_shape_combo.addItems(["Прямоугольник", "Произвольная"])
        self.site_front_setback_spin = self._meter_spin(0.0, 30.0, 0.5, 1)
        self.site_rear_setback_spin = self._meter_spin(0.0, 30.0, 0.5, 1)
        self.site_left_setback_spin = self._meter_spin(0.0, 30.0, 0.5, 1)
        self.site_right_setback_spin = self._meter_spin(0.0, 30.0, 0.5, 1)
        self.site_entry_side_combo = QComboBox()
        self.site_entry_side_combo.addItems(["Север", "Юг", "Запад", "Восток"])
        site_form.addRow("Площадь участка", self.site_area_spin)
        site_form.addRow("Ширина", self.site_width_spin)
        site_form.addRow("Длина", self.site_length_spin)
        site_form.addRow("Форма", self.site_shape_combo)
        site_form.addRow("Отступ спереди", self.site_front_setback_spin)
        site_form.addRow("Отступ сзади", self.site_rear_setback_spin)
        site_form.addRow("Отступ слева", self.site_left_setback_spin)
        site_form.addRow("Отступ справа", self.site_right_setback_spin)
        site_form.addRow("Сторона въезда", self.site_entry_side_combo)

        modes_box = QGroupBox("Режимы отображения")
        modes_layout = QVBoxLayout(modes_box)
        self.show_architecture_layer_check = QCheckBox("Архитектура")
        self.show_site_layer_check = QCheckBox("Участок")
        self.show_electric_layer_check = QCheckBox("Электрика")
        self.show_plumbing_layer_check = QCheckBox("Сантехника")
        self.show_estimate_layer_check = QCheckBox("Смета")
        for check in (
            self.show_architecture_layer_check,
            self.show_site_layer_check,
            self.show_electric_layer_check,
            self.show_plumbing_layer_check,
            self.show_estimate_layer_check,
        ):
            modes_layout.addWidget(check)

        tools_box = QGroupBox("Элементы участка")
        tools_layout = QVBoxLayout(tools_box)
        self.site_tool_buttons: dict[str, QPushButton] = {}
        site_tools = [
            ("fence", "Добавить забор"),
            ("gate", "Добавить ворота"),
            ("wicket", "Добавить калитку"),
            ("parking", "Добавить парковку"),
            ("path", "Добавить дорожку"),
            ("septic", "Добавить септик"),
            ("well", "Добавить скважину"),
            ("electric_input", "Добавить электрический ввод"),
            ("water_input", "Добавить водопровод"),
            ("landscaping", "Добавить зону озеленения"),
            ("electric_panel", "Электрощит"),
            ("outlet", "Розетка"),
            ("switch", "Выключатель"),
            ("light", "Светильник"),
            ("electric_line", "Линия электрики"),
            ("water_pipe", "Труба"),
            ("plumbing_point", "Сантехническая точка"),
            ("sewer_output", "Канализационный вывод"),
        ]
        for kind, caption in site_tools:
            button = QPushButton(caption)
            button.setMinimumHeight(42)
            button.clicked.connect(lambda checked=False, value=kind: self._activate_site_tool(value))
            self.site_tool_buttons[kind] = button
            tools_layout.addWidget(button)

        self.site_warning_label = QLabel("")
        self.site_warning_label.setObjectName("WarningLabel")
        self.site_warning_label.setWordWrap(True)

        layout.addWidget(site_box)
        layout.addWidget(modes_box)
        layout.addWidget(tools_box)
        layout.addWidget(self.site_warning_label)
        layout.addStretch()
        return container

    def _build_estimate_box(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.estimate_empty_label = QLabel("Проект не создан. Начните с добавления стен или выберите шаблон.")
        self.estimate_empty_label.setWordWrap(True)
        self.estimate_empty_label.setAlignment(Qt.AlignCenter)
        self.estimate_empty_label.setMinimumHeight(140)

        summary_box = QGroupBox("Главный итог")
        summary_form = QFormLayout(summary_box)
        self._setup_form(summary_form)
        self.summary_area_label = QLabel("0.0 м²")
        self.summary_total_label = QLabel("0 ₽")
        self.summary_cost_m2_label = QLabel("0 ₽")
        for label in (self.summary_area_label, self.summary_total_label, self.summary_cost_m2_label):
            label.setAlignment(Qt.AlignRight)
        self.summary_total_label.setObjectName("TotalLabel")
        summary_form.addRow("Площадь дома", self.summary_area_label)
        summary_form.addRow("Стоимость строительства", self.summary_total_label)
        summary_form.addRow("Стоимость за м²", self.summary_cost_m2_label)

        extra_box = QGroupBox("Дополнительные расходы")
        extra_layout = QVBoxLayout(extra_box)
        self.extra_cost_table = QTableWidget(0, 2)
        self.extra_cost_table.setHorizontalHeaderLabels(["Статья", "Сумма"])
        self.extra_cost_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.extra_cost_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.extra_cost_table.verticalHeader().setVisible(False)
        self.extra_cost_table.setAlternatingRowColors(True)
        self.extra_cost_table.setMinimumHeight(150)
        extra_layout.addWidget(self.extra_cost_table)

        extra_buttons = QHBoxLayout()
        self.add_extra_cost_button = QPushButton("Добавить расход")
        self.remove_extra_cost_button = QPushButton("Удалить строку")
        extra_buttons.addWidget(self.add_extra_cost_button)
        extra_buttons.addWidget(self.remove_extra_cost_button)
        extra_layout.addLayout(extra_buttons)

        category_box = QGroupBox("Категории сметы")
        category_layout = QVBoxLayout(category_box)
        self.estimate_category_table = QTableWidget(0, 5)
        self.estimate_category_table.setHorizontalHeaderLabels(["Категория", "Кол-во", "Ед.", "Цена", "Сумма"])
        self.estimate_category_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 5):
            self.estimate_category_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.estimate_category_table.verticalHeader().setVisible(False)
        self.estimate_category_table.setAlternatingRowColors(True)
        category_layout.addWidget(self.estimate_category_table)

        box = QGroupBox("Смета")
        self.estimate_details_box = box
        form = QFormLayout(box)
        self._setup_form(form)
        self.labels: dict[str, QLabel] = {}
        rows = {
            "floor_1_area": "Площадь 1 этажа",
            "floor_2_area": "Площадь 2 этажа",
            "house_area": "Площадь дома",
            "footprint_area": "Площадь застройки",
            "wall_length": "Длина стен",
            "wall_area": "Площадь стен",
            "total_wall_height": "Высота стен",
            "walls_cost": "Стены",
            "foundation_cost": "Фундамент",
            "roof_type": "Тип крыши",
            "roof_angle": "Угол крыши",
            "roof_ridge_height": "Высота конька",
            "roof_overhang": "Свес",
            "roofing": "Кровля",
            "roof_area": "Площадь крыши",
            "roof_slope_area": "Площадь ската",
            "gable_area": "Площадь фронтонов",
            "gable_cost": "Фронтоны",
            "roofing_cost": "Кровля",
            "roof_cost": "Крыша всего",
            "windows_cost": "Окна",
            "doors_cost": "Двери",
            "stairs_cost": "Лестница",
            "slab_cost": "Перекрытие",
            "second_floor_cost": "Второй этаж",
            "insulation_cost": "Утепление",
            "facade_cost": "Фасад",
            "site_cost": "Участок",
            "septic_cost": "Септик",
            "electric_cost": "Электрика",
            "plumbing_cost": "Сантехника",
            "complexity_extra": "Этажность/сложность",
            "extra_costs_total": "Дополнительные расходы",
            "cost_per_m2": "Цена за м²",
            "total": "Итого",
        }
        for key, caption in rows.items():
            label = QLabel("0")
            label.setAlignment(Qt.AlignRight)
            if key == "total":
                label.setObjectName("TotalLabel")
            self.labels[key] = label
            form.addRow(caption, label)
        layout.addWidget(self.estimate_empty_label)
        layout.addWidget(summary_box)
        layout.addWidget(extra_box)
        layout.addWidget(category_box)
        layout.addWidget(box)
        layout.addStretch()
        return container

    def _connect_signals(self) -> None:
        for canvas in self._all_canvases():
            canvas.project_changed.connect(self._on_project_changed)
            canvas.selection_changed.connect(self._refresh_selection_panel)
            canvas.room_place_requested.connect(self._place_room)
            canvas.tutorial_event.connect(self._handle_tutorial_event)
        self.site_canvas.project_changed.connect(self._on_project_changed)
        self.site_canvas.warning_requested.connect(self._show_site_warning)
        self.facade_side_combo.currentTextChanged.connect(self.facade_view.set_side)

        for signal in (
            self.floor_mode_combo.currentTextChanged,
            self.floor_1_height_spin.valueChanged,
            self.floor_2_height_spin.valueChanged,
            self.plinth_height_spin.valueChanged,
            self.slab_height_spin.valueChanged,
            self.project_wall_material_combo.currentIndexChanged,
            self.foundation_combo.currentIndexChanged,
            self.insulation_combo.currentIndexChanged,
            self.facade_finish_combo.currentIndexChanged,
            self.show_roof_check.toggled,
            self.auto_roof_height_check.toggled,
            self.roof_type_combo.currentIndexChanged,
            self.roof_direction_combo.currentTextChanged,
            self.roofing_combo.currentIndexChanged,
            self.roof_angle_spin.valueChanged,
            self.roof_ridge_height_spin.valueChanged,
            self.roof_overhang_spin.valueChanged,
            self.roof_gable_height_spin.valueChanged,
            self.roof_complexity_spin.valueChanged,
            self.show_roof_ridge_check.toggled,
            self.show_roof_slopes_check.toggled,
            self.show_roof_overhangs_check.toggled,
            self.show_roof_dimensions_check.toggled,
            self.show_rooms_check.toggled,
            self.show_windows_check.toggled,
            self.show_doors_check.toggled,
        ):
            signal.connect(self._apply_project_params)
        for signal in (
            self.site_area_spin.valueChanged,
            self.site_width_spin.valueChanged,
            self.site_length_spin.valueChanged,
            self.site_shape_combo.currentTextChanged,
            self.site_front_setback_spin.valueChanged,
            self.site_rear_setback_spin.valueChanged,
            self.site_left_setback_spin.valueChanged,
            self.site_right_setback_spin.valueChanged,
            self.site_entry_side_combo.currentTextChanged,
            self.show_architecture_layer_check.toggled,
            self.show_site_layer_check.toggled,
            self.show_electric_layer_check.toggled,
            self.show_plumbing_layer_check.toggled,
            self.show_estimate_layer_check.toggled,
        ):
            signal.connect(self._apply_site_params)
        self.auto_build_roof_button.clicked.connect(self._auto_build_roof)
        self.open_roof_view_button.clicked.connect(self._open_roof_view)

        self.wall_length_spin.valueChanged.connect(self._apply_wall_params)
        self.wall_height_spin.valueChanged.connect(self._apply_wall_params)
        self.wall_thickness_spin.valueChanged.connect(self._apply_wall_params)
        self.wall_material_combo.currentIndexChanged.connect(self._wall_material_changed)
        self.wall_price_spin.valueChanged.connect(self._apply_wall_params)
        self.load_bearing_check.toggled.connect(self._apply_wall_params)

        self.door_template_combo.currentIndexChanged.connect(self._door_template_changed)
        self.door_width_spin.valueChanged.connect(self._apply_door_params)
        self.door_height_spin.valueChanged.connect(self._apply_door_params)
        self.door_direction_combo.currentTextChanged.connect(self._apply_door_params)
        self.door_hinge_combo.currentTextChanged.connect(self._apply_door_params)
        self.door_price_spin.valueChanged.connect(self._apply_door_params)

        self.window_template_combo.currentIndexChanged.connect(self._window_template_changed)
        self.window_width_spin.valueChanged.connect(self._apply_window_params)
        self.window_height_spin.valueChanged.connect(self._apply_window_params)
        self.window_install_height_spin.valueChanged.connect(self._apply_window_params)
        self.window_glass_combo.currentTextChanged.connect(self._apply_window_params)
        self.window_price_spin.valueChanged.connect(self._apply_window_params)
        self.window_price_m2_spin.valueChanged.connect(self._apply_window_params)
        self.window_count_spin.valueChanged.connect(self._apply_window_params)

        self.room_name_combo.currentTextChanged.connect(self._apply_room_params)
        self.stair_type_combo.currentTextChanged.connect(self._apply_stair_params)
        self.stair_width_spin.valueChanged.connect(self._apply_stair_params)
        self.stair_length_spin.valueChanged.connect(self._apply_stair_params)
        self.stair_rise_spin.valueChanged.connect(self._apply_stair_params)
        self.stair_steps_spin.valueChanged.connect(self._apply_stair_params)
        self.stair_price_spin.valueChanged.connect(self._apply_stair_params)
        self.add_extra_cost_button.clicked.connect(self._add_extra_cost)
        self.remove_extra_cost_button.clicked.connect(self._remove_extra_cost)
        self.extra_cost_table.cellChanged.connect(self._extra_cost_cell_changed)

    def _activate_tool(self, tool: str) -> None:
        if tool == "door":
            dialog = OpeningTemplateDialog("Добавить дверь", self.materials.get("door_templates", {}), "door", self)
            if dialog.exec() != QDialog.Accepted:
                self._set_active_tool("select")
                self.canvas.set_tool("select")
                return
            self.canvas.set_door_template(dialog.values())
        elif tool == "window":
            dialog = OpeningTemplateDialog("Добавить окно", self.materials.get("window_templates", {}), "window", self)
            if dialog.exec() != QDialog.Accepted:
                self._set_active_tool("select")
                self.canvas.set_tool("select")
                return
            self.canvas.set_window_template(dialog.values())
        elif tool == "room":
            self.right_tabs.setCurrentIndex(5)
        elif tool == "stair":
            self.right_tabs.setCurrentIndex(6)
            self.canvas.set_stair_template(self._current_stair_template())
        elif tool == "roof":
            self.project.show_roof = True
            self.show_roof_check.setChecked(True)
            self.right_tabs.setCurrentIndex(2)
        elif tool == "site":
            if self.center_tabs is not None:
                self.center_tabs.setCurrentIndex(self.site_tab_index)
            self.right_tabs.setCurrentIndex(7)
            self.site_canvas.set_tool("site")
        self._set_active_tool(tool)
        if tool != "site":
            self.canvas.set_tool(tool)
        self.roof_mode_box.setVisible(tool == "roof")
        if tool == "roof":
            self.help_label.setText("Режим крыши: настройте тип, угол, конёк и кровлю справа. Подробные скаты и фронтоны показываются только в этом режиме.")
        elif tool == "room":
            self.help_label.setText("Кликните внутри контура этажа и выберите назначение помещения. Подпись и площадь появятся на плане.")
        elif tool == "stair":
            self.help_label.setText("Настройте лестницу справа, затем кликните на плане в месте установки.")
        elif tool == "delete":
            self.help_label.setText("Режим удаления: кликните по стене, окну, двери, помещению или лестнице, чтобы удалить объект.")
        elif tool == "site":
            self.help_label.setText("Участок: выберите объект справа и кликните на плане участка, чтобы поставить его.")
        else:
            self.help_label.setText("Окна и двери выбираются по шаблону и ставятся кликом по существующей стене.")
        self._refresh_roof_mode_summary()

    def _set_active_tool(self, tool: str) -> None:
        if tool in self.tool_buttons:
            self.tool_buttons[tool].setChecked(True)

    def _apply_project_params(self) -> None:
        if self._updating_controls:
            return
        self.project.floor_mode = self.floor_mode_combo.currentText()
        self.project.floors = 2 if self.project.floor_mode == "2 этажа" else 1
        self.project.floor_1_height = float(self.floor_1_height_spin.value())
        self.project.floor_2_height = float(self.floor_2_height_spin.value())
        self.project.wall_height = self.project.floor_1_height
        self.project.plinth_height = float(self.plinth_height_spin.value())
        self.project.slab_height = float(self.slab_height_spin.value())
        self.project.wall_material = self._combo_value(self.project_wall_material_combo)
        self.project.foundation_type = self._combo_value(self.foundation_combo)
        self.project.insulation_type = self._combo_value(self.insulation_combo)
        self.project.facade_finish = self._combo_value(self.facade_finish_combo)
        self.project.finishing = self.project.facade_finish
        self.project.roof_type = self._combo_value(self.roof_type_combo)
        self.project.roof_ridge_direction = self.roof_direction_combo.currentText()
        self.project.roofing = self._combo_value(self.roofing_combo)
        self.project.roof_angle = float(self.roof_angle_spin.value())
        self.project.auto_roof_ridge_height = self.auto_roof_height_check.isChecked()
        auto_ridge_active = self.project.auto_roof_ridge_height and self.project.roof_type == "Двускатная"
        if not auto_ridge_active:
            self.project.roof_ridge_height = float(self.roof_ridge_height_spin.value())
        self.project.roof_overhang = float(self.roof_overhang_spin.value())
        self.project.roof_gable_height = float(self.roof_gable_height_spin.value())
        self.project.roof_complexity = float(self.roof_complexity_spin.value())
        self.project.show_roof = self.show_roof_check.isChecked()
        self.project.show_roof_ridge = self.show_roof_ridge_check.isChecked()
        self.project.show_roof_slopes = self.show_roof_slopes_check.isChecked()
        self.project.show_roof_overhangs = self.show_roof_overhangs_check.isChecked()
        self.project.show_roof_dimensions = self.show_roof_dimensions_check.isChecked()
        self.project.show_rooms = self.show_rooms_check.isChecked()
        self.project.show_windows = self.show_windows_check.isChecked()
        self.project.show_doors = self.show_doors_check.isChecked()
        self.project.update_auto_roof_height()
        self.auto_roof_height_check.setEnabled(self.project.roof_type == "Двускатная")
        self.roof_ridge_height_spin.setEnabled(not auto_ridge_active)
        if auto_ridge_active:
            self.roof_ridge_height_spin.blockSignals(True)
            self.roof_ridge_height_spin.setValue(self.project.roof_ridge_height)
            self.roof_ridge_height_spin.blockSignals(False)
        self.project.ensure_floor_count(max(1, self.project.floors))
        self._sync_floor_tabs()
        self._refresh_estimate()
        for canvas in self._all_canvases():
            canvas.update()
        self.facade_view.update()
        self.section_view.update()
        if self.roof_preview is not None:
            self.roof_preview.update()

    def _apply_wall_params(self) -> None:
        if self._updating_controls or self.canvas.selected_kind != "wall" or self.canvas.selected_index < 0:
            return
        wall = self._active_floor().walls[self.canvas.selected_index]
        wall.height = float(self.wall_height_spin.value())
        wall.thickness = float(self.wall_thickness_spin.value())
        wall.material = self._combo_value(self.wall_material_combo)
        wall.price_per_m2 = float(self.wall_price_spin.value())
        wall.is_load_bearing = self.load_bearing_check.isChecked()
        self.canvas.resize_selected_wall(float(self.wall_length_spin.value()))
        self._refresh_estimate()
        for canvas in self._all_canvases():
            canvas.update()
        self.facade_view.update()
        self.section_view.update()

    def _wall_material_changed(self) -> None:
        if self._updating_controls:
            return
        material = self._combo_value(self.wall_material_combo)
        info = wall_material_info(self.materials, material)
        thickness = float(info.get("thickness_m", self.wall_thickness_spin.value()) or self.wall_thickness_spin.value())
        rate = float(info.get("price_per_m2", 0) or 0)
        if not rate and float(info.get("price_per_m3", 0) or 0):
            rate = float(info.get("price_per_m3", 0)) * thickness
        self.wall_thickness_spin.blockSignals(True)
        self.wall_price_spin.blockSignals(True)
        self.wall_thickness_spin.setValue(thickness)
        self.wall_price_spin.setValue(rate)
        self.wall_thickness_spin.blockSignals(False)
        self.wall_price_spin.blockSignals(False)
        self._apply_wall_params()

    def _door_template_changed(self) -> None:
        if self._updating_controls or self.canvas.selected_kind != "door":
            return
        name = self._combo_value(self.door_template_combo)
        data = self._template_payload("door_templates", name)
        self._updating_controls = True
        try:
            self.door_width_spin.setValue(float(data.get("width", self.door_width_spin.value()) or self.door_width_spin.value()))
            self.door_height_spin.setValue(float(data.get("height", self.door_height_spin.value()) or self.door_height_spin.value()))
            self.door_direction_combo.setCurrentText(str(data.get("opening_direction", self.door_direction_combo.currentText())))
            self.door_hinge_combo.setCurrentText(str(data.get("hinge_side", self.door_hinge_combo.currentText())))
            self.door_price_spin.setValue(float(data.get("price", self.door_price_spin.value()) or 0))
        finally:
            self._updating_controls = False
        self._apply_door_params()

    def _apply_door_params(self) -> None:
        if self._updating_controls or self.canvas.selected_kind != "door" or self.canvas.selected_index < 0:
            return
        floor = self._active_floor()
        door = floor.doors[self.canvas.selected_index]
        door.template_name = self._combo_value(self.door_template_combo)
        door.width = float(self.door_width_spin.value())
        door.height = float(self.door_height_spin.value())
        door.opening_direction = self.door_direction_combo.currentText()
        door.hinge_side = self.door_hinge_combo.currentText()
        door.price = float(self.door_price_spin.value())
        if door.wall_index < len(floor.walls):
            door.distance_from_start = door.position * floor.walls[door.wall_index].length_m
        self._refresh_estimate()
        self.canvas.update()
        self.facade_view.update()
        self.section_view.update()

    def _window_template_changed(self) -> None:
        if self._updating_controls or self.canvas.selected_kind != "window":
            return
        name = self._combo_value(self.window_template_combo)
        data = self._template_payload("window_templates", name)
        self._updating_controls = True
        try:
            self.window_width_spin.setValue(float(data.get("width", self.window_width_spin.value()) or self.window_width_spin.value()))
            self.window_height_spin.setValue(float(data.get("height", self.window_height_spin.value()) or self.window_height_spin.value()))
            self.window_install_height_spin.setValue(float(data.get("sill_height", self.window_install_height_spin.value()) or self.window_install_height_spin.value()))
            self.window_glass_combo.setCurrentText(str(data.get("glass_type", self.window_glass_combo.currentText())))
            self.window_price_spin.setValue(float(data.get("price", self.window_price_spin.value()) or 0))
            self.window_price_m2_spin.setValue(float(data.get("price_per_m2", self.window_price_m2_spin.value()) or 0))
        finally:
            self._updating_controls = False
        self._apply_window_params()

    def _apply_window_params(self) -> None:
        if self._updating_controls or self.canvas.selected_kind != "window" or self.canvas.selected_index < 0:
            return
        floor = self._active_floor()
        window = floor.windows[self.canvas.selected_index]
        window.template_name = self._combo_value(self.window_template_combo)
        window.width = float(self.window_width_spin.value())
        window.height = float(self.window_height_spin.value())
        window.install_height = float(self.window_install_height_spin.value())
        window.glass_type = self.window_glass_combo.currentText()
        window.price = float(self.window_price_spin.value())
        window.price_per_m2 = float(self.window_price_m2_spin.value())
        window.count = int(self.window_count_spin.value())
        if window.wall_index < len(floor.walls):
            window.distance_from_start = window.position * floor.walls[window.wall_index].length_m
        self._refresh_estimate()
        self.canvas.update()
        self.facade_view.update()

    def _refresh_estimate(self) -> None:
        self._recalculate_rooms()
        self.estimate = calculate_estimate(self.project, self.materials)
        has_walls = self._project_has_walls()
        if hasattr(self, "estimate_empty_label"):
            self.estimate_empty_label.setVisible(not has_walls)
        if hasattr(self, "estimate_details_box"):
            self.estimate_details_box.setVisible(has_walls)
        self.labels["floor_1_area"].setText(f"{self.estimate['floor_1_area']:.1f} м²")
        self.labels["floor_2_area"].setText(f"{self.estimate['floor_2_area']:.1f} м²")
        self.labels["house_area"].setText(f"{self.estimate['house_area']:.1f} м²")
        self.labels["footprint_area"].setText(f"{self.estimate['footprint_area']:.1f} м²")
        self.labels["wall_length"].setText(f"{self.estimate['wall_length']:.1f} м")
        self.labels["wall_area"].setText(f"{self.estimate['wall_area']:.1f} м²")
        self.labels["total_wall_height"].setText(f"{self.estimate['total_wall_height']:.1f} м")
        self.labels["walls_cost"].setText(format_money(self.estimate["walls_cost"]))
        self.labels["foundation_cost"].setText(format_money(self.estimate["foundation_cost"]))
        self.labels["roof_type"].setText(self.project.roof_type)
        self.labels["roof_angle"].setText(f"{self.project.roof_angle:.0f}°")
        self.labels["roof_ridge_height"].setText(f"{self.project.roof_ridge_height:.1f} м")
        self.labels["roof_overhang"].setText(f"{self.project.roof_overhang:.1f} м")
        self.labels["roofing"].setText(self.project.roofing)
        self.labels["roof_area"].setText(f"{self.estimate['roof_area']:.1f} м²")
        self.labels["roof_slope_area"].setText(
            f"{int(self.estimate['roof_slope_count'])} x {self.estimate['roof_slope_area']:.1f} м²"
        )
        self.labels["gable_area"].setText(f"{self.estimate['gable_area']:.1f} м²")
        self.labels["gable_cost"].setText(format_money(self.estimate["gable_cost"]))
        self.labels["roofing_cost"].setText(format_money(self.estimate["roofing_cost"]))
        self.labels["roof_cost"].setText(format_money(self.estimate["roof_cost"]))
        self.labels["windows_cost"].setText(format_money(self.estimate["windows_cost"]))
        self.labels["doors_cost"].setText(format_money(self.estimate["doors_cost"]))
        self.labels["stairs_cost"].setText(format_money(self.estimate["stairs_cost"]))
        self.labels["slab_cost"].setText(format_money(self.estimate["slab_cost"]))
        self.labels["second_floor_cost"].setText(format_money(self.estimate["second_floor_cost"]))
        self.labels["insulation_cost"].setText(format_money(self.estimate["insulation_cost"]))
        self.labels["facade_cost"].setText(format_money(self.estimate["facade_cost"]))
        self.labels["site_cost"].setText(format_money(self.estimate["site_cost"]))
        self.labels["septic_cost"].setText(format_money(self.estimate["septic_cost"]))
        self.labels["electric_cost"].setText(format_money(self.estimate["electric_cost"]))
        self.labels["plumbing_cost"].setText(format_money(self.estimate["plumbing_cost"]))
        self.labels["complexity_extra"].setText(format_money(self.estimate["complexity_extra"]))
        self.labels["extra_costs_total"].setText(format_money(self.estimate["extra_costs_total"]))
        self.labels["cost_per_m2"].setText(format_money(self.estimate["cost_per_m2"]))
        self.labels["total"].setText(format_money(self.estimate["total"]))
        if hasattr(self, "summary_area_label"):
            self.summary_area_label.setText(f"{self.estimate['house_area']:.1f} м²")
            self.summary_total_label.setText(format_money(self.estimate["total"]))
            self.summary_cost_m2_label.setText(format_money(self.estimate["cost_per_m2"]))
        if hasattr(self, "extra_cost_table"):
            self._refresh_extra_cost_table()
        if hasattr(self, "estimate_category_table"):
            self._refresh_estimate_category_table()
        if hasattr(self, "roof_ridge_height_spin") and self.project.auto_roof_ridge_height and self.project.roof_type == "Двускатная":
            self.roof_ridge_height_spin.blockSignals(True)
            self.roof_ridge_height_spin.setValue(self.project.roof_ridge_height)
            self.roof_ridge_height_spin.blockSignals(False)
        if hasattr(self, "roof_labels"):
            self.roof_labels["type"].setText(self.project.roof_type)
            self.roof_labels["angle"].setText(f"{self.project.roof_angle:.0f}°")
            self.roof_labels["ridge_height"].setText(f"{self.project.roof_ridge_height:.1f} м")
            self.roof_labels["ridge_length"].setText(f"{self.estimate['roof_ridge_length']:.1f} м")
            self.roof_labels["overhang"].setText(f"{self.project.roof_overhang:.1f} м")
            self.roof_labels["roof_area"].setText(f"{self.estimate['roof_area']:.1f} м²")
            self.roof_labels["slope_area"].setText(
                f"{int(self.estimate['roof_slope_count'])} x {self.estimate['roof_slope_area']:.1f} м²"
            )
            self.roof_labels["material"].setText(self.project.roofing)
            self.roof_labels["weight"].setText(f"{self.estimate['roof_weight']:.0f} кг")
            self.roof_labels["roofing_cost"].setText(format_money(self.estimate["roofing_cost"]))
            self.roof_labels["gable_area"].setText(f"{self.estimate['gable_area']:.1f} м²")
            self.roof_labels["gable_cost"].setText(format_money(self.estimate["gable_cost"]))
            self.roof_labels["service_life"].setText(f"{self.estimate['roof_service_life']:.0f} лет")
            self.roof_labels["cost"].setText(format_money(self.estimate["roof_cost"]))
        self._refresh_roof_mode_summary()
        self._refresh_explanation()
        self.facade_view.update()
        self.section_view.update()
        if self.roof_preview is not None:
            self.roof_preview.update()
        self.site_canvas.update()

    def _project_has_walls(self) -> bool:
        return any(floor.walls for floor in self.project.all_floors())

    def _refresh_roof_mode_summary(self) -> None:
        if not hasattr(self, "roof_mode_labels") or not self.estimate:
            return
        self.roof_mode_labels["type"].setText(self.project.roof_type)
        self.roof_mode_labels["angle"].setText(f"{self.project.roof_angle:.0f}°")
        self.roof_mode_labels["ridge"].setText(f"{self.project.roof_ridge_height:.1f} м")
        self.roof_mode_labels["area"].setText(f"{self.estimate['roof_area']:.1f} м²")
        self.roof_mode_labels["slope"].setText(
            f"{int(self.estimate['roof_slope_count'])} x {self.estimate['roof_slope_area']:.1f}"
        )
        self.roof_mode_labels["cost"].setText(format_money(self.estimate["roof_cost"]))

    def _refresh_selection_panel(self, kind: str, index: int) -> None:
        self._sync_selection_placeholders(kind, index)
        self._updating_controls = True
        try:
            if kind == "wall" and index >= 0:
                self.right_tabs.setCurrentIndex(1)
                wall = self._active_floor().walls[index]
                self.wall_length_spin.setValue(max(0.2, wall.length_m))
                self.wall_height_spin.setValue(wall.height)
                self.wall_thickness_spin.setValue(wall.thickness)
                self._set_combo_value(self.wall_material_combo, wall.material)
                self.wall_price_spin.setValue(float(wall.price_per_m2 or self._wall_rate(wall.material, wall.thickness)))
                self.load_bearing_check.setChecked(wall.is_load_bearing)
            elif kind == "door" and index >= 0:
                self.right_tabs.setCurrentIndex(4)
                door = self._active_floor().doors[index]
                self._set_combo_value(self.door_template_combo, door.template_name)
                self.door_width_spin.setValue(door.width)
                self.door_height_spin.setValue(door.height)
                self.door_direction_combo.setCurrentText(door.opening_direction)
                self.door_hinge_combo.setCurrentText(door.hinge_side)
                self.door_price_spin.setValue(door.price)
            elif kind == "window" and index >= 0:
                self.right_tabs.setCurrentIndex(3)
                window = self._active_floor().windows[index]
                self._set_combo_value(self.window_template_combo, window.template_name)
                self.window_width_spin.setValue(window.width)
                self.window_height_spin.setValue(window.height)
                self.window_install_height_spin.setValue(window.install_height)
                self.window_glass_combo.setCurrentText(window.glass_type)
                self.window_price_spin.setValue(window.price)
                self.window_price_m2_spin.setValue(window.price_per_m2)
                self.window_count_spin.setValue(window.count)
            elif kind == "room" and index >= 0:
                self.right_tabs.setCurrentIndex(5)
                room = self._active_floor().rooms[index]
                self.room_name_combo.setCurrentText(room.name)
                self.room_floor_label.setText(f"{room.floor} этаж")
                self.room_area_label.setText(f"{room.area:.1f} м²")
                self.room_perimeter_label.setText(f"{room.perimeter:.1f} м")
            elif kind == "stair" and index >= 0:
                self.right_tabs.setCurrentIndex(6)
                stair = self._active_floor().stairs[index]
                self.stair_type_combo.setCurrentText(stair.stair_type)
                self.stair_width_spin.setValue(stair.width)
                self.stair_length_spin.setValue(stair.length)
                self.stair_rise_spin.setValue(stair.rise_height)
                self.stair_steps_spin.setValue(stair.steps)
                self.stair_price_spin.setValue(stair.price)
            elif kind == "roof":
                self.right_tabs.setCurrentIndex(2)
                self.project.show_roof = True
                if hasattr(self, "show_roof_check"):
                    self.show_roof_check.setChecked(True)
            else:
                self.right_tabs.setCurrentIndex(0)
                self._sync_controls_from_project()
        finally:
            self._updating_controls = False

    def _sync_selection_placeholders(self, kind: str, index: int) -> None:
        selected = index >= 0
        states = {
            "wall": selected and kind == "wall",
            "door": selected and kind == "door",
            "window": selected and kind == "window",
        }
        pairs = (
            ("wall", "wall_empty_label", "wall_details_box"),
            ("door", "door_empty_label", "door_details_box"),
            ("window", "window_empty_label", "window_details_box"),
        )
        for object_kind, empty_name, details_name in pairs:
            empty = getattr(self, empty_name, None)
            details = getattr(self, details_name, None)
            has_object = states[object_kind]
            if empty is not None:
                empty.setVisible(not has_object)
            if details is not None:
                details.setVisible(has_object)
        if hasattr(self, "no_selection_label"):
            self.no_selection_label.setVisible(kind in ("project", "") or index < 0)

    def _on_project_changed(self) -> None:
        self._refresh_estimate()
        for canvas in self._all_canvases():
            canvas.update()
        self.site_canvas.update()

    def _center_tab_changed(self, index: int) -> None:
        if index == getattr(self, "site_tab_index", -1):
            if "site" in self.tool_buttons:
                self.tool_buttons["site"].setChecked(True)
            self.right_tabs.setCurrentIndex(7)
            return
        if index == getattr(self, "plan2_tab_index", -1):
            self.canvas = self.canvas2
        else:
            self.canvas = self.canvas1
        checked_tool = next((tool for tool, button in self.tool_buttons.items() if button.isChecked()), "select")
        self.canvas.set_tool(checked_tool)
        self._refresh_selection_panel(self.canvas.selected_kind, self.canvas.selected_index)

    def _sync_floor_tabs(self) -> None:
        if self.center_tabs is None:
            return
        show_second = self.project.floor_mode == "2 этажа"
        self.center_tabs.setTabVisible(self.plan2_tab_index, show_second)
        self.copy_second_floor_button.setVisible(show_second)
        self._sync_floor_controls_visibility()
        if not show_second and self.center_tabs.currentIndex() == self.plan2_tab_index:
            self.center_tabs.setCurrentIndex(self.plan1_tab_index)
            self.canvas = self.canvas1

    def _sync_floor_controls_visibility(self) -> None:
        show_second = self.project.floor_mode == "2 этажа"
        for widget in (
            getattr(self, "floor_2_height_label", None),
            getattr(self, "floor_2_height_spin", None),
            getattr(self, "slab_height_label", None),
            getattr(self, "slab_height_spin", None),
        ):
            if widget is not None:
                widget.setVisible(show_second)

    def _delete_selected(self) -> None:
        self.canvas.delete_selected_element()
        self._refresh_explanation()

    def _fit_current_project(self) -> None:
        self.canvas.fit_project_to_view()

    def _activate_site_tool(self, kind: str) -> None:
        if self.center_tabs is not None:
            self.center_tabs.setCurrentIndex(self.site_tab_index)
        self.right_tabs.setCurrentIndex(7)
        self.site_canvas.set_tool(kind)
        preset = SITE_ELEMENT_PRESETS.get(kind, {})
        name = preset.get("name", "элемент")
        if kind == "fence":
            self.help_label.setText("Забор добавляется по периметру участка. Нажмите на плане участка в любом месте.")
        else:
            self.help_label.setText(f"Кликните на плане участка, чтобы поставить: {name}.")

    def _apply_site_params(self) -> None:
        if self._updating_controls:
            return
        site = self.project.site
        sender = self.sender()
        site.area_sotka = float(self.site_area_spin.value())
        if sender == self.site_area_spin:
            width, length = self._suggest_site_size(site.area_sotka)
            self.site_width_spin.blockSignals(True)
            self.site_length_spin.blockSignals(True)
            self.site_width_spin.setValue(width)
            self.site_length_spin.setValue(length)
            self.site_width_spin.blockSignals(False)
            self.site_length_spin.blockSignals(False)
        site.width_m = float(self.site_width_spin.value())
        site.length_m = float(self.site_length_spin.value())
        site.shape = self.site_shape_combo.currentText()
        site.front_setback_m = float(self.site_front_setback_spin.value())
        site.rear_setback_m = float(self.site_rear_setback_spin.value())
        site.left_setback_m = float(self.site_left_setback_spin.value())
        site.right_setback_m = float(self.site_right_setback_spin.value())
        site.entry_side = self.site_entry_side_combo.currentText()
        self.project.show_architecture_layer = self.show_architecture_layer_check.isChecked()
        self.project.show_site_layer = self.show_site_layer_check.isChecked()
        self.project.show_electric_layer = self.show_electric_layer_check.isChecked()
        self.project.show_plumbing_layer = self.show_plumbing_layer_check.isChecked()
        self.project.show_estimate_layer = self.show_estimate_layer_check.isChecked()
        self.site_canvas.update()
        self._refresh_estimate()

    def _suggest_site_size(self, area_sotka: float) -> tuple[float, float]:
        if abs(area_sotka - 6.0) <= 0.25:
            return 20.0, 30.0
        if abs(area_sotka - 8.0) <= 0.25:
            return 20.0, 40.0
        if abs(area_sotka - 10.0) <= 0.25:
            return 25.0, 40.0
        area_m2 = max(100.0, area_sotka * 100.0)
        width = max(10.0, round((area_m2 / 1.5) ** 0.5, 1))
        length = round(area_m2 / width, 1)
        return width, length

    def _show_site_warning(self, text: str) -> None:
        self.site_warning_label.setText(text)
        self.right_tabs.setCurrentIndex(7)

    def _auto_build_roof(self) -> None:
        width_m, depth_m = self.project.footprint_bounds_m()
        if width_m <= 0 or depth_m <= 0:
            QMessageBox.information(self, "Крыша", "Сначала нарисуйте внешний контур дома.")
            return
        corners = self._footprint_corner_count()
        self.project.roof_type = "Двускатная" if corners <= 4 else "Вальмовая"
        self.project.roof_ridge_direction = "по X" if width_m >= depth_m else "по Y"
        self.project.roof_angle = 30.0 if self.project.roof_type == "Двускатная" else 25.0
        self.project.roof_overhang = max(0.4, self.project.roof_overhang)
        self.project.show_roof = True
        self.project.auto_roof_ridge_height = self.project.roof_type == "Двускатная"
        self.project.update_auto_roof_height()
        self._sync_controls_from_project()
        for canvas in self._all_canvases():
            canvas.update()

    def _footprint_corner_count(self) -> int:
        seen: set[tuple[float, float]] = set()
        for wall in self.project.get_floor(1).walls:
            for point in (wall.start, wall.end):
                seen.add((round(point.x, 2), round(point.y, 2)))
        return len(seen)

    def _open_roof_view(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Схема крыши")
        dialog.resize(980, 720)
        layout = QVBoxLayout(dialog)
        viewer = RoofPreviewWidget(self.project)
        viewer.setMinimumSize(900, 620)
        layout.addWidget(viewer, stretch=1)
        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        dialog.exec()

    def _create_second_floor_from_first(self) -> None:
        self.project.create_second_floor_from_first()
        self.floor_mode_combo.setCurrentText("2 этажа")
        self._sync_floor_tabs()
        if self.center_tabs is not None:
            self.center_tabs.setCurrentIndex(self.plan2_tab_index)
        self._refresh_estimate()
        for canvas in self._all_canvases():
            canvas.update()
        QTimer.singleShot(0, self._fit_current_project)

    def _place_room(self, x: float, y: float, floor_level: int) -> None:
        name, ok = QInputDialog.getItem(self, "Помещение", "Выберите назначение помещения", ROOM_TYPES, 0, False)
        if not ok or not name:
            return
        floor = self.project.get_floor(floor_level)
        area, perimeter = self._room_metrics_for_floor(floor_level, x, y)
        room = RoomItem(name=name, floor=floor_level, center=Point(x, y), area=area, perimeter=perimeter)
        floor.rooms.append(room)
        self.canvas._select("room", len(floor.rooms) - 1)
        self._refresh_selection_panel("room", len(floor.rooms) - 1)
        self._refresh_estimate()
        self.canvas.update()

    def _room_metrics_for_floor(self, floor_level: int, x: float | None = None, y: float | None = None) -> tuple[float, float]:
        floor = self.project.get_floor(floor_level)
        exterior_walls = [wall for wall in floor.walls if wall.is_load_bearing] or floor.walls
        if x is not None and y is not None:
            tolerance = 6.0
            verticals: list[float] = []
            horizontals: list[float] = []
            for wall in floor.walls:
                dx = abs(wall.end.x - wall.start.x)
                dy = abs(wall.end.y - wall.start.y)
                min_x, max_x = sorted((wall.start.x, wall.end.x))
                min_y, max_y = sorted((wall.start.y, wall.end.y))
                if dx <= tolerance and min_y - tolerance <= y <= max_y + tolerance:
                    verticals.append((wall.start.x + wall.end.x) / 2)
                if dy <= tolerance and min_x - tolerance <= x <= max_x + tolerance:
                    horizontals.append((wall.start.y + wall.end.y) / 2)
            left = max((value for value in verticals if value < x), default=None)
            right = min((value for value in verticals if value > x), default=None)
            top = max((value for value in horizontals if value < y), default=None)
            bottom = min((value for value in horizontals if value > y), default=None)
            if left is not None and right is not None and top is not None and bottom is not None:
                width_m = (right - left) / PIXELS_PER_METER
                depth_m = (bottom - top) / PIXELS_PER_METER
                if width_m > 0 and depth_m > 0:
                    return width_m * depth_m, 2 * (width_m + depth_m)
        area = self.project.floor_area_m2(floor_level)
        perimeter = sum(wall.length_m for wall in exterior_walls)
        return area, perimeter

    def _recalculate_rooms(self) -> None:
        for floor in self.project.all_floors():
            for room in floor.rooms:
                area, perimeter = self._room_metrics_for_floor(floor.level, room.center.x, room.center.y)
                caps = {
                    "Санузел": 6.0,
                    "Ванная": 8.0,
                    "Котельная": 7.0,
                    "Гардероб": 6.0,
                    "Кладовая": 5.0,
                    "Постирочная": 6.0,
                    "Прихожая": 8.0,
                    "Коридор": 10.0,
                    "Терраса": 16.0,
                }
                cap = next((limit for name, limit in caps.items() if room.name.startswith(name)), None)
                if cap is not None and area > cap:
                    area = cap
                    perimeter = 4 * (area ** 0.5)
                room.area, room.perimeter = area, perimeter

    def _apply_room_params(self) -> None:
        if self._updating_controls or self.canvas.selected_kind != "room" or self.canvas.selected_index < 0:
            return
        room = self._active_floor().rooms[self.canvas.selected_index]
        room.name = self.room_name_combo.currentText()
        self.canvas.update()
        self._refresh_explanation()

    def _current_stair_template(self) -> dict[str, object]:
        if not hasattr(self, "stair_type_combo"):
            return {
                "stair_type": "Прямая",
                "width": 0.9,
                "length": 3.0,
                "rise_height": 3.1,
                "steps": 16,
                "price": 120000.0,
            }
        return {
            "stair_type": self.stair_type_combo.currentText(),
            "width": float(self.stair_width_spin.value()),
            "length": float(self.stair_length_spin.value()),
            "rise_height": float(self.stair_rise_spin.value()),
            "steps": int(self.stair_steps_spin.value()),
            "price": float(self.stair_price_spin.value()),
        }

    def _apply_stair_params(self) -> None:
        if self._updating_controls:
            return
        template = self._current_stair_template()
        for canvas in self._all_canvases():
            canvas.set_stair_template(template)
        if self.canvas.selected_kind == "stair" and self.canvas.selected_index >= 0:
            stair = self._active_floor().stairs[self.canvas.selected_index]
            stair.stair_type = str(template["stair_type"])
            stair.width = float(template["width"])
            stair.length = float(template["length"])
            stair.rise_height = float(template["rise_height"])
            stair.steps = int(template["steps"])
            stair.price = float(template["price"])
            self._refresh_estimate()
            self.canvas.update()
            self.section_view.update()

    def _refresh_extra_cost_table(self) -> None:
        table = self.extra_cost_table
        table.blockSignals(True)
        try:
            table.setRowCount(len(self.project.extra_costs))
            for row, item in enumerate(self.project.extra_costs):
                name_item = QTableWidgetItem(item.name)
                amount_item = QTableWidgetItem(f"{item.amount:.0f}")
                amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(row, 0, name_item)
                table.setItem(row, 1, amount_item)
        finally:
            table.blockSignals(False)

    def _add_extra_cost(self) -> None:
        presets = [
            "Работа строителей",
            "Доставка материалов",
            "Аренда техники",
            "Подключение электричества",
            "Скважина",
            "Септик",
            "Благоустройство",
            "Своя статья",
        ]
        name, ok = QInputDialog.getItem(self, "Дополнительный расход", "Выберите статью", presets, 0, False)
        if not ok or not name:
            return
        if name == "Своя статья":
            name, ok = QInputDialog.getText(self, "Своя статья", "Название расхода")
            if not ok or not name.strip():
                return
            name = name.strip()
        amount, ok = QInputDialog.getDouble(self, "Сумма расхода", "Сумма, ₽", 0, 0, 100000000, 0)
        if not ok:
            return
        self.project.extra_costs.append(ExtraCostItem(name=name, amount=float(amount)))
        self._refresh_estimate()

    def _remove_extra_cost(self) -> None:
        row = self.extra_cost_table.currentRow()
        if 0 <= row < len(self.project.extra_costs):
            del self.project.extra_costs[row]
            self._refresh_estimate()

    def _extra_cost_cell_changed(self, row: int, column: int) -> None:
        if self._updating_controls or not (0 <= row < len(self.project.extra_costs)):
            return
        table_item = self.extra_cost_table.item(row, column)
        if table_item is None:
            return
        extra = self.project.extra_costs[row]
        if column == 0:
            extra.name = table_item.text().strip() or "Дополнительный расход"
        else:
            raw = table_item.text().replace("₽", "").replace(" ", "").replace(",", ".")
            try:
                extra.amount = max(0.0, float(raw))
            except ValueError:
                extra.amount = 0.0
        self._refresh_estimate()

    def _refresh_estimate_category_table(self) -> None:
        rows = self.estimate.get("estimate_categories", [])
        table = self.estimate_category_table
        table.blockSignals(True)
        try:
            table.setRowCount(len(rows))
            for row, data in enumerate(rows):
                values = [
                    str(data.get("category", "")),
                    f"{float(data.get('quantity', 0)):.0f}",
                    str(data.get("unit", "")),
                    format_money(float(data.get("price", 0))),
                    format_money(float(data.get("amount", 0))),
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column in (1, 3, 4):
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    table.setItem(row, column, item)
        finally:
            table.blockSignals(False)

    def _refresh_explanation(self) -> None:
        if self.explanation_table is None:
            return
        rooms = self.project.all_rooms()
        self.explanation_table.setRowCount(len(rooms))
        total = 0.0
        for row, room in enumerate(rooms):
            total += room.area
            values = [f"Этаж {room.floor}", room.name, f"{room.area:.1f} м²", f"{room.perimeter:.1f} м"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in (2, 3):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.explanation_table.setItem(row, column, item)
        if hasattr(self, "explanation_total_label"):
            self.explanation_total_label.setText(f"Итого площадь: {total:.1f} м²")

    def _show_welcome_or_start(self) -> None:
        app = QApplication.instance()
        if app is not None and app.platformName().lower() == "offscreen":
            return
        if not self.settings.value("welcome_hidden", False, type=bool):
            dialog = WelcomeDialog(self)
            accepted = dialog.exec() == QDialog.Accepted
            if dialog.hide_check.isChecked():
                self.settings.setValue("welcome_hidden", True)
            if accepted and dialog.action:
                self._handle_welcome_action(dialog.action)
                return
        self._show_start_screen()

    def _handle_welcome_action(self, action: str) -> None:
        if action == "new":
            self._new_project_with_floor_mode("1 этаж")
        elif action == "template":
            self._choose_house_template()
        elif action == "demo":
            self._open_demo_project()
        elif action == "tutorial":
            self._new_project_with_floor_mode("1 этаж")
            self._start_tutorial()
        elif action == "open":
            self._open_project()

    def _start_tutorial(self) -> None:
        self._tutorial_active = True
        self._tutorial_stage = "need_wall"
        self._set_active_tool("wall")
        self.canvas.set_tool("wall")
        self.help_label.setText("Шаг 1: Нарисуйте внешний контур дома.")
        if "wall" in self.tool_buttons:
            self.tool_buttons["wall"].setChecked(True)
            self._show_tutorial_bubble(self.tool_buttons["wall"], "Шаг 1. Нажмите «Добавить стену» и нарисуйте внешний контур дома.")

    def _handle_tutorial_event(self, event_name: str) -> None:
        if not self._tutorial_active:
            return
        if event_name == "wall_added" and self._tutorial_stage == "need_wall":
            self._tutorial_stage = "need_contour"
            self.help_label.setText("Продолжайте рисовать стены. Замкните контур дома.")
            self._show_tutorial_bubble(self.canvas, "Продолжайте рисовать стены. Когда последняя стена соединится с первой, контур будет замкнут.")
        elif event_name == "contour_closed":
            self._tutorial_stage = "need_openings"
            self.help_label.setText("Дом создан. Теперь добавьте окна и двери.")
            if "door" in self.tool_buttons:
                self.tool_buttons["door"].setChecked(True)
                self._show_tutorial_bubble(self.tool_buttons["door"], "Дом создан. Теперь добавьте дверь на существующую стену.")
        elif event_name == "door_added":
            self._tutorial_stage = "need_window"
            self.help_label.setText("Вы можете менять направление открывания двери в настройках справа.")
            if "window" in self.tool_buttons:
                self._show_tutorial_bubble(self.tool_buttons["window"], "Теперь добавьте окно. Его размеры и тип остекления можно менять справа.")
        elif event_name == "window_added":
            self._tutorial_stage = "done"
            self._tutorial_active = False
            self.help_label.setText("Вы можете изменять размеры окна и тип остекления в настройках справа.")
            self._hide_tutorial_bubble()

    def _show_tutorial_bubble(self, target: QWidget | None, text: str) -> None:
        if hasattr(self, "tutorial_overlay"):
            self.tutorial_overlay.show_tip(target, text)

    def _hide_tutorial_bubble(self) -> None:
        if hasattr(self, "tutorial_overlay"):
            self.tutorial_overlay.hide()

    def _reset_tips(self) -> None:
        self.settings.setValue("welcome_hidden", False)
        self._start_tutorial()

    def _check_updates(self, manual: bool = False) -> None:
        if not manual and QApplication.activeModalWidget() is not None:
            QTimer.singleShot(3000, lambda: self._check_updates(manual=False))
            return
        try:
            update_info = check_for_updates()
        except Exception:
            if manual:
                QMessageBox.information(self, "Обновления", "Не удалось проверить обновления. Проверьте интернет.")
            return
        if not update_info:
            if manual:
                QMessageBox.information(self, "Обновления", f"У вас актуальная версия {APP_VERSION}.")
            return
        self._show_update_dialog(update_info)

    def _show_update_dialog(self, update_info: dict[str, Any]) -> None:
        new_version = str(update_info.get("version", ""))
        notes = str(update_info.get("notes", ""))
        dialog = QDialog(self)
        dialog.setWindowTitle("Доступно обновление")
        dialog.setObjectName("LightDialog")
        dialog.setMinimumSize(520, 320)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel(f"Доступна новая версия {new_version}")
        title.setObjectName("PanelTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        body = QLabel(
            f"Текущая версия: {APP_VERSION}\n"
            f"Новая версия: {new_version}\n\n"
            f"Что изменилось:\n{notes or 'Описание изменений не указано.'}"
        )
        body.setWordWrap(True)
        layout.addWidget(body)

        buttons = QHBoxLayout()
        update_button = QPushButton("Обновить")
        later_button = QPushButton("Позже")
        update_button.setMinimumHeight(48)
        later_button.setMinimumHeight(48)
        buttons.addWidget(update_button)
        buttons.addWidget(later_button)
        layout.addLayout(buttons)

        update_button.clicked.connect(lambda: self._download_and_run_update(update_info, dialog))
        later_button.clicked.connect(dialog.reject)
        dialog.exec()

    def _download_and_run_update(self, update_info: dict[str, Any], dialog: QDialog) -> None:
        try:
            installer_path = download_update(update_info)
            run_installer(installer_path)
        except Exception as exc:
            QMessageBox.critical(self, "Обновление", f"Не удалось скачать или запустить обновление:\n{exc}")
            return
        dialog.accept()
        QApplication.quit()

    def _show_start_screen(self) -> None:
        if self._start_screen_shown or self._project_has_walls():
            return
        app = QApplication.instance()
        if app is not None and app.platformName().lower() == "offscreen":
            return
        self._start_screen_shown = True
        dialog = StartDialog(self)
        if dialog.exec() != QDialog.Accepted or not dialog.action:
            return
        if dialog.action == "one_floor":
            self._new_project_with_floor_mode("1 этаж")
        elif dialog.action == "two_floor":
            self._new_project_with_floor_mode("2 этажа")
        elif dialog.action == "open":
            self._open_project()
        elif dialog.action == "template":
            self._choose_house_template()

    def _new_project_with_floor_mode(self, floor_mode: str) -> None:
        project = Project()
        project.floor_mode = floor_mode
        project.floors = 2 if floor_mode == "2 этажа" else 1
        project.ensure_floor_count(project.floors)
        self._set_project_for_views(project)
        self.current_project_path = None
        self.canvas = self.canvas1
        if self.center_tabs is not None:
            self.center_tabs.setCurrentIndex(self.plan1_tab_index)
        self._sync_controls_from_project()
        self._sync_floor_tabs()
        self._refresh_selection_panel("project", -1)
        QTimer.singleShot(0, self._fit_current_project)

    def _choose_house_template(self) -> None:
        templates = ["Дом 70 м²", "Дом 90 м²", "Дом 110 м²", "Дом 140 м²"]
        name, ok = QInputDialog.getItem(self, "Шаблон дома", "Выберите простой шаблон", templates, 0, False)
        if not ok or not name:
            return
        self._apply_house_template(name)

    def _open_demo_project(self) -> None:
        self._apply_house_template("Дом 110 м²")
        floor = self.project.get_floor(1)
        floor.rooms = self._demo_rooms()
        floor.doors = [
            DoorItem(wall_index=2, position=0.50, template_name="Входная 0.9 x 2.1 м"),
            DoorItem(wall_index=1, position=0.82, width=1.5, height=2.2, template_name="Террасная дверь 1.5 x 2.2 м"),
        ]
        floor.windows = [
            WindowItem(wall_index=0, position=0.22, template_name="Стандартное окно 1.5 x 1.4 м"),
            WindowItem(wall_index=0, position=0.55, template_name="Большое окно 2.0 x 1.5 м"),
            WindowItem(wall_index=0, position=0.82, template_name="Стандартное окно 1.5 x 1.4 м"),
            WindowItem(wall_index=1, position=0.38, template_name="Окно котельной 0.8 x 0.8 м"),
            WindowItem(wall_index=3, position=0.28, template_name="Стандартное окно 1.5 x 1.4 м"),
            WindowItem(wall_index=3, position=0.70, template_name="Стандартное окно 1.5 x 1.4 м"),
        ]
        self.project.show_roof = True
        self.project.roof_type = "Двускатная"
        self.project.roofing = "Металлочерепица"
        self.project.roof_angle = 32.0
        self.project.auto_roof_ridge_height = True
        self.project.update_auto_roof_height()
        self.project.site.area_sotka = 8.0
        self.project.site.width_m = 20.0
        self.project.site.length_m = 40.0
        self.project.site.front_setback_m = 6.0
        self.project.site.rear_setback_m = 5.0
        self.project.site.left_setback_m = 3.0
        self.project.site.right_setback_m = 3.0
        self.project.site_elements = [
            SiteElement("gate", "Ворота", Point(10.0, 39.0), width_m=4.0, length_m=0.4, price=65000),
            SiteElement("parking", "Парковка", Point(6.0, 33.0), width_m=6.0, length_m=5.0, quantity=30.0, unit="м²", price=1600),
            SiteElement("well", "Скважина", Point(17.0, 8.0), width_m=1.2, length_m=1.2, price=180000),
            SiteElement(
                "septic",
                "Септик",
                Point(4.0, 28.0),
                width_m=2.0,
                length_m=2.0,
                price=120000,
                parameters={"type": "Станция биоочистки", "volume_m3": 3.0, "delivery": 12000, "installation": 35000},
            ),
            SiteElement("electric_input", "Электрический ввод", Point(18.0, 36.0), price=35000),
            SiteElement("water_input", "Ввод воды", Point(16.0, 9.5), price=18000),
            SiteElement("path", "Дорожка", Point(10.0, 31.0), width_m=1.2, length_m=10.0, quantity=12.0, unit="м²", price=1400),
        ]
        self.project._sync_legacy_lists()
        self.current_project_path = None
        self._sync_controls_from_project()
        self._sync_floor_tabs()
        self._refresh_selection_panel("project", -1)
        QTimer.singleShot(0, self._fit_current_project)

    def _apply_house_template(self, name: str) -> None:
        sizes = {
            "Дом 70 м²": (7.0, 10.0, "1 этаж"),
            "Дом 90 м²": (9.0, 10.0, "1 этаж"),
            "Дом 110 м²": (10.0, 11.0, "1 этаж"),
            "Дом 140 м²": (10.0, 7.0, "2 этажа"),
        }
        width_m, depth_m, floor_mode = sizes.get(name, sizes["Дом 70 м²"])
        project = Project()
        project.floor_mode = floor_mode
        project.floors = 2 if floor_mode == "2 этажа" else 1
        project.ensure_floor_count(project.floors)
        project.show_roof = True
        project.roof_type = "Двускатная"
        project.roof_ridge_direction = "по X" if width_m >= depth_m else "по Y"
        project.update_auto_roof_height()

        floor = project.get_floor(1)
        w = width_m * PIXELS_PER_METER
        d = depth_m * PIXELS_PER_METER
        floor.walls = self._template_walls(width_m, depth_m, project.wall_material, project.floor_1_height)
        project.update_auto_roof_height()
        floor.doors = [DoorItem(wall_index=2, position=0.5, template_name="Входная 0.9 x 2.1 м")]
        floor.windows = [
            WindowItem(wall_index=0, position=0.25, template_name="Стандартное окно 1.5 x 1.4 м"),
            WindowItem(wall_index=0, position=0.72, template_name="Стандартное окно 1.5 x 1.4 м"),
            WindowItem(wall_index=1, position=0.5, template_name="Большое окно 2.0 x 1.5 м"),
            WindowItem(wall_index=3, position=0.45, template_name="Стандартное окно 1.5 x 1.4 м"),
        ]
        floor.rooms = self._template_rooms(width_m, depth_m, 1)

        if floor_mode == "2 этажа":
            project.create_second_floor_from_first()
            second = project.get_floor(2)
            second.walls = self._template_walls(width_m, depth_m, project.wall_material, project.floor_2_height)
            second.windows = [
                WindowItem(wall_index=0, position=0.30, template_name="Стандартное окно 1.5 x 1.4 м"),
                WindowItem(wall_index=0, position=0.70, template_name="Стандартное окно 1.5 x 1.4 м"),
                WindowItem(wall_index=3, position=0.45, template_name="Стандартное окно 1.5 x 1.4 м"),
            ]
            second.doors = [DoorItem(wall_index=4, position=0.52, width=0.8, height=2.0, template_name="Межкомнатная 0.8 x 2.0 м")]
            second.rooms = self._template_rooms(width_m, depth_m, 2)

        project._sync_legacy_lists()
        self._set_project_for_views(project)
        self.current_project_path = None
        self.canvas = self.canvas1
        if self.center_tabs is not None:
            self.center_tabs.setCurrentIndex(self.plan1_tab_index)
        self._sync_controls_from_project()
        self._sync_floor_tabs()
        self._refresh_selection_panel("project", -1)
        QTimer.singleShot(0, self._fit_current_project)

    def _template_walls(self, width_m: float, depth_m: float, material: str, height: float) -> list[Wall]:
        w = width_m * PIXELS_PER_METER
        d = depth_m * PIXELS_PER_METER
        split_x = w * 0.58
        split_y = d * 0.54
        return [
            Wall(Point(0, 0), Point(w, 0), height=height, material=material, is_load_bearing=True),
            Wall(Point(w, 0), Point(w, d), height=height, material=material, is_load_bearing=True),
            Wall(Point(w, d), Point(0, d), height=height, material=material, is_load_bearing=True),
            Wall(Point(0, d), Point(0, 0), height=height, material=material, is_load_bearing=True),
            Wall(Point(split_x, 0), Point(split_x, d), height=height, thickness=0.15, material=material, is_load_bearing=False),
            Wall(Point(0, split_y), Point(w, split_y), height=height, thickness=0.15, material=material, is_load_bearing=False),
        ]

    def _template_rooms(self, width_m: float, depth_m: float, floor_level: int) -> list[RoomItem]:
        area = width_m * depth_m
        if area > 80 and floor_level == 1:
            specs = [
                ("Кухня-гостиная", 0.27, 0.28, min(32.0, area * 0.30)),
                ("Спальня", 0.28, 0.76, min(15.0, area * 0.15)),
                ("Прихожая", 0.78, 0.14, 5.5),
                ("Коридор", 0.78, 0.38, 8.0),
                ("Котельная", 0.88, 0.25, 5.0),
                ("Санузел", 0.86, 0.52, 4.5),
            ]
        elif area > 80 and floor_level == 2:
            specs = [
                ("Спальня 1", 0.28, 0.30, min(16.0, area * 0.22)),
                ("Спальня 2", 0.74, 0.30, min(15.0, area * 0.20)),
                ("Детская", 0.28, 0.76, min(14.0, area * 0.18)),
                ("Гардероб", 0.74, 0.72, 5.0),
                ("Санузел", 0.86, 0.54, 4.5),
            ]
        elif floor_level == 2:
            specs = [
                ("Спальня", 0.29, 0.27, area * 0.30),
                ("Детская", 0.79, 0.27, area * 0.23),
                ("Кабинет", 0.29, 0.77, area * 0.27),
                ("Санузел", 0.79, 0.77, 4.0),
            ]
        else:
            specs = [
                ("Гостиная", 0.29, 0.27, area * 0.31),
                ("Кухня", 0.79, 0.27, area * 0.23),
                ("Спальня", 0.29, 0.77, area * 0.27),
                ("Санузел", 0.79, 0.77, 4.0),
            ]
        rooms: list[RoomItem] = []
        for room_name, cx, cy, room_area in specs:
            side = room_area ** 0.5
            rooms.append(
                RoomItem(
                    name=room_name,
                    floor=floor_level,
                    center=Point(width_m * PIXELS_PER_METER * cx, depth_m * PIXELS_PER_METER * cy),
                    area=room_area,
                    perimeter=side * 4,
                )
            )
        return rooms

    def _demo_rooms(self) -> list[RoomItem]:
        specs = [
            ("Кухня-гостиная", 0.30, 0.30, 32.0),
            ("Спальня 1", 0.24, 0.76, 14.0),
            ("Спальня 2", 0.56, 0.77, 13.0),
            ("Спальня 3", 0.84, 0.77, 12.0),
            ("Прихожая", 0.78, 0.13, 5.5),
            ("Коридор", 0.76, 0.40, 8.0),
            ("Котельная", 0.90, 0.26, 5.0),
            ("Санузел", 0.88, 0.52, 4.5),
            ("Терраса", 0.78, 0.93, 14.0),
        ]
        return [
            RoomItem(
                name=name,
                floor=1,
                center=Point(10.0 * PIXELS_PER_METER * cx, 11.0 * PIXELS_PER_METER * cy),
                area=area,
                perimeter=4 * (area ** 0.5),
            )
            for name, cx, cy, area in specs
        ]

    def _new_project(self) -> None:
        self._new_project_with_floor_mode("1 этаж")

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Открыть проект", "", "JSON (*.json)")
        if not path:
            return
        try:
            self._set_project_for_views(load_project(path))
            self.current_project_path = path
            self.canvas = self.canvas1
            if self.center_tabs is not None:
                self.center_tabs.setCurrentIndex(self.plan1_tab_index)
            self._sync_controls_from_project()
            self._sync_floor_tabs()
            self._refresh_selection_panel("project", -1)
            QTimer.singleShot(0, self._fit_current_project)
        except Exception as exc:  # pragma: no cover - диалоговая обработка ошибки
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть проект:\n{exc}")

    def _save_project(self) -> None:
        self._apply_project_params()
        if self.current_project_path:
            save_project(self.project, self.current_project_path)
            return
        self._save_project_as()

    def _save_project_as(self) -> None:
        self._apply_project_params()
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить проект", "project.json", "JSON (*.json)")
        if path:
            save_project(self.project, path)
            self.current_project_path = path

    def _export_txt(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт сметы", "estimate.txt", "TXT (*.txt)")
        if path:
            export_text(estimate_to_text(self.project, self.estimate), path)

    def _export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт сметы PDF", "estimate.pdf", "PDF (*.pdf)")
        if not path:
            return
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)
        document = QTextDocument()
        document.setHtml(
            "<pre style='font-family: Arial; font-size: 11pt;'>"
            + escape(estimate_to_text(self.project, self.estimate))
            + "</pre>"
        )
        document.print_(printer)

    def _export_image(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт изображения", "plan.png", "PNG (*.png)")
        if not path:
            return
        self.canvas.grab().save(path, "PNG")

    def _export_commercial_offer(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Коммерческое предложение", "commercial_offer.pdf", "PDF (*.pdf)")
        if not path:
            return
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)
        document = QTextDocument()
        html = f"""
        <h1>Коммерческое предложение</h1>
        <p><b>Проект:</b> Планировка дома и смета</p>
        <p><b>Площадь дома:</b> {self.estimate.get('house_area', 0):.1f} м²</p>
        <p><b>Тип крыши:</b> {escape(self.project.roof_type)}</p>
        <p><b>Материал кровли:</b> {escape(self.project.roofing)}</p>
        <h2>Итоговая стоимость</h2>
        <p style="font-size:18pt;"><b>{format_money(self.estimate.get('total', 0))}</b></p>
        <h2>Состав расчёта</h2>
        <pre>{escape(estimate_to_text(self.project, self.estimate))}</pre>
        """
        document.setHtml(html)
        document.print_(printer)

    def _sync_controls_from_project(self) -> None:
        self._updating_controls = True
        try:
            self.floor_mode_combo.setCurrentText(self.project.floor_mode)
            self.floor_1_height_spin.setValue(self.project.floor_1_height)
            self.floor_2_height_spin.setValue(self.project.floor_2_height)
            self.plinth_height_spin.setValue(self.project.plinth_height)
            self.slab_height_spin.setValue(self.project.slab_height)
            self._set_combo_value(self.project_wall_material_combo, self.project.wall_material)
            self._set_combo_value(self.foundation_combo, self.project.foundation_type)
            self._set_combo_value(self.insulation_combo, self.project.insulation_type)
            self._set_combo_value(self.facade_finish_combo, self.project.facade_finish or self.project.finishing)
            self._set_combo_value(self.roof_type_combo, self.project.roof_type)
            self.roof_direction_combo.setCurrentText(self.project.roof_ridge_direction)
            self._set_combo_value(self.roofing_combo, self.project.roofing)
            self.roof_angle_spin.setValue(self.project.roof_angle)
            self.roof_ridge_height_spin.setValue(self.project.roof_ridge_height)
            self.roof_overhang_spin.setValue(self.project.roof_overhang)
            self.roof_gable_height_spin.setValue(self.project.roof_gable_height)
            self.roof_complexity_spin.setValue(self.project.roof_complexity)
            self.auto_roof_height_check.setChecked(self.project.auto_roof_ridge_height)
            self.show_roof_check.setChecked(self.project.show_roof)
            self.show_roof_ridge_check.setChecked(self.project.show_roof_ridge)
            self.show_roof_slopes_check.setChecked(self.project.show_roof_slopes)
            self.show_roof_overhangs_check.setChecked(self.project.show_roof_overhangs)
            self.show_roof_dimensions_check.setChecked(self.project.show_roof_dimensions)
            self.show_rooms_check.setChecked(self.project.show_rooms)
            self.show_windows_check.setChecked(self.project.show_windows)
            self.show_doors_check.setChecked(self.project.show_doors)
            site = self.project.site
            self.site_area_spin.setValue(site.area_sotka)
            self.site_width_spin.setValue(site.width_m)
            self.site_length_spin.setValue(site.length_m)
            self.site_shape_combo.setCurrentText(site.shape)
            self.site_front_setback_spin.setValue(site.front_setback_m)
            self.site_rear_setback_spin.setValue(site.rear_setback_m)
            self.site_left_setback_spin.setValue(site.left_setback_m)
            self.site_right_setback_spin.setValue(site.right_setback_m)
            self.site_entry_side_combo.setCurrentText(site.entry_side)
            self.show_architecture_layer_check.setChecked(self.project.show_architecture_layer)
            self.show_site_layer_check.setChecked(self.project.show_site_layer)
            self.show_electric_layer_check.setChecked(self.project.show_electric_layer)
            self.show_plumbing_layer_check.setChecked(self.project.show_plumbing_layer)
            self.show_estimate_layer_check.setChecked(self.project.show_estimate_layer)
            auto_ridge_active = self.project.auto_roof_ridge_height and self.project.roof_type == "Двускатная"
            self.auto_roof_height_check.setEnabled(self.project.roof_type == "Двускатная")
            self.roof_ridge_height_spin.setEnabled(not auto_ridge_active)
        finally:
            self._updating_controls = False
        self._sync_floor_tabs()
        self._refresh_estimate()

    def _setup_form(self, form: QFormLayout) -> None:
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

    def _add_soft_shadow(self, widget: QWidget) -> None:
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(37, 49, 45, 28))
        widget.setGraphicsEffect(shadow)

    def _scroll_panel(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(widget)
        return scroll

    def _wall_combo(self) -> QComboBox:
        combo = QComboBox()
        for name, data in wall_catalog(self.materials).items():
            combo.addItem(material_price_label(name, data), name)
        combo.setMinimumWidth(220)
        return combo

    def _section_combo(self, section: str, price_key: str | None = None) -> QComboBox:
        combo = QComboBox()
        for name, data in self.materials.get(section, {}).items():
            label = name
            if price_key:
                price = float(data.get(price_key, 0) or 0)
                if price:
                    unit = "/м²" if price_key == "price_per_m2" else ""
                    label = f"{name} — {format_money(price)}{unit}"
            combo.addItem(label, name)
        combo.setMinimumWidth(220)
        return combo

    def _combo_value(self, combo: QComboBox) -> str:
        value = combo.currentData()
        return str(value if value is not None else combo.currentText())

    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index < 0:
            index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _template_payload(self, section: str, name: str) -> dict[str, Any]:
        data = dict(self.materials.get(section, {}).get(name, {}))
        data["template_name"] = name
        return data

    def _wall_rate(self, material: str, thickness: float) -> float:
        info = wall_material_info(self.materials, material)
        price_per_m2 = float(info.get("price_per_m2", 0) or 0)
        if price_per_m2:
            return price_per_m2
        if float(info.get("price_per_m3", 0) or 0):
            return float(info.get("price_per_m3", 0)) * thickness
        return 0.0

    def _meter_spin(self, minimum: float, maximum: float, step: float, decimals: int) -> QDoubleSpinBox:
        return self._plain_spin(minimum, maximum, step, decimals, " м")

    def _money_spin(self, suffix: str) -> QDoubleSpinBox:
        return self._plain_spin(0, 1000000, 100, 0, suffix)

    def _plain_spin(self, minimum: float, maximum: float, step: float, decimals: int, suffix: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        spin.setSuffix(suffix)
        return spin
