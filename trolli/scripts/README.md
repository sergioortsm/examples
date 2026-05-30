# Scripts de test del watcher en vivo

Documento de memoria/contexto para los scripts `test-watcher-*.ps1`. Resume **cómo
funciona el watcher en Trolli**, **por qué los tests están escritos así** y los
**gotchas** que ya se descubrieron (para no volver a tropezar).

> Alcance: SOLO uso local sobre `.log` de SharePoint OnPrem (ULS tabulado).
> Plataforma: Windows + PowerShell + Flet 0.85.2.

---

## 1. Arquitectura del watcher (resumen funcional)

Módulos en [src/](../src):

- [log_tailer.py](../src/log_tailer.py): abre el fichero con **Win32 `CreateFileW`**
  vía `ctypes`, con `FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE` y
  `FILE_FLAG_SEQUENTIAL_SCAN`. Lee por bloques de 1 MB y hace split por bytes
  (sin re-leer). Soporta `start_from_end=True` (primer arranque) y `False`
  (rotaciones, para no perder líneas).
- [log_buffer.py](../src/log_buffer.py): `LifoLogBuffer` thread-safe, basado en
  `deque(maxlen=100_000)` con `appendleft` → O(1) descarte del más antiguo.
- [log_watcher.py](../src/log_watcher.py): **thread propio** con polling de
  500 ms sobre la carpeta + regex del patrón. Detecta rotación por
  `LastWriteTime` y hace handoff al nuevo fichero. Al abrir nuevo fichero,
  lee la cabecera para enriquecer parseo.
- [log_service.py](../src/log_service.py): parseo ULS + filtros + paginación +
  export CSV (no específico del watcher, pero el drain pasa por aquí).
- Integración en [main.py](../src/main.py) y UI en [logs_view.py](../src/logs_view.py).

### Flujo watcher → UI

1. El **thread del watcher** detecta líneas nuevas y las acumula en una lista
   pendiente bajo `Lock`. **NUNCA toca `logs_state` ni `page`**.
2. Una **coroutine asyncio** (drain) corre cada **250 ms** desde el loop de Flet,
   vacía el batch pendiente, lo mete en el `LifoLogBuffer` y refresca la UI con
   coalescing (varios batches → un único `page.update()`).
3. Si la vista está "siguiendo en vivo" (page == 1, sin search, level == "All"),
   las nuevas filas se inyectan arriba.
4. Si hay **filtros activos o page > 1** → auto-pausa: incrementa
   `pending_new_count` y muestra chip **"N nuevas — clic para ver"**.

---

## 2. Gotcha clave: por qué NO usar `Add-Content`

`Add-Content` (y `>>`, `Out-File -Append`) en PowerShell abren el fichero **sin
`FileShare.ReadWrite`**. Como nuestro tailer ya tiene el handle abierto en modo
compartido, choca:

```
Add-Content : El proceso no puede obtener acceso al archivo '...' porque está
siendo utilizado en otro proceso.
```

SharePoint OnPrem **sí** abre sus `.log` con `FileShare.ReadWrite | Delete`,
por eso nuestro tailer funciona en producción. Para emularlo en local, los
tests usan `System.IO.FileStream` directamente con esos flags.

> Conclusión: el problema NO es el código del tailer. Es la PS API. Para
> reproducir la condición real de SharePoint hay que ir por .NET.

---

## 3. Cómo escriben los tests (patrón común)

`test-watcher-common.ps1` expone:

- `Resolve-WatcherLogFile -Folder -Pattern` → fichero **más reciente por
  `LastWriteTime`** (mismo criterio que el watcher).
- `Open-WatcherAppender -Path` → `FileStream` `Append` + `Write` +
  `FileShare.ReadWrite | Delete`, envuelto en `StreamWriter` UTF-8 **sin BOM**
  (para no ensuciar el primer parseo del tailer).
- `New-UlsLine -Message [-Area -Category -Level -Process -Tid -EventId]` →
  línea ULS tabulada con el formato que parsea [log_service.py](../src/log_service.py):

  ```
  Timestamp \t Process \t TID \t Area \t Category \t EventID \t Level \t Message \t Correlation
  ```

  Timestamp en formato `MM/dd/yyyy HH:mm:ss.fff` (US, como ULS real).

Todos los scripts:

- Hacen `Flush()` por línea (o al final, según el caso).
- Cierran handle en `finally` para no dejar el fichero ocupado entre runs.
- Por defecto miran en `C:\Temp\LOGS` con `*.log`. Override con `-Folder`,
  `-Pattern` o `-LogFile` directo.

---

## 4. Mapa de scripts ↔ tests del MD raíz

Referencia: [`PAUSA_REANUDAR.md`](../PAUSA_REANUDAR.md) y
[`TESTING_WATCHER_PENDIENTE.md`](../TESTING_WATCHER_PENDIENTE.md).

| Script | Test | Qué valida |
|---|---|---|
| [`test-watcher-append.ps1`](test-watcher-append.ps1) | **Test 1** – Append en vivo | 1 línea/intervalo aparece arriba (LIFO, page 1). `buffer_count` sube 1 a 1. `lines/s` ≈ 1/intervalo. `file_label` NO cambia. |
| [`test-watcher-stress.ps1`](test-watcher-stress.ps1) | **Test 2** – Stress 50k | `buffer_count` se acerca al cap (100k) sin romper. Pico de `lines/s`. UI responde. Sin `[WATCHER] Error`. |
| [`test-watcher-trickle.ps1`](test-watcher-trickle.ps1) | **Tests 3 y 4** – Auto-pausa y Stop/Start | Mientras el trickle escribe: activar filtros → chip "N nuevas". Stop → status vacío. Cambiar carpeta/patrón → Play → arranca limpio desde EOF. Persistencia tras reinicio de la app. |
| [`test-watcher-rotate.ps1`](test-watcher-rotate.ps1) | **bonus** – Rotación | `Copy-Item` + `mtime = now` → el watcher hace handoff y abre con `offset=0`. |

### Casos de uso típicos

```powershell
# Terminal 1: app
cd c:\repositorio\examples\trolli
.\.venv\Scripts\python.exe src\main.py

# Terminal 2: tests (uno cada vez, o el trickle en paralelo)
.\scripts\test-watcher-append.ps1                          # Test 1 rápido
.\scripts\test-watcher-stress.ps1 -Lines 50000             # Test 2
.\scripts\test-watcher-trickle.ps1 -DurationSeconds 600    # Tests 3+4 (10 min)
.\scripts\test-watcher-rotate.ps1                          # rotación on-demand
```

### Cómo observar la app mientras tanto

```powershell
Get-Content c:\repositorio\examples\trolli\src\trolli.log -Tail 30 -Wait
```

Buscar en `trolli.log`:

- `Abre <fichero>.log (offset inicial=N)` → confirma primer arranque (N=EOF)
  o rotación (N=0).
- Ausencia de `[WATCHER] Error` o `[TAILER] Error` durante todo el run.

---

## 5. Parámetros sensibles (por si hay que tunear)

- **Polling del watcher**: 500 ms (en [log_watcher.py](../src/log_watcher.py)).
  Si bajas el intervalo del `trickle` por debajo de 500 ms, varias líneas se
  agruparán en un mismo batch (esperado, no es bug).
- **Drain coroutine**: 250 ms (en [main.py](../src/main.py)). Por eso el
  append "fugaz" de 5 líneas seguidas se ve casi instantáneo y no línea a línea.
- **Cap del buffer LIFO**: 100.000 líneas. El stress de 50k lo deja a mitad;
  para validar el descarte, lanzar el stress dos veces o con `-Lines 150000`.
- **`start_from_end`**: `True` en el primer Play (no parsear histórico), `False`
  en rotaciones detectadas por el watcher (para no perder líneas del nuevo).

---

## 6. Reglas de oro al editar los scripts

1. **Nunca** usar `Add-Content`, `Out-File -Append`, `>>` ni `Set-Content` en
   el fichero que el watcher está leyendo. Solo `FileStream` con
   `FileShare.ReadWrite | Delete`.
2. UTF-8 **sin BOM**. `UTF8Encoding::new($false)`.
3. Cerrar el handle en `finally` con `.Dispose()` (ver
   `Open-WatcherAppender.Dispose`).
4. Mantener el formato tabulado de `New-UlsLine` — si cambia, hay que tocar el
   parser en [log_service.py](../src/log_service.py).
5. Para rotación, ajustar `LastWriteTime = Get-Date` tras `Copy-Item`
   (algunos casos copian con mtime original y el watcher no lo elige).
