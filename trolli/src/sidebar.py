import flet as ft
from data_store import DataStore


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
        ]

        self.top_nav_rail = ft.NavigationRail(
            selected_index=None,
            label_type=ft.NavigationRailLabelType.ALL,
            on_change=self.top_nav_change,
            destinations=self.top_nav_items,
            bgcolor=ft.Colors.BLUE_GREY,
            extended=True,
            height=165,
        )

        self.bottom_nav_rail = ft.NavigationRail(
            selected_index=None,
            label_type=ft.NavigationRailLabelType.ALL,
            on_change=self.bottom_nav_change,
            extended=True,
            expand=True,
            bgcolor=ft.Colors.BLUE_GREY,
        )
        self.toggle_nav_rail_button = ft.IconButton(ft.Icons.ARROW_BACK)

        super().__init__(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Workspace"),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    # divider
                    ft.Container(
                        bgcolor=ft.Colors.BLACK26,
                        border_radius=ft.BorderRadius(30, 30, 30, 30),
                        height=1,
                        alignment=ft.Alignment(x=1, y=0),
                        width=220,
                    ),
                    self.top_nav_rail,
                    # divider
                    ft.Container(
                        bgcolor=ft.Colors.BLACK26,
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
            bgcolor=ft.Colors.BLUE_GREY,
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

    def bottom_nav_change(self, e):
        index = e if (type(e) == int) else e.control.selected_index
        self.top_nav_rail.selected_index = None
        self.bottom_nav_rail.selected_index = index
        self.page.navigate(f"/board/{index}")
