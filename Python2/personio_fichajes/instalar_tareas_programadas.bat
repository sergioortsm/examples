@echo off
setlocal

set "BAT=%~dp0lanzar_tarea_programada.bat"

echo Instalando tareas programadas de Personio...
echo.
echo [INFO] Las tareas usaran Chrome Personio y requieren sesion iniciada del usuario.
echo.

:: Tarea 1: Lunes a Jueves a las 17:50
schtasks /create ^
    /tn "Fichaje Personio Lun-Jue" ^
    /tr "cmd.exe /c \"%BAT% --silent\"" ^
    /sc weekly ^
    /d MON,TUE,WED,THU ^
    /st 17:50 ^
    /f

if errorlevel 1 (
    echo [ERROR] No se pudo registrar la tarea Lun-Jue
    goto :fin
)
echo [OK] Tarea "Fichaje Personio Lun-Jue" registrada ^(Lun-Jue 17:50^)

:: Tarea 2: Viernes a las 14:20
schtasks /create ^
    /tn "Fichaje Personio Vie" ^
    /tr "cmd.exe /c \"%BAT% --silent\"" ^
    /sc weekly ^
    /d FRI ^
    /st 14:20 ^
    /f

if errorlevel 1 (
    echo [ERROR] No se pudo registrar la tarea Vie
    goto :fin
)
echo [OK] Tarea "Fichaje Personio Vie" registrada ^(Vie 14:20^)

:: Tarea 3: Watchdog catch-up - Lunes a Viernes al inicio de sesion + 09:00
::          Cubre los dias en que el PC estaba apagado a la hora de fichaje.
set "BAT_CATCHUP=%~dp0lanzar_catch_up.bat"

schtasks /create ^
    /tn "Fichaje Personio Catch-up" ^
    /tr "cmd.exe /c \"%BAT_CATCHUP% --silent\"" ^
    /sc weekly ^
    /d MON,TUE,WED,THU,FRI ^
    /st 09:00 ^
    /f

if errorlevel 1 (
    echo [ERROR] No se pudo registrar la tarea Catch-up
    goto :fin
)
echo [OK] Tarea "Fichaje Personio Catch-up" registrada ^(Lun-Vie 09:00^)

echo.
echo Tareas visibles en: Programador de tareas ^> Biblioteca del Programador
echo Log fichaje diario en: %~dp0runtime\tarea_programada.log
echo Log catch-up en:       %~dp0runtime\catch_up.log

:fin
pause
endlocal
