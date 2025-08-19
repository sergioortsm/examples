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
set SCRIPT2=editor_config.py
set EXENAME2=editor_config.exe

echo ===============================
echo Generando EXE: %EXENAME%
echo ===============================
"%PY%" -m PyInstaller --clean --onefile %SCRIPT%

if errorlevel 1 (
    echo Error al compilar.
    pause
    exit /b 1
)

if not exist "%DESTINO%" mkdir "%DESTINO%"
move /Y dist\%EXENAME% "%DESTINO%"

echo ===============================
echo Generando EXE: %EXENAME2%
echo ===============================
"%PY%" -m PyInstaller --clean --onefile --noconsole --add-data "icons;icons" --hidden-import=chromedriver_autoinstaller %SCRIPT2%
if errorlevel 1 (
    echo Error al compilar %SCRIPT2%.
    pause
    exit /b 1
)
move /Y dist\%EXENAME2% "%DESTINO%"


:: copy /Y %JSON% "%DESTINO%"
copy /Y %PKL% "%DESTINO%"
copy /Y %TOKEN% "%DESTINO%"

echo EXEs y configuración copiados a %DESTINO%
pause
endlocal