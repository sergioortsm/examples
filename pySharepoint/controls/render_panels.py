from typing import Any, List, Optional
import flet as ft
from common.interfaces import RoleDefinition


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
                        ),
                        ft.Column(
                            [ft.Text("Permissions Levels", weight=ft.FontWeight.BOLD)],
                            col={"xs": 12, "sm": 6, "md": 6},
                        ),
                    ]
                ),
                padding=ft.padding.only(top=20) 
                # o margin=ft.margin.only(top=10) si quieres margen externo
            )
        )

    # Filas con los grupos
    for group in groups:
        controls.append(render_group_row(group, page, state))

    return controls


def render_lists_panels(state, page):

    _state = state  # para usar en funciones internas
    expanded_index: Optional[int] = None
    selected_tabs: dict[int, int] = {}
    panels: list[ft.ExpansionPanel] = []

    def handle_change(e: ft.ControlEvent):
        nonlocal expanded_index
        idx = int(e.data) if e.data is not None else None
        expanded_index = idx if expanded_index != idx else None

        for i, p in enumerate(panels):
            p.expanded = (i == expanded_index)

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
                                controls=render_groups_table_editable(lst.Groups, page, _state),
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
                                controls=render_groups_table_editable(lst.Users, page, _state),
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
            adaptive=True
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
