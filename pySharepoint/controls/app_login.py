import flet as ft
from msal import PublicClientApplication
import requests

# Parámetros de tu app registrada en Azure AD
CLIENT_ID = "0ee25780-948d-4e07-bccf-5457e16d705f"
CLIENT_SECRET = "0xL/LkFCpcyIE5EMkl1oiudyedbk4wZdI90ghxFS1Zg="
TENANT_ID = "a272015e-e187-4c3c-95a6-93cfdba816b8"
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
#SCOPES = ["User.Read", "Sites.Read.All"]  # o el scope para SharePoint
SCOPES = ["https://sortsactivedev.sharepoint.com/.default"]  # o el scope para SharePoint 
# URL ejemplo para SharePoint Online (ajusta tu site)
SHAREPOINT_SITE = "https://sortsactivedev.sharepoint.com/sites/prueba/_api/web/lists"

def main(page: ft.Page):
    page.title = "Login y consulta SharePoint Online"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    email = ft.TextField(label="Correo electrónico (User Principal Name)", width=350)
    info_text = ft.Text()
    login_button = ft.ElevatedButton(text="Entrar")

    def login_click(e):
        user = email.value.strip() if email.value is not None else ""
        if not user:
            info_text.value = "sorts@sortsactivedev.onmicrosoft.com"
            page.update()
            return

        app = PublicClientApplication(CLIENT_ID, authority=AUTHORITY)
        # Flujo de login interactivo (abre navegador para login)
        try:
            result = app.acquire_token_interactive(scopes=SCOPES, login_hint=user)
        except Exception as ex:
            info_text.value = f"Error en autenticación: {ex}"
            page.update()
            return

        if "access_token" in result:
            info_text.value = "Login correcto, consultando listas de SharePoint..."
            page.update()

            headers = {"Authorization": f"Bearer {result['access_token']}", "Accept": "application/json;odata=verbose"}
            response = requests.get(SHAREPOINT_SITE, headers=headers)

            if response.status_code == 200:
                data = response.json()
                titles = [lst["Title"] for lst in data["d"]["results"]]
                info_text.value = "Listas encontradas:\n" + "\n".join(titles)
            else:
                info_text.value = f"Error al consultar SharePoint: {response.status_code}"
        else:
            info_text.value = "No se pudo obtener token."

        page.update()

    login_button.on_click = login_click

    page.add(
        ft.Column([
            ft.Text("Iniciar sesión en Microsoft 365 / SharePoint Online", size=24),
            email,
            login_button,
            info_text
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=15)
    )

ft.app(target=main)
