@echo off
echo Instalando librerías necesarias para el servicio de fichaje...
python -m pip install --upgrade pip
pip install requests
pip install schedule
pip install pywin32
echo.
echo Todas las librerías han sido instaladas correctamente.
pause
