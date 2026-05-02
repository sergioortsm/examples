# Personio Auto Fichajes Bot

Bot de automatizacion de fichajes para Personio, inspirado en la arquitectura del proyecto original de auto fichajes.

## Estructura

```text
BotPersonio/
  src/
    __init__.py
    attendance_bot.py       # logica Selenium de fichaje
    auth.py                 # autenticacion SSO y cookies
    config.py               # modelo de configuracion (Pydantic)
    editor_config.py        # editor grafico de configuracion (Tkinter)
    filtrar_fichajes.py
    limpiar_stamp_desde_logs.py
    logger.py
    servicio.py             # punto de entrada del servicio
  dist/
    configuracion.json      # configuracion de produccion (no en git)
    personio_fichajes_servicio.exe  (tras compilar con build_exe.bat)
  runtime/
    fichajes_realizados.json  # stamp file de dias imputados
    session_cookies.json      # cookies persistidas
  requirements.txt
  arrancar_chrome_personio.bat
  ejecutar_servicio_script.bat
  lanzar_tarea_programada.bat
  lanzar_catch_up.bat
  instalar_tareas_programadas.bat
  limpiar_stamp_desde_logs.bat
  build_exe.bat
```

## Flujo diario

1. Comprueba si la fecha es festivo (lista `festivos` en config) — si lo es, la marca en stamp y termina sin abrir Chrome.
2. Login SSO en Personio (Microsoft/Azure AD + MFA) reutilizando cookies persistidas si son validas.
3. Navegacion con Selenium a la pagina de attendance del empleado.
4. Localizacion de la fila del dia en el timesheet semanal.
5. Salto de dias no aplicables: fin de semana (`data-is-weekend`), festivo que Personio conoce (`data-is-off-day`), dia ya con horas imputadas o aprobado.
6. Determinacion del horario segun el tipo de dia (vigilia intensiva / viernes / Lun-Jue).
7. Apertura del formulario de imputacion y relleno de los tramos horarios via Selenium.
8. Guardado y verificacion. Registro en stamp file si el guardado se confirma.

## Configuracion

Archivo: `dist/configuracion.json`

Campos principales:
- `employee_id` — ID numerico del empleado en Personio (obligatorio)
- `timezone` — zona horaria (defecto: `"Europe/Madrid"`)
- `base_url` — URL base de tu instancia Personio
- Horarios Lun-Jue: `morning_start`, `morning_end`, `afternoon_start`, `afternoon_end`
- Horario viernes: `friday_start`, `friday_end`
- Dias especiales: `festivos` (lista ISO), `vigilias_nacionales` (lista ISO) — ver seccion dedicada
- `headless` — Chrome invisible (defecto: `false`)
- `modo_prueba` — simula sin guardar en Personio (defecto: `false`)
- `modo_interactivo` — pide confirmacion en terminal (defecto: `true`; poner `false` en tareas programadas)
- `request_timeout_sec`, `login_timeout_sec`, `max_retries`
- `catch_up_dias` — ventana de dias a cubrir en modo catch-up (defecto: `7`)
- `sesion_cookies_path` — ruta al fichero de cookies (defecto: `session_cookies.json`)
- `remote_debug_port` (recomendado: `9222`)
- `chrome_user_data_dir` (recomendado: `C:\\chromeDebug-personio`)
- `chrome_profile_directory` (recomendado: `Profile 1`)
- SMTP (opcionales): `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `email_destinatario`

## Variables de entorno

### Variables de ejecucion (pasadas por los .bat)

| Variable | Descripcion |
|---|---|
| `SOLO_FECHA` | Fecha a imputar en formato `YYYY-MM-DD`. Obligatoria en modo normal. |
| `MODO_CATCH_UP` | Si es `1`, el servicio entra en modo catch-up y procesa los dias pendientes. |

### Variables de autenticacion (fichero `.env`)

Crear `.env` desde `.env.example`:

| Variable | Descripcion |
|---|---|
| `PERSONIO_SSO_USERNAME` | Usuario para autocompletar login SSO (opcional) |
| `PERSONIO_SSO_PASSWORD` | Password para autocompletar login SSO (opcional) |
| `RUTA_CONFIG` | Ruta alternativa al `configuracion.json` (opcional) |

Notas:
- Con MFA, normalmente se requerira confirmacion manual aunque se definan usuario y password.
- Las cookies de sesion se persisten en `runtime/session_cookies.json` para reutilizarlas en ejecuciones futuras.

## Instalacion y ejecucion (script)

```powershell
cd BotPersonio
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
- `BotPersonio\dist\personio_fichajes_servicio.exe`

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
cd BotPersonio
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
cd BotPersonio
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

## Festivos y jornada intensiva (vigilias)

El bot admite dos listas de fechas en `dist/configuracion.json` para controlar el comportamiento
en dias especiales:

### `festivos`

Fechas en las que **no se ficha**. El bot las omite completamente y las marca en el stamp file
para que el catch-up tampoco las reintente.

Corresponde a los festivos del calendario laboral de tu comunidad autónoma. Personio los marca
como `off-day` si están configurados en el sistema, pero si Personio no los conoce (festivos
locales, puentes pactados, etc.) puedes declararlos aquí para que el bot no los intente.

```json
"festivos": [
  "2026-01-01",
  "2026-01-06",
  "2026-04-03",
  "2026-05-01",
  "2026-08-15",
  "2026-10-12",
  "2026-11-02",
  "2026-12-07",
  "2026-12-08",
  "2026-12-25"
]
```

### `vigilias_nacionales`

Fechas de **jornada intensiva**: vísperas de festivos nacionales en las que se trabaja de
08:30 a 14:30 (tramo único, sin descanso de mediodía). Es el mismo esquema que los viernes
pero con el horario de mañana (`morning_start` → `morning_end`).

> Nota: solo aplica a vísperas de festivos **nacionales**. Los días anteriores a festivos
> exclusivamente locales o autonómicos se tratan con jornada normal.

```json
"vigilias_nacionales": [
  "2025-12-31",
  "2026-01-05",
  "2026-04-02",
  "2026-04-30",
  "2026-08-14",
  "2026-12-24"
]
```

### Comportamiento completo

| Tipo de día | Resultado |
|---|---|
| Fin de semana | Omitido (Personio lo marca como weekend) |
| Festivo en `festivos` | Omitido, marcado en stamp (sin Chrome) |
| Festivo que Personio ya conoce | Omitido por `data-is-off-day="true"` |
| Vigilia en `vigilias_nacionales` | Fichaje 08:30-14:30 (tramo único) |
| Viernes normal | Fichaje `friday_start`-`friday_end` (un tramo) |
| Lun-Jue normal | Fichaje mañana + tarde (dos tramos) |

### Editar las listas

Editar directamente `dist/configuracion.json` con un editor de texto. El editor gráfico
(`editor_config.py`) **no muestra** estas listas pero las preserva al guardar — no se perderán
si abres el editor para cambiar otros parámetros.

Las fechas deben estar en formato **`YYYY-MM-DD`**. El bot validará el formato al arrancar y
mostrará un error claro si alguna fecha es incorrecta.

---

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
