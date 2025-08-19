import flet as ft

def render_card(usuario, page):
    """Devuelve una Card en modo solo lectura, con botón de edición"""
    return ft.Card(
        content=ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text(usuario["nombre"], weight=ft.FontWeight.BOLD, size=16),
                    ft.Text(usuario["email"], size=12, color="grey"),
                ], expand=True),
                ft.IconButton(
                    icon=ft.Icons.EDIT,
                    tooltip="Editar",
                    on_click=lambda e: editar_card(e, usuario, page)
                )
            ]),
            padding=10
        )
    )


def editar_card(e, usuario, page):
    """Convierte la Card en modo edición inline"""
    card = e.control.parent.parent.parent  # sube desde IconButton → Row → Container → Card

    nombre_field = ft.TextField(value=usuario["nombre"], label="Nombre", expand=True)
    email_field = ft.TextField(value=usuario["email"], label="Email", expand=True)

    def guardar(_):
        usuario["nombre"] = nombre_field.value
        usuario["email"] = email_field.value
        card.content = render_card(usuario, page).content
        page.update()

    def cancelar(_):
        card.content = render_card(usuario, page).content
        page.update()

    card.content = ft.Container(
        content=ft.Column([
            nombre_field,
            email_field,
            ft.Row([
                ft.ElevatedButton("Guardar", on_click=guardar),
                ft.TextButton("Cancelar", on_click=cancelar),
            ])
        ]),
        padding=10
    )
    page.update()
