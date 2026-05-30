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

## Demo

Prueba la app en producción: [https://flet-trolli.fly.dev/](https://flet-trolli.fly.dev/)

## Créditos y notas

- Proyecto educativo/demostrativo, no afiliado a Atlassian ni Microsoft.
- El visor de logs soporta solo formato ULS tabulado de SharePoint.
- Compatible con Flet >= 0.85.2.

---
Desarrollado por [tu-nombre-o-alias].
