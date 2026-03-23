@echo off
setlocal
set EXE=%~dp0personio_fichajes\dist\personio_fichajes_servicio.exe

if not exist "%EXE%" (
	echo [ERROR] No se encontro el ejecutable:
	echo   %EXE%
	echo Compilalo con personio_fichajes\build_exe.bat
	exit /b 1
)

"%EXE%"
endlocal
pause