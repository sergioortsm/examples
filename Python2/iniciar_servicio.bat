@echo off
echo Iniciando el servicio de fichaje...
echo [INFO] Si vas a reutilizar sesion, abre antes "Chrome Personio".
if not "%~1"=="" (
	call "%~dp0ejecutar_servicio_script.bat" "%~1"
) else (
	call "%~dp0ejecutar_servicio_script.bat"
)
pause
