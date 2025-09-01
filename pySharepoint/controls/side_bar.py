from typing import Callable
import flet as ft

from common.app_state import app_state

class side_bar(ft.Container):
    def __init__(self, app_layout, store: app_state, page: ft.Page, on_nav_change):
        self.store: app_state = store
        self.app_layout = app_layout
        self.page = page
        self.nav_rail_visible = True
        self.on_nav_change_callback = on_nav_change 
          
        # Items comunes
        self.items = [
            ("Site Users", ft.Icons.PERSON),
            ("Site Administrators", ft.Icons.MANAGE_ACCOUNTS_ROUNDED),
            ("Site Groups", ft.Icons.GROUPS),
            ("Lists/Libraries", ft.Icons.LIST_ALT_SHARP),
        ]

        # Rail lateral (desktop/tablet)
        self.nav_rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            on_change=self._on_nav_change_internal,
            destinations=[
                ft.NavigationRailDestination(
                    label_content=ft.Text(lbl),
                    label=lbl,
                    icon=icon,
                    selected_icon=icon,
                )
                for (lbl, icon) in self.items
            ],
            bgcolor=ft.Colors.GREY_100,
            expand=True,
        )

        # Barra inferior (móvil)
        self.nav_bar = ft.NavigationBar(
            destinations=[
                ft.NavigationBarDestination(icon=icon, label=lbl)
                for (lbl, icon) in self.items
            ],
            on_change=self._on_nav_change_internal,
            bgcolor=ft.Colors.GREY_100,
        )

        # Layout contenedor
        super().__init__(
            content=self.nav_rail,
            width=150,
            bgcolor=ft.Colors.GREY_100,
            expand=True,
            visible=self.nav_rail_visible,
        )

        # Solo asignamos el listener de resize
        if self.page is not None:
            self.page.on_resize = self.on_resize  # type: ignore
            # No llamamos a on_resize aquí, se llamará automáticamente al primer render

    def on_resize(self, e):
        if self.page is None or self.page.width is None:
            return  # aún no está disponible
        w = self.page.width
        if w < 600:
            # móvil → nav bar
            self.content = self.nav_bar
            self.width = None
            self.height = 60
        elif w < 1000:
            # tablet → rail estrecho
            self.content = self.nav_rail
            self.width = 80
            self.nav_rail.extended = False
        else:
            # desktop → rail extendido
            self.content = self.nav_rail
            self.width = 250
            self.nav_rail.extended = True
        self.update()

    def _on_nav_change_internal(self, e):
        
        if isinstance(e, int):
            index = e
            if self.on_nav_change_callback:
                self.nav_rail.selected_index = 3
                self.on_nav_change_callback(self.items[3][0]) #posicionamos en libraries, si ha entrado aquí es porque probablemente se cambió de subsite..
        else:
            index = getattr(e.control, "selected_index", e)
            if 0 <= index < len(self.items):
                print("Navegando a:", self.items[index][0])
                if self.on_nav_change_callback:
                    self.on_nav_change_callback(self.items[index][0])
                
    def select_item(self, index: int):
        """Selecciona un item en el sidebar según el componente visible"""
        if self.content == self.nav_rail:
            self.nav_rail.selected_index = index
        elif self.content == self.nav_bar:
            self.nav_bar.selected_index = index
        # Llamamos al callback automáticamente
        self._on_nav_change_internal(index)
        self.update()
