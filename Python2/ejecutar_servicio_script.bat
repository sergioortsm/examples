@echo off
setlocal
cd /d "%~dp0personio_fichajes"

echo [INFO] Flujo recomendado:
echo [INFO]   1. Abre "Chrome Personio" o ejecuta arrancar_chrome_personio.bat
echo [INFO]   2. Deja esa ventana abierta con sesion iniciada
echo [INFO]   3. Lanza este script con la fecha a procesar

if "%~1"=="" (
	echo [ERROR] Debes indicar una fecha en formato YYYY-MM-DD
	echo [ERROR] Ejemplo: ejecutar_servicio_script.bat 2026-03-22
	pause
	exit /b 1
)

call "%~dp0personio_fichajes\ejecutar_servicio_script.bat" "%~1"

endlocal
pause