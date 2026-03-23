@echo off
setlocal
cd /d "%~dp0"

set PY_EXE=%~dp0.venv\Scripts\python.exe

if not exist "%PY_EXE%" (
    echo [ERROR] No existe el entorno virtual en .venv
    echo Crea el entorno y dependencias con:
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)

:: ---------------------------------------------------------------------------
:: USO RECOMENDADO
:: 1. Abre Chrome Personio (acceso directo dedicado del escritorio) o ejecuta:
::      arrancar_chrome_personio.bat
:: 2. Deja esa ventana abierta con sesion iniciada en Personio.
:: 3. Lanza este script indicando SOLO_FECHA.
::
:: El bot se conectara al Chrome dedicado por el puerto 9222, abrira una
:: pestaña nueva para operar y la cerrara al terminar sin tocar tu Chrome normal.
:: ---------------------------------------------------------------------------

if "%~1"=="" (
    echo [ERROR] Debes indicar una fecha en formato YYYY-MM-DD
    echo [ERROR] Ejemplo: ejecutar_servicio_script.bat 2026-03-22
    exit /b 1
)

set "SOLO_FECHA=%~1"
echo [INFO] Modo fecha unica: SOLO_FECHA=%SOLO_FECHA%

"%PY_EXE%" -m src.servicio
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo [INFO] Ejecucion finalizada con codigo %EXIT_CODE%

if /i not "%NO_PAUSE%"=="1" (
    echo.
    pause
)

endlocal & exit /b %EXIT_CODE%
