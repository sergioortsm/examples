@echo off
setlocal

set PYTHON_EXE=%~dp0.venv\Scripts\python.exe
set DIST_DIR=%~dp0dist

if not exist "%PYTHON_EXE%" (
    echo [ERROR] No existe entorno virtual en .venv
    echo Ejecuta primero: python -m venv .venv ^&^& .venv\Scripts\activate ^&^& pip install -r requirements.txt
    exit /b 1
)

if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

cd /d "%~dp0src"
"%PYTHON_EXE%" -m PyInstaller --clean --onefile servicio.py --name personio_fichajes_servicio --collect-submodules selenium --collect-submodules webdriver_manager
if errorlevel 1 (
    echo [ERROR] Fallo compilando servicio.py
    exit /b 1
)

copy /Y "%~dp0src\dist\personio_fichajes_servicio.exe" "%DIST_DIR%\personio_fichajes_servicio.exe" >nul
echo [OK] EXE generado en %DIST_DIR%\personio_fichajes_servicio.exe
endlocal
