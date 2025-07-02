@echo off
setlocal

:: Ruta a Python dentro del entorno virtual
set PY=C:\repositorio\examples\Python\.venv\Scripts\python.exe
set SCRIPT=servicio.py
set EXENAME=servicio.exe
set DESTINO=C:\repositorio\examples\Python\src\dist
set JSON=configuracion.json
set PKL=cookies.pkl
set TOKEN=token_csrf.txt

echo Generando EXE con entorno virtual...
"%PY%" -m PyInstaller --clean --onefile %SCRIPT%

if errorlevel 1 (
    echo Error al compilar.
    pause
    exit /b 1
)

if not exist "%DESTINO%" mkdir "%DESTINO%"

move /Y dist\%EXENAME% "%DESTINO%"
:: copy /Y %JSON% "%DESTINO%"
copy /Y %PKL% "%DESTINO%"
copy /Y %TOKEN% "%DESTINO%"

echo EXE y configuración copiados a %DESTINO%
pause
endlocal
