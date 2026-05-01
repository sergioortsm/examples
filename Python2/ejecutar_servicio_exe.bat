@echo off
setlocal
set EXE=%~dp0personio_fichajes\dist\personio_fichajes_servicio.exe
set "SHOULD_PAUSE=1"

if /i "%NO_PAUSE%"=="1" set "SHOULD_PAUSE="
if /i "%~2"=="--no-pause" set "SHOULD_PAUSE="

echo [INFO] Flujo recomendado:
echo [INFO]   1. Abre "Chrome Personio" o ejecuta arrancar_chrome_personio.bat
echo [INFO]   2. Deja esa ventana abierta con sesion iniciada
echo [INFO]   3. Lanza este ejecutable con la fecha a procesar
echo [INFO]   4. Confirma en consola si deseas continuar con la imputacion

if not exist "%EXE%" (
	echo [ERROR] No se encontro el ejecutable:
	echo   %EXE%
	echo Compilalo con personio_fichajes\build_exe.bat
	exit /b 1
)

if "%~1"=="" (
	echo [ERROR] Debes indicar una fecha en formato YYYY-MM-DD
	echo [ERROR] Ejemplo: ejecutar_servicio_exe.bat 2026-03-22
	if defined SHOULD_PAUSE pause
	exit /b 1
)

set "SOLO_FECHA=%~1"
echo [INFO] Modo fecha unica: SOLO_FECHA=%SOLO_FECHA%

"%EXE%"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo [INFO] Ejecucion finalizada con codigo %EXIT_CODE%
endlocal
if defined SHOULD_PAUSE pause
exit /b %EXIT_CODE%