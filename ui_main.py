from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
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
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from canvas import PlanCanvas, RoofPreviewWidget
from models import Project
from pricing import calculate_estimate, estimate_to_text, format_money, load_prices
from storage import export_text, load_project, save_project


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Простая планировка дома и смета")
        self.resize(1680, 980)
        self.setMinimumSize(1280, 760)

        self.project = Project()
        self.prices = load_prices()
        self.canvas = PlanCanvas(self.project)
        self.roof_preview: RoofPreviewWidget | None = None
        self.estimate: dict[str, float] = {}
        self._updating_controls = False

        self._build_menu()
        self._build_layout()
        self._connect_signals()
        self._sync_controls_from_project()
        self._refresh_selection_panel("project", -1)
        self._refresh_estimate()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Файл")

        new_action = QAction("Новый проект", self)
        new_action.triggered.connect(self._new_project)
        file_menu.addAction(new_action)

        open_action = QAction("Открыть JSON...", self)
        open_action.triggered.connect(self._open_project)
        file_menu.addAction(open_action)

        save_action = QAction("Сохранить JSON...", self)
        save_action.triggered.connect(self._save_project)
        file_menu.addAction(save_action)

        export_txt_action = QAction("Экспорт сметы TXT...", self)
        export_txt_action.triggered.connect(self._export_txt)
        file_menu.addAction(export_txt_action)

        export_pdf_action = QAction("Экспорт сметы PDF...", self)
        export_pdf_action.triggered.connect(self._export_pdf)
        file_menu.addAction(export_pdf_action)

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
        work_area.addWidget(self.canvas, stretch=1)
        work_area.addWidget(self._build_right_panel())
        layout.addLayout(work_area, stretch=1)
        self.setCentralWidget(root)

    def _build_tools_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFixedWidth(260)
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
            button.setMinimumHeight(54)
            self.tool_group.addButton(button)
            button.clicked.connect(lambda checked=False, value=tool_id: self.canvas.set_tool(value))
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
        help_label = QLabel("Двери и окна ставятся кликом по существующей стене. При наведении видно место установки.")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFixedWidth(420)
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
        params_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        layout.addWidget(params_scroll)
        layout.addWidget(self._build_estimate_box())
        layout.addStretch()
        return panel

    def _build_project_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox("Параметры проекта")
        form = QFormLayout(box)
        self._setup_form(form)

        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(2.0, 6.0)
        self.height_spin.setSingleStep(0.1)
        self.height_spin.setDecimals(1)
        self.height_spin.setSuffix(" м")
        form.addRow("Высота новых стен", self.height_spin)

        floors_box = QWidget()
        floors_layout = QHBoxLayout(floors_box)
        floors_layout.setContentsMargins(0, 0, 0, 0)
        self.floor_1 = QRadioButton("1 этаж")
        self.floor_2 = QRadioButton("2 этажа")
        floors_layout.addWidget(self.floor_1)
        floors_layout.addWidget(self.floor_2)
        form.addRow("Этажность", floors_box)

        self.project_wall_material_combo = self._combo("wall_materials")
        self.foundation_combo = self._combo("foundation")
        self.finishing_combo = self._combo("finishing")

        form.addRow("Материал новых стен", self.project_wall_material_combo)
        form.addRow("Фундамент", self.foundation_combo)
        form.addRow("Отделка", self.finishing_combo)

        roof_box = QGroupBox("Крыша")
        roof_form = QFormLayout(roof_box)
        self._setup_form(roof_form)
        self.show_roof_check = QCheckBox("Показать крышу на плане")
        self.roof_type_combo = self._combo("roof_type_multiplier")
        self.roof_direction_combo = QComboBox()
        self.roof_direction_combo.addItems(["по X", "по Y"])
        self.roofing_combo = self._combo("roofing")
        self.roof_angle_spin = QDoubleSpinBox()
        self.roof_angle_spin.setRange(1, 60)
        self.roof_angle_spin.setDecimals(0)
        self.roof_angle_spin.setSuffix("°")
        self.roof_angle_spin.setSingleStep(1)
        self.roof_ridge_height_spin = QDoubleSpinBox()
        self.roof_ridge_height_spin.setRange(0.1, 8.0)
        self.roof_ridge_height_spin.setDecimals(1)
        self.roof_ridge_height_spin.setSingleStep(0.1)
        self.roof_ridge_height_spin.setSuffix(" м")
        self.roof_overhang_spin = QDoubleSpinBox()
        self.roof_overhang_spin.setRange(0.0, 2.0)
        self.roof_overhang_spin.setDecimals(1)
        self.roof_overhang_spin.setSingleStep(0.1)
        self.roof_overhang_spin.setSuffix(" м")
        self.roof_complexity_spin = QDoubleSpinBox()
        self.roof_complexity_spin.setRange(0.5, 3.0)
        self.roof_complexity_spin.setDecimals(2)
        self.roof_complexity_spin.setSingleStep(0.05)
        roof_form.addRow("", self.show_roof_check)
        roof_form.addRow("Тип крыши", self.roof_type_combo)
        roof_form.addRow("Направление конька", self.roof_direction_combo)
        roof_form.addRow("Материал кровли", self.roofing_combo)
        roof_form.addRow("Угол наклона", self.roof_angle_spin)
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

        self.wall_length_spin = QDoubleSpinBox()
        self.wall_length_spin.setRange(0.2, 100.0)
        self.wall_length_spin.setSingleStep(0.1)
        self.wall_length_spin.setDecimals(1)
        self.wall_length_spin.setSuffix(" м")
        form.addRow("Длина стены", self.wall_length_spin)

        self.wall_height_spin = QDoubleSpinBox()
        self.wall_height_spin.setRange(2.0, 6.0)
        self.wall_height_spin.setSingleStep(0.1)
        self.wall_height_spin.setDecimals(1)
        self.wall_height_spin.setSuffix(" м")
        form.addRow("Высота стены", self.wall_height_spin)

        self.wall_thickness_spin = QDoubleSpinBox()
        self.wall_thickness_spin.setRange(0.05, 1.0)
        self.wall_thickness_spin.setSingleStep(0.05)
        self.wall_thickness_spin.setDecimals(2)
        self.wall_thickness_spin.setSuffix(" м")
        form.addRow("Толщина стены", self.wall_thickness_spin)

        self.wall_material_combo = self._combo("wall_materials")
        form.addRow("Материал стены", self.wall_material_combo)

        self.wall_price_spin = QDoubleSpinBox()
        self.wall_price_spin.setRange(0, 50000)
        self.wall_price_spin.setSingleStep(100)
        self.wall_price_spin.setDecimals(0)
        self.wall_price_spin.setSuffix(" ₽/м²")
        form.addRow("Цена материала", self.wall_price_spin)

        self.load_bearing_check = QCheckBox("Несущая стена")
        form.addRow("", self.load_bearing_check)
        return box

    def _build_door_panel(self) -> QWidget:
        box = QGroupBox("Параметры двери")
        form = QFormLayout(box)
        self._setup_form(form)

        self.door_width_spin = QDoubleSpinBox()
        self.door_width_spin.setRange(0.5, 2.0)
        self.door_width_spin.setSingleStep(0.1)
        self.door_width_spin.setDecimals(1)
        self.door_width_spin.setSuffix(" м")
        form.addRow("Ширина двери", self.door_width_spin)

        self.door_direction_combo = QComboBox()
        self.door_direction_combo.addItems(["Внутрь", "Наружу"])
        form.addRow("Открывание", self.door_direction_combo)

        self.door_hinge_combo = QComboBox()
        self.door_hinge_combo.addItems(["Левая", "Правая"])
        form.addRow("Петли", self.door_hinge_combo)
        return box

    def _build_window_panel(self) -> QWidget:
        box = QGroupBox("Параметры окна")
        form = QFormLayout(box)
        self._setup_form(form)

        self.window_width_spin = QDoubleSpinBox()
        self.window_width_spin.setRange(0.4, 4.0)
        self.window_width_spin.setSingleStep(0.1)
        self.window_width_spin.setDecimals(1)
        self.window_width_spin.setSuffix(" м")
        form.addRow("Ширина окна", self.window_width_spin)

        self.window_height_spin = QDoubleSpinBox()
        self.window_height_spin.setRange(0.4, 3.0)
        self.window_height_spin.setSingleStep(0.1)
        self.window_height_spin.setDecimals(1)
        self.window_height_spin.setSuffix(" м")
        form.addRow("Высота окна", self.window_height_spin)

        self.window_count_spin = QSpinBox()
        self.window_count_spin.setRange(1, 100)
        form.addRow("Количество в смете", self.window_count_spin)
        return box

    def _build_estimate_box(self) -> QWidget:
        box = QGroupBox("Смета")
        form = QFormLayout(box)
        self._setup_form(form)
        self.labels: dict[str, QLabel] = {}
        rows = {
            "house_area": "Площадь дома",
            "wall_length": "Длина стен",
            "wall_area": "Площадь стен",
            "walls_cost": "Стены",
            "foundation_cost": "Фундамент",
            "roof_type": "Тип крыши",
            "roof_direction": "Конёк",
            "roofing": "Кровля",
            "roof_area": "Площадь крыши",
            "roof_cost": "Крыша",
            "openings_cost": "Окна и двери",
            "finishing_cost": "Отделка",
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

    def _combo(self, price_key: str) -> QComboBox:
        combo = QComboBox()
        combo.addItems(self.prices[price_key].keys())
        combo.setMinimumWidth(190)
        return combo

    def _setup_form(self, form: QFormLayout) -> None:
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

    def _connect_signals(self) -> None:
        self.canvas.project_changed.connect(self._refresh_estimate)
        self.canvas.selection_changed.connect(self._refresh_selection_panel)

        self.height_spin.valueChanged.connect(self._apply_project_params)
        self.floor_1.toggled.connect(self._apply_project_params)
        for combo in (
            self.project_wall_material_combo,
            self.foundation_combo,
            self.finishing_combo,
        ):
            combo.currentTextChanged.connect(self._apply_project_params)
        for widget_signal in (
            self.show_roof_check.toggled,
            self.roof_type_combo.currentTextChanged,
            self.roof_direction_combo.currentTextChanged,
            self.roofing_combo.currentTextChanged,
            self.roof_angle_spin.valueChanged,
            self.roof_ridge_height_spin.valueChanged,
            self.roof_overhang_spin.valueChanged,
            self.roof_complexity_spin.valueChanged,
        ):
            widget_signal.connect(self._apply_project_params)

        self.wall_length_spin.valueChanged.connect(self._apply_wall_params)
        self.wall_height_spin.valueChanged.connect(self._apply_wall_params)
        self.wall_thickness_spin.valueChanged.connect(self._apply_wall_params)
        self.wall_material_combo.currentTextChanged.connect(self._wall_material_changed)
        self.wall_price_spin.valueChanged.connect(self._apply_wall_params)
        self.load_bearing_check.toggled.connect(self._apply_wall_params)

        self.door_width_spin.valueChanged.connect(self._apply_door_params)
        self.door_direction_combo.currentTextChanged.connect(self._apply_door_params)
        self.door_hinge_combo.currentTextChanged.connect(self._apply_door_params)

        self.window_width_spin.valueChanged.connect(self._apply_window_params)
        self.window_height_spin.valueChanged.connect(self._apply_window_params)
        self.window_count_spin.valueChanged.connect(self._apply_window_params)

    def _apply_project_params(self) -> None:
        if self._updating_controls:
            return
        self.project.wall_height = float(self.height_spin.value())
        self.project.floors = 1 if self.floor_1.isChecked() else 2
        self.project.wall_material = self.project_wall_material_combo.currentText()
        self.project.foundation_type = self.foundation_combo.currentText()
        self.project.roof_type = self.roof_type_combo.currentText()
        self.project.roof_ridge_direction = self.roof_direction_combo.currentText()
        self.project.roofing = self.roofing_combo.currentText()
        self.project.roof_angle = float(self.roof_angle_spin.value())
        self.project.roof_ridge_height = float(self.roof_ridge_height_spin.value())
        self.project.roof_overhang = float(self.roof_overhang_spin.value())
        self.project.roof_complexity = float(self.roof_complexity_spin.value())
        self.project.show_roof = self.show_roof_check.isChecked()
        self.project.finishing = self.finishing_combo.currentText()
        self._refresh_estimate()
        self.canvas.update()
        if self.roof_preview is not None:
            self.roof_preview.update()

    def _apply_wall_params(self) -> None:
        if self._updating_controls or self.canvas.selected_kind != "wall" or self.canvas.selected_index < 0:
            return
        wall = self.project.walls[self.canvas.selected_index]
        wall.height = float(self.wall_height_spin.value())
        wall.thickness = float(self.wall_thickness_spin.value())
        wall.material = self.wall_material_combo.currentText()
        wall.price_per_m2 = float(self.wall_price_spin.value())
        wall.is_load_bearing = self.load_bearing_check.isChecked()
        self.canvas.resize_selected_wall(float(self.wall_length_spin.value()))
        self._refresh_estimate()
        self.canvas.update()

    def _wall_material_changed(self) -> None:
        if self._updating_controls:
            return
        material = self.wall_material_combo.currentText()
        self.wall_price_spin.blockSignals(True)
        self.wall_price_spin.setValue(float(self.prices["wall_materials"].get(material, 0)))
        self.wall_price_spin.blockSignals(False)
        self._apply_wall_params()

    def _apply_door_params(self) -> None:
        if self._updating_controls or self.canvas.selected_kind != "door" or self.canvas.selected_index < 0:
            return
        door = self.project.doors[self.canvas.selected_index]
        door.width = float(self.door_width_spin.value())
        door.opening_direction = self.door_direction_combo.currentText()
        door.hinge_side = self.door_hinge_combo.currentText()
        self._refresh_estimate()
        self.canvas.update()

    def _apply_window_params(self) -> None:
        if self._updating_controls or self.canvas.selected_kind != "window" or self.canvas.selected_index < 0:
            return
        window = self.project.windows[self.canvas.selected_index]
        window.width = float(self.window_width_spin.value())
        window.height = float(self.window_height_spin.value())
        window.count = int(self.window_count_spin.value())
        self._refresh_estimate()
        self.canvas.update()

    def _refresh_estimate(self) -> None:
        self.estimate = calculate_estimate(self.project, self.prices)
        self.labels["house_area"].setText(f"{self.estimate['house_area']:.1f} м²")
        self.labels["wall_length"].setText(f"{self.estimate['wall_length']:.1f} м")
        self.labels["wall_area"].setText(f"{self.estimate['wall_area']:.1f} м²")
        self.labels["walls_cost"].setText(format_money(self.estimate["walls_cost"]))
        self.labels["foundation_cost"].setText(format_money(self.estimate["foundation_cost"]))
        self.labels["roof_type"].setText(self.project.roof_type)
        self.labels["roof_direction"].setText(self.project.roof_ridge_direction)
        self.labels["roofing"].setText(self.project.roofing)
        self.labels["roof_area"].setText(f"{self.estimate['roof_area']:.1f} м²")
        self.labels["roof_cost"].setText(format_money(self.estimate["roof_cost"]))
        self.labels["openings_cost"].setText(format_money(self.estimate["openings_cost"]))
        self.labels["finishing_cost"].setText(format_money(self.estimate["finishing_cost"]))
        self.labels["total"].setText(format_money(self.estimate["total"]))

    def _refresh_selection_panel(self, kind: str, index: int) -> None:
        self._updating_controls = True
        try:
            if kind == "wall" and index >= 0:
                self.params_stack.setCurrentIndex(1)
                wall = self.project.walls[index]
                self.wall_length_spin.setValue(max(0.2, wall.length_m))
                self.wall_height_spin.setValue(wall.height)
                self.wall_thickness_spin.setValue(wall.thickness)
                self.wall_material_combo.setCurrentText(wall.material)
                self.wall_price_spin.setValue(float(wall.price_per_m2 or self.prices["wall_materials"].get(wall.material, 0)))
                self.load_bearing_check.setChecked(wall.is_load_bearing)
            elif kind == "door" and index >= 0:
                self.params_stack.setCurrentIndex(2)
                door = self.project.doors[index]
                self.door_width_spin.setValue(door.width)
                self.door_direction_combo.setCurrentText(door.opening_direction)
                self.door_hinge_combo.setCurrentText(door.hinge_side)
            elif kind == "window" and index >= 0:
                self.params_stack.setCurrentIndex(3)
                window = self.project.windows[index]
                self.window_width_spin.setValue(window.width)
                self.window_height_spin.setValue(window.height)
                self.window_count_spin.setValue(window.count)
            else:
                self.params_stack.setCurrentIndex(0)
                self._sync_controls_from_project()
        finally:
            self._updating_controls = False

    def _new_project(self) -> None:
        self.project = Project()
        self.canvas.set_project(self.project)
        self._sync_controls_from_project()
        self._refresh_selection_panel("project", -1)

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Открыть проект", "", "JSON (*.json)")
        if not path:
            return
        try:
            self.project = load_project(path)
            self.canvas.set_project(self.project)
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
            self.height_spin.setValue(self.project.wall_height)
            self.floor_1.setChecked(self.project.floors == 1)
            self.floor_2.setChecked(self.project.floors == 2)
            self.project_wall_material_combo.setCurrentText(self.project.wall_material)
            self.foundation_combo.setCurrentText(self.project.foundation_type)
            self.roof_type_combo.setCurrentText(self.project.roof_type)
            self.roof_direction_combo.setCurrentText(self.project.roof_ridge_direction)
            self.roofing_combo.setCurrentText(self.project.roofing)
            self.roof_angle_spin.setValue(self.project.roof_angle)
            self.roof_ridge_height_spin.setValue(self.project.roof_ridge_height)
            self.roof_overhang_spin.setValue(self.project.roof_overhang)
            self.roof_complexity_spin.setValue(self.project.roof_complexity)
            self.show_roof_check.setChecked(self.project.show_roof)
            self.finishing_combo.setCurrentText(self.project.finishing)
        finally:
            self._updating_controls = False
        self._refresh_estimate()
        if self.roof_preview is not None:
            self.roof_preview.set_project(self.project)
