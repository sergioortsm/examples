from typing import List, Dict, Any, Optional
import flet as ft
from common.interfaces import ISiteCollection
from controls.render_panels import render_lists_panels
from services.SHPService import SHPService
from common.SharePointHelper import SharePointHelper
from controls.Text import TitleText
from controls.user_card import render_card
from diskcache import Cache

 
CACHE_DIR = "./site_cache"
 
# -----------------------------
# Estado centralizado de la app
# -----------------------------
class AppState:
    def __init__(self):
        self.sp_service = SHPService()
        self.cache = Cache(CACHE_DIR)
        self.cache.clear()
        self.helper: SharePointHelper = SharePointHelper(self.sp_service.sp, cache=self.cache)
        self.site_selected: Optional[ISiteCollection] = None
        self.subsite_selected: Optional[ISiteCollection] = None
        self.sites_options = []
        self.subsites_options = []
        self.site_collections: List[ISiteCollection] = [] 
        self.auth_token = {"token": ""}
        
        # Declarar los controles UI para que Pylance los conozca
        self.lista_control: ft.Column = ft.Column(spacing=5, expand=3, scroll=ft.ScrollMode.AUTO)
        self.menu_control: ft.Column = ft.Column()
        self.roles_definiciones: List[Dict[str, Any]] = []
        
        
# -----------------------------
# Funciones de SharePoint
# -----------------------------
async def cargar_datos_sites(state: AppState) -> List[ISiteCollection]:
    site: ISiteCollection = state.site_selected or ISiteCollection(Title="", Url="")
    subsite: ISiteCollection = state.subsite_selected or ISiteCollection(Title="", Url="")
    datos_sites:List[ISiteCollection] = []
        
    if site is None or site.Url == "":
        return []
        
    if site.Url and not subsite.Url:
        datos_sites_temp = await state.helper.obtener_datos_site(site, es_subsite=False)
        datos_sites = await state.helper.obtener_datos_subsites(datos_sites_temp)
        datos_sites = await state.helper.rellenar_objetos_sites(datos_sites)        
        state.roles_definiciones = await state.helper.map2dropdown_option_tooltips(site) or []
    elif subsite.Url:
        datos_sites = await state.helper.rellenar_objetos_sites([subsite]) 
        state.roles_definiciones = await state.helper.map2dropdown_option_tooltips(subsite) or []
    
        
    return datos_sites

# -----------------------------
# Menú lateral
# -----------------------------
def mostrar_opciones_menu(state: AppState, menu_control, page):
    
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
                on_click=lambda e, opt=opt: cargar_datos_opcion(opt["Id"], state, page)
            )
    )
        
    page.update()

# -----------------------------
# Cargar datos en lista principal
# -----------------------------
def cargar_datos_opcion(opcion_id, state: AppState, page):
    # Aquí se carga la información según la opción seleccionada
    lista_control = state.lista_control
    lista_control.controls.clear()

    if opcion_id == "users":
        for users in state.site_collections or []: 
            for u in users.Users or []: 
                lista_control.controls.append(render_card(u, page))
        
    elif opcion_id == "admins":
        for users in state.site_collections or []: 
            for u in users.Admins or []: 
                lista_control.controls.append(render_card(u, page))
    elif opcion_id == "groups":
        for users in state.site_collections or []: 
            for u in users.Groups or []: 
                lista_control.controls.append(render_card(u, page))
    elif opcion_id == "libraries":
        panel_list = render_lists_panels(state, page)
        lista_control.controls.append(panel_list)
    else:
        lista_control.controls.append(ft.Text("Opción no reconocida."))

    page.update()

# -----------------------------
# Función principal
# -----------------------------
async def main(page: ft.Page):
    page.title = "App SharePoint Flet"
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.padding = 20

    # Estado
    state = AppState()
    state.helper = SharePointHelper(state.sp_service.sp, state.cache)

    # Controles principales
    state.menu_control = ft.Column()
    state.lista_control = ft.Column(spacing=5, expand=3, scroll=ft.ScrollMode.AUTO)

    
    # -----------------------------
    # Login simplificado
    # -----------------------------
    def show_login():
        page.clean()

        email = ft.TextField(label="Correo electrónico (User Principal Name)", width=350)
        info_text = ft.Text()
        login_button = ft.ElevatedButton(text="Entrar")
        email.value = "sorts@sortsactivedev.onmicrosoft.com"  # Valor por defecto para pruebas

        async def login_click(e):
            user = email.value.strip() if email.value else ""

            if not user:
                info_text.value = "Por favor, introduce tu correo electrónico."
                page.update()
                return

            # Inicializar sp_service si no existe
            if state.sp_service is None:
                state.sp_service = SHPService()

            # Inicializar helper si no existe
            if state.helper is None:
                state.helper = SharePointHelper(state.sp_service.sp, state.cache)
            # Asegurarse de que sp esté definido
            elif state.helper.sp is None:
                state.helper.sp = state.sp_service.get_client()

            try:
                result = state.helper.sp._get_access_token()
            except Exception as ex:
                info_text.value = f"Error en autenticación: {ex}"
                page.update()
                return

            if result is not None:
                state.auth_token["token"] = result
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

    # -----------------------------
    # Pantalla principal
    # -----------------------------
    async def show_main_page():
        page.clean()

        # Cargar site inicial
        site_info = ISiteCollection(
                        Title="Prueba",
                        Url="https://sortsactivedev.sharepoint.com/sites/prueba")
        
        sites = await state.helper.obtener_datos_site(site_info, es_subsite=False)

        state.site_collections = await cargar_datos_sites(state)
        
        # Dropdowns
        dd_sites = ft.Dropdown(
            label="Selecciona un site",
            width=450,
            options=[
                ft.dropdown.Option(key=s.Url, text=s.Title) for s in sites # type: ignore
            ]
        )

        dd_subsites = ft.Dropdown(
            label="Selecciona un subsite",
            width=400,
            options=[]
        )

        # Evento cambio de site
        async def on_site_change(e):
            selected_key = dd_sites.value
            state.site_selected = next(
                (ISiteCollection(Title=s.Title, Url=s.Url) for s in sites if s.Url == selected_key),
                ISiteCollection(Title="", Url="") 
            )

            state.subsite_selected = ISiteCollection(Title="", Url="") 

            # Cargar subsites
            state.site_collections = await cargar_datos_sites(state)
            
            subsite_filtrados = [
                obj for obj in (state.site_collections or []) 
                if obj.SubSites and obj.Title == state.site_selected.Title # type: ignore
            ]
            subsites_flat = []
            for site in subsite_filtrados:
                subsites_flat.extend(site.SubSites or [])

            state.subsites_options = [
                ft.dropdown.Option(key=sub.Url, text=sub.Title)
                for sub in subsites_flat
            ]
            dd_subsites.options = state.subsites_options
            dd_subsites.value = None
            page.update()

        dd_sites.on_change = on_site_change

        # Evento cambio de subsite
        async def on_subsite_change(e):
            selected_key = dd_subsites.value
            state.subsite_selected = next(
                (
                    ISiteCollection(Title=sub.Title, Url=sub.Url)
                    for site in state.site_collections
                    for sub in site.SubSites
                    if sub.Url == selected_key
                ),
                ISiteCollection(Title="", Url="")
            )
                        
            if state.subsite_selected:
                state.site_collections = await cargar_datos_sites(state)
        
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
                
        state.lista_control = ft.Column(spacing=5, expand=3, scroll=ft.ScrollMode.AUTO)
        state.lista_control.controls.clear()
        
        page.update()

        contenido_row = ft.Row(
            [
                ft.Container(
                    content=state.menu_control,
                    expand=1,
                    padding=10
                ),
                ft.VerticalDivider(thickness=1, width=20),
                ft.Container(
                    content=state.lista_control,
                    expand=3,
                    padding=10
                )
            ],
            spacing=0,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START
        )
        
        # Layout principal
        page.add(
            ft.Column([
                filtros_row,
                contenido_row
            ], expand=True, spacing=20)
        )
        
        mostrar_opciones_menu(state, state.menu_control, page)

    
    
    # -----------------------------
    # Empezar en login
    # -----------------------------
    show_login()

# -----------------------------
# Ejecutar app
# -----------------------------
ft.app(target=main, port=8550, host="127.0.0.1", view=ft.AppView.WEB_BROWSER)
