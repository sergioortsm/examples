# Testing del watcher en vivo — Estado actualizado

> Documento de continuidad del modo "watcher en vivo" (File Watcher LIFO) sobre ficheros `.log`
> de SharePoint OnPrem en local. Queda como resumen limpio de lo ya validado y de los
> seguimientos reales que restan.

## Contexto rápido

- App: `src/main.py` (Flet 0.85.2).
- Entorno: Windows + `.venv` en `c:\repositorio\examples\trolli\.venv`.
- Constraint: SOLO uso local, solo lectura, lo más rápido posible.
- Módulos nuevos:
  - `src/log_tailer.py` — Win32 `CreateFileW` con `FILE_SHARE_READ|WRITE|DELETE` + `FILE_FLAG_SEQUENTIAL_SCAN`.
  - `src/log_buffer.py` — `LifoLogBuffer` thread-safe (`deque(maxlen=100_000)`).
  - `src/log_watcher.py` — polling 500 ms, regex sobre filename, rotación por mtime.
- Integración: estado/handlers en `src/main.py`, UI en `src/logs_view.py` (carpeta + patrón + botón Play/Stop + chip "Nuevas (N)").
- Scripts de test en `scripts/` (ver `scripts/README.md` para detalle completo).

## Validado ✅

1. **Carga inicial** (snapshot tail desde EOF) — OK.
2. **Rotación** (Copy-Item del actual con timestamp > mtime original):
   - `file_label` cambia.
   - Nuevo fichero se abre desde `offset=0` (confirmado en `trolli.log`):
     ```
     19:16:24  Abre SAPCOL03-20260529-2319.log (offset inicial=9203558)  ← primer arranque (EOF)
     19:25:02  Abre SAPCOL03-20260530-1200.log (offset inicial=0)         ← rotación
     19:29:15  Abre SAPCOL03-20260529-2319.log (offset inicial=0)         ← otra rotación
     ```
   - Sin errores `[WATCHER]` ni `[TAILER]`.
3. **Append rápido (5 líneas)** — funciona, pero visualmente fugaz (poll 500 ms + drain 250 ms).
4. **`watch_status_text` en verde** durante toda la operación.
5. **Test 1 — Append en vivo** ✅ (30/05/2026)
    - Script usado: `scripts/test-watcher-append.ps1`.
    - Escritura real: 30 líneas, 1 por segundo, sin errores de acceso.
    - Comportamiento observado en UI: entraban filas nuevas y contadores activos; se vieron ~19 líneas porque el watcher abrió el fichero desde EOF unos 10 s después de arrancar el script.
    - Conclusión: correcto. Si el append empieza antes de que el watcher quede activo, las primeras líneas previas al offset inicial no se verán en vivo.
6. **Test 2 — Stress 50.000 líneas** ✅ (30/05/2026)
    - Script usado: `scripts/test-watcher-stress.ps1 -Lines 50000`.
    - Resultado de escritura: 50.000 líneas en 2,97 s (~16.847 líneas/s).
    - Resultado en UI: `buffer_count=50019`, carga fluida, sin errores en `trolli.log`.

## Estado actual

- No hay bloqueantes funcionales abiertos para el watcher en vivo.
- El problema de testing con `Add-Content` quedó acotado: no sirve para emular SharePoint porque
  no abre con `FileShare.ReadWrite`. Los scripts de `scripts/` ya usan `System.IO.FileStream`
  con `FileShare.ReadWrite | Delete`, que es el camino válido para las pruebas.
- Los tests principales de append, stress, auto-pausa y ciclo Stop/Start quedaron cerrados.

### Test 3 — Auto-pausa con filtros ✅ (30/05/2026)

Recomendación práctica: lanzar `scripts/test-watcher-trickle.ps1` como **job de PowerShell**,
no como comando foreground largo, porque en sesiones previas la ejecución larga desde terminal
interactiva terminó con exit code 1 aunque el script corto sí funcionó.

```powershell
$job = Start-Job -Name watcher_trickle_test -ScriptBlock {
    Set-Location 'C:\repositorio\examples\trolli'
    .\scripts\test-watcher-trickle.ps1 -DurationSeconds 120
}
```

Para parar y limpiar el job:

```powershell
Get-Job -Name watcher_trickle_test | Stop-Job
Get-Job -Name watcher_trickle_test | Remove-Job
```

Validado en repetición de prueba con `scripts/test-watcher-trickle.ps1` (120 s, 1 línea/s):

1. Con watcher activo y filtro aplicado, aparece el chip **"Nuevas (N)"** y el contador sube.
2. Mientras hay filtro activo, las filas nuevas no se inyectan en la tabla (auto-pausa correcta).
3. Al hacer clic en el chip, se vuelca el buffer de pendientes y el chip desaparece.

Conclusión: **cerrado**. El comportamiento de auto-pausa + recuperación manual de nuevas líneas funciona como se diseñó.

### Test 4 — Stop/Start cycle ✅ (30/05/2026)

Validado con evidencia en runtime (`src/trolli.log`) + revisión de flujo en código:

1. **Stop/Start observado en logs**:
    - `20:03:35` → `[WATCHER] Arrancando ...`
    - `20:05:17` → `[WATCHER] Parado ...`
    - `20:10:04` → `[WATCHER] Arrancando ...`
2. **Arranque limpio desde EOF** confirmado en log de tailer:
    - `20:10:05` → `[TAILER] Abierto ... (offset inicial=14957534)`
    - Esto confirma comportamiento de primer arranque del fichero actual desde final (`start_from_end=True`).
3. **Reinicio de estado al volver a Play** confirmado en código (`_start_watcher`):
    - resetea buffer (`LifoLogBuffer` nuevo), `pending_new_count=0`, `buffer_count=0`, `current_page=1`.
4. **Persistencia de `watch_folder` y `watch_pattern`** confirmada en código:
    - guardado en `_persist_logs_preferences()` y restaurado en `_restore_logs_preferences()`.

Conclusión: **cerrado**. El ciclo Stop/Start cumple lo esperado para modo live y mantiene persistencia de carpeta/patrón.

## Seguimiento real pendiente 🔲

1. Hacer una pasada final de smoke manual con datos reales de la carpeta objetivo antes de dar el
    flujo por completamente cerrado en uso diario.
2. Si se quiere documentar operación para terceros, mover de este archivo a README una versión
    corta de arranque + scripts de prueba, dejando este documento solo como historial técnico.

## Scripts disponibles

- `scripts/test-watcher-append.ps1` — append secuencial con shares compatibles.
- `scripts/test-watcher-stress.ps1` — burst de 50.000 líneas.
- `scripts/test-watcher-trickle.ps1` — goteo sostenido para auto-pausa y reanudación visual.
- `scripts/test-watcher-rotate.ps1` — simulación manual de rotación.
- `scripts/test-watcher-common.ps1` — helpers compartidos.

## Comandos útiles

### Reanudar app
```powershell
cd c:\repositorio\examples\trolli
.\.venv\Scripts\python.exe src\main.py
```

### Ver log de la app
```powershell
Get-Content c:\repositorio\examples\trolli\src\trolli.log -Tail 30 -Wait
```

### Smoke test de imports
```powershell
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); import log_tailer, log_buffer, log_watcher, log_service; print('OK')"
```

## Notas de diseño confirmadas

- **Tailer**: `start_from_end=True` en primer arranque (no parsear histórico), `=False` en rotaciones (no perder líneas).
- **Buffer**: LIFO con `appendleft`, `maxlen=100_000`, O(1) descarte.
- **Drain loop**: async cada 250 ms, coalescing de lotes pendientes acumulados por el watcher (que vive en thread).
- **Thread safety**: callbacks del watcher SOLO acumulan a `_watcher_pending_batches` bajo `Lock`, nunca tocan UI ni `logs_state` directamente.
- **Auto-pausa**: `_is_view_following_live()` → `True` solo si `page==1` + sin search + level=="All". Si no, acumula `pending_new_count` y muestra chip.
- **Tests con datos realistas**: `scripts/test-watcher-common.ps1` ahora genera líneas ULS tabuladas con valores inspirados en logs reales (Process, Area, Category, EventID, Level, Correlation), para que los filtros sean significativos.
- **Chip de pendientes**: formato compacto actual en UI: `Nuevas (N)`.

## Resumen corto

El watcher en vivo quedó funcional y con los casos principales validados en local. Lo que queda no
es un bug abierto del watcher sino, como mucho, una validación final de operación con datos reales
en el entorno objetivo y decidir si parte de esta guía se compacta en documentación estable.
