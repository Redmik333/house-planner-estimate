from __future__ import annotations

from html import escape
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QTextDocument
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
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from canvas import PlanCanvas, RoofPreviewWidget
from facade_view import FacadeView
from models import Project
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
        self.canvas = PlanCanvas(self.project)
        self.facade_view = FacadeView(self.project)
        self.roof_preview: RoofPreviewWidget | None = None
        self.estimate: dict[str, float] = {}
        self._updating_controls = False
        self.tool_buttons: dict[str, QPushButton] = {}

        self.canvas.set_window_template(self._template_payload("window_templates", "Стандартное окно 1.5 x 1.4 м"))
        self.canvas.set_door_template(self._template_payload("door_templates", "Входная 0.9 x 2.1 м"))

        self._build_menu()
        self._build_layout()
        self._connect_signals()
        self._sync_controls_from_project()
        self._refresh_selection_panel("project", -1)
        self._refresh_estimate()

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

        work_area = QHBoxLayout()
        work_area.setSpacing(10)
        work_area.addWidget(self._build_tools_panel())
        work_area.addWidget(self._build_center_tabs(), stretch=1)
        work_area.addWidget(self._build_right_panel())
        layout.addLayout(work_area, stretch=1)
        self.setCentralWidget(root)

    def _build_center_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.addTab(self.canvas, "План")

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
        return tabs

    def _build_tools_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFixedWidth(270)
        panel.setFrameShape(QFrame.StyledPanel)
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
        self.delete_button.clicked.connect(self.canvas.delete_selected_element)
        layout.addWidget(self.delete_button)

        layout.addSpacing(12)
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
        help_label = QLabel("Окна и двери выбираются по шаблону и ставятся кликом по существующей стене.")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFixedWidth(450)
        panel.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(panel)

        self.params_stack = QStackedWidget()
        self.params_stack.addWidget(self._build_project_panel())
        self.params_stack.addWidget(self._build_wall_panel())
        self.params_stack.addWidget(self._build_door_panel())
        self.params_stack.addWidget(self._build_window_panel())

        params_scroll = QScrollArea()
        params_scroll.setWidgetResizable(True)
        params_scroll.setFrameShape(QFrame.NoFrame)
        params_scroll.setWidget(self.params_stack)
        params_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(params_scroll, stretch=2)
        layout.addWidget(self._build_estimate_box(), stretch=1)
        return panel

    def _build_project_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox("Параметры дома")
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

        roof_box = QGroupBox("Крыша")
        roof_form = QFormLayout(roof_box)
        self._setup_form(roof_form)
        self.show_roof_check = QCheckBox("Показать крышу на плане")
        self.auto_roof_height_check = QCheckBox("Автоматически рассчитывать высоту конька")
        self.roof_type_combo = self._section_combo("roof_types")
        self.roof_direction_combo = QComboBox()
        self.roof_direction_combo.addItems(["по X", "по Y"])
        self.roofing_combo = self._section_combo("roofing_materials", "price_per_m2")
        self.roof_angle_spin = self._plain_spin(1, 60, 1, 0, "°")
        self.roof_ridge_height_spin = self._meter_spin(0.1, 8.0, 0.1, 1)
        self.roof_overhang_spin = self._meter_spin(0.0, 2.0, 0.1, 1)
        self.roof_complexity_spin = self._plain_spin(0.5, 3.0, 0.05, 2, "")
        roof_form.addRow("", self.show_roof_check)
        roof_form.addRow("Тип крыши", self.roof_type_combo)
        roof_form.addRow("Направление конька", self.roof_direction_combo)
        roof_form.addRow("Материал кровли", self.roofing_combo)
        roof_form.addRow("Угол наклона", self.roof_angle_spin)
        roof_form.addRow("", self.auto_roof_height_check)
        roof_form.addRow("Высота конька", self.roof_ridge_height_spin)
        roof_form.addRow("Свес крыши", self.roof_overhang_spin)
        roof_form.addRow("Сложность", self.roof_complexity_spin)
        self.roof_preview = RoofPreviewWidget(self.project)
        roof_form.addRow("3D-просмотр", self.roof_preview)

        layout.addWidget(box)
        layout.addWidget(roof_box)
        layout.addStretch()
        return container

    def _build_wall_panel(self) -> QWidget:
        box = QGroupBox("Параметры стены")
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
        box = QGroupBox("Параметры двери")
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
        box = QGroupBox("Параметры окна")
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

    def _build_estimate_box(self) -> QWidget:
        box = QGroupBox("Смета")
        form = QFormLayout(box)
        self._setup_form(form)
        self.labels: dict[str, QLabel] = {}
        rows = {
            "house_area": "Площадь дома",
            "footprint_area": "Площадь застройки",
            "wall_length": "Длина стен",
            "wall_area": "Площадь стен",
            "total_wall_height": "Высота стен",
            "walls_cost": "Стены",
            "foundation_cost": "Фундамент",
            "roof_type": "Тип крыши",
            "roofing": "Кровля",
            "roof_area": "Площадь крыши",
            "roof_cost": "Крыша",
            "windows_cost": "Окна",
            "doors_cost": "Двери",
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
        self.canvas.project_changed.connect(self._refresh_estimate)
        self.canvas.selection_changed.connect(self._refresh_selection_panel)
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
            self.roof_complexity_spin.valueChanged,
        ):
            signal.connect(self._apply_project_params)

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
        self._set_active_tool(tool)
        self.canvas.set_tool(tool)

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
        if not self.project.auto_roof_ridge_height:
            self.project.roof_ridge_height = float(self.roof_ridge_height_spin.value())
        self.project.roof_overhang = float(self.roof_overhang_spin.value())
        self.project.roof_complexity = float(self.roof_complexity_spin.value())
        self.project.show_roof = self.show_roof_check.isChecked()
        self.project.update_auto_roof_height()
        self.roof_ridge_height_spin.setEnabled(not self.project.auto_roof_ridge_height)
        if self.project.auto_roof_ridge_height:
            self.roof_ridge_height_spin.blockSignals(True)
            self.roof_ridge_height_spin.setValue(self.project.roof_ridge_height)
            self.roof_ridge_height_spin.blockSignals(False)
        self._refresh_estimate()
        self.canvas.update()
        self.facade_view.update()
        if self.roof_preview is not None:
            self.roof_preview.update()

    def _apply_wall_params(self) -> None:
        if self._updating_controls or self.canvas.selected_kind != "wall" or self.canvas.selected_index < 0:
            return
        wall = self.project.walls[self.canvas.selected_index]
        wall.height = float(self.wall_height_spin.value())
        wall.thickness = float(self.wall_thickness_spin.value())
        wall.material = self._combo_value(self.wall_material_combo)
        wall.price_per_m2 = float(self.wall_price_spin.value())
        wall.is_load_bearing = self.load_bearing_check.isChecked()
        self.canvas.resize_selected_wall(float(self.wall_length_spin.value()))
        self._refresh_estimate()
        self.canvas.update()
        self.facade_view.update()

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
        door = self.project.doors[self.canvas.selected_index]
        door.template_name = self._combo_value(self.door_template_combo)
        door.width = float(self.door_width_spin.value())
        door.height = float(self.door_height_spin.value())
        door.opening_direction = self.door_direction_combo.currentText()
        door.hinge_side = self.door_hinge_combo.currentText()
        door.price = float(self.door_price_spin.value())
        if door.wall_index < len(self.project.walls):
            door.distance_from_start = door.position * self.project.walls[door.wall_index].length_m
        self._refresh_estimate()
        self.canvas.update()
        self.facade_view.update()

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
        window = self.project.windows[self.canvas.selected_index]
        window.template_name = self._combo_value(self.window_template_combo)
        window.width = float(self.window_width_spin.value())
        window.height = float(self.window_height_spin.value())
        window.install_height = float(self.window_install_height_spin.value())
        window.glass_type = self.window_glass_combo.currentText()
        window.price = float(self.window_price_spin.value())
        window.price_per_m2 = float(self.window_price_m2_spin.value())
        window.count = int(self.window_count_spin.value())
        if window.wall_index < len(self.project.walls):
            window.distance_from_start = window.position * self.project.walls[window.wall_index].length_m
        self._refresh_estimate()
        self.canvas.update()
        self.facade_view.update()

    def _refresh_estimate(self) -> None:
        self.estimate = calculate_estimate(self.project, self.materials)
        self.labels["house_area"].setText(f"{self.estimate['house_area']:.1f} м²")
        self.labels["footprint_area"].setText(f"{self.estimate['footprint_area']:.1f} м²")
        self.labels["wall_length"].setText(f"{self.estimate['wall_length']:.1f} м")
        self.labels["wall_area"].setText(f"{self.estimate['wall_area']:.1f} м²")
        self.labels["total_wall_height"].setText(f"{self.estimate['total_wall_height']:.1f} м")
        self.labels["walls_cost"].setText(format_money(self.estimate["walls_cost"]))
        self.labels["foundation_cost"].setText(format_money(self.estimate["foundation_cost"]))
        self.labels["roof_type"].setText(self.project.roof_type)
        self.labels["roofing"].setText(self.project.roofing)
        self.labels["roof_area"].setText(f"{self.estimate['roof_area']:.1f} м²")
        self.labels["roof_cost"].setText(format_money(self.estimate["roof_cost"]))
        self.labels["windows_cost"].setText(format_money(self.estimate["windows_cost"]))
        self.labels["doors_cost"].setText(format_money(self.estimate["doors_cost"]))
        self.labels["insulation_cost"].setText(format_money(self.estimate["insulation_cost"]))
        self.labels["facade_cost"].setText(format_money(self.estimate["facade_cost"]))
        self.labels["complexity_extra"].setText(format_money(self.estimate["complexity_extra"]))
        self.labels["total"].setText(format_money(self.estimate["total"]))
        if hasattr(self, "roof_ridge_height_spin") and self.project.auto_roof_ridge_height:
            self.roof_ridge_height_spin.blockSignals(True)
            self.roof_ridge_height_spin.setValue(self.project.roof_ridge_height)
            self.roof_ridge_height_spin.blockSignals(False)
        self.facade_view.update()
        if self.roof_preview is not None:
            self.roof_preview.update()

    def _refresh_selection_panel(self, kind: str, index: int) -> None:
        self._updating_controls = True
        try:
            if kind == "wall" and index >= 0:
                self.params_stack.setCurrentIndex(1)
                wall = self.project.walls[index]
                self.wall_length_spin.setValue(max(0.2, wall.length_m))
                self.wall_height_spin.setValue(wall.height)
                self.wall_thickness_spin.setValue(wall.thickness)
                self._set_combo_value(self.wall_material_combo, wall.material)
                self.wall_price_spin.setValue(float(wall.price_per_m2 or self._wall_rate(wall.material, wall.thickness)))
                self.load_bearing_check.setChecked(wall.is_load_bearing)
            elif kind == "door" and index >= 0:
                self.params_stack.setCurrentIndex(2)
                door = self.project.doors[index]
                self._set_combo_value(self.door_template_combo, door.template_name)
                self.door_width_spin.setValue(door.width)
                self.door_height_spin.setValue(door.height)
                self.door_direction_combo.setCurrentText(door.opening_direction)
                self.door_hinge_combo.setCurrentText(door.hinge_side)
                self.door_price_spin.setValue(door.price)
            elif kind == "window" and index >= 0:
                self.params_stack.setCurrentIndex(3)
                window = self.project.windows[index]
                self._set_combo_value(self.window_template_combo, window.template_name)
                self.window_width_spin.setValue(window.width)
                self.window_height_spin.setValue(window.height)
                self.window_install_height_spin.setValue(window.install_height)
                self.window_glass_combo.setCurrentText(window.glass_type)
                self.window_price_spin.setValue(window.price)
                self.window_price_m2_spin.setValue(window.price_per_m2)
                self.window_count_spin.setValue(window.count)
            else:
                self.params_stack.setCurrentIndex(0)
                self._sync_controls_from_project()
        finally:
            self._updating_controls = False

    def _new_project(self) -> None:
        self.project = Project()
        self.canvas.set_project(self.project)
        self.facade_view.set_project(self.project)
        if self.roof_preview is not None:
            self.roof_preview.set_project(self.project)
        self._sync_controls_from_project()
        self._refresh_selection_panel("project", -1)

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Открыть проект", "", "JSON (*.json)")
        if not path:
            return
        try:
            self.project = load_project(path)
            self.canvas.set_project(self.project)
            self.facade_view.set_project(self.project)
            if self.roof_preview is not None:
                self.roof_preview.set_project(self.project)
            self._sync_controls_from_project()
            self._refresh_selection_panel("project", -1)
        except Exception as exc:  # pragma: no cover - диалоговая обработка ошибки
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть проект:\n{exc}")

    def _save_project(self) -> None:
        self._apply_project_params()
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить проект", "project.json", "JSON (*.json)")
        if path:
            save_project(self.project, path)

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
            self.roof_complexity_spin.setValue(self.project.roof_complexity)
            self.auto_roof_height_check.setChecked(self.project.auto_roof_ridge_height)
            self.show_roof_check.setChecked(self.project.show_roof)
            self.roof_ridge_height_spin.setEnabled(not self.project.auto_roof_ridge_height)
        finally:
            self._updating_controls = False
        self._refresh_estimate()

    def _setup_form(self, form: QFormLayout) -> None:
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

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
