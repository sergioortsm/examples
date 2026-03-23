@echo off
setlocal EnableDelayedExpansion

set "BASE=%~dp0"
set "PY_EXE=%BASE%.venv\Scripts\python.exe"
set "LOG=%BASE%runtime\tarea_programada.log"
set "ARRANCAR_CHROME=%BASE%arrancar_chrome_personio.bat"
set "DEBUG_PORT=9222"
set "SILENT=0"
set "MAX_ATTEMPTS=2"
set "RETRY_DELAY_SEC=20"
set "STARTED_CHROME=0"

if exist "%LOG%" (
    powershell -NoProfile -Command "$p='%LOG%'; $b=[System.IO.File]::ReadAllBytes($p); if ($b -contains 0) { $backup = $p + '.legacy-' + (Get-Date -Format 'yyyyMMdd-HHmmss'); Move-Item -Path $p -Destination $backup -Force }"
)

if /i "%~1"=="--silent" set "SILENT=1"

if not exist "%PY_EXE%" (
    call :log [ERROR] No existe el entorno virtual en .venv
    exit /b 1
)

if not exist "%ARRANCAR_CHROME%" (
    call :log [ERROR] No existe el lanzador de Chrome Personio: %ARRANCAR_CHROME%
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

set "EXIT_CODE=1"
for /l %%A in (1,1,%MAX_ATTEMPTS%) do (
    call :log [INFO] Intento %%A/%MAX_ATTEMPTS%

    call :ensure_chrome_debug
    if errorlevel 1 (
        call :log [ERROR] No se pudo preparar Chrome Personio en el puerto %DEBUG_PORT%
        set "EXIT_CODE=1"
    ) else (
        if "%SILENT%"=="1" (
            powershell -NoProfile -Command "& '%PY_EXE%' -m src.servicio 2>&1 | ForEach-Object { $_ | Out-File -FilePath '%LOG%' -Append -Encoding utf8 }; exit $LASTEXITCODE"
            set "EXIT_CODE=!ERRORLEVEL!"
        ) else (
            powershell -NoProfile -Command "& '%PY_EXE%' -m src.servicio 2>&1 | ForEach-Object { $_; $_ | Out-File -FilePath '%LOG%' -Append -Encoding utf8 }; exit $LASTEXITCODE"
            set "EXIT_CODE=!ERRORLEVEL!"
        )
    )

    if "!EXIT_CODE!"=="0" goto :done

    if %%A LSS %MAX_ATTEMPTS% (
        call :log [WARNING] Ejecucion con codigo !EXIT_CODE!. Reintentando en %RETRY_DELAY_SEC%s...
        timeout /t %RETRY_DELAY_SEC% /nobreak >nul
    )
)

:done

if "%STARTED_CHROME%"=="1" (
    call :log [INFO] Cerrando Chrome Personio arrancado por esta ejecucion...
    call :stop_chrome_debug
)

call :log [INFO] Tarea finalizada con codigo !EXIT_CODE!

if not "%SILENT%"=="1" (
    echo.
    pause
)

exit /b !EXIT_CODE!

:ensure_chrome_debug
powershell -NoProfile -Command "$client = [System.Net.Sockets.TcpClient]::new(); try { $client.Connect('127.0.0.1', %DEBUG_PORT%); exit 0 } catch { exit 1 } finally { $client.Dispose() }"
if not errorlevel 1 (
    call :log [INFO] Chrome Personio ya estaba disponible en puerto %DEBUG_PORT%
    exit /b 0
)

call :log [INFO] Chrome Personio no estaba disponible; lanzando instancia dedicada...
call "%ARRANCAR_CHROME%" >nul 2>&1
set "STARTED_CHROME=1"

for /l %%i in (1,1,20) do (
    powershell -NoProfile -Command "$client = [System.Net.Sockets.TcpClient]::new(); try { $client.Connect('127.0.0.1', %DEBUG_PORT%); exit 0 } catch { exit 1 } finally { $client.Dispose() }"
    if not errorlevel 1 (
        call :log [INFO] Chrome Personio disponible en puerto %DEBUG_PORT% tras espera %%i
        exit /b 0
    )
    timeout /t 1 /nobreak >nul
)

exit /b 1

:stop_chrome_debug
powershell -NoProfile -Command "$conn = Get-NetTCPConnection -LocalPort %DEBUG_PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($null -eq $conn) { exit 0 }; Stop-Process -Id $conn.OwningProcess -Force -ErrorAction Stop"
if errorlevel 1 (
    call :log [WARNING] No se pudo cerrar automaticamente Chrome Personio del puerto %DEBUG_PORT%
) else (
    call :log [INFO] Chrome Personio cerrado tras finalizar la tarea
)
exit /b 0

:log
setlocal DisableDelayedExpansion
set "LOG_MSG=%*"
powershell -NoProfile -Command "$env:LOG_MSG | Out-File -FilePath '%LOG%' -Append -Encoding utf8"
if not "%SILENT%"=="1" echo %*
endlocal
exit /b 0
