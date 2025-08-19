import shelve
from types import SimpleNamespace
import webbrowser
import flet as ft
from msal import PublicClientApplication
import requests
from common.SharePointHelper import SharePointHelper
from controls.Text import TitleText
from controls.autocomplete import autocomplete

from controls.user_card import render_card
from services.SHPService import SHPService
from sharepoint_client import SharePointOnlineClient
from flet.core.types import AppView, WebRenderer

# CLIENT_ID = "0ee25780-948d-4e07-bccf-5457e16d705f"
# TENANT_ID = "a272015e-e187-4c3c-95a6-93cfdba816b8"
# AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
# SCOPES = ["https://sortsactivedev.sharepoint.com/.default"]
# SHAREPOINT_SITE = "https://sortsactivedev.sharepoint.com/sites/prueba/_api/web/lists?$filter=Hidden eq false"
# SHAREPOINT_ROOT = "https://sortsactivedev.sharepoint.com/sites/prueba"
# CLIENT_SECRET = "xSw8Q~.3X0U8mu7qKBU9QV2zZwdopqeC9nq_CaCI"  # No se usa en este ejemplo, pero necesario para SharePointOnlineClient

    # Estado centralizado (como los hooks en React)
state = SimpleNamespace(
    sp_service=None,
    helper=None,
    site_selected=None,
    sites_options=None,
    subsite_selected=None,
    subsites_options=[],
    site_collections=[],
    site_roles_options=[]
)
    
    
def main(page: ft.Page):
    page.title = "App SharePoint Flet"
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.padding = 20

    # Variables para guardar token y datos globales
    auth_token = {"token": ""}
    sp_service = SHPService()
    site_selected = {"key": "", "text": ""}
    subsite_selected = {"key": "", "text": ""}
    cache = shelve.open("sharepoint_cache.db")
    helper = SharePointHelper(sp_service.sp, cache)
    datos_sites = []
    roles = []
    
    state.sp_service = sp_service
    state.helper = helper
    state.site_selected = site_selected
    state.subsite_selected = subsite_selected
    state.sites_options = []
    state.subsites_options = []
        
    async def on_load_data(e):
             
        site = state.site_selected
        subsite = state.subsite_selected
        datos_sites = []
        
        try:
            if site.get("key") == "":
                return
            
            if site["key"] and not subsite:
                datos_sites_temp = await state.helper.obtener_datos_site(site, es_subsite=False)
                datos_sites = await state.helper.obtener_datos_subsites(datos_sites_temp)
                datos_sites = await state.helper.rellenar_objetos_sites(datos_sites)
                
            elif subsite["key"]:
                datos_sites = await state.helper.rellenar_objetos_sites(subsite)
                roles = await state.helper.obtener_definiciones_roles(subsite)
                
            
            state.site_collections = datos_sites
            
        except Exception as e:
                print(f"Error loading data: {site['Url']}: {e}")
    
    def show_login():
        page.clean()

        email = ft.TextField(label="Correo electrónico (User Principal Name)", width=350)
        info_text = ft.Text()
        login_button = ft.ElevatedButton(text="Entrar")
        email.value = "sorts@sortsactivedev.onmicrosoft.com"  # Valor por defecto para pruebas

        # Función para manejar el clic en el botón de login
        async def login_click(e):
            user = email.value.strip() if email.value else ""
       
            state.helper.sp = SHPService().get_client()
            
            if not user:
                info_text.value = "Por favor, introduce tu correo electrónico."
                page.update()
                return

           # app = PublicClientApplication(CLIENT_ID, authority=AUTHORITY)
            try:
                result = state.helper.sp._get_access_token()
                #result = app.acquire_token_interactive(scopes=SCOPES, login_hint=user)
            except Exception as ex:
                info_text.value = f"Error en autenticación: {ex}"
                page.update()
                return
            if result is not None:
            #if "access_token" in result:
                #auth_token["token"] = result["access_token"]
                auth_token["token"] = result
                info_text.value = "Login correcto."
                page.update()
                await show_main_page()
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
        page.update()
    
       
            
    async def show_main_page():
        page.clean()

        # Inicializar sp_service una sola vez
        if state.sp_service is None:
            state.sp_service = sp_service
           
        # Crear helper persistente
        if state.helper.sp is None:
            state.helper = SharePointHelper(state.sp_service.sp, cache)
                
        site_info = {"key": "https://sortsactivedev.sharepoint.com/sites/prueba", "text": "Prueba"}
        sites = await state.helper.obtener_datos_site(site_info, es_subsite=False)
        
        await on_load_data(None)  # Cargar datos iniciales

        # Fila 1: filtros simples (ejemplo: filtro de texto)
        filtro_text = ft.TextField(label="Filtro", width=300)
        boton_filtrar = ft.ElevatedButton(text="Aplicar filtro")
    
        page.update()
        
        sites_options = [
            ft.dropdown.Option(key=site["Url"], text=site["Title"])
            for site in sites
        ]
        
        state.sites_options = sites_options
        
        # Dropdown y botón
        dd_sites = ft.Dropdown(
            label="Selecciona un site",
            width=450,  # ancho para que sea visible
            options=state.sites_options
        )

        # Dropdown y botón
        dd_subsites = ft.Dropdown(
            label="Selecciona un subsite",
            width=400,
            options=[],
        )
        
        # --- Evento cambio de site --- 
        async def on_site_change(e):
            selected_key = dd_sites.value
            #site_selected = next((s for s in sites if s["Url"] == selected_key), None)
            site_selected = next(
                        ({"key": s["Url"], "text": s["Title"]} for s in sites if s["Url"] == selected_key),
                        None
                    )


            state.site_selected = site_selected
            state.subsite_selected = None

            # Obtener subsites reales desde helper
            await on_load_data(None) 
            
            #items = await helper.obtener_datos_subsites(sites)
            items = state.site_collections 
            subsite_filtrados = []
            
            if site_selected:
                subsite_filtrados = [
                    obj
                    for obj in items
                    if obj.get("SubSites") and obj.get("Title") == site_selected.get("text")
                ]

            subsites_flat = []
            
            for site in subsite_filtrados:
                subsites_flat.extend(site["SubSites"])

            state.subsites_options = [
                ft.dropdown.Option(key=sub["Url"], text=sub["Title"])
                for sub in subsites_flat
            ]

            # refrescar dropdown de subsites
            dd_subsites.options = state.subsites_options
            dd_subsites.value = None
            page.update()


        # --- Evento cambio de subsite ---
        def on_subsite_change(e):
            selected_key = dd_subsites.value
            subsite_selected = next(
                (s for s in state.subsites_options if s.key == selected_key), None
            )
            state.subsite_selected = subsite_selected
            print("Subsite seleccionado:", state.subsite_selected)
            
        dd_sites.on_change = on_site_change
        dd_subsites.on_change = on_subsite_change
        
        t = ft.Text()

        def button_clicked(e):
            t.value = f"Dropdown value is: {dd_sites.value}"
            t.update()

        b = ft.ElevatedButton(text="Submit", on_click=button_clicked)

        t2 = ft.Text()

        def button_sub_clicked(e):
            t2.value = f"Dropdown value is: {dd_subsites.value}"
            t2.update()

        b2 = ft.ElevatedButton(text="Submit", on_click=button_sub_clicked)
        
        #Cómo funciona este layout
        # ResponsiveRow divide la fila en una rejilla de 12 columnas.
        # col={"xs": 12} → ocupa todo el ancho en móviles.
        # col={"sm": 6} → ocupa media fila en tablet.
        # col={"md": 4} → ocupa 4 columnas de 12 en escritorio.
        # Si no cabe, el control automáticamente baja a la siguiente fila.
        # run_spacing añade espacio vertical entre las filas cuando hacen wrap.
        
        # ResponsiveRow para filtros        
        filtros_row = ft.ResponsiveRow(
            controls=[
                ft.Column(col={"xs": 12, "sm": 6, "md": 3}, controls=[dd_sites]),
                ft.Column(col={"xs": 12, "sm": 6, "md": 1}, controls=[b]),
                ft.Column(col={"xs": 12, "sm": 6, "md": 1}, controls=[t]),
                ft.Column(col={"xs": 12, "sm": 6, "md": 3}, controls=[dd_subsites]),
                ft.Column(col={"xs": 12, "sm": 6, "md": 1}, controls=[b2]),
                ft.Column(col={"xs": 12, "sm": 6, "md": 1}, controls=[t2]),
            ],
            spacing=10,
            run_spacing=10
        )        
            
        # Fila 2: dos columnas invertidas: detalles a la izquierda (25%), lista a la derecha (75%)
        menu_control = ft.Column([ft.Text("Detalles aquí")], 
                                 expand=1, scroll=ft.ScrollMode.AUTO, 
                                 width=None  # Para que el expand funcione bien
        )

        #lista_control = ft.ListView( spacing=5, padding=10, expand=3)
        
        lista_control = ft.Column(spacing=5, expand=3, scroll=ft.ScrollMode.AUTO)

        lista_control.controls.clear()
        # usuarios =  await helper.rellenar_objetos_sites(site_selected)
        # for u in usuarios:
        #     lista_control.controls.append(render_card(u, page))
        
        page.update()

        contenido_row = ft.Row(
            [
                ft.Container(
                    content=menu_control,
                    expand=1,
                    padding=10
                ),
                ft.VerticalDivider(thickness=1, width=20),
                ft.Container(
                    content=lista_control,
                    expand=3,
                    padding=10
                )
            ],
            spacing=0,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START
        )
    
        # ================================
        # Nueva función para mostrar opciones fijas
        # ================================
        def mostrarListaOpciones():
            menu_control.controls.clear()

            opciones = [
                {"Title": "Site Users", "Id": "users"},
                {"Title": "Site Admins", "Id": "admins"},
                {"Title": "Site Groups", "Id": "groups"},
                {"Title": "Libraries/Lists", "Id": "libraries"}
            ]

            for opt in opciones:
                menu_control.controls.append(
                    ft.ListTile(
                        title=ft.Text(opt["Title"]),
                        on_click=lambda e, opt=opt: cargar_datos_opcion(opt["Id"])
                    )
                )

            page.update()
        
        # ================================
        # Función que carga datos en lista_control según opción
        # ================================
        def cargar_datos_opcion(opcion_id):
            lista_control.controls.clear()

            if opcion_id == "users":
                lista_control.controls.append(ft.Text("Aquí iría la lista de usuarios..."))
            elif opcion_id == "admins":
                lista_control.controls.append(ft.Text("Aquí iría la lista de administradores..."))
            elif opcion_id == "groups":
                lista_control.controls.append(ft.Text("Aquí iría la lista de grupos..."))
            elif opcion_id == "libraries":
                lista_control.controls.append(ft.Text("Aquí iría la lista de bibliotecas/listas..."))
            else:
                lista_control.controls.append(ft.Text("Opción no reconocida."))

            page.update()

        boton_filtrar.on_click = lambda e: mostrarListaOpciones()
       
        
        def cargar_listas():
            headers = {
                "Authorization": f"Bearer {auth_token['token']}",
                "Accept": "application/json;odata=verbose"
            }
            response = requests.get(sp_service.SHAREPOINT_SITE, headers=headers)
            lista_control.controls.clear()
            if response.status_code == 200:
                data = response.json()
                
                for lst in data["d"]["results"]:
                    item = ft.ListTile(
                        title=ft.Text(lst.get("Title", "")),
                        subtitle=ft.Text(lst.get("Id", "")),
                        on_click=lambda e, lst=lst: mostrar_detalle(lst)
                    )
                    lista_control.controls.append(item)
            else:
                lista_control.controls.append(ft.Text(f"Error al cargar listas: {response.status_code}"))

        page.update()

        def mostrar_detalle(lista):
            menu_control.controls.clear()
            menu_control.controls.append(TitleText(f"Title: {lista.get('Title')}"))
            menu_control.controls.append(TitleText(f"ID: {lista.get('Id')}"))
            # Añade más detalles si quieres
            page.update()

        boton_filtrar.on_click = lambda e: cargar_listas()

        # Mostrar todo en la página
        page.add(
            ft.Column([
                filtros_row,
                contenido_row
            ], expand=True, spacing=20)
        )

        # Carga inicial de listas
        # cargar_listas()

        # # Mostrar todo en la página
        # page.add(
        #     ft.Column([
        #         filtros_row,
        #         contenido_row
        #     ], expand=True, spacing=20)
        # )

        # Carga inicial de opciones
        mostrarListaOpciones()
    
        page.update()

    # Empezamos en la pantalla de login
    show_login()

#ft.app(target=main) #Abre la aplicación Flet en ventana independiente

# Abrir servidor sin ventana embebida
ft.app(target=main, port=8550, host="127.0.0.1", view=AppView.WEB_BROWSER)  

