# Plan: Chrome Remote Debugging para reutilizar sesión existente

## Objetivo

Permitir que el bot se conecte a un Chrome ya abierto por el usuario (con su perfil y sesión activa en Personio) sin pedir login ni MFA, abriendo simplemente una pestaña nueva en esa sesión.

## Por qué es necesario `--remote-debugging-port`

Chrome es un proceso cerrado. Selenium no puede conectarse a un Chrome ya en ejecución sin una "puerta" de comunicación. El flag `--remote-debugging-port=9222` activa el protocolo CDP (Chrome DevTools Protocol) en ese puerto, que es el único mecanismo estándar para que Selenium se enganche a un proceso Chrome existente.

Sin ese flag → Selenium solo puede lanzar Chrome nuevo → sesión vacía → login obligatorio.
Con ese flag → Selenium conecta al Chrome ya abierto → pestaña nueva en sesión existente → sin login.

## Solución implementada

### 1. `dist/configuracion.json`

Añadidos los campos:
- `"remote_debug_port": 9222` — puerto CDP donde Selenium buscará Chrome
- `"chrome_user_data_dir"` — ruta al perfil de Chrome del usuario
- `"chrome_profile_directory": "Profile 1"` — directorio del perfil concreto

### 2. `src/config.py`

Nuevos campos en `Configuracion`:
- `chrome_user_data_dir: str | None`
- `chrome_profile_directory: str | None`

### 3. `src/auth.py` — `_crear_o_conectar_driver()`

Lógica de prioridad:
1. Si `remote_debug_port` activo y Chrome escucha en ese puerto → conectar con `debuggerAddress`
2. Si `chrome_user_data_dir` configurado y Chrome no está en uso → lanzar Chrome con `--user-data-dir` + `--profile-directory` (carga cookies del perfil automáticamente)
3. Fallback → Chrome limpio + inyección de `session_cookies.json`

### 4. Accesos directos de Chrome (escritorio + menú inicio)

Modificados para incluir `--remote-debugging-port=9222 --profile-directory="Profile 1"`.

Así cada vez que el usuario abra Chrome normalmente, ya arranca con el puerto CDP activo.

### 5. `arrancar_chrome_personio.bat` (nuevo, ya creado)

Script de conveniencia para arrancar Chrome con el perfil y puerto correctos si el usuario prefiere no modificar sus accesos directos.

## Flujo resultante

```
Usuario abre Chrome normalmente (acceso directo modificado)
        │
        ▼
Chrome arranca con --remote-debugging-port=9222
        │
        ▼
Tarea programada lanza el bot
        │
        ▼
_chrome_debug_disponible() → True (socket abierto en 9222)
        │
        ▼
Selenium conecta con debuggerAddress → abre pestaña nueva
        │
        ▼
navegar_con_sesion() → driver.get(attendance_url)
        │
        ▼
Sesión ya activa → bot ficha sin login
```

## Pendiente / posibles mejoras

- [ ] Probar con Chrome abierto desde el acceso directo modificado y lanzar el bot
- [ ] Verificar que el acceso directo del menú inicio (ProgramData) se actualizó correctamente (requiere admin)
- [ ] Considerar si reutilizar el perfil de Chrome puede interferir con uso normal del navegador durante el fichaje
- [ ] Evaluar si `headless: true` + perfil es viable como alternativa sin abrir ventana visible
