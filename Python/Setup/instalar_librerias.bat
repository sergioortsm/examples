@echo off
echo ✅ Creando entorno virtual .venv...
python -m venv .venv

echo ✅ Activando entorno virtual...
call .venv\Scripts\activate.bat

echo ✅ Instalando dependencias desde requirements.txt...
pip install --upgrade pip
pip install -r requirements.txt

echo ✅ Entorno configurado correctamente.

@REM echo 🏁 Ejecutando servicio.py...
@REM python servicio.py

REM Esperar unos segundos antes de cerrar (opcional)
timeout /t 3 > nul
