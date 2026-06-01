# Motor de Reglas Inteligentes — Trolli

Implementación del sistema de detección de patrones de error en logs ULS de SharePoint.

---

## Objetivo

Detectar automáticamente errores relacionados con:
- **SPFx** — componentes web, manifiestos, CORS, tokens
- **Timer Jobs** — fallos de jobs, timeouts, OWSTIMER
- **wsps / Paquetes** — despliegue de soluciones, activación de features, ensamblados
- **PowerShell / Deploy** — acceso denegado, políticas de ejecución, identidades de AppPool

Cuando se activa un perfil:
1. Las filas coincidentes reciben un **borde izquierdo de color** (4 px) en la tabla.
2. Se muestra un **panel de análisis colapsable** con el recuento de matches por regla.

---

## Archivos nuevos

### `src/smart_rules.py`
Motor de reglas. Contiene:

| Símbolo | Descripción |
|---------|-------------|
| `SmartRule` | Dataclass con `id, name, domain, field, pattern, is_regex, highlight_color, enabled` |
| `ALL_DOMAINS` | Lista de los 4 dominios en orden de presentación |
| `DOMAIN_COLORS` | Colores hexadecimales por dominio |
| `_DEFAULT_RULES` | ~39 reglas predefinidas para los 4 dominios |
| `RulesEngine` | Motor con `load()`, `save()`, `apply()`, `get_rules()`, `get_rules_for_domain()`, `add_rule()`, `update_rule()`, `delete_rule()`, `reset_to_defaults()` |
| `rules_engine` | Instancia global compartida (singleton) |

**`apply(rows, domain)`** devuelve `dict[int, list[SmartRule]]` — índice en la lista de filas → reglas que matchearon. Es seguro llamarlo desde un hilo secundario (no muta estado).

IDs de reglas: deterministas vía MD5 truncado sobre `domain:name`, lo que garantiza estabilidad entre reinicios.

**Fichero de persistencia:** `%LOCALAPPDATA%\Trolli\smart_rules.json` (mismo directorio que `logs_prefs.json`).

---

### `src/_logs_rules_mixin.py`
Mixin para `TrelloApp`. Métodos públicos:

| Método | Llamado desde |
|--------|---------------|
| `on_profile_change(domain)` | `logs_view.py` — dropdown de perfil |
| `on_logs_toggle_analysis_panel()` | `logs_view.py` — botón analytics |
| `rerun_rules_if_active()` | `settings_view.py` — tras editar reglas |
| `_run_rules_async()` | Tarea asyncio interna |

`_run_rules_async` usa como snapshot `_logs_sort_cache_rows` si existe; si está vacío, cae back a `_logs_filter_cache_rows`. Llama a `rules_engine.apply()` en un hilo secundario (`asyncio.to_thread`) y actualiza `logs_state["rule_matches"]` solo si el dominio no cambió mientras corría.

---

### `src/settings_view.py`
Vista completa de CRUD de reglas (`ft.Column`, `expand=True`).

- **Tabs** por dominio (SPFx / Timer Jobs / wsps / PowerShell). Se implementan con un `ft.Row` manual + `GestureDetector` por pestaña (no `ft.Tabs`, cuya API cambió en Flet 0.85.x). La pestaña activa muestra un borde inferior de 3 px con el color de dominio y fondo `APP_SURFACE_MUTED`.
- **Lista de reglas** con columnas: Activa (checkbox), Nombre, Campo, Patrón, RE (regex), Color, Acciones
- **Botones**: Añadir regla, Restaurar predefinidas
- **Diálogo de edición**: Nombre, Campo (dropdown), Patrón, Es regex (checkbox), Color hex, Activa (checkbox)
- Confirmación para eliminar y para restaurar
- Guarda automáticamente en `smart_rules.json` en cada cambio. La ruta se deriva de `app._prefs_path.parent / "smart_rules.json"`.
- Relanza las reglas sobre los datos actuales si hay un perfil activo (`rerun_rules_if_active`)
- Usa `app._open_control(dialog)` / `app._close_control(dialog)` para abrir y cerrar `AlertDialog` de forma compatible con Flet 0.85.x.

---

## Archivos modificados

### `src/logs_view.py`

**Nuevos controles en `__init__`** (antes de `self.controls = [...]`):

```python
self.profile_dropdown       # ft.Dropdown, width=170, opciones Sin perfil + 4 dominios
self.analysis_toggle_button # ft.IconButton, ANALYTICS_OUTLINED, visible solo con perfil activo
self.analysis_panel         # ft.Container con analysis_total_text + analysis_chips_row
self.analysis_chips_row     # ft.Row(wrap=True) con chips por regla
self.analysis_total_text    # ft.Text con resumen
```

**Cambios en `self.controls`:** `analysis_panel` insertado entre `column_filters_row` y la fila del botón de pendientes.

**Cambios en toolbar:** `profile_dropdown` y `analysis_toggle_button` insertados entre `export_csv_button` y el espaciador `ft.Row([], expand=True)`.

**Nota:** `profile_dropdown` usa `on_select=` (no `on_change=`) porque en Flet 0.85.x `ft.Dropdown` emite el evento `on_select` al elegir una opción.

**Cambios en `_render_impl`:** actualiza `profile_dropdown.value`, `analysis_toggle_button.visible/icon_color` y llama a `_render_analysis_panel(state)`.

**Cambios en `_render_table`:** por cada slot, calcula `global_idx = (current_page - 1) * page_size + slot` y aplica:
```python
self._pool_row_decorations[slot].border = ft.Border(
    left=ft.BorderSide(4, matched[0].highlight_color)
)  # o None si no hay match
```

**Nuevo método `_render_analysis_panel(state)`:** construye chips de resumen (nombre corto + recuento) ordenados por frecuencia descendente.

---

### `src/main.py`

Nuevos helpers de diálogos (compatibilidad Flet 0.85.x, usados por `SettingsView`):

| Método | Comportamiento |
|--------|----------------|
| `_open_control(control)` | Si es `SnackBar`: asigna a `page.snack_bar` + `open=True`; fallback a `page.overlay`. Si es `AlertDialog`: usa `page.show_dialog()` o lo añade a `page.overlay`. |
| `_close_control(control)` | Pone `control.open = False`. |
| `_show_snack_bar(message)` | Envuelve `ft.SnackBar(ft.Text(message))` en `_open_control`. |

| Cambio | Detalle |
|--------|---------|
| Imports nuevos | `LogsRulesMixin`, `SettingsView`, `rules_engine as _rules_engine` |
| Herencia | `LogsRulesMixin` añadido como primer mixin en `TrelloApp` |
| `logs_state` | 3 nuevas claves: `active_domain: None`, `rule_matches: {}`, `analysis_panel_open: False` |
| `__init__` | Carga `smart_rules.json` vía `_rules_engine.load(...)` tras definir `_prefs_path` |
| `__init__` | `self.settings_view = SettingsView(self)` tras `self.logs_view` |
| `route_change` | Añadido `elif troute.match("/settings"): self.set_settings_view()` |

---

### `src/sidebar.py`

- Añadido `ft.NavigationRailDestination(label="Settings", icon=SETTINGS_OUTLINED, selected_icon=SETTINGS)` como cuarto destino.
- `height` del `top_nav_rail` aumentado de `165` a `210` px para acomodar el nuevo destino.
- `top_nav_change`: añadido `elif index == 3: self.page.navigate("/settings")`.

---

### `src/app_layout.py`

- Añadido `if not hasattr(self, "settings_view"): self.settings_view = ft.Text("settings view")` junto al placeholder de `logs_view`.
- Añadido método `set_settings_view()` que activa la vista y selecciona el índice 3 del rail.

---

## Colores de dominio

| Dominio | Color borde |
|---------|-------------|
| SPFx | `#7B52AB` (púrpura) |
| Timer Jobs | `#1565C0` (azul) |
| wsps / Paquetes | `#2E7D32` (verde) |
| PowerShell / Deploy | `#B71C1C` (rojo) |

---

## Reglas predefinidas (resumen)

### SPFx (11 reglas)
`failed to load component`, `could not find component`, `clientsideassets`, `component manifest`, `clientsidecomponent`, `script.*failed to load` (RE), `access-control-allow-origin`, `401 unauthorized`, `403 forbidden`, `webpart.*exception` (RE), `requestdigest`

### Timer Jobs (9 reglas)
`job.*failed` (RE), `job definition.*was not found`, `exceeded.*time limit` (RE), `sptimerjob`, `spjobdefinition`, `owstimer`, `timer.*job.*exception` (RE), `health analyzer`, `job.*throttl` (RE)

### wsps / Paquetes (9 reglas)
`solution deployment.*failed` (RE), `spfeaturereceiver` (RE), `assembly.*not found` (RE), `feature activation.*failed` (RE), `safecontrol`, `solution.*retract` (RE), `solution.*cannot be deployed`, `feature.*already activated` (RE), `strong name.*validation` (RE)

### PowerShell / Deploy (9 reglas)
`access is denied` (RE), `unauthorized`, `execution policy`, `running scripts is disabled`, `unauthorizedaccessexception`, `the remote server returned.*(401|403|500)` (RE), `cannot be loaded because`, `apppool.*identity` (RE), `token.*expired` (RE)
