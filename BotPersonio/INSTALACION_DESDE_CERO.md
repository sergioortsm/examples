# Instalacion del bot en otra maquina (desde cero)

Esta guia deja el bot funcionando en Windows desde un equipo nuevo.

## 1. Requisitos previos

- Windows 10/11
- Google Chrome instalado
- Python 3.12 o 3.13 con launcher `py`
- Acceso a Personio con SSO/MFA
- Permisos para crear tareas programadas (ideal: PowerShell/CMD como Administrador)

## 2. Copiar el proyecto a la nueva maquina

Opcion A (recomendada, con git):

```powershell
git clone https://github.com/sergioortsm/examples.git
cd examples/BotPersonio
```

Opcion B (ZIP):

1. Descargar el repositorio como ZIP.
2. Extraerlo en una ruta fija, por ejemplo `C:\repositorio\examples\BotPersonio`.
3. Abrir terminal en esa carpeta.

## 3. Crear entorno virtual e instalar dependencias

Ejecuta estos comandos desde la raiz del proyecto (carpeta `BotPersonio`, donde estan `requirements.txt` y `.venv`).

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Si estas en otra carpeta, usa la ruta al archivo:

```powershell
.\.venv\Scripts\python.exe -m pip install -r C:\ruta\a\BotPersonio\requirements.txt
```

## 4. Configurar variables de entorno

Crear `.env` a partir de [.env.example](.env.example):

```powershell
Copy-Item .env.example .env
```

Editar `.env` y poner, si aplica:

- `PERSONIO_SSO_USERNAME`
- `PERSONIO_SSO_PASSWORD`
- `RUTA_CONFIG` (solo si quieres usar una ruta de config fuera de `dist/configuracion.json`)

## 5. Configurar el archivo JSON del bot

El bot busca configuracion en [dist/configuracion.json](dist/configuracion.json). Edita ese archivo y revisa al menos:

- `employee_id`
- `base_url`
- horarios (`morning_*`, `afternoon_*`, `friday_*`)
- `remote_debug_port` (9222 recomendado)
- `chrome_user_data_dir` (`C:\\chromeDebug-personio` recomendado)
- `chrome_profile_directory` (`Profile 1` recomendado)
- `festivos` y `vigilias_nacionales`

Notas importantes:

- Si no quieres alertas email, deja vacios `smtp_*` y `email_destinatario`.
- No compartas ni subas credenciales reales (`smtp_password`, password SSO, etc.).

## 6. Primer login en Chrome dedicado de Personio

Ejecuta una vez [arrancar_chrome_personio.bat](arrancar_chrome_personio.bat):

```powershell
.\arrancar_chrome_personio.bat
```

Luego, en la ventana de Chrome que se abre:

1. Inicia sesion en Personio.
2. Completa MFA si lo pide.
3. Deja esa ventana abierta.

## 7. Prueba manual del bot

Lanza una fecha concreta con [ejecutar_servicio_script.bat](ejecutar_servicio_script.bat):

```powershell
.\ejecutar_servicio_script.bat 2026-05-02
```

Si todo va bien, revisa logs en:

- `runtime/personio_fichajes.log`
- `runtime/tarea_programada.log`

## 8. Instalar tareas programadas (produccion)

Ejecuta [instalar_tareas_programadas.bat](instalar_tareas_programadas.bat) (mejor como Administrador):

```powershell
.\instalar_tareas_programadas.bat
```

Se crean estas tareas:

- `Fichaje Personio Lun-Jue` (17:50)
- `Fichaje Personio Vie` (14:20)
- `Fichaje Personio Catch-up` (09:00)

La tarea diaria usa [lanzar_tarea_programada.bat](lanzar_tarea_programada.bat) y el catch-up usa [lanzar_catch_up.bat](lanzar_catch_up.bat).

## 9. Verificacion rapida final

Checklist:

- `python -m src.servicio` se ejecuta sin errores en la terminal del proyecto.
- Chrome dedicado abre y responde en el puerto 9222.
- Existe `runtime/session_cookies.json` tras un login exitoso.
- Las tareas aparecen en el Programador de tareas de Windows.

## 10. Mantenimiento basico

Actualizar dependencias cuando sea necesario:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt --upgrade
```

Reintentar dias fallidos limpiando stamp desde logs:

```powershell
.\limpiar_stamp_desde_logs.bat
```
