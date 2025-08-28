import flet as ft

def render_loading():
    return ft.Container(
        expand=True,  # ocupa toda la pantalla
        alignment=ft.alignment.center,
        content=ft.Column(
            [
                ft.ProgressRing(stroke_width=4, width=50, height=50),
                ft.Text("Cargando datos...", size=16, weight=ft.FontWeight.NORMAL),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20,   # separa un poco el texto del ProgressRing
        ),
    )