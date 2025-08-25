import flet as ft

def render_loading():
    return ft.Container(
        content=ft.Column(
            [
                ft.ProgressRing(),
                ft.Text("Cargando datos...", size=16, weight=ft.FontWeight.BOLD)
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        expand=True,
        alignment=ft.alignment.center
)    
