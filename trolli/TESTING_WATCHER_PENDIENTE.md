# Testing del watcher en vivo — Estado y pendientes

> Documento de continuidad para retomar en otro chat. Resume qué se ha validado y qué queda
> pendiente del modo "watcher en vivo" (File Watcher LIFO) sobre ficheros `.log` de
> SharePoint OnPrem en local.

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

## Pendiente 🔲

### Problema bloqueante encontrado al hacer append

`Add-Content` de PowerShell **NO comparte escritura** y choca contra nuestro tailer (abierto con share read+write+delete). SharePoint sí abre con esos shares, así que para emularlo hay que usar `System.IO.FileStream` directamente.

Error obtenido:
```
Add-Content : El proceso no puede obtener acceso al archivo 'C:\Temp\LOGS\SAPCOL03-20260529-2319.log'
porque está siendo utilizado en otro proceso.
```

> **Importante**: el problema NO es nuestro código (nuestro tailer está bien). Es que `Add-Content`
> no abre con `FileShare.ReadWrite`. La prueba realista debe usar el snippet .NET de abajo.

> Estado actual: resuelto para testing mediante scripts PowerShell en `scripts/` que usan
> `System.IO.FileStream` con `FileShare.ReadWrite | Delete`.

### Test 1 — Append en vivo (compartiendo escritura como SharePoint) ✅

```powershell
$current = "C:\Temp\LOGS\SAPCOL03-20260529-2319.log"  # ajustar al actual "En vivo:"

$fs = [System.IO.FileStream]::new(
    $current,
    [System.IO.FileMode]::Append,
    [System.IO.FileAccess]::Write,
    [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
)
$sw = [System.IO.StreamWriter]::new($fs, [System.Text.Encoding]::UTF8)
try {
    1..30 | ForEach-Object {
        $ts = (Get-Date).ToString("MM/dd/yyyy HH:mm:ss.fff")
        $sw.WriteLine("$ts`tw3wp.exe (0x1234)`t0x5678`tTest Area`tTest Category`tabcd`tInformation`tAppend secuencial #$_`t")
        $sw.Flush()
        Start-Sleep -Seconds 1
    }
}
finally {
    $sw.Dispose()
    $fs.Dispose()
}
```

**Esperado**:
- 1 fila nueva por segundo, aparece arriba (LIFO, page 1).
- `buffer_count` sube 1 a 1.
- `lines/s` ≈ 1.
- `file_label` no cambia.

### Test 2 — Stress (50.000 líneas de golpe) ✅

```powershell
$current = "C:\Temp\LOGS\SAPCOL03-20260529-2319.log"

$fs = [System.IO.FileStream]::new(
    $current,
    [System.IO.FileMode]::Append,
    [System.IO.FileAccess]::Write,
    [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
)
$sw = [System.IO.StreamWriter]::new($fs, [System.Text.Encoding]::UTF8)
try {
    for ($i = 1; $i -le 50000; $i++) {
        $ts = (Get-Date).ToString("MM/dd/yyyy HH:mm:ss.fff")
        $sw.WriteLine("$ts`tw3wp.exe (0x1234)`t0x5678`tStress Area`tStress Category`tabcd`tInformation`tStress line #$i`t")
    }
    $sw.Flush()
}
finally {
    $sw.Dispose()
    $fs.Dispose()
}
```

**Esperado**:
- `buffer_count` salta a ~50.000 (cap 100.000).
- `lines/s` pico alto y baja.
- UI sigue respondiendo (scroll, clic).
- Sin `[WATCHER] Error` en consola.

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

## Scripts disponibles

- `scripts/test-watcher-append.ps1` — Test 1.
- `scripts/test-watcher-stress.ps1` — Test 2.
- `scripts/test-watcher-trickle.ps1` — soporte para Test 3 y Test 4.
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
