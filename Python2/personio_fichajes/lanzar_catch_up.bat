@echo off
setlocal EnableDelayedExpansion

set "BASE=%~dp0"
set "PY_EXE=%BASE%.venv\Scripts\python.exe"
set "LOG=%BASE%runtime\catch_up.log"
set "SILENT=0"
set "MAX_ATTEMPTS=2"
set "RETRY_DELAY_SEC=30"

if exist "%LOG%" (
    powershell -NoProfile -Command "$p='%LOG%'; $b=[System.IO.File]::ReadAllBytes($p); if ($b -contains 0) { $backup = $p + '.legacy-' + (Get-Date -Format 'yyyyMMdd-HHmmss'); Move-Item -Path $p -Destination $backup -Force }"
)

if /i "%~1"=="--silent" set "SILENT=1"

if not exist "%PY_EXE%" (
    call :log [ERROR] No existe el entorno virtual en .venv
    exit /b 1
)

cd /d "%BASE%"
call :log [INFO] Iniciando catch-up de fichajes Personio ^(usa headless si asi esta configurado^)...

set "EXIT_CODE=1"
for /l %%A in (1,1,%MAX_ATTEMPTS%) do (
    call :log [INFO] Intento %%A/%MAX_ATTEMPTS%

    if "%SILENT%"=="1" (
        powershell -NoProfile -Command "$env:MODO_CATCH_UP='1'; & '%PY_EXE%' -m src.servicio 2>&1 | ForEach-Object { $_ | Out-File -FilePath '%LOG%' -Append -Encoding utf8 }; exit $LASTEXITCODE"
        set "EXIT_CODE=!ERRORLEVEL!"
    ) else (
        powershell -NoProfile -Command "$env:MODO_CATCH_UP='1'; & '%PY_EXE%' -m src.servicio 2>&1 | ForEach-Object { $_; $_ | Out-File -FilePath '%LOG%' -Append -Encoding utf8 }; exit $LASTEXITCODE"
        set "EXIT_CODE=!ERRORLEVEL!"
    )

    if "!EXIT_CODE!"=="0" goto :done

    if %%A LSS %MAX_ATTEMPTS% (
        call :log [WARNING] Ejecucion con codigo !EXIT_CODE!. Reintentando en %RETRY_DELAY_SEC%s...
        timeout /t %RETRY_DELAY_SEC% /nobreak >nul
    )
)

:done

call :log [INFO] Catch-up finalizado con codigo !EXIT_CODE!

if not "%SILENT%"=="1" (
    echo.
    pause
)

exit /b !EXIT_CODE!

:log
setlocal DisableDelayedExpansion
set "LOG_MSG=%*"
powershell -NoProfile -Command "$env:LOG_MSG | Out-File -FilePath '%LOG%' -Append -Encoding utf8"
if not "%SILENT%"=="1" echo %*
endlocal
exit /b 0
