
------------------------------------------------------------------------------------------------------------------------------------------------------
Para instalar en otra máquina, antes hay que tener Python instalado (3.13.5):

    ✅ 1. Descargar Python
    Ve a la página oficial:
    👉 https://www.python.org/downloads/windows/

    Haz clic en el botón de "Download Python X.Y.Z" (elige la versión estable, como 3.13.5).

    ✅ 2. Ejecutar el instalador
    MUY IMPORTANTE: Marca la casilla "Add Python to PATH" antes de instalar.

    Haz clic en "Install Now".

    Espera a que termine la instalación.

-----------------------------------------------------------------------------------------------------------------------------------------------------

    Para activar el entorno virtual:

    C:\repositorio\examples\Python\.venv\Scripts> .\Activate.ps1 

    Desde el directorio (en entorno virtual) del proyecto hacemos:

    pip install -r requirements.txt

    NOTA: El fichero .env no estará en el GitHub (hay que crearlo manualmente en el raíz) por seguridad ya que contiene:

    CONTRASENA=XXXXX #La contraseña para acceder a 'https://telefichajes.zimaltec.es/'
    RUTA_CONFIG="C:\repositorio\examples\Python\src\dist"

    Para compilar todo:

    C:\repositorio\examples\Python\src> .\build_servicio.bat

    En C:\repositorio\examples\Python\src\dist\ se generan los exe´s (y el resto de recursos).

    El Log: C:\repositorio\examples\Python\src\dist\fichajes.log
    El Json de configuración: C:\repositorio\examples\Python\src\dist\configuracion.json
    El editor de la configuración: C:\repositorio\examples\Python\src\dist\editor_config.exe
    El servicio de auto fichajes: C:\repositorio\examples\Python\src\dist\servicio.exe

    Se necesita configurar un programador de tareas a la hora que se quiere fichar apuntando al bat: C:\repositorio\examples\Python\iniciar_servicio.bat
