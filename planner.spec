# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs


block_cipher = None
app_name = "\u041f\u043b\u0430\u043d\u0438\u0440\u043e\u0432\u043a\u0430 \u0434\u043e\u043c\u0430 \u0438 \u0441\u043c\u0435\u0442\u0430"
root = Path(SPECPATH)
icon_path = root / "app.ico"

datas = []
binaries = []

# PySide6 uses shiboken6.Shiboken during import. Some one-dir builds include
# the binary but miss the Python package files, so add them explicitly.
datas += collect_data_files("shiboken6", includes=["*.py", "*.pyi", "py.typed"])
binaries += collect_dynamic_libs("shiboken6")

if (root / "prices.json").exists():
    datas.append((str(root / "prices.json"), "."))
if (root / "README.md").exists():
    datas.append((str(root / "README.md"), "."))

a = Analysis(
    ["main.py"],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "shiboken6",
        "shiboken6.Shiboken",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtPrintSupport",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=app_name,
)
