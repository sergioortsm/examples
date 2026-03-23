@echo off
setlocal

set "BASE=%~dp0"
set "PY_EXE=%BASE%.venv\Scripts\python.exe"
set "LOG=%BASE%runtime\tarea_programada.log"
set "ARRANCAR_CHROME=%BASE%arrancar_chrome_personio.bat"
set "DEBUG_PORT=9222"
set "SILENT=0"

if /i "%~1"=="--silent" set "SILENT=1"

if not exist "%PY_EXE%" (
    echo [ERROR] No existe el entorno virtual en .venv >> "%LOG%"
    exit /b 1
)

if not exist "%ARRANCAR_CHROME%" (
    echo [ERROR] No existe el lanzador de Chrome Personio: %ARRANCAR_CHROME% >> "%LOG%"
    exit /b 1
)

:: Calcula la fecha de hoy en formato YYYY-MM-DD sin depender del locale de Windows.
for /f "delims=" %%d in ('powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd'"') do set "SOLO_FECHA=%%d"

if "%SOLO_FECHA%"=="" (
    call :log [ERROR] No se pudo obtener la fecha del sistema
    exit /b 1
)

cd /d "%BASE%"
call :log [INFO] Iniciando tarea programada para SOLO_FECHA=%SOLO_FECHA%

call :ensure_chrome_debug
if errorlevel 1 (
    call :log [ERROR] No se pudo preparar Chrome Personio en el puerto %DEBUG_PORT%
    exit /b 1
)

if "%SILENT%"=="1" (
    "%PY_EXE%" -m src.servicio >> "%LOG%" 2>&1
    set EXIT_CODE=%ERRORLEVEL%
) else (
    powershell -NoProfile -Command "& '%PY_EXE%' -m src.servicio 2>&1 | Tee-Object -FilePath '%LOG%' -Append; exit $LASTEXITCODE"
    set EXIT_CODE=%ERRORLEVEL%
)

call :log [INFO] Tarea finalizada con codigo %EXIT_CODE%

if not "%SILENT%"=="1" (
    echo.
    pause
)

exit /b %EXIT_CODE%

:ensure_chrome_debug
powershell -NoProfile -Command "$client = [System.Net.Sockets.TcpClient]::new(); try { $client.Connect('127.0.0.1', %DEBUG_PORT%); exit 0 } catch { exit 1 } finally { $client.Dispose() }"
if not errorlevel 1 (
    call :log [INFO] Chrome Personio ya estaba disponible en puerto %DEBUG_PORT%
    exit /b 0
)

call :log [INFO] Chrome Personio no estaba disponible; lanzando instancia dedicada...
call "%ARRANCAR_CHROME%" >nul 2>&1

for /l %%i in (1,1,20) do (
    powershell -NoProfile -Command "$client = [System.Net.Sockets.TcpClient]::new(); try { $client.Connect('127.0.0.1', %DEBUG_PORT%); exit 0 } catch { exit 1 } finally { $client.Dispose() }"
    if not errorlevel 1 (
        call :log [INFO] Chrome Personio disponible en puerto %DEBUG_PORT% tras espera %%i
        exit /b 0
    )
    timeout /t 1 /nobreak >nul
)

exit /b 1

:log
echo %*>>"%LOG%"
if not "%SILENT%"=="1" echo %*
exit /b 0
