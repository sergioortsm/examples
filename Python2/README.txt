Personio Auto Fichajes (workspace Python2)

Este workspace contiene dos ramas:
- `personio_fichajes/` -> proyecto ACTUAL (bot Selenium para Personio).
- `src/` y `Setup/` -> contenido legacy, conservado por compatibilidad.

--------------------------------------------------------------------------------
1) Requisitos
--------------------------------------------------------------------------------

- Python 3.13+ instalado en Windows.
- Chrome disponible (recomendado usar puerto de depuracion remota 9222 para reusar sesion).

Descarga Python:
https://www.python.org/downloads/windows/

Al instalar, marcar: Add Python to PATH.

--------------------------------------------------------------------------------
2) Puesta en marcha (proyecto actual)
--------------------------------------------------------------------------------

Desde `C:\repositorio\examples\Python2\personio_fichajes`:

1. Crear entorno virtual (solo la primera vez):
    python -m venv .venv

2. Instalar dependencias:
    .venv\Scripts\python.exe -m pip install -r requirements.txt

3. Ejecutar:
    ejecutar_servicio_script.bat

Opcional: probar una fecha concreta (formato YYYY-MM-DD):
    ejecutar_servicio_script.bat 2026-03-18

Tambien puedes lanzarlo desde la raiz del workspace:
    C:\repositorio\examples\Python2\ejecutar_servicio_script.bat 2026-03-18

--------------------------------------------------------------------------------
3) Compilar EXE (proyecto actual)
--------------------------------------------------------------------------------

Desde `personio_fichajes`:
    build_exe.bat

Salida:
    personio_fichajes\dist\personio_fichajes_servicio.exe

Lanzador de EXE desde raiz:
    ejecutar_servicio_exe.bat

--------------------------------------------------------------------------------
4) Programador de tareas
--------------------------------------------------------------------------------

Si usas Task Scheduler/NSSM, apunta al lanzador de raiz:
    C:\repositorio\examples\Python2\iniciar_servicio.bat

Flujo recomendado para Personio:
    1. Abrir "Chrome Personio" (acceso directo dedicado).
    2. Mantener esa ventana abierta con sesion iniciada.
    3. Dejar que la tarea programada lance el bot.

Nota importante:
    - En Chrome 136+ se usa perfil dedicado en C:\chromeDebug-personio para depuracion remota.
    - Si la sesion SSO/MFA caduca, puede requerirse intervencion manual.

Puedes pasar fecha opcional como argumento (uso manual de prueba):
    iniciar_servicio.bat 2026-03-18

--------------------------------------------------------------------------------
5) Configuracion y logs
--------------------------------------------------------------------------------

- Config principal del bot actual: `personio_fichajes\dist\configuracion.json`
- Runtime/cookies del bot actual: `personio_fichajes\runtime\`
- Para registrar tareas con `personio_fichajes\instalar_tareas_programadas.bat`, usar consola como Administrador.

Nota de seguridad:
- No guardar secretos en el raiz del repo.
- Mantener credenciales y tokens fuera de control de versiones.
