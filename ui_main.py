from __future__ import annotations

from html import escape
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QColor, QTextDocument
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
from models import PIXELS_PER_METER, Point, Project, ROOM_TYPES, RoomItem
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
        self.roof_preview: RoofPreviewWidget | None = None
        self.center_tabs: QTabWidget | None = None
        self.explanation_table: QTableWidget | None = None
        self.current_project_path: str | None = None
        self.estimate: dict[str, float] = {}
        self._updating_controls = False
        self.tool_buttons: dict[str, QPushButton] = {}

        for canvas in self._all_canvases():
            canvas.set_window_template(self._template_payload("window_templates", "Стандартное окно 1.5 x 1.4 м"))
            canvas.set_door_template(self._template_payload("door_templates", "Входная 0.9 x 2.1 м"))
            canvas.set_stair_template(self._current_stair_template())

        self._build_menu()
        self._build_layout()
        self._connect_signals()
        self._sync_controls_from_project()
        self._refresh_selection_panel("project", -1)
        self._refresh_estimate()
        QTimer.singleShot(0, self._fit_current_project)

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
        if self.roof_preview is not None:
            self.roof_preview.set_project(project)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Файл")

        actions = [
            ("Новый проект", self._new_project),
            ("Открыть JSON...", self._open_project),
            ("Сохранить JSON...", self._save_project),
            ("Экспорт сметы TXT...", self._export_txt),
            ("Экспорт сметы PDF...", self._export_pdf),
        ]
        for caption, handler in actions:
            action = QAction(caption, self)
            action.triggered.connect(handler)
            file_menu.addAction(action)

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
                    ("Открыть", self._open_project),
                    ("Сохранить", self._save_project),
                    ("Сохранить как", self._save_project_as),
                ],
            )
        )
        layout.addWidget(self._menu_button("Конструкции", [("Стена", lambda: self._activate_tool("wall")), ("Крыша", lambda: self._activate_tool("roof")), ("Лестница", lambda: self._activate_tool("stair"))]))
        layout.addWidget(self._menu_button("Планировки", [("Помещение", lambda: self._activate_tool("room")), ("Вписать проект", self._fit_current_project)]))
        layout.addWidget(self._menu_button("Смета", [("Открыть смету", lambda: self.right_tabs.setCurrentIndex(7)), ("Экспорт TXT", self._export_txt)]))
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
        box = QGroupBox("Стена")
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
        return box

    def _build_door_panel(self) -> QWidget:
        box = QGroupBox("Дверь")
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
        return box

    def _build_window_panel(self) -> QWidget:
        box = QGroupBox("Окно")
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
        return box

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

    def _build_estimate_box(self) -> QWidget:
        box = QGroupBox("Смета")
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
            "complexity_extra": "Этажность/сложность",
            "total": "Итого",
        }
        for key, caption in rows.items():
            label = QLabel("0")
            label.setAlignment(Qt.AlignRight)
            if key == "total":
                label.setObjectName("TotalLabel")
            self.labels[key] = label
            form.addRow(caption, label)
        return box

    def _connect_signals(self) -> None:
        for canvas in self._all_canvases():
            canvas.project_changed.connect(self._on_project_changed)
            canvas.selection_changed.connect(self._refresh_selection_panel)
            canvas.room_place_requested.connect(self._place_room)
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
        self._set_active_tool(tool)
        self.canvas.set_tool(tool)
        self.roof_mode_box.setVisible(tool == "roof")
        if tool == "roof":
            self.help_label.setText("Режим крыши: настройте тип, угол, конёк и кровлю справа. Подробные скаты и фронтоны показываются только в этом режиме.")
        elif tool == "room":
            self.help_label.setText("Кликните внутри контура этажа и выберите назначение помещения. Подпись и площадь появятся на плане.")
        elif tool == "stair":
            self.help_label.setText("Настройте лестницу справа, затем кликните на плане в месте установки.")
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
        self.labels["complexity_extra"].setText(format_money(self.estimate["complexity_extra"]))
        self.labels["total"].setText(format_money(self.estimate["total"]))
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

    def _on_project_changed(self) -> None:
        self._refresh_estimate()
        for canvas in self._all_canvases():
            canvas.update()

    def _center_tab_changed(self, index: int) -> None:
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
        self.copy_second_floor_button.setVisible(True)
        if not show_second and self.center_tabs.currentIndex() == self.plan2_tab_index:
            self.center_tabs.setCurrentIndex(self.plan1_tab_index)
            self.canvas = self.canvas1

    def _delete_selected(self) -> None:
        self.canvas.delete_selected_element()
        self._refresh_explanation()

    def _fit_current_project(self) -> None:
        self.canvas.fit_project_to_view()

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
                room.area, room.perimeter = self._room_metrics_for_floor(floor.level, room.center.x, room.center.y)

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

    def _new_project(self) -> None:
        self._set_project_for_views(Project())
        self.current_project_path = None
        self.canvas = self.canvas1
        if self.center_tabs is not None:
            self.center_tabs.setCurrentIndex(self.plan1_tab_index)
        self._sync_controls_from_project()
        self._sync_floor_tabs()
        self._refresh_selection_panel("project", -1)
        QTimer.singleShot(0, self._fit_current_project)

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
