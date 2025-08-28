# confirm_dialog.py
import flet as ft

class confirm_dialog(ft.AlertDialog):
        def __init__(self, message, on_confirm, on_cancel, title="Confirmation"):
            self.on_confirm = on_confirm
            self.on_cancel = on_cancel
            super().__init__(
                title=ft.Text(title),
                content=ft.Text(message),
                actions=[
                    ft.TextButton("Yes", on_click=self._yes_clicked),
                    ft.TextButton("No", on_click=self._no_clicked),
                ],
                modal=True
            )

        def _yes_clicked(self, e):
            if self.on_confirm:
                self.on_confirm(e)
            self.open = False
            e.page.update()

        def _no_clicked(self, e):
            if self.on_cancel: # type: ignore
                self.on_cancel(e) # type: ignore
            self.open = False
            e.page.update()
