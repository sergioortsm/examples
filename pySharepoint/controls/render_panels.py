from typing import Any, List, Optional
import flet as ft
from common.app_state import app_state
from common.interfaces import RoleDefinition

# --- Helpers ---------------------------------------------------------------

def _normalize_roles(items):
    """
    Devuelve una lista de dicts {'Id': int|None, 'Name': str}
    Acepta objetos RoleDefinition, dicts {'Id','Name'} o dropdown {'key','text'}.
    """
    norm = []
    for r in items or []:
        if isinstance(r, dict):
            _id = r.get("Id", r.get("key"))
            _name = r.get("Name", r.get("text") or r.get("Title"))
        else:
            _id = getattr(r, "Id", getattr(r, "key", None))
            _name = getattr(r, "Name", getattr(r, "text", getattr(r, "Title", None)))
        try:
            _id = int(_id) if _id is not None else None
        except Exception:
            pass
        if _name is None and _id is not None:
            _name = str(_id)
        norm.append({"Id": _id, "Name": _name or ""})
    return norm


def _to_role_definitions(simple_list):
    """Convierte [{'Id','Name'}] -> List[RoleDefinition]."""
    return [RoleDefinition(Id=x["Id"], Name=x["Name"]) for x in simple_list]


# --- Fila inline -----------------------------------------------------------

def _render_group_row_inline(group, page: ft.Page, state) -> ft.Control:
    all_roles = _normalize_roles(state.roles_definiciones)
    current_roles = _normalize_roles(getattr(group, "Roles", []))

    roles_col = ft.Column(tight=True)
    actions_col = ft.Row(spacing=8)

    def _chips_from(roles):
        return ft.Row([ft.Chip(label=ft.Text(r["Name"])) for r in roles], wrap=True)

    def cancel_edit(_=None):
        # Recuperar últimos roles del grupo y mostrarlos como chips
        current = _normalize_roles(getattr(group, "Roles", []))
        roles_col.controls = [_chips_from(current)]
        actions_col.controls = [
            ft.IconButton(icon=ft.Icons.EDIT, tooltip="Editar", on_click=start_edit)
        ]
        page.update()

    def start_edit(_):
        # Checkboxes con todos los roles; marcamos los actuales
        selected_ids = {r["Id"] for r in current_roles if r["Id"] is not None}
        cbs = [
            ft.Checkbox(label=r["Name"], value=(r["Id"] in selected_ids))
            for r in all_roles
        ]
        roles_col.controls = cbs
        actions_col.controls = [
            ft.IconButton(icon=ft.Icons.SAVE, tooltip="Guardar", on_click=save_edit),
            ft.IconButton(icon=ft.Icons.CANCEL, tooltip="Cancelar", on_click=cancel_edit),
        ]
        page.update()

    def save_edit(_):
        # Lee checkboxes, mapea a RoleDefinition y guarda en el objeto
        selected_simple = []
        for cb, role in zip(roles_col.controls, all_roles):
            if isinstance(cb, ft.Checkbox) and cb.value:
                selected_simple.append({"Id": role["Id"], "Name": role["Name"]})
        group.Roles = _to_role_definitions(selected_simple)
        
        # (si aquí quieres llamar a SharePoint, este es el sitio)        
        #state.helper.update_group(group)
        
        cancel_edit()

    # Vista inicial (solo lectura)
    cancel_edit()

    return ft.ResponsiveRow(
        controls=[
            ft.Column([ft.Text(getattr(group, "Title", "Sin nombre"))],
                      col={"xs": 12, "sm": 6, "md": 6}),
            ft.Column([roles_col], col={"xs": 10, "sm": 5, "md": 5}),
            ft.Column([actions_col], col={"xs": 2, "sm": 1, "md": 1}),
        ],
        spacing=10,
        run_spacing=10,
    )
    
def render_library_row(library, state, page: ft.Page):
    """
    Renderiza una fila de Library con sus roles visibles y editable inline
    """

    # Roles actuales del library (ya los traes como objetos RoleDefinition)
    current_roles = getattr(library, "Roles", []) or []

    # Contenedor donde se verán roles (chips o checkboxes)
    roles_column = ft.Column()
    action_column = ft.Column()

    # --- Helpers ---
    def show_roles_as_chips():
        roles_column.controls = [
            ft.Row(
                [ft.Chip(label=ft.Text(r.Name or "")) for r in current_roles],
                wrap=True,
            )
        ]
        action_column.controls = [
            ft.IconButton(icon=ft.Icons.EDIT, tooltip="Editar", on_click=start_edit)
        ]
        page.update()

    def start_edit(e):
        checkboxes = [
            ft.Checkbox(
                label=r.Name,
                value=any(cr.Id == r.Id for cr in current_roles),
            )
            for r in state.roles_definiciones or []
        ]
        roles_column.controls = checkboxes
        action_column.controls = [
            ft.IconButton(icon=ft.Icons.SAVE, tooltip="Guardar", on_click=save_edit),
            ft.IconButton(icon=ft.Icons.CANCEL, tooltip="Cancelar", on_click=lambda _: show_roles_as_chips())
        ]
        page.update()

    def save_edit(e):
        selected = [
            r for cb, r in zip(roles_column.controls, state.roles_definiciones or [])
            if isinstance(cb, ft.Checkbox) and cb.value
        ]
        library.Roles = selected  # 🔥 convertir en List[RoleDefinition]
        show_roles_as_chips()

    # Inicializar en modo lectura
    show_roles_as_chips()

    return ft.Row(
        controls=[
            ft.Text(library.Title, weight=ft.FontWeight.BOLD, width=200),
            roles_column,
            action_column,
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )


def render_group_row(group, page, state):

    current_roles = getattr(group, "Roles", []) or []

    selected_ids: Optional[List[RoleDefinition]] = (
        list({r.Id: r for r in current_roles if r.Id is not None}.values()) or None
    )

    # Estado local: checkboxes para cada role
    checkboxes = []
    for role in (state.roles_definiciones or []):
        cb = ft.Checkbox(
            label=role["text"],
            value=any(int(role["key"]) == r.Id for r in selected_ids) if selected_ids else False,
        )
        checkboxes.append(cb)

    # Contenedor que simula el dropdown (colapsable con los checkboxes dentro)
    dropdown_panel = ft.Column(checkboxes, visible=False)

    def toggle_dropdown(_):
        dropdown_panel.visible = not dropdown_panel.visible
        page.update()

    def guardar(_):
        # Obtener IDs seleccionados
        selected_ids = [cb.label for cb in checkboxes if cb.value]

        # Buscar los objetos RoleDefinition completos
        selected_roles = [
            role for role in (state.roles_definiciones or [])
            if role["text"] in selected_ids
        ]
        # Actualizar el grupo
        group.Roles = [
            RoleDefinition(
                Id=int(role["key"]) if role.get("key") is not None else None,
                Name=role.get("text")
            )
            for role in selected_roles
        ]
        
        dropdown_panel.visible = False
        page.update()

    return ft.ResponsiveRow(
        controls=[
            # Columna izquierda: nombre fijo
            ft.Column(
                [ft.Text(group.Title, weight=ft.FontWeight.NORMAL)],
                col={"xs": 12, "sm": 6, "md": 6}
            ),
            # Columna derecha: permisos editables + botón guardar
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                text="Seleccionar roles",
                                on_click=toggle_dropdown,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.SAVE,
                                tooltip="Guardar cambios",
                                on_click=guardar,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    dropdown_panel
                ],
                col={"xs": 12, "sm": 6, "md": 6},
            ),
        ],
        spacing=10,
        run_spacing=5,
    )


def render_groups_table_editable(groups, page, state):
    """Devuelve lista de grupos como tabla editable (solo permisos)"""
    controls = []

    # Encabezado
    controls.append(
        ft.Container(
            content=ft.ResponsiveRow(
                controls=[
                    ft.Column(
                        [ft.Text("Group Name", weight=ft.FontWeight.BOLD)],
                        col={"xs": 12, "sm": 6, "md": 6},
                        horizontal_alignment=ft.CrossAxisAlignment.START,
                    ),
                    ft.Column(
                        [ft.Text("Permissions Levels", weight=ft.FontWeight.BOLD)],
                        col={"xs": 12, "sm": 6, "md": 6},
                        horizontal_alignment=ft.CrossAxisAlignment.START,
                    ),
                ],
                spacing=30,      # 👈 añade separación horizontal
                run_spacing=10,  # 👈 separación si se desborda en varias filas
            ),
            padding=ft.padding.symmetric(vertical=10, horizontal=20),  # 👈 más aire alrededor
        )
    )

    # Filas con los grupos
    for group in groups:
        controls.append(_render_group_row_inline(group, page, state))
        #controls.append(render_group_row(group, page, state))

    return controls



def render_lists_panels(state, page):
    _state = state   # 👈 alias estable, seguro en closures
    expanded_index: Optional[int] = None
    selected_tabs: dict[int, int] = {}
    panels: list[ft.ExpansionPanel] = []

    def handle_change(e: ft.ControlEvent):
        nonlocal expanded_index
                
        idx = int(e.data) if e.data is not None else None
        expanded_index = idx if expanded_index != idx else None

        for i, p in enumerate(panels):
            p.expanded = (i == expanded_index)

        if expanded_index is not None:
            selected_panel = panels[expanded_index]
            lista_id = selected_panel.data.get("id") # type: ignore
            lista_title = selected_panel.data.get("title") # type: ignore
            print(f"Panel abierto -> Id: {lista_id}, Title: {lista_title}")
            _state.list_selected ={"Id": lista_id, "Title": lista_title}  # type: ignore
      
        panel_list.update()

    def on_tab_change(e: ft.ControlEvent, panel_idx: int):
        selected_tabs[panel_idx] = e.control.selected_index
        e.control.update()

    all_lists = []
    for site in state.site_collections or []:
        for lst in site.Lists or []:
            all_lists.append(lst)

    for i, lst in enumerate(all_lists):
        selected_tabs.setdefault(i, 0)

        tabs = ft.Tabs(
            selected_index=selected_tabs[i],
            expand=1,
            on_change=lambda e, idx=i: on_tab_change(e, idx),
            tabs=[
                ft.Tab(
                    text="GROUPS",
                    content=ft.Column(
                        [
                            ft.ResponsiveRow(
                                controls=render_groups_table_editable(lst.Groups, page, state),
                                spacing=10,
                                run_spacing=10
                            )
                        ]
                    )
                ),
                ft.Tab(
                    text="USERS",
                    content=ft.Column(
                        [
                            ft.ResponsiveRow(
                                controls=render_groups_table_editable(lst.Users, page, state),
                                spacing=10,
                                run_spacing=10
                            )
                        ]
                    )
                ),
                ft.Tab(
                    text="INFO",
                    content=ft.Column(
                        [
                            ft.Text("Cualquier otra información"),
                        ],
                        tight=True,
                    ),
                ),
            ],
        )

        body = ft.Container(
            content=tabs,
            padding=20,
            height=500
        )

        panel = ft.ExpansionPanel(
            header=ft.Text(getattr(lst, "Title", "Sin título"), weight=ft.FontWeight.BOLD),
            content=body,
            adaptive=True,
            data={"id": getattr(lst, "Id", None), "title": getattr(lst, "Title", None)}            
        )
        
        panels.append(panel)

    panel_list = ft.ExpansionPanelList(
        controls=panels,
        on_change=handle_change,
    )

    main_column = ft.Column(
        [
            ft.Text(
                "Libraries/Lists",
                size=18,
                weight=ft.FontWeight.BOLD
            ),
            panel_list
        ],
        spacing=10,
        alignment=ft.MainAxisAlignment.START,
    )

    return main_column
