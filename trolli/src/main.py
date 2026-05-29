import flet as ft
from datetime import datetime
from pathlib import Path
from app_layout import AppLayout
from board import Board
from user import User
from data_store import DataStore
from memory_store import InMemoryStore
from logs_view import LogsView
from log_service import (
    apply_filters_sort_paginate,
    export_rows_to_csv,
    load_sharepoint_log,
)


class TrelloApp(AppLayout):
    def __init__(self, page: ft.Page, store: DataStore):
        self.page: ft.Page = page
        self.store: DataStore = store
        self.user: str | None = None
        self.page.on_route_change = self.route_change
        self.boards = self.store.get_boards()
        self.logs_rows: list[dict[str, str]] = []
        self.logs_state = {
            "file_path": "",
            "file_label": "Sin archivo cargado",
            "is_loading": False,
            "columns": [],
            "visible_columns": [],
            "level_options": ["All"],
            "search_text": "",
            "level_filter": "All",
            "sort_by": None,
            "sort_desc": False,
            "page_size": 100,
            "current_page": 1,
            "total_pages": 1,
            "filtered_total": 0,
            "page_rows": [],
            "error": "",
            "message_dialog_open": False,
            "message_dialog_text": "",
            "message_dialog_title": "Detalle de Message",
        }
        self.login_profile_button = ft.PopupMenuItem(text="Log in", on_click=self.login)
        self.appbar_items = [
            self.login_profile_button,
            ft.PopupMenuItem(),  # divider
            ft.PopupMenuItem(text="Open SharePoint LOG", on_click=self.open_log_file_dialog),
            ft.PopupMenuItem(text="Settings"),
        ]
        self.appbar = ft.AppBar(
            leading=ft.Icon(ft.Icons.GRID_GOLDENRATIO_ROUNDED),
            leading_width=100,
            title=ft.Text(
                f"Trolli",
                font_family="Pacifico",
                size=32,
                text_align=ft.TextAlign.START,
            ),
            center_title=False,
            toolbar_height=75,
            bgcolor=ft.Colors.LIGHT_BLUE_ACCENT_700,
            actions=[
                ft.Container(
                    content=ft.PopupMenuButton(items=self.appbar_items),
                    margin=ft.margin.only(left=50, right=25),
                )
            ],
        )
        self.page.appbar = self.appbar
        self.file_picker = ft.FilePicker(on_result=self.on_log_file_selected)
        self.page.overlay.append(self.file_picker)
        self.logs_message_dialog_title = ft.Text("")
        self.logs_message_dialog_body = ft.Text("", selectable=True)
        self.logs_message_dialog: ft.AlertDialog = ft.AlertDialog(
            modal=True,
            title=self.logs_message_dialog_title,
            content=ft.Container(
                content=self.logs_message_dialog_body,
                width=800,
                height=360,
                padding=ft.padding.all(8),
            ),
            actions=[
                ft.TextButton("Copiar", on_click=self.on_logs_copy_message_detail),
                ft.TextButton("Cerrar", on_click=self.on_logs_close_message_detail),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=self.on_logs_close_message_detail,
        )
        self._restore_logs_preferences()
        self.logs_view = LogsView(self)
        self.logs_view.render(self.logs_state)

        self.page.update()
        super().__init__(
            self,
            self.page,
            self.store,
            tight=False,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def initialize(self):
        self.page.views.append(
            ft.View(
                "/",
                [self.appbar, self],
                padding=ft.padding.all(0),
                bgcolor=ft.Colors.BLUE_GREY_200,
            )
        )
        self.page.update()
        # create an initial board for demonstration if no boards
        if len(self.boards) == 0:
            self.create_new_board("My First Board")
        self.page.go("/")

    def _restore_logs_preferences(self):
        defaults = {
            "search_text": "",
            "level_filter": "All",
            "sort_by": None,
            "sort_desc": False,
            "page_size": 100,
            "visible_columns": [],
        }
        for key, default_value in defaults.items():
            try:
                stored_value = self.page.client_storage.get(f"logs_{key}")
            except Exception:
                stored_value = None
            self.logs_state[key] = default_value if stored_value is None else stored_value

    def _persist_logs_preferences(self):
        self.page.client_storage.set("logs_search_text", self.logs_state["search_text"])
        self.page.client_storage.set("logs_level_filter", self.logs_state["level_filter"])
        self.page.client_storage.set("logs_sort_by", self.logs_state["sort_by"])
        self.page.client_storage.set("logs_sort_desc", self.logs_state["sort_desc"])
        self.page.client_storage.set("logs_page_size", self.logs_state["page_size"])
        self.page.client_storage.set("logs_visible_columns", self.logs_state["visible_columns"])

    def open_log_file_dialog(self, e=None):
        self.file_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["log"],
            dialog_title="Selecciona un archivo .log de SharePoint",
        )

    def on_log_file_selected(self, e: ft.FilePickerResultEvent):
        if not e.files:
            return
        file_path = e.files[0].path
        if not file_path:
            return
        self.load_log_file(file_path)
        if self.page.route != "/logs":
            self.page.go("/logs")
        else:
            self.set_logs_view()

    def load_log_file(self, file_path: str):
        self.logs_state["is_loading"] = True
        self.logs_view.render(self.logs_state)
        self.page.update()

        try:
            result = load_sharepoint_log(file_path)
            if result.error:
                self.logs_rows = []
                self.logs_state.update(
                    {
                        "file_path": file_path,
                        "file_label": f"Archivo: {Path(file_path).name}",
                        "columns": [],
                        "visible_columns": [],
                        "level_options": ["All"],
                        "current_page": 1,
                        "total_pages": 1,
                        "filtered_total": 0,
                        "page_rows": [],
                        "error": result.error,
                    }
                )
                return

            self.logs_rows = result.rows
            visible_columns = self.logs_state.get("visible_columns", [])
            valid_visible = [c for c in visible_columns if c in result.columns]
            if not valid_visible:
                valid_visible = list(result.columns)

            sort_by = self.logs_state.get("sort_by")
            if sort_by not in result.columns:
                sort_by = result.columns[0] if result.columns else None

            level_filter = self.logs_state.get("level_filter", "All")
            level_options = ["All"] + result.levels
            if level_filter not in level_options:
                level_filter = "All"

            self.logs_state.update(
                {
                    "file_path": file_path,
                    "file_label": f"Archivo: {Path(file_path).name}",
                    "columns": result.columns,
                    "visible_columns": valid_visible,
                    "level_options": level_options,
                    "sort_by": sort_by,
                    "level_filter": level_filter,
                    "current_page": 1,
                    "error": "",
                }
            )

            self.refresh_logs_view()
        finally:
            self.logs_state["is_loading"] = False
            self.logs_view.render(self.logs_state)
            self.page.update()

    def _refresh_logs_view_core(self):
        if not self.logs_state.get("columns"):
            self.logs_state.update(
                {
                    "page_rows": [],
                    "filtered_total": 0,
                    "total_pages": 1,
                    "current_page": 1,
                }
            )
            self.logs_view.render(self.logs_state)
            self.page.update()
            return

        page_rows, filtered_total, total_pages, safe_page = apply_filters_sort_paginate(
            self.logs_rows,
            self.logs_state["columns"],
            self.logs_state["search_text"],
            self.logs_state["level_filter"],
            self.logs_state["sort_by"],
            self.logs_state["sort_desc"],
            self.logs_state["current_page"],
            int(self.logs_state["page_size"]),
        )

        self.logs_state.update(
            {
                "page_rows": page_rows,
                "filtered_total": filtered_total,
                "total_pages": total_pages,
                "current_page": safe_page,
            }
        )
        self._persist_logs_preferences()
        self.logs_view.render(self.logs_state)
        self.page.update()

    def refresh_logs_view(self, show_loading: bool = True):
        # Centraliza el overlay para cualquier accion que refresque el listado.
        if show_loading and not bool(self.logs_state.get("is_loading", False)):
            self.logs_state["is_loading"] = True
            self.logs_view.render(self.logs_state)
            self.page.update()
            try:
                self._refresh_logs_view_core()
            finally:
                self.logs_state["is_loading"] = False
                self.logs_view.render(self.logs_state)
                self.page.update()
            return

        self._refresh_logs_view_core()

    def on_logs_search_change(self, value: str):
        self.logs_state["search_text"] = value or ""
        self.logs_state["current_page"] = 1
        self.refresh_logs_view()

    def on_logs_level_change(self, value: str | None):
        self.logs_state["level_filter"] = value or "All"
        self.logs_state["current_page"] = 1
        self.refresh_logs_view()

    def on_logs_sort_column_change(self, value: str | None):
        if value and value in self.logs_state["columns"]:
            self.logs_state["sort_by"] = value
        self.logs_state["current_page"] = 1
        self.refresh_logs_view()

    def on_logs_toggle_sort_direction(self):
        self.logs_state["sort_desc"] = not self.logs_state["sort_desc"]
        self.logs_state["current_page"] = 1
        self.refresh_logs_view()

    def on_logs_page_size_change(self, value: str | None):
        try:
            self.logs_state["page_size"] = int(value or "100")
        except ValueError:
            self.logs_state["page_size"] = 100
        self.logs_state["current_page"] = 1
        self.refresh_logs_view()

    def on_logs_prev_page(self):
        self.logs_state["current_page"] = max(1, int(self.logs_state["current_page"]) - 1)
        self.refresh_logs_view()

    def on_logs_next_page(self):
        self.logs_state["current_page"] = min(
            int(self.logs_state["total_pages"]), int(self.logs_state["current_page"]) + 1
        )
        self.refresh_logs_view()

    def on_logs_toggle_column(self, column_name: str, is_visible: bool):
        current = list(self.logs_state.get("visible_columns", []))
        if is_visible and column_name not in current:
            current.append(column_name)
        if not is_visible and column_name in current:
            current.remove(column_name)

        if not current and self.logs_state["columns"]:
            current = [self.logs_state["columns"][0]]

        self.logs_state["visible_columns"] = current
        self.refresh_logs_view()

    def on_logs_export_click(self):
        if not self.logs_state.get("file_path"):
            self.page.open(ft.SnackBar(ft.Text("Carga un archivo antes de exportar.")))
            self.page.update()
            return

        visible_columns = self.logs_state.get("visible_columns", [])
        if not visible_columns:
            self.page.open(ft.SnackBar(ft.Text("No hay columnas visibles para exportar.")))
            self.page.update()
            return

        rows_to_export, _, _, _ = apply_filters_sort_paginate(
            self.logs_rows,
            self.logs_state["columns"],
            self.logs_state["search_text"],
            self.logs_state["level_filter"],
            self.logs_state["sort_by"],
            self.logs_state["sort_desc"],
            1,
            max(len(self.logs_rows), 1),
        )

        source = Path(str(self.logs_state["file_path"]))
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        export_file = source.with_name(f"{source.stem}-filtered-{timestamp}.csv")
        output_path = export_rows_to_csv(str(export_file), visible_columns, rows_to_export)
        self.page.open(ft.SnackBar(ft.Text(f"CSV exportado: {output_path}")))
        self.page.update()

    def on_logs_open_message_detail(self, message_text: str, column_name: str = "Message"):
        self.logs_state["message_dialog_open"] = True
        self.logs_state["message_dialog_text"] = message_text or ""
        self.logs_state["message_dialog_title"] = f"{column_name} completo"
        self.logs_message_dialog_title.value = self.logs_state["message_dialog_title"]
        self.logs_message_dialog_body.value = self.logs_state["message_dialog_text"]
        self.page.open(self.logs_message_dialog)
        self.page.update()

    def on_logs_close_message_detail(self, e=None):
        if not bool(self.logs_state.get("message_dialog_open", False)):
            return
        self.logs_state["message_dialog_open"] = False
        self.page.close(self.logs_message_dialog)
        self.page.update()

    def on_logs_copy_message_detail(self, e=None):
        message_text = str(self.logs_state.get("message_dialog_text", ""))
        if not message_text:
            self.page.open(ft.SnackBar(ft.Text("No hay texto para copiar.")))
            self.page.update()
            return

        self.page.set_clipboard(message_text)
        self.page.open(ft.SnackBar(ft.Text("Mensaje copiado al portapapeles.")))
        self.page.update()

    def login(self, e):
        def close_dlg(e):
            if user_name.value == "" or password.value == "":
                user_name.error_text = "Please provide username"
                password.error_text = "Please provide password"
                self.page.update()
                return
            else:
                user = User(user_name.value, password.value)
                if user not in self.store.get_users():
                    self.store.add_user(user)
                self.user = user_name.value
                self.page.client_storage.set("current_user", user_name.value)

            self.page.close(dialog)
            self.appbar_items[0] = ft.PopupMenuItem(
                text=f"{self.page.client_storage.get('current_user')}'s Profile"
            )
            self.page.update()

        user_name = ft.TextField(label="User name")
        password = ft.TextField(label="Password", password=True)
        dialog = ft.AlertDialog(
            title=ft.Text("Please enter your login credentials"),
            content=ft.Column(
                [
                    user_name,
                    password,
                    ft.ElevatedButton(text="Login", on_click=close_dlg),
                ],
                tight=True,
            ),
            on_dismiss=lambda e: print("Modal dialog dismissed!"),
        )
        self.page.open(dialog)

    def route_change(self, e):
        troute = ft.TemplateRoute(self.page.route)
        if troute.match("/"):
            self.page.go("/boards")
        elif troute.match("/board/:id"):
            if int(troute.id) >= len(self.store.get_boards()): # type: ignore
                self.page.go("/")
                return
            self.set_board_view(int(troute.id)) # type: ignore
        elif troute.match("/boards"):
            self.set_all_boards_view()
        elif troute.match("/members"):
            self.set_members_view()
        elif troute.match("/logs"):
            self.set_logs_view()
            self.refresh_logs_view()
        self.page.update()

    def add_board(self, e):
        def close_dlg(e):
            if (hasattr(e.control, "text") and not e.control.text == "Cancel") or (
                type(e.control) is ft.TextField and e.control.value != ""
            ):
                self.create_new_board(dialog_text.value)
            self.page.close(dialog)
            self.page.update()

        def textfield_change(e):
            if dialog_text.value == "":
                create_button.disabled = True
            else:
                create_button.disabled = False
            self.page.update()

        dialog_text = ft.TextField(
            label="New Board Name", on_submit=close_dlg, on_change=textfield_change
        )
        create_button = ft.ElevatedButton(
            text="Create", bgcolor=ft.Colors.BLUE_200, on_click=close_dlg, disabled=True
        )
        dialog = ft.AlertDialog(
            title=ft.Text("Name your new board"),
            content=ft.Column(
                [
                    dialog_text,
                    ft.Row(
                        [
                            ft.ElevatedButton(text="Cancel", on_click=close_dlg),
                            create_button,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                tight=True,
            ),
            on_dismiss=lambda e: print("Modal dialog dismissed!"),
        )
        self.page.open(dialog)
        dialog.open = True
        self.page.update()
        dialog_text.focus()

    def create_new_board(self, board_name):
        new_board = Board(self, self.store, board_name, self.page)
        self.store.add_board(new_board)
        self.hydrate_all_boards_view()

    def delete_board(self, e):
        self.store.remove_board(e.control.data)
        self.set_all_boards_view()


def main(page: ft.Page):

    page.title = "Flet Trello clone"
    page.padding = 0
    page.theme = ft.Theme(font_family="Verdana")
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme.page_transitions.windows = "cupertino" # type: ignore
    page.fonts = {"Pacifico": "Pacifico-Regular.ttf"}
    page.bgcolor = ft.Colors.BLUE_GREY_200
    app = TrelloApp(page, InMemoryStore())
    page.add(app)
    page.update()
    app.initialize()


print("flet version: ", ft.version.version) # type: ignore
print("flet path: ", ft.__file__)
ft.app(target=main, assets_dir="../assets")
