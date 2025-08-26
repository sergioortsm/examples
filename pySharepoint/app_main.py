import flet as ft
from common.app_state import app_state
from sharepoint_app import SharePointApp


def main(page: ft.Page):
    store = app_state()
    app = SharePointApp(page, store)
    page.add(app)


ft.app(target=main, port=8550, host="127.0.0.1", view=ft.AppView.WEB_BROWSER)


