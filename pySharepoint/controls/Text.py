import flet as ft

class TitleText(ft.Text):
    def __init__(self, value: str):
        super().__init__(
            value,
            size=18,
            weight=ft.FontWeight.BOLD,
            color="#0D47A1",
            selectable=True
        )

def safe_get(d: dict, *keys, default="N/D"):
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return 

# def main(page: ft.Page):
#     page.add(
#         TitleText("Título con clase personalizada"),
#         TitleText("Otro más")
#     )

# ft.app(target=main)


