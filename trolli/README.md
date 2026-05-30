# Trolli (flet-trello-clone)

Clon de Trello construido con [Flet](https://flet.dev/) en Python. Permite gestionar tableros, listas y tarjetas, e incluye un visor avanzado de logs ULS de SharePoint.

## Características principales

- **Tableros tipo Trello**: creación, edición y visualización de tableros y listas.
- **Visor de logs ULS**: carga archivos `.log` de SharePoint (hasta 50 MB), con:
	- Filtros por nivel, búsqueda de texto libre y paginación eficiente.
	- Selector de columnas visibles y exportación a CSV del filtrado actual.
	- Overlay de carga no bloqueante y preferencias de usuario persistentes.
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

## Demo

Prueba la app en producción: [https://flet-trolli.fly.dev/](https://flet-trolli.fly.dev/)

## Créditos y notas

- Proyecto educativo/demostrativo, no afiliado a Atlassian ni Microsoft.
- El visor de logs soporta solo formato ULS tabulado de SharePoint.
- Compatible con Flet >= 0.85.2.

---
Desarrollado por [tu-nombre-o-alias].
