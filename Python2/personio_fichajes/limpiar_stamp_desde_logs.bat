@echo off
setlocal
cd /d "%~dp0"

set "PY_EXE=%~dp0.venv\Scripts\python.exe"

if not exist "%PY_EXE%" (
    echo [ERROR] No existe el entorno virtual en .venv
    echo Crea el entorno y dependencias con:
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)

echo [INFO] Limpiando stamp segun estado detectado en logs...
"%PY_EXE%" -m src.limpiar_stamp_desde_logs
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo [INFO] Finalizado con codigo %EXIT_CODE%

if /i not "%NO_PAUSE%"=="1" (
    echo.
    pause
)

endlocal & exit /b %EXIT_CODE%
