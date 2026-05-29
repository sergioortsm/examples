# Estado de pausa - migración Flet 0.85.2

Fecha: 2026-05-29
Proyecto: trolli

## Objetivo original
Corregir error de ejecución:
- module 'flet.controls.margin' has no attribute 'only'

## Cambios YA aplicados
Se migraron usos de API antigua de Flet en estos archivos:
- src/main.py
- src/logs_view.py
- src/board.py
- src/app_layout.py
- src/board_list.py
- src/sidebar.py

### Ajustes realizados
1. margin/padding:
- Se reemplazó `ft.margin.only/all(...)` por `ft.margin.Margin(...)`.
- Se reemplazó `ft.padding.only/all/symmetric(...)` por `ft.padding.Padding(...)`.

2. FilePicker (Flet 0.85):
- Se cambió `ft.FilePicker(on_result=...)` a `ft.FilePicker()`.
- Se cambió el registro de overlay a servicios de página: `page.services.append(file_picker)`.
- Se cambió apertura de archivo a método async con `await file_picker.pick_files(...)`.

3. Dropdown:
- Se cambió `on_change` por `on_select` en dropdowns de logs.

4. alignment:
- Se reemplazó `ft.alignment.center` y `ft.alignment.center_right` por `ft.Alignment(x=..., y=...)`.

## Último error visto antes de pausar
Al ejecutar `python src/main.py` apareció:
- AttributeError: module 'flet.controls.border_radius' has no attribute 'all'

Archivo reportado en traceback:
- src/logs_view.py (border_radius=ft.border_radius.all(6))

## Pendiente inmediato al reanudar
1. Reemplazar todos los `ft.border_radius.all(...)` por constructor compatible (ejemplo: `ft.BorderRadius(...)` o API equivalente de 0.85).
2. Ejecutar app y corregir siguientes incompatibilidades si aparecen en cascada.
3. Validar navegación principal, logs y carga de archivo .log.

## Búsquedas útiles
- Buscar incompatibilidades de border radius:
  - rg "ft\.border_radius\.all\(" src

- Ejecutar app:
  - c:/repositorio/examples/trolli/.venv/Scripts/python.exe src/main.py

## Nota rápida
La migración va bien, pero hay más cambios de API en Flet 0.85 que salen en cadena al ejecutar.
