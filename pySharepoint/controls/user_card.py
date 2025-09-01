from typing import Union
import flet as ft
from common.interfaces import IGroup, IUser, RoleDefinition


def render_card(usuario: Union[IUser, IGroup], page, all_roles):

    siteadmin =  bool(getattr(usuario, "IsSiteAdmin", False))
    current_roles = getattr(usuario, "Roles", [])

    def chips_from(roles):
        return ft.Row([ft.Chip(label=ft.Text(r.Name)) for r in roles], wrap=True)

    return ft.Card(
        content=ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(usuario.Title, weight=ft.FontWeight.BOLD, size=16),
                            chips_from(current_roles),
                        ],
                        expand=True,
                    ),
                    # Solo agrega el botón si NO es siteadmin
                    *(
                        [] if siteadmin else [
                            ft.IconButton(
                                icon=ft.Icons.EDIT,
                                tooltip="Editar",
                                on_click=lambda e: editar_card(e, usuario, page, all_roles),
                            )
                        ]
                    )
                ]
            ),
            padding=10,
        )
    )


def editar_card(e, usuario:Union[IUser, IGroup], page, all_roles):
    """Convierte la Card en modo edición inline (solo roles)"""
    card = e.control.parent.parent.parent  # sube desde IconButton → Row → Container → Card

    # Title solo lectura
    title_field = ft.Text(usuario.Title, weight=ft.FontWeight.BOLD, size=16)

    # checkboxes con roles
    selected_ids = {r.Id for r in usuario.Roles or [] if r.Id is not None}

    cbs = [
        ft.Checkbox(label=r["text"], value=(int(r["key"]) in selected_ids))
        for r in all_roles
    ]

    def guardar(_):
        selected_simple: list[RoleDefinition] = []
        for cb, role in zip(cbs, all_roles):
            if isinstance(cb, ft.Checkbox) and cb.value:
                selected_simple.append(RoleDefinition(Id=role["key"], Name=role["text"]))
        usuario.Roles = selected_simple
        card.content = render_card(usuario, page, all_roles).content
        page.update()

    def cancelar(_):
        card.content = render_card(usuario, page, all_roles).content
        page.update()

    card.content = ft.Container(
        content=ft.Column(
            [
                title_field,   # solo lectura
                ft.Column(cbs, tight=True),
                ft.Row(
                    [
                        ft.ElevatedButton("Guardar", on_click=guardar),
                        ft.TextButton("Cancelar", on_click=cancelar),
                    ]
                ),
            ]
        ),
        padding=10,
    )
    page.update()

# import flet as ft

# def render_card(usuario, page):
#     """Devuelve una Card en modo solo lectura, con botón de edición"""
#     return ft.Card(
#         content=ft.Container(
#             content=ft.Row([
#                 ft.Column([
#                     ft.Text(usuario["Title"], weight=ft.FontWeight.BOLD, size=16),
#                     ft.Text(usuario["Email"], size=12, color="grey"),
#                 ], expand=True),
#                 ft.IconButton(
#                     icon=ft.Icons.EDIT,
#                     tooltip="Editar",
#                     on_click=lambda e: editar_card(e, usuario, page)
#                 )
#             ]),
#             padding=10
#         )
#     )


# def editar_card(e, usuario, page):
#     """Convierte la Card en modo edición inline"""
#     card = e.control.parent.parent.parent  # sube desde IconButton → Row → Container → Card

#     nombre_field = ft.TextField(value=usuario["Title"], label="Title", expand=True)
#     email_field = ft.TextField(value=usuario["Email"], label="Email", expand=True)

#     def guardar(_):
#         usuario["Title"] = nombre_field.value
#         usuario["Email"] = email_field.value
#         card.content = render_card(usuario, page).content
#         page.update()

#     def cancelar(_):
#         card.content = render_card(usuario, page).content
#         page.update()

#     card.content = ft.Container(
#         content=ft.Column([
#             nombre_field,
#             email_field,
#             ft.Row([
#                 ft.ElevatedButton("Guardar", on_click=guardar),
#                 ft.TextButton("Cancelar", on_click=cancelar),
#             ])
#         ]),
#         padding=10
#     )
#     page.update()
