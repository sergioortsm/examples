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
- Si Chrome Personio esta cerrado, `lanzar_tarea_programada.bat` lo arranca automaticamente.
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

Notas:
- Para registrar tareas, ejecutar `instalar_tareas_programadas.bat` como Administrador.
- Las tareas estan pensadas para ejecutarse con sesion de usuario iniciada (flujo interactivo de Chrome).

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
