@echo off
:: ----------------------------------------------------------------------------
:: Arranca un Chrome aislado para Personio con depuracion remota en el puerto
:: 9222. Usa un directorio de datos NO estandar para que Chrome 136+ permita
:: remote debugging sin bloquear el perfil personal del usuario.
::
:: USO:
::   1. Ejecuta este script UNA VEZ al inicio del dia.
::   2. En la ventana de Chrome que se abre, inicia sesion en Personio una vez.
::      A partir de ahi, la sesion quedara persistida en este perfil aislado.
::   3. Lanza el bot normalmente con ejecutar_servicio_script.bat.
:: ----------------------------------------------------------------------------

set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
set "USER_DATA=C:\chromeDebug-personio"
set "PROFILE=Profile 1"
set "DEBUG_PORT=9222"

if not exist "%CHROME%" (
    echo [ERROR] No se encontro Chrome en: %CHROME%
    echo Ajusta la variable CHROME en este script.
    pause
    exit /b 1
)

if not exist "%USER_DATA%" mkdir "%USER_DATA%"

echo [INFO] Iniciando Chrome aislado para Personio en puerto de depuracion %DEBUG_PORT%...
start "" "%CHROME%" ^
    --remote-debugging-port=%DEBUG_PORT% ^
    --user-data-dir="%USER_DATA%" ^
    --profile-directory="%PROFILE%"

echo [INFO] Chrome lanzado con datos en %USER_DATA%.
echo [INFO] Si es la primera vez, inicia sesion en Personio en esta ventana.
echo [INFO] Luego lanza: ejecutar_servicio_script.bat YYYY-MM-DD
