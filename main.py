from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ui_main import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(
        """
        QWidget {
            font-family: Segoe UI, Arial;
            font-size: 15px;
            color: #172126;
        }
        QMainWindow, QMenuBar, QMenu {
            background: #f3f5f2;
            color: #172126;
        }
        QFrame, QGroupBox {
            background: #ffffff;
            border: 1px solid #d9e0dc;
            border-radius: 12px;
            color: #172126;
        }
        QFrame#TopBar {
            background: #ffffff;
            border: 1px solid #d9e0dc;
            border-radius: 12px;
        }
        QGroupBox {
            margin-top: 16px;
            padding: 16px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 14px;
            padding: 0 8px;
            font-weight: bold;
            color: #21302f;
            background: #ffffff;
        }
        QLabel {
            color: #172126;
            border: none;
            background: transparent;
        }
        QLineEdit, QComboBox {
            background: #ffffff;
            color: #172126;
            border: 1px solid #b8c6bf;
            border-radius: 10px;
            padding: 8px 11px;
            min-height: 36px;
        }
        QSpinBox, QDoubleSpinBox {
            background: #ffffff;
            color: #172126;
            border: 1px solid #aebfb7;
            border-radius: 10px;
            padding-left: 10px;
            padding-right: 32px;
            min-height: 40px;
        }
        QSpinBox::up-button, QDoubleSpinBox::up-button {
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 28px;
            height: 19px;
            border-left: 1px solid #aebbb5;
            border-bottom: 1px solid #d3dbd6;
            background: #eef3ef;
            border-top-right-radius: 9px;
        }
        QSpinBox::down-button, QDoubleSpinBox::down-button {
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 28px;
            height: 19px;
            border-left: 1px solid #aebbb5;
            background: #eef3ef;
            border-bottom-right-radius: 9px;
        }
        QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
        QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
            background: #dcebe3;
        }
        QRadioButton, QCheckBox {
            color: #172126;
            background: transparent;
            border: none;
        }
        QTabWidget::pane {
            border: 1px solid #d7e0da;
            border-radius: 12px;
            background: #ffffff;
        }
        QTabBar::tab {
            background: #f7f8f6;
            border: 1px solid #d5ded8;
            border-bottom: none;
            padding: 12px 20px;
            margin-right: 4px;
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
        }
        QTabBar::tab:selected {
            background: #e6efea;
            color: #203b35;
            font-weight: bold;
        }
        QPushButton {
            background: #f8f9f7;
            border: 1px solid #cdd7d1;
            border-radius: 12px;
            padding: 12px;
            text-align: left;
            color: #172126;
        }
        QPushButton:checked {
            background: #e2eee9;
            border: 2px solid #6f9186;
            font-weight: bold;
            color: #1f4038;
        }
        QPushButton:hover {
            background: #edf2ee;
        }
        QToolButton#TopMenuButton, QPushButton#TopActionButton {
            background: #f8f9f7;
            border: 1px solid #d4ddd7;
            border-radius: 10px;
            padding: 9px 14px;
            color: #1f2c2a;
            font-weight: 600;
        }
        QToolButton#TopMenuButton:hover, QPushButton#TopActionButton:hover {
            background: #eef3ef;
        }
        QLabel#PanelTitle {
            font-size: 21px;
            font-weight: bold;
            border: none;
        }
        QLabel#AppTitle {
            font-size: 28px;
            font-weight: bold;
            color: #1f3a36;
            padding: 4px 6px;
        }
        QLabel#TotalLabel {
            font-size: 22px;
            font-weight: bold;
            color: #00725f;
        }
        """
    )
    window = MainWindow()
    screen = app.primaryScreen().availableGeometry()
    width = min(1800, max(1280, int(screen.width() * 0.92)))
    height = min(1100, max(760, int(screen.height() * 0.9)))
    window.resize(width, height)
    window.move(
        screen.x() + (screen.width() - width) // 2,
        screen.y() + (screen.height() - height) // 2,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
