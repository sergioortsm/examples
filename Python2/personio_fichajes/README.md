# Personio Auto Fichajes Bot

Bot de automatizacion de fichajes para Personio, inspirado en la arquitectura del proyecto original de auto fichajes.

## Estructura

```text
personio_fichajes/
  src/
    auth.py
    config.py
    editor_config.py
    filtrar_fichajes.py
    logger.py
    personio_client.py
    servicio.py
  dist/
    configuracion.json
  .env.example
  requirements.txt
  ejecutar_servicio_script.bat
  build_exe.bat
```

## Flujo diario

1. Login SSO en Personio (Microsoft/Azure AD + MFA).
2. Consulta del timesheet semanal.
3. Localizacion del dia actual.
4. Salto de dias no aplicables (fin de semana, off day, dia ya fichado).
5. Construccion de periodos (desde working schedule si esta disponible; fallback a config).
6. Validacion de periodos con endpoint `validate-and-calculate-full-day`.
7. Guardado final con endpoint `PUT /svc/attendance-api/v1/days/{attendance_day_id}`.

## Configuracion

Archivo: `dist/configuracion.json`

Campos principales:
- `employee_id`
- `timezone`
- `base_url`
- Horarios: `morning_start`, `morning_end`, `afternoon_start`, `afternoon_end`, `friday_start`, `friday_end`
- `headless`, `modo_prueba`, `modo_interactivo`
- `request_timeout_sec`, `login_timeout_sec`, `max_retries`
- `remote_debug_port` (recomendado: `9222`)
- `chrome_user_data_dir` (recomendado: `C:\\chromeDebug-personio`)
- `chrome_profile_directory` (recomendado: `Profile 1`)

## Variables de entorno

Crear `.env` desde `.env.example`.

Variables opcionales:
- `PERSONIO_SSO_USERNAME`
- `PERSONIO_SSO_PASSWORD`
- `RUTA_CONFIG` (si se quiere apuntar a otra ubicacion del JSON)

Notas:
- Con MFA, normalmente se requerira validacion manual en el flujo SSO.
- Las cookies de sesion se persisten en `runtime/session_cookies.json`.

## Instalacion y ejecucion (script)

```powershell
cd personio_fichajes
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python .\src\servicio.py
```

O con lanzador:

```bat
ejecutar_servicio_script.bat
```

## Flujo recomendado (Chrome Personio dedicado)

Por cambios de seguridad en Chrome 136+, para usar depuracion remota de forma fiable se debe usar
un `user-data-dir` no estandar.

Flujo diario recomendado:
1. Abrir `Chrome Personio.lnk` (perfil dedicado en `C:\chromeDebug-personio`).
2. Mantener esa ventana abierta con sesion iniciada en Personio.
3. Ejecutar el bot (`ejecutar_servicio_script.bat YYYY-MM-DD`) o dejar que lo lance la tarea.

Comportamiento:
- Si Chrome Personio ya esta abierto, el bot se conecta al puerto `9222` y abre una pestaña nueva.
- Si Chrome Personio esta cerrado, `lanzar_tarea_programada.bat` lo arranca automaticamente y lo cierra al terminar si lo habia levantado esa misma ejecucion.
- Si la sesion SSO/MFA esta caducada, se requerira validacion manual.

## Ejecutar editor de configuracion

```powershell
python .\src\editor_config.py
```

## Compilar EXE con PyInstaller

```bat
build_exe.bat
```

Salida esperada:
- `personio_fichajes\dist\personio_fichajes_servicio.exe`

## Estrategia de autenticacion implementada

- Se intenta reutilizar cookies persistidas.
- Se intenta conectar a Chrome Personio existente por `remote_debug_port`.
- Si la sesion no es valida, se lanza Selenium para login SSO.
- Se admite autocompletado de usuario/password por variables de entorno (si aplica).
- Se espera confirmacion de login y MFA hasta timeout configurable.
- Tras login correcto, se guardan cookies para futuras ejecuciones.

## Tareas programadas

Scripts:
- `instalar_tareas_programadas.bat`
- `lanzar_tarea_programada.bat`
- `lanzar_catch_up.bat`
- `limpiar_stamp_desde_logs.bat`

Notas:
- Para registrar tareas, ejecutar `instalar_tareas_programadas.bat` como Administrador.
- Las tareas estan pensadas para ejecutarse con sesion de usuario iniciada (flujo interactivo de Chrome).
- Se registran 3 tareas:
  - **Fichaje Personio Lun-Jue** — Lun-Jue a las 17:50
  - **Fichaje Personio Vie** — Viernes a las 14:20
  - **Fichaje Personio Catch-up** — Lun-Vie a las 09:00 (watchdog de recuperacion)

## Limpieza automatica del stamp desde logs

Si algun dia quedo marcado por error en `runtime/fichajes_realizados.json`, puedes ejecutar:

```bat
limpiar_stamp_desde_logs.bat
```

Que hace esta utilidad:
- Analiza `runtime/personio_fichajes.log`, `runtime/tarea_programada.log` y `runtime/catch_up.log`.
- Detecta por fecha si el ultimo estado en logs es **exito** o **fallo**.
- Elimina del stamp solo las fechas cuyo ultimo estado sea fallo, para que catch-up las reintente.

Tambien se puede lanzar directamente con Python:

```powershell
cd personio_fichajes
.\.venv\Scripts\python.exe -m src.limpiar_stamp_desde_logs
```

## Recuperacion automatica de dias perdidos (catch-up)

Si el PC esta apagado o el bot falla a la hora programada, la tarea watchdog de las 09:00 detecta
automaticamente los dias sin imputar y los rellena.

Mecanismo:
- Tras cada imputacion exitosa se escribe `runtime/fichajes_realizados.json` (stamp file).
- Al arrancar en modo catch-up, el bot compara los ultimos `catch_up_dias` dias laborables con el stamp.
- Los dias ausentes del stamp se procesan automaticamente (el bot ya es idempotente: si Personio
  ya tiene periodos, no los sobreescribe).
- Si `headless=true`, el catch-up se ejecuta sin abrir Chrome visible y no reutiliza la ventana con
  depuracion remota aunque exista.
- Si algun dia falla igualmente, puede enviarse una alerta por email (ver seccion siguiente).
- Log de catch-up en `runtime/catch_up.log`.

Parametro de configuracion: `catch_up_dias` (defecto: `7`).

Limitacion importante:
- El catch-up headless funciona bien cuando puede reutilizar cookies/sesion persistida.
- Si la sesion SSO ha caducado y Microsoft/Personio vuelve a pedir MFA o confirmacion manual, el
  catch-up no podra completarlo en invisible y fallara, dejando log y opcionalmente enviando email.

### Alerta por email (opcional)

Si al terminar el catch-up quedan dias sin imputar, el bot puede enviar un email de aviso.

Configurar en `dist/configuracion.json`:

```json
{
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "smtp_user": "tu.cuenta@gmail.com",
  "smtp_password": "abcdefghijklmnop",
  "email_destinatario": "tu.cuenta@gmail.com"
}
```

Si no se configuran estos campos, la alerta por email queda desactivada silenciosamente.

#### Configurar Gmail — App Password

Gmail **no permite la contrasena normal** para SMTP. Se necesita una **Contrasena de aplicacion**:

1. Activar verificacion en 2 pasos en [myaccount.google.com/security](https://myaccount.google.com/security)
2. Ir a [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Seleccionar aplicacion **Correo**, dispositivo **Otro** (ej. "Personio Bot") → **Generar**
4. Copiar la clave de 16 caracteres (ej. `abcdefghijklmnop`) — solo se muestra una vez
5. Pegarla en `smtp_password` **sin espacios**

> **Seguridad:** asegurarse de que `configuracion.json` no este en ninguna ruta indexada por git
> (esta en `dist/`, que deberia estar en `.gitignore`).

#### Probar el envio de email desde consola

Para verificar que la configuracion SMTP funciona sin necesidad de que el bot falle realmente:

```powershell
cd personio_fichajes
.\.venv\Scripts\python.exe -c "
import sys; sys.path.insert(0, '.')
from src.config import cargar_configuracion
from src.logger import configurar_logger
from src.servicio import _enviar_alerta_email
from datetime import date

cfg = cargar_configuracion()
logger = configurar_logger(None)
_enviar_alerta_email(cfg, [date(2026, 4, 15), date(2026, 4, 16)], logger)
print('Listo.')
"
```

Si la configuracion es correcta, llega un email a `email_destinatario` con asunto
**"Personio: dias sin imputar tras catch-up"** y las dos fechas de prueba en el cuerpo.

## Fiabilidad

- Reintentos HTTP configurables para errores transitorios (429/5xx).
- Deteccion de sesion expirada (401/403 o redireccion implicita a login).
- Reautenticacion automatica y reintento de la llamada.
- Prevencion de duplicados: si el dia ya tiene periodos, no escribe de nuevo.
- Logs centralizados en consola y archivo rotativo.

## Consideraciones de produccion

- Mantener `modo_prueba=true` hasta validar entorno.
- Verificar permisos y politicas corporativas para automatizacion SSO.
- Revisar cambios de endpoints internos en Personio, ya que pueden variar con el tiempo.
