import flet as ft
from data_store import DataStore
from ui_tokens import APP_BORDER, APP_DIVIDER, APP_SIDEBAR_BG, APP_TEXT_ON_ACCENT


class Sidebar(ft.Container):

    def __init__(self, app_layout, store: DataStore):
        self.store: DataStore = store
        self.app_layout = app_layout
        self.nav_rail_visible = True
        self.top_nav_items = [
            ft.NavigationRailDestination(
                label="Boards",
                icon=ft.Icons.BOOK_OUTLINED,
                selected_icon=ft.Icons.BOOK_OUTLINED,
            ),
            ft.NavigationRailDestination(
                label="Members",
                icon=ft.Icons.PERSON,
                selected_icon=ft.Icons.PERSON,
            ),
            ft.NavigationRailDestination(
                label="Logs",
                icon=ft.Icons.DESCRIPTION_OUTLINED,
                selected_icon=ft.Icons.DESCRIPTION,
            ),
            ft.NavigationRailDestination(
                label="Settings",
                icon=ft.Icons.SETTINGS_OUTLINED,
                selected_icon=ft.Icons.SETTINGS,
            ),
            ft.NavigationRailDestination(
                label="Buscador",
                icon=ft.Icons.MANAGE_SEARCH,
                selected_icon=ft.Icons.MANAGE_SEARCH,
            ),
        ]

        self.top_nav_rail = ft.NavigationRail(
            selected_index=None,
            label_type=ft.NavigationRailLabelType.ALL,
            on_change=self.top_nav_change,
            destinations=self.top_nav_items,
            bgcolor=APP_SIDEBAR_BG,
            extended=True,
            height=260,
        )

        self.bottom_nav_rail = ft.NavigationRail(
            selected_index=None,
            label_type=ft.NavigationRailLabelType.ALL,
            on_change=self.bottom_nav_change,
            extended=True,
            expand=True,
            bgcolor=APP_SIDEBAR_BG,
        )
        self.toggle_nav_rail_button = ft.IconButton(ft.Icons.ARROW_BACK)

        super().__init__(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Workspace", color=APP_TEXT_ON_ACCENT),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    # divider
                    ft.Container(
                        bgcolor=APP_DIVIDER,
                        border_radius=ft.BorderRadius(30, 30, 30, 30),
                        height=1,
                        alignment=ft.Alignment(x=1, y=0),
                        width=220,
                    ),
                    self.top_nav_rail,
                    # divider
                    ft.Container(
                        bgcolor=APP_DIVIDER,
                        border_radius=ft.BorderRadius(30, 30, 30, 30),
                        height=1,
                        alignment=ft.Alignment(x=1, y=0),
                        width=220,
                    ),
                    self.bottom_nav_rail,
                ],
                tight=True,
            ),
            padding=ft.padding.Padding(left=15, top=15, right=15, bottom=15),
            margin=ft.margin.Margin(left=0, top=0, right=0, bottom=0),
            width=250,
            bgcolor=APP_SIDEBAR_BG,
            border=ft.Border(right=ft.BorderSide(1, APP_BORDER)),
            visible=self.nav_rail_visible,
        )

    def sync_board_destinations(self):
        boards = self.store.get_boards()
        self.bottom_nav_rail.destinations = []
        for i in range(len(boards)):
            b = boards[i]
            self.bottom_nav_rail.destinations.append(
                ft.NavigationRailDestination(
                    label=b.name,
                    selected_icon=ft.Icons.CHEVRON_RIGHT_ROUNDED,
                    icon=ft.Icons.CHEVRON_RIGHT_OUTLINED,
                )
            )

    def toggle_nav_rail(self, e):
        self.visible = not self.visible
        self.page.update()

    def board_name_focus(self, e):
        e.control.read_only = False
        e.control.border = ft.InputBorder.OUTLINE
        self.page.update()

    def board_name_blur(self, e):
        self.store.update_board(
            self.store.get_boards()[e.control.data], {"name": e.control.value}
        )
        self.app_layout.hydrate_all_boards_view()
        e.control.read_only = True
        e.control.border = ft.InputBorder.NONE
        self.page.update()

    def top_nav_change(self, e):
        index = e if (type(e) == int) else e.control.selected_index
        self.bottom_nav_rail.selected_index = None
        self.top_nav_rail.selected_index = index
        if index == 0:
            self.page.navigate("/boards")
        elif index == 1:
            self.page.navigate("/members")
        elif index == 2:
            self.page.navigate("/logs")
        elif index == 3:
            self.page.navigate("/settings")
        elif index == 4:
            self.page.navigate("/search")

    def bottom_nav_change(self, e):
        index = e if (type(e) == int) else e.control.selected_index
        self.top_nav_rail.selected_index = None
        self.bottom_nav_rail.selected_index = index
        self.page.navigate(f"/board/{index}")
