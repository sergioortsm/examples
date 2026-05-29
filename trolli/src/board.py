import itertools
import flet as ft
from board_list import BoardList
from data_store import DataStore


class Board(ft.Container):
    id_counter = itertools.count()

    def __init__(self, app, store: DataStore, name: str, page: ft.Page):
        self.page: ft.Page = page
        self.board_id = next(Board.id_counter)
        self.store: DataStore = store
        self.app = app
        self.name = name
        self.min_column_width = 240
        self.max_column_width = 420
        self.default_column_width = 250
        self.sidebar_width = 250
        self.chrome_width = 60        
        self.add_list_button = ft.FloatingActionButton(
            icon=ft.Icons.ADD, text="add a list", height=30, on_click=self.create_list
        )

        self.board_lists = ft.Row(
            controls=[self.add_list_button],
            vertical_alignment=ft.CrossAxisAlignment.START,
            scroll=ft.ScrollMode.AUTO,
            spacing=10,
            expand=True,
            width=self._get_available_width(True, self.app.page.width),
            height=(self.app.page.height - 95),
        )
        for l in self.store.get_lists_by_board(self.board_id):
            self.add_list(l)

        super().__init__(
            content=self.board_lists,
            data=self,
            margin=ft.margin.all(0),
            padding=ft.padding.only(top=10, right=0),
            height=self.app.page.height,
            expand=True,
        )
        self._apply_column_widths()

    def resize(self, nav_rail_extended, width, height):
        self.board_lists.width = self._get_available_width(nav_rail_extended, width)
        self._apply_column_widths()
        self.height = height
        self.update()

    def _get_available_width(self, nav_rail_extended: bool, width: float) -> float:
        sidebar_offset = self.sidebar_width if nav_rail_extended else 0
        return max(320, width - sidebar_offset - self.chrome_width)

    def _get_lists(self):
        return [c for c in self.board_lists.controls if isinstance(c, BoardList)]

    def _calculate_column_width(self) -> float:
        lists = self._get_lists()
        list_count = len(lists)

        if list_count == 0:
            return self.default_column_width

        page_width = self.app.page.width if self.app.page else 1200
        available_width = self.board_lists.width or self._get_available_width(
            True, page_width
        )

        # Solo hay gaps entre columnas: N-1
        total_gap_width = self.board_lists.spacing * max(0, list_count - 1)

        # Para pocas columnas, que llenen todo el ancho disponible
        width_for_lists = max(
            self.min_column_width * list_count,
            available_width - total_gap_width,
        )
        dynamic_width = width_for_lists / list_count

        # 1-4 columnas: sin tope superior para que se estiren y no quede hueco
        if list_count <= 4:
            return max(self.min_column_width, dynamic_width)

        # 5+ columnas: mantener tope para no tener columnas excesivas
        return max(self.min_column_width, min(self.max_column_width, dynamic_width))

    def _apply_column_widths(self):
        nav_visible = getattr(getattr(self.app, "sidebar", None), "visible", True)
        page_width = self.app.page.width if self.app.page else 1200
        self.board_lists.width = self._get_available_width(nav_visible, page_width)
        column_width = self._calculate_column_width()
        for board_list in self._get_lists():
            board_list.set_width(column_width)

    def create_list(self, e):

        option_dict = {
            ft.Colors.LIGHT_GREEN: self.color_option_creator(ft.Colors.LIGHT_GREEN),
            ft.Colors.RED_200: self.color_option_creator(ft.Colors.RED_200),
            ft.Colors.AMBER_500: self.color_option_creator(ft.Colors.AMBER_500),
            ft.Colors.PINK_300: self.color_option_creator(ft.Colors.PINK_300),
            ft.Colors.ORANGE_300: self.color_option_creator(ft.Colors.ORANGE_300),
            ft.Colors.LIGHT_BLUE: self.color_option_creator(ft.Colors.LIGHT_BLUE),
            ft.Colors.DEEP_ORANGE_300: self.color_option_creator(
                ft.Colors.DEEP_ORANGE_300
            ),
            ft.Colors.PURPLE_100: self.color_option_creator(ft.Colors.PURPLE_100),
            ft.Colors.RED_700: self.color_option_creator(ft.Colors.RED_700),
            ft.Colors.TEAL_500: self.color_option_creator(ft.Colors.TEAL_500),
            ft.Colors.YELLOW_400: self.color_option_creator(ft.Colors.YELLOW_400),
            ft.Colors.PURPLE_400: self.color_option_creator(ft.Colors.PURPLE_400),
            ft.Colors.BROWN_300: self.color_option_creator(ft.Colors.BROWN_300),
            ft.Colors.CYAN_500: self.color_option_creator(ft.Colors.CYAN_500),
            ft.Colors.BLUE_GREY_500: self.color_option_creator(ft.Colors.BLUE_GREY_500),
        }

        def set_color(e):
            color_options.data = e.control.data
            for k, v in option_dict.items():
                if k == e.control.data:
                    v.border = ft.border.all(3, ft.Colors.BLACK26)
                else:
                    v.border = None
            dialog.content.update()

        color_options = ft.GridView(runs_count=3, max_extent=40, data="", height=150)

        for _, v in option_dict.items():
            v.on_click = set_color
            color_options.controls.append(v)

        def close_dlg(e):
            if (hasattr(e.control, "text") and not e.control.text == "Cancel") or (
                type(e.control) is ft.TextField and e.control.value != ""
            ):
                new_list = BoardList(
                    self,
                    self.store,
                    dialog_text.value,
                    self.page,
                    color=color_options.data,
                )
                self.add_list(new_list)
            self.page.close(dialog)

        def textfield_change(e):
            if dialog_text.value == "":
                create_button.disabled = True
            else:
                create_button.disabled = False
            self.page.update()

        dialog_text = ft.TextField(
            label="New List Name", on_submit=close_dlg, on_change=textfield_change
        )
        create_button = ft.ElevatedButton(
            text="Create", bgcolor=ft.Colors.BLUE_200, on_click=close_dlg, disabled=True
        )
        dialog = ft.AlertDialog(
            title=ft.Text("Name your new list"),
            content=ft.Column(
                [
                    ft.Container(
                        content=dialog_text, padding=ft.padding.symmetric(horizontal=5)
                    ),
                    color_options,
                    ft.Row(
                        [
                            ft.ElevatedButton(text="Cancel", on_click=close_dlg),
                            create_button,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                tight=True,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            on_dismiss=lambda e: print("Modal dialog dismissed!"),
        )
        self.page.open(dialog)
        dialog_text.focus()

    def remove_list(self, list: BoardList, e):
        self.board_lists.controls.remove(list)
        self.store.remove_list(self.board_id, list.board_list_id)
        self._apply_column_widths()
        self.page.update()

    def add_list(self, list):
        self.board_lists.controls.insert(-1, list)
        self.store.add_list(self.board_id, list)
        self._apply_column_widths()
        self.page.update()

    def color_option_creator(self, color: str):
        return ft.Container(
            bgcolor=color,
            border_radius=ft.border_radius.all(50),
            height=10,
            width=10,
            padding=ft.padding.all(5),
            alignment=ft.alignment.center,
            data=color,
        )
