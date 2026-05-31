# Trolli (flet-trello-clone)

Clon de Trello construido con [Flet](https://flet.dev/) en Python. Permite gestionar tableros, listas y tarjetas, e incluye un visor avanzado de logs ULS de SharePoint.

## Características principales

- **Tableros tipo Trello**: creación, edición y visualización de tableros y listas.
- **Visor de logs ULS**: carga archivos `.log` de SharePoint (hasta 50 MB), con:
	- Filtros por nivel, búsqueda de texto libre y paginación eficiente.
	- Selector de columnas visibles y exportación a CSV del filtrado actual.
	- Overlay de carga no bloqueante y preferencias de usuario persistentes.
- **Notificaciones de aplicación**: banners superiores responsivos para mensajes de error y éxito, pensados para flujos de aplicación y `try/except` controlados.
- **UI responsiva**: interfaz moderna con [Flet](https://flet.dev/) y componentes personalizables.

## Requisitos

- Python >= 3.8
- [Flet 0.85.x](https://pypi.org/project/flet/)

Instalación de dependencias:

```bash
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r requirements.txt
```

## Ejecución local

```bash
flet run src/main.py
```

## Estructura del código fuente

`TrelloApp` usa **herencia múltiple por mixins** para mantener cada área funcional en su propio fichero. El orden de resolución (MRO) es:

```
TrelloApp(
    LogsWatcherMixin,      # _logs_watcher_mixin.py  — live tailing, ciclo de vida del watcher
    LogsExportMixin,       # _logs_export_mixin.py   — exportación a CSV
    LogsDetailMixin,       # _logs_detail_mixin.py   — diálogo de detalle + portapapeles
    LogsEventsMixin,       # _logs_events_mixin.py   — handlers de búsqueda, sort, paginación, columnas
    LogsLoadMixin,         # _logs_load_mixin.py     — carga de archivo, refresco paginado
    LogsCacheMixin,        # _logs_cache_mixin.py    — firmas e invalidación de caché
    LogsPreferencesMixin,  # _logs_prefs_mixin.py    — preferencias y almacenamiento persistente
    AppLayout,             # app_layout.py           — layout base con sidebar y área principal
)
```

`src/main.py` retiene únicamente `__init__`, helpers de UI, login/boards/routing y `main()` (~530 líneas).
Los ficheros de servicio (`log_service.py`, `log_buffer.py`, `log_watcher.py`, `logs_view.py`) permanecen sin cambios.

## Notificaciones de aplicación

La app incluye un componente reutilizable basado en `ft.Banner` para mostrar mensajes de estado en la parte superior de la pantalla, justo debajo del `AppBar`.

- Componente: `src/notification_banner.py`
- API pública en `TrelloApp`: `show_error(message)` y `show_success(message)`
- Casos de uso: errores controlados, confirmaciones de acciones y mensajes breves de la app

Ejemplo de uso desde la app:

```python
try:
	output_path = export_rows_to_csv(...)
	self.show_success(f"CSV exportado: {output_path}")
except Exception as exc:
	self.show_error(f"Error al exportar: {exc}")
```

## Log interno de la aplicación

- Por defecto, el log interno se escribe en la misma carpeta del punto de arranque:
	- En desarrollo, junto a `src/main.py`, por ejemplo `src/trolli.log`.
	- En una app empaquetada, junto al ejecutable.
- Si defines la variable de entorno `TROLLI_LOG_DIR`, esa carpeta tiene prioridad y el archivo se crea como `trolli.log` dentro de ella.

## Generar ejecutable Windows (.exe)

Usa el script `scripts/build-windows-exe.ps1` desde la raíz del proyecto (requiere entorno virtual activo):

```powershell
# Modo PyInstaller (recomendado, no requiere Flutter SDK)
.\scripts\build-windows-exe.ps1 -UsePyInstaller -OpenOutputDir

# Modo flet build (requiere Flutter SDK instalado)
.\scripts\build-windows-exe.ps1
```

El ejecutable queda en `build\pyinstaller\trolli\`. Copia **la carpeta entera** al servidor (no solo el `.exe`).

### Despliegue en servidor SharePoint

1. Copia la carpeta `build\pyinstaller\trolli\` al servidor.
2. Configura `watch_folder` en `logs_prefs.json` (o desde la UI) a la ruta de logs ULS:
   ```
   C:\Program Files\Common Files\Microsoft Shared\Web Server Extensions\16\LOGS
   ```
3. Ejecuta `trolli.exe`.

### Entornos con proxy SSL corporativo (CA privada)

En servidores SharePoint con proxy que intercepta SSL, el primer arranque falla con:

```
ssl.SSLCertVerificationError: certificate verify failed: unable to get local issuer certificate
```

Esto ocurre porque `flet_desktop` descarga su cliente Flutter (~20 MB) en el primer arranque via HTTPS. Una vez descargado queda cacheado en `%LOCALAPPDATA%\flet\bin\` y el error no vuelve a producirse.

**Solución: generar el ejecutable con `-AllowUntrustedSSL`**

```powershell
.\scripts\build-windows-exe.ps1 -UsePyInstaller -AllowUntrustedSSL -OpenOutputDir
```

Esto incluye un `trolli-launcher.bat` junto al `.exe`. En el servidor, ejecuta **`trolli-launcher.bat`** en lugar de `trolli.exe` directamente. El `.bat` activa la variable `TROLLI_SKIP_SSL_VERIFY=1` que parchea el contexto SSL de Python antes de que `flet_desktop` haga la descarga.

**Solución alternativa con CA corporativa (más segura)**

Si tienes el certificado raíz de la CA corporativa (exportado desde `certmgr.msc` → *Entidades de certificación raíz de confianza* → formato `.pem`):

```powershell
.\scripts\build-windows-exe.ps1 -UsePyInstaller -CACertBundle C:\ruta\ca-bundle.pem -OpenOutputDir
```

El `.pem` se copia junto al ejecutable y el launcher lo apunta via `SSL_CERT_FILE`. Esta opción mantiene la verificación SSL activa.

## Demo

Prueba la app en producción: [https://flet-trolli.fly.dev/](https://flet-trolli.fly.dev/)

## Créditos y notas

- Proyecto educativo/demostrativo, no afiliado a Atlassian ni Microsoft.
- El visor de logs soporta solo formato ULS tabulado de SharePoint.
- Compatible con Flet >= 0.85.2.

---

## Informe de rendimiento: Virtual Scrolling Real (2026-05-31)

### Contexto

`DataTable2` construye el body con un `ListView.builder` interno en Flutter, que **solo virtualiza si recibe una altura acotada (`bounded height`)**. Sin `height` fijo en el container, Flutter expande el widget a su contenido total y pinta **todas** las filas — independientemente del pool de Python.

### Cambios implementados

| Fichero | Cambio |
|---------|--------|
| [src/logs_view.py](src/logs_view.py) | `table_content_container.height=600` (inicial) + `clip_behavior=ANTI_ALIAS`. Constante `_TABLE_UI_OVERHEAD_PX=310`. `visible_vertical_scroll_bar=True` en `_build_table_pool`. Método `update_table_height(viewport_height)`. |
| [src/main.py](src/main.py) | `page.on_resize = _on_page_resize`. Llamada a `update_table_height(page.height)` en `initialize()`. |

### Datos de benchmark

**Archivo de prueba:** `SAPCOL03-20260529-1219.log` — 56.512 filas, 9 columnas, 20 MB.

#### Pre-fix (sin height acotado)

| rows | render ms | Impacto |
|------|-----------|--------|
| 50 | 295–490 ms | UI usable pero lenta |
| 250 | **27.464 ms** | Freeze total de UI — bloqueante |

#### Post-fix (con height acotado, `ListView.builder` activo en Flutter)

| Escenario | rows | render ms |
|-----------|------|-----------|
| Primera carga (cold, pool build) | 250 | ~4.000 ms |
| Render inmediata siguiente (warm, mismo tamaño) | 250 | **417 ms** |
| Cambio de tamaño de página 50→250 (warm) | 250 | 1.476–2.062 ms |
| rows=100 warm | 100 | 669–1.351 ms |
| rows=100 (cambio de tamaño desde 50) | 100 | 839–1.351 ms |
| rows=50 steady state (sin rebuild de pool) | 50 | 293–580 ms |
| rows=50 tras rebuild (250→50) | 50 | 885–1.253 ms |
| rows=18 (filtro activo) | 18 | 248 ms |
| rows=6 (live mode, primeras líneas) | 6 | 140 ms |

#### Coste de bridge por tamaño de slice

El pool mutación (Python) es O(1). El coste de serialización Flet (WebSocket diff) depende del **cambio en la longitud de la lista `rows`**:

| Evento | rows enviadas al bridge | Coste observado |
|--------|------------------------|-----------------|
| Sin cambio de longitud (steady state rows=50) | 0 diffs de estructura | 311–580 ms |
| Cambio 50→250 | +200 DataRow2 nuevas | ~1.500 ms |
| Cambio 250→50 | −200 DataRow2 removidas | ~885–1.253 ms |
| Rebuild completo de pool (cold build) | 250 DataRow2 × N celdas | ~4.000 ms (una sola vez) |

### Análisis

El freeze de **27 segundos** con `rows=250` desaparece completamente. Flutter ahora utiliza su `ListView.builder` interno y solo renderiza las ~14 filas visibles en pantalla (altura tabla ≈600px / 42px por fila).

El cuello de botella residual en cambios de tamaño es **100% coste del bridge de Flet**: `_pool_rows[:n]` serializa diffs estructurales del árbol de controles cuando `n` varía. 250 `DataRow2` × 9 columnas = 2.250 referencias de control enviadas al bridge. El pool elimina la *creación* de objetos Python pero no el coste de serialización estructural.

En steady state con `rows=50` fijo (paginación sin cambio de page_size), el rendimiento es idéntico al pre-fix (~350–490 ms), confirmando que el bottleneck pre-fix era exclusivamente Flutter render.

### Estado actual del stack de rendimiento

| Capa | Estado | Coste típico |
|------|--------|--------------|
| Creación de objetos Python (pool) | ✅ Sin allocations en render | 0 ms |
| Mutación de datos en pool | ✅ Solo `.value` y `bgcolor` | <1 ms |
| Renderizado Flutter | ✅ O(filas visibles) ~14 rows | incluido en render ms |
| Bridge Flet — steady state (mismo n) | ✅ Solo diffs de valores | 293–580 ms |
| Bridge Flet — cambio de tamaño de slice | ⚠️ O(Δn × celdas) | 800–2.000 ms |
| Filter + sort Python (100k filas) | ✅ Cache dos niveles | filter ~5ms, sort ~65ms |

### Siguiente paso pendiente (Opción B — Sliding Window)

Para eliminar el coste de bridge en cambios de page_size: **sliding window de tamaño fijo** (~60 `DataRow2` siempre en el slice), con dos `Container` spacers de altura variable que simulan el scroll total del dataset. El bridge siempre serializa exactamente ~60 rows independientemente del tamaño del dataset, la página actual o el page_size configurado.

---
Desarrollado por [tu-nombre-o-alias].
