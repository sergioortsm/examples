from board import Board
from data_store import DataStore
import flet as ft
from sidebar import Sidebar
from ui_tokens import APP_BORDER, APP_SHELL_ACCENT, APP_SHELL_ACCENT_HOVER, APP_SURFACE, APP_TEXT_MUTED, CLICK_CURSOR, click_button_style, surface_shadow


class AppLayout(ft.Row):
    def __init__(self, app, page: ft.Page, store: DataStore, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app = app
        self._page: ft.Page = page
        self._page.on_resized = self.page_resize
        self.store: DataStore = store
        self.toggle_nav_rail_button = ft.IconButton(
            icon=ft.Icons.ARROW_CIRCLE_LEFT,
            icon_color=APP_TEXT_MUTED,
            selected=False,
            selected_icon=ft.Icons.ARROW_CIRCLE_RIGHT,
            on_click=self.toggle_nav_rail,
        )
        self.sidebar = Sidebar(self, self.store)
        # Inicio con panel lateral contraido.
        self.sidebar.visible = False
        self.members_view = ft.Text("members view")
        if not hasattr(self, "logs_view"):
            self.logs_view = ft.Text("logs view")
        if not hasattr(self, "settings_view"):
            self.settings_view = ft.Text("settings view")
        if not hasattr(self, "search_view"):
            self.search_view = ft.Text("search view")
        if not hasattr(self, "analytics_view"):
            self.analytics_view = ft.Text("analytics view")
        self.all_boards_view = ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(
                            ft.Text(
                                value="Your Boards",
                                theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM,
                            ),
                            expand=True,
                            padding=ft.padding.Padding(top=15),
                        ),
                        ft.Container(
                            ft.TextButton(
                                "Add new board",
                                icon=ft.Icons.ADD,
                                on_click=self.app.add_board,
                                style=ft.ButtonStyle(
                                    bgcolor={
                                        ft.ControlState.DEFAULT: APP_SHELL_ACCENT,
                                        ft.ControlState.HOVERED: APP_SHELL_ACCENT_HOVER,
                                    },
                                    color={
                                        ft.ControlState.DEFAULT: APP_SURFACE,
                                        ft.ControlState.HOVERED: APP_SURFACE,
                                    },
                                    shape={
                                        ft.ControlState.DEFAULT: ft.RoundedRectangleBorder(
                                            radius=3
                                        )
                                    },
                                ),
                            ),
                            padding=ft.padding.Padding(right=50, top=15),
                        ),
                    ]
                ),
                ft.Row(
                    [
                        ft.TextField(
                            hint_text="Search all boards",
                            autofocus=False,
                            content_padding=ft.padding.Padding(left=10),
                            width=200,
                            height=40,
                            text_size=12,
                            border_color=APP_BORDER,
                            focused_border_color=APP_SHELL_ACCENT,
                            suffix_icon=ft.Icons.SEARCH,
                        )
                    ]
                ),
                ft.Row([ft.Text("No Boards to Display")]),
            ],
            expand=True,
        )
        self._active_view: ft.Control = self.all_boards_view

        self.controls = [self.sidebar, self.toggle_nav_rail_button, self.active_view]
        # Refleja estado contraido en el boton (muestra icono de expandir).
        self.toggle_nav_rail_button.selected = True

    @property
    def active_view(self):
        return self._active_view

    @active_view.setter
    def active_view(self, view):
        self._active_view = view
        if hasattr(self._active_view, "expand"):
            self._active_view.expand = True
        self.controls[-1] = self._active_view
        self.sidebar.sync_board_destinations()
        self._page.update()

    def set_board_view(self, i):
        self.active_view = self.store.get_boards()[i]
        self.sidebar.bottom_nav_rail.selected_index = i
        self.sidebar.top_nav_rail.selected_index = None
        self.page_resize()
        self._page.update()

    def set_all_boards_view(self):
        self.active_view = self.all_boards_view
        self.hydrate_all_boards_view()
        self.sidebar.top_nav_rail.selected_index = 0
        self.sidebar.bottom_nav_rail.selected_index = None
        self._page.update()

    def set_members_view(self):
        self.active_view = self.members_view
        self.sidebar.top_nav_rail.selected_index = 1
        self.sidebar.bottom_nav_rail.selected_index = None
        self._page.update()

    def set_logs_view(self):
        self.active_view = self.logs_view
        self.sidebar.top_nav_rail.selected_index = 2
        self.sidebar.bottom_nav_rail.selected_index = None
        self._page.update()

    def set_settings_view(self):
        self.active_view = self.settings_view
        self.sidebar.top_nav_rail.selected_index = 3
        self.sidebar.bottom_nav_rail.selected_index = None
        self._page.update()

    def set_search_view(self):
        self.active_view = self.search_view
        self.sidebar.top_nav_rail.selected_index = 4
        self.sidebar.bottom_nav_rail.selected_index = None
        if hasattr(self.search_view, "refresh"):
            self.search_view.refresh()
        self._page.update()

    def set_analytics_view(self):
        self.active_view = self.analytics_view
        self.sidebar.top_nav_rail.selected_index = 5
        self.sidebar.bottom_nav_rail.selected_index = None
        if hasattr(self.analytics_view, "refresh"):
            self.analytics_view.refresh()
        self._page.update()

    def page_resize(self, e=None):
        if type(self.active_view) is Board:
            self.active_view.resize(
                self.sidebar.visible, self._page.width, self._page.height
            )
        if hasattr(self.app, "on_layout_resize"):
            try:
                self.app.on_layout_resize(e)
            except Exception:
                pass
        self._page.update()

    def hydrate_all_boards_view(self):
        self.all_boards_view.controls[-1] = ft.Row(
            [
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(
                                expand=True,
                                content=ft.GestureDetector(
                                    content=ft.Text(value=b.name),
                                    data=b,
                                    mouse_cursor=CLICK_CURSOR,
                                    on_tap=self.board_click,
                                ),
                            ),
                            ft.Container(
                                content=ft.PopupMenuButton(
                                    items=[
                                        ft.PopupMenuItem(
                                            content=ft.Text(
                                                value="Delete",
                                                theme_style=ft.TextThemeStyle.LABEL_MEDIUM,
                                                text_align=ft.TextAlign.CENTER,
                                            ),
                                            on_click=self.app.delete_board,
                                            data=b,
                                            mouse_cursor=CLICK_CURSOR,
                                        ),
                                        ft.PopupMenuItem(),
                                        ft.PopupMenuItem(
                                            content=ft.Text(
                                                value="Archive",
                                                theme_style=ft.TextThemeStyle.LABEL_MEDIUM,
                                                text_align=ft.TextAlign.CENTER,
                                            ),
                                        ),
                                    ],
                                    style=click_button_style(),
                                ),
                                padding=ft.padding.Padding(right=-10),
                                border_radius=ft.BorderRadius(3, 3, 3, 3),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    border=ft.Border.all(1, APP_BORDER),
                    border_radius=ft.BorderRadius(5, 5, 5, 5),
                    bgcolor=APP_SURFACE,
                    shadow=surface_shadow(offset_y=4, blur_radius=12),
                    padding=ft.padding.Padding(left=10, top=10, right=10, bottom=10),
                    width=250,
                    data=b,
                )
                for b in self.store.get_boards()
            ],
            wrap=True,
        )
        self.sidebar.sync_board_destinations()

    def board_click(self, e):
        self.sidebar.bottom_nav_change(self.store.get_boards().index(e.control.data))

    def toggle_nav_rail(self, e):
        self.sidebar.visible = not self.sidebar.visible
        self.toggle_nav_rail_button.selected = not self.toggle_nav_rail_button.selected
        self.page_resize()
        self._page.update()
