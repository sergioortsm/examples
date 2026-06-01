# Smart Rules — Plan de pruebas y estado actual

## Estado del desarrollo (1 junio 2026)

### Archivos implementados

| Archivo | Estado |
|---|---|
| `src/smart_rules.py` | ✅ Creado y funcional |
| `src/_logs_rules_mixin.py` | ✅ Creado y funcional |
| `src/settings_view.py` | ✅ Creado — errores de API Flet corregidos |
| `src/logs_view.py` | ✅ Modificado (dropdown perfil, panel análisis, bordes) |
| `src/main.py` | ✅ Modificado (imports, mixin, estado, ruta /settings) |
| `src/sidebar.py` | ✅ Modificado (4ª entrada Settings) |
| `src/app_layout.py` | ✅ Modificado (`set_settings_view`) |

### Correcciones de API Flet 0.85.x aplicadas

- `ft.Tab(text=d)` → `ft.Tab(d)` (posicional, el param se llama `label=`)
- `ft.Tabs(tabs=[...])` → eliminado; reemplazado por barra manual con `ft.GestureDetector` + `ft.Container`
- `ft.TextButton(mouse_cursor=...)` → eliminado (no existe en 0.85.x); solo `ft.IconButton` y `ft.GestureDetector` lo aceptan

---

## Plan de pruebas

### 1. Settings — gestión de reglas

**Cómo acceder:** Clic en el icono ⚙️ en el sidebar (4ª posición)

| Prueba | Pasos | Resultado esperado |
|---|---|---|
| Cargar reglas predefinidas | Abrir Settings | 4 pestañas de dominio visibles; cada una muestra sus reglas |
| Cambiar pestaña | Clic en "Timer Jobs" | Lista cambia a reglas de Timer Jobs |
| Añadir regla | Clic "Añadir regla" → rellenar nombre/campo/patrón → Guardar | Regla aparece en lista; persiste tras reiniciar |
| Editar regla | Clic ✏️ en una regla → cambiar patrón → Guardar | Regla actualizada en lista |
| Eliminar regla | Clic 🗑️ → confirmar en diálogo | Regla desaparece de la lista |
| Restaurar predefinidas | Clic "Restaurar predefinidas" → confirmar | Todas las reglas vuelven a su estado original |
| Activar/desactivar regla | Toggle switch en una regla | Regla se activa o desactiva (no matchea cuando está desactivada) |

---

### 2. Perfil activo + highlighting de filas

**Requisito:** Tener un log ULS cargado en la vista de Logs

| Prueba | Pasos | Resultado esperado |
|---|---|---|
| Seleccionar perfil | En toolbar de Logs, dropdown "Sin perfil" → elegir "SPFx" | Se ejecutan las reglas en background; filas con match reciben borde izquierdo morado (#7B52AB) |
| Cambiar perfil | Cambiar a "Timer Jobs" | Bordes cambian a azul (#1565C0); matches recalculados |
| Desactivar perfil | Elegir "Sin perfil" | Todos los bordes desaparecen |
| Paginación con perfil activo | Navegar a página 2 | Las filas de la nueva página también muestran bordes si coinciden |
| Múltiples matches en la misma fila | Fila que coincide con 2 reglas | Borde del color de la **primera** regla que matchea |

---

### 3. Panel de análisis

| Prueba | Pasos | Resultado esperado |
|---|---|---|
| Abrir panel | Con perfil activo, clic en botón 📊 de la toolbar | Panel visible bajo los filtros de columna; muestra chips con nombre de regla y contador |
| Cerrar panel | Clic de nuevo en 📊 | Panel se oculta |
| Sin perfil | Desactivar perfil → intentar abrir panel | Botón 📊 no visible o inactivo |
| Conteo correcto | Log con 3 líneas SPFx error + 1 web part | Chips muestran los conteos correctos por regla |

---

### 4. Persistencia

| Prueba | Pasos | Resultado esperado |
|---|---|---|
| Reglas se guardan | Añadir una regla → cerrar app → reabrir | La regla añadida sigue ahí |
| Fichero de reglas | Abrir `%APPDATA%\trolli\smart_rules.json` (o carpeta app data) | Fichero existe y contiene las reglas en JSON |
| Reglas no se mezclan entre perfiles | Editar regla de SPFx, cambiar a Timer Jobs | La lista de Timer Jobs no se ve afectada |

---

### 5. Prueba con log simulado (sin log ULS real)

Usa los scripts del proyecto para generar líneas de log en tiempo real:

```powershell
cd c:\repositorio\examples\trolli

# Genera un fichero de log con appends continuos
.\scripts\test-watcher-append.ps1
```

Luego en Trolli:
1. Ir a **Logs** → **Watcher** → apuntar a la carpeta `tmp-log-dir/`
2. Activar el watcher
3. En otro terminal ejecutar el script de append
4. Seleccionar un perfil en el dropdown
5. Verificar que los bordes aparecen en las filas que coincidan

---

### 6. Prueba de integración (reglas + watcher live)

| Prueba | Pasos | Resultado esperado |
|---|---|---|
| Rules con watcher activo | Perfil "SPFx" activo + watcher en marcha | Nuevas filas que llegan también reciben borde si coinciden (tras cada ciclo de drain) |
| Cambiar regla con watcher activo | Editar regla → Guardar | Las reglas se re-aplican automáticamente (`rerun_rules_if_active`) |

---

## Posibles problemas conocidos / a vigilar

- Si el dropdown "Sin perfil" no aparece en toolbar: verificar que `logs_view.py` fue guardado con los cambios (buscar `self.profile_dropdown`)
- Si Settings no abre: verificar que `sidebar.py` tiene 4 destinos y `app_layout.py` tiene `set_settings_view`
- Si las reglas no persisten: verificar que `resolve_app_data_dir()` devuelve una ruta escribible y que `smart_rules.json` se crea al añadir/editar
- Si el borde de color no aparece: verificar que `_pool_row_decorations` existe en `logs_view.py` y que `rule_matches` se rellena en `_logs_rules_mixin.py`
