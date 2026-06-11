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
            font-size: 14px;
            color: #172126;
        }
        QMainWindow, QMenuBar, QMenu {
            background: #eef2ef;
            color: #172126;
        }
        QFrame, QGroupBox {
            background: #ffffff;
            border: 1px solid #d7e0da;
            border-radius: 14px;
            color: #172126;
        }
        QGroupBox {
            margin-top: 14px;
            padding: 14px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 14px;
            padding: 0 8px;
            font-weight: bold;
            color: #172126;
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
            border-radius: 9px;
            padding: 7px 10px;
            min-height: 34px;
        }
        QSpinBox, QDoubleSpinBox {
            background: #ffffff;
            color: #172126;
            border: 1px solid #aebfb7;
            border-radius: 9px;
            padding-left: 10px;
            padding-right: 32px;
            min-height: 38px;
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
        QPushButton {
            background: #f8faf7;
            border: 1px solid #c3d0c9;
            border-radius: 12px;
            padding: 12px;
            text-align: left;
            color: #172126;
        }
        QPushButton:checked {
            background: #caeadf;
            border: 2px solid #16846d;
            font-weight: bold;
            color: #123a32;
        }
        QPushButton:hover {
            background: #edf5ef;
        }
        QLabel#PanelTitle {
            font-size: 20px;
            font-weight: bold;
            border: none;
        }
        QLabel#AppTitle {
            font-size: 26px;
            font-weight: bold;
            color: #143b34;
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
