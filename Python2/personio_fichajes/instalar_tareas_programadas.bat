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

echo.
echo Tareas visibles en: Programador de tareas ^> Biblioteca del Programador
echo Log de ejecucion en: %~dp0runtime\tarea_programada.log

:fin
pause
endlocal
