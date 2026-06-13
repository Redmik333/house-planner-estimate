@echo off
setlocal

echo.
echo === Installing dependencies ===
python -m pip install --upgrade pip
if errorlevel 1 goto error

python -m pip install -r requirements.txt
if errorlevel 1 goto error

echo.
echo === Building app with PyInstaller ===
python -m PyInstaller --noconfirm --clean planner.spec
if errorlevel 1 goto error

echo.
echo === Copying extra files ===
python -c "from pathlib import Path; import shutil; app='\u041f\u043b\u0430\u043d\u0438\u0440\u043e\u0432\u043a\u0430 \u0434\u043e\u043c\u0430 \u0438 \u0441\u043c\u0435\u0442\u0430'; d=Path('dist')/app; d.mkdir(parents=True, exist_ok=True); [shutil.copy2(f, d/f) for f in ('materials.json','prices.json','version.json','README.md','app.ico') if Path(f).exists()]"
if errorlevel 1 goto error
python -c "from pathlib import Path; import shutil; app='\u041f\u043b\u0430\u043d\u0438\u0440\u043e\u0432\u043a\u0430 \u0434\u043e\u043c\u0430 \u0438 \u0441\u043c\u0435\u0442\u0430'; src=Path('assets'); dst=Path('dist')/app/'assets'; shutil.rmtree(dst, ignore_errors=True); shutil.copytree(src, dst) if src.exists() else None"
if errorlevel 1 goto error

echo.
echo Build complete.
echo Output folder:
echo dist
echo.
echo Open the folder dist and then the app folder with the Russian program name.
echo To create installer: open installer.iss in Inno Setup and press Compile.
exit /b 0

:error
echo.
echo Build failed. Check the messages above.
exit /b 1
