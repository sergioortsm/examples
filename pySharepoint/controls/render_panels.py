# controls/render_panels.py
from typing import Any, List, Optional
import flet as ft
from common.app_state import app_state
from common.interfaces import ISiteCollection, RoleDefinition

class PanelsRenderer:
    def __init__(self, store: app_state, page: ft.Page):
        self.store = store
        self.page = page
        self.expanded_index: Optional[int] = None
        self.selected_tabs: dict[int, int] = {}
        self.panels: list[ft.ExpansionPanel] = []

    # --- Helpers -----------------------------------------------------------

    def _normalize_roles(self, items):
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

    def _to_role_definitions(self, simple_list):
        return [RoleDefinition(Id=x["Id"], Name=x["Name"]) for x in simple_list]

    # --- Renderizado de filas ----------------------------------------------

    def _render_group_row_inline(self, group) -> ft.Control:
        all_roles = self._normalize_roles(self.store.get_roles_definiciones() or [])
        current_roles = self._normalize_roles(getattr(group, "Roles", []))

        roles_col = ft.Column(tight=True)
        actions_col = ft.Row(spacing=8)

        def _chips_from(roles):
            return ft.Row([ft.Chip(label=ft.Text(r["Name"])) for r in roles], wrap=True)

        def cancel_edit(_=None):
            current = self._normalize_roles(getattr(group, "Roles", []))
            roles_col.controls = [_chips_from(current)]
            actions_col.controls = [
                ft.IconButton(icon=ft.Icons.EDIT, tooltip="Editar", on_click=start_edit)
            ]
            self.page.update()

        def start_edit(_):
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
            self.page.update()

        def save_edit(_):
            selected_simple = []
            for cb, role in zip(roles_col.controls, all_roles):
                if isinstance(cb, ft.Checkbox) and cb.value:
                    selected_simple.append({"Id": role["Id"], "Name": role["Name"]})
            group.Roles = self._to_role_definitions(selected_simple)
            cancel_edit()

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

    def render_groups_table_editable(self, groups):
        controls = []
        # encabezado
        controls.append(
            ft.Container(
                content=ft.ResponsiveRow(
                    controls=[
                        ft.Column([ft.Text("Group Name", weight=ft.FontWeight.BOLD)],
                                  col={"xs": 12, "sm": 6, "md": 6}),
                        ft.Column([ft.Text("Permissions Levels", weight=ft.FontWeight.BOLD)],
                                  col={"xs": 12, "sm": 6, "md": 6}),
                    ],
                    spacing=30,
                    run_spacing=10,
                ),
                padding=ft.padding.symmetric(vertical=10, horizontal=20),
            )
        )
        for g in groups:
            controls.append(self._render_group_row_inline(g))
        return controls

    # --- Panels principales ------------------------------------------------

    def _handle_change(self, e: ft.ControlEvent):
        idx = int(e.data) if e.data is not None else None
        self.expanded_index = idx if self.expanded_index != idx else None

        for i, p in enumerate(self.panels):
            p.expanded = (i == self.expanded_index)

        if self.expanded_index is not None:
            selected_panel = self.panels[self.expanded_index]
            lista_id = selected_panel.data.get("id") # type: ignore
            lista_title = selected_panel.data.get("title") # type: ignore
            self.store.set_list_selected({"Id": lista_id, "Title": lista_title}) # type: ignore

        self.panel_list.update()

    def _on_tab_change(self, e: ft.ControlEvent, panel_idx: int):
        self.selected_tabs[panel_idx] = e.control.selected_index
        e.control.update()

    def _find_site_by_url(self, sites: list[ISiteCollection], url: str) -> ISiteCollection | None:
        """
        Busca recursivamente un ISiteCollection por URL dentro de una lista de sites/subsites.
        """
        for site in sites:
            if site.Url == url:
                return site
            if site.SubSites:
                found = self._find_site_by_url(site.SubSites, url)
                if found:
                    return found
        return None


    def render_lists_panels(self):
        all_lists = []
        
        # Determinar qué URL usar (subsite tiene prioridad)
        selected_url = None
        if self.store.subsite_selected and self.store.subsite_selected.Url:
            selected_url = self.store.subsite_selected.Url
        elif self.store.site_selected and self.store.site_selected.Url:
            selected_url = self.store.site_selected.Url

        if not selected_url:
            return ft.Text("No hay site o subsite seleccionado.")

        # Buscar el objeto ISiteCollection real de la URL seleccionada
        site = self._find_site_by_url(self.store.get_site_collections() or [], selected_url)
        
        if not site:
            return ft.Text(f"No se encontró el site/subsite con URL {selected_url}")
    
        all_lists = site.Lists or []
        
        for i, lst in enumerate(all_lists):
            self.selected_tabs.setdefault(i, 0)
            tabs = ft.Tabs(
                selected_index=self.selected_tabs[i],
                expand=1,
                on_change=lambda e, idx=i: self._on_tab_change(e, idx),
                tabs=[
                    ft.Tab(
                        text="GROUPS",
                        content=ft.Column(
                            [ft.ResponsiveRow(
                                controls=self.render_groups_table_editable(lst.Groups),
                                spacing=10, run_spacing=10
                            )]
                        )
                    ),
                    ft.Tab(
                        text="USERS",
                        content=ft.Column(
                            [ft.ResponsiveRow(
                                controls=self.render_groups_table_editable(lst.Users),
                                spacing=10, run_spacing=10
                            )]
                        )
                    ),
                    ft.Tab(text="INFO", content=ft.Column([ft.Text("Cualquier otra información")]))
                ],
            )

            body = ft.Container(content=tabs, padding=20, height=500)
            panel = ft.ExpansionPanel(
                header=ft.Text(getattr(lst, "Title", "Sin título"), weight=ft.FontWeight.BOLD),
                content=body,
                adaptive=True,
                data={"id": getattr(lst, "Id", None), "title": getattr(lst, "Title", None)}
            )
            self.panels.append(panel)

        self.panel_list = ft.ExpansionPanelList(
            controls=self.panels,
            on_change=self._handle_change,
        )

        return ft.Column(
            [ft.Text("Libraries/Lists", size=18, weight=ft.FontWeight.BOLD), self.panel_list],
            spacing=10,
            alignment=ft.MainAxisAlignment.START,
        )
