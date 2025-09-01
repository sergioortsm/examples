from typing import List, Optional, Union
import flet as ft
from common.app_state import app_state
from common.interfaces import IGroup, IList, ISiteCollection, IUser, RoleDefinition
from common.utils import Utils
from controls.render_loading import render_loading
from controls.panels_renderer import panels_renderer
from controls.side_bar import side_bar
from services.shp_service import shp_service
from common.shp_helper import shp_helper
from controls.Text import TitleText
from controls.user_card import render_card


class SharePointApp(ft.Column):
    def __init__(self, page: ft.Page, store: app_state):
        super().__init__(expand=True, spacing=20)
        self.page = page
        self.store = store
        self.page.vertical_alignment = ft.MainAxisAlignment.START
        self.page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        self.page.title = "App SharePoint Flet"
        page.theme = ft.Theme(font_family="Verdana")
        page.theme_mode = ft.ThemeMode.LIGHT
        page.theme.page_transitions.windows = "cupertino" # type: ignore      
        self.page.padding = 20
        self.page.fonts = {
            "Pacifico": "Pacifico-Regular.ttf",
           # "Roboto": "https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap"
        }
        page.theme = ft.Theme(font_family="Roboto")
        
        # Inicializar sp_service & helper si aún no están
        if not self.store.helper:
            self.store._sp_service = shp_service()
            self.store._helper = shp_helper(self.store._sp_service.sp, self.store, cache=self.store._cache)

        # Controles persistentes
        self.sidebar = side_bar(self, self.store, self.page, on_nav_change=self.handle_sidebar_selection)
        # Pantalla inicial
        self.show_login()

    # -----------------------
    # Login
    # -----------------------
    def show_login(self):
        self.page.clean() # type: ignore
        #self.controls.clear()

        email = ft.TextField(label="Correo electrónico", width=350)
        info_text = ft.Text()
        login_button = ft.ElevatedButton(text="Entrar")
        email.value = "sorts@sortsactivedev.onmicrosoft.com"  # Valor por defecto para pruebas
        
        async def login_click(e):
            user = email.value.strip() # type: ignore
            if not user:
                info_text.value = "Por favor, introduce tu correo electrónico."
                self.page.update() # type: ignore
                return

            # Inicializar sp_service si no existe
            if self.store._sp_service is None:
                self.store._sp_service = shp_service()

            # Inicializar helper si no existe
            if self.store.helper is None:
                self.store.helper = shp_helper(self.store._sp_service.sp, self.store, self.store._cache)
                
            # Asegurarse de que sp esté definido
            elif self.store.helper.sp is None:
                self.store.helper.sp = self.store._sp_service.get_client()

            try:
                result = self.store.helper.sp._get_access_token()
            except Exception as ex:
                info_text.value = f"Error en login: {ex}"
                self.page.update() # type: ignore
                return

            if result:
                self.store.set_auth_token(result)
                await self.show_main_page() # type: ignore
            else:
                info_text.value = "No se pudo autenticar."
                self.page.update() # type: ignore

        login_button.on_click = login_click

        self.controls.append(
            ft.Column(
                [
                    ft.Text("Iniciar sesión en M365 / SharePoint", size=24),
                    email,
                    login_button,
                    info_text,
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=15,
            )
        )
        
        self.page.update() # type: ignore

     # -----------------------

    # -----------------------------
    # Menú lateral
    # -----------------------------
    def mostrar_opciones_menu(self):
   
        self.store._menu_control.controls.clear()
        
        opciones = [
            {"Title": "Site Users", "Id": "users"},
            {"Title": "Site Admins", "Id": "admins"},
            {"Title": "Site Groups", "Id": "groups"},
            {"Title": "Libraries/Lists", "Id": "libraries"}
        ]
        
        for opt in opciones:
            lista_menu =   ft.ListTile(
                    title=ft.Text(opt["Title"]),
                    on_click=lambda e, opt=opt: self.cargar_datos_opcion(opt["Id"]),
                    bgcolor=ft.Colors.GREY_100,
                    horizontal_spacing=10,
                    shape=ft.RoundedRectangleBorder(radius=5),
            )
            sidebar = self.sidebar
            self.store._menu_control.controls = [sidebar]
            
        self.page.update() # type: ignore

    # -----------------------
    # Pantalla principal
    # -----------------------
    def find_site_by_url(self, sites, url):
        """
        Busca recursivamente en una lista de ISiteCollection y sus SubSites
        el primer site que tenga Url == url.
        """
        for site in sites:
            if site.Url == url:
                return site
            if site.SubSites:  # si hay hijos, buscar ahí
                found = self.find_site_by_url(site.SubSites, url)
                if found:
                    return found
        return None
    
    # -----------------------------
    # Cargar datos en lista principal
    # -----------------------------
    def cargar_datos_opcion(self, opcion_id):
        # Aquí se carga la información según la opción seleccionada
       
        self.store._lista_control.controls.clear()

        if opcion_id == "Site Users":
            for users in self.store.get_site_collections() or []: 
                for u in users.Users or []: 
                    self.store._lista_control.controls.append(render_card(u, self.page, self.store.get_roles_definiciones()))        
        elif opcion_id == "Site Administrators":
            for users in self.store.get_site_collections() or []: 
                for u in users.Admins or []: 
                    self.store._lista_control.controls.append(render_card(u, self.page,self.store.get_roles_definiciones()))
        elif opcion_id == "Site Groups":
            for users in self.store.get_site_collections() or []: 
                for u in users.Groups or []: 
                    self.store._lista_control.controls.append(render_card(u, self.page,self.store.get_roles_definiciones()))
        elif opcion_id == "Lists/Libraries":
            panel_list = panels_renderer(self.store, self.page) # type: ignore
            self.store._lista_control.controls.append(panel_list.render_lists_panels())
        else:
            self.store._lista_control.controls.append(ft.Text("Opción no reconocida."))

        self.page.update() # type: ignore

    def handle_sidebar_selection(self, opcion_Id):
        self.cargar_datos_opcion(opcion_Id)

    async def show_main_page(self):
        self.page.clean()    # type: ignore
        
        # Site inicial
        site_info = ISiteCollection(
                        Title="Prueba",
                        Url="https://sortsactivedev.sharepoint.com/sites/prueba")
        
        self.store.set_site_selected(site_info)

        # Dropdowns
        dd_sites = ft.Dropdown(label="Selecciona un site", width=450, options=[])
        dd_subsites = ft.Dropdown(label="Selecciona un subsite", width=400, disabled=True, options=[])

        # Loader superpuesto al dropdown de subsites
        subsites_loader_overlay = ft.Container(
            content=ft.ProgressRing(width=24, height=24),
            alignment=ft.alignment.center,
            visible=False,
        )
        subsites_stack = ft.Stack([dd_subsites, subsites_loader_overlay], width=400, height=56)

        # Área derecha: empieza con loader
        self.store._lista_control = ft.Column(spacing=5, expand=3, scroll=ft.ScrollMode.AUTO)
        self.store._lista_control.controls.clear()
        self.store._lista_control.controls.append(render_loading())

        # Botones de acción
        btnLinkSite = ft.IconButton(icon=ft.Icons.OPEN_IN_NEW, tooltip="Abrir en SharePoint")
        btnLinkSubSite = ft.IconButton(icon=ft.Icons.OPEN_IN_NEW, tooltip="Abrir subsite en SharePoint")
        btn_upsite = ft.IconButton(icon=ft.Icons.ARROW_UPWARD, tooltip="Subir nivel")

        # --- Eventos async ---

        async def on_site_change(e):
            selected_key = dd_sites.value
            self.store.set_site_selected(
                next((ISiteCollection(Title=s.Title, Url=s.Url) for s in sites if s.Url == selected_key), # type: ignore
                    ISiteCollection(Title="", Url=""))
            )
            self.store.set_subsite_selected(ISiteCollection(Title="", Url=""))

            # Mostrar loader
            dd_subsites.disabled = True
            subsites_loader_overlay.visible = True
            self.store._lista_control.controls.clear()
            self.store._lista_control.controls.append(render_loading())
            self.page.update() # type: ignore

            # Cargar colecciones
            self.store.set_site_collections(await self.store.helper.cargar_datos_sites())

            # Subsites
            subsite_filtrados = [
                obj for obj in (self.store.get_site_collections() or [])
                if getattr(obj, "SubSites", None) and obj.Title == self.store._site_selected.Title # type: ignore
            ]
            subsites_flat = []
            for site_obj in subsite_filtrados:
                subsites_flat.extend(site_obj.SubSites or [])

            dd_subsites.options = [ft.dropdown.Option(key=sub.Url, text=sub.Title) for sub in subsites_flat]
            dd_subsites.value = None

            # Quitar loader
            subsites_loader_overlay.visible = False
            dd_subsites.disabled = False

            # Pintar panel derecho
            self.store._lista_control.controls.clear()
            panel_list = panels_renderer(self.store, self.page)  # type: ignore
            self.store._lista_control.controls.append(panel_list.render_lists_panels())
            self.page.update() # type: ignore

        async def on_subsite_change(e):
            selected_key_sub = dd_subsites.value

            # Mostrar loader
            dd_subsites.disabled = True
            self.store._lista_control.controls.clear()
            self.store._lista_control.controls.append(render_loading())
            self.page.update() # type: ignore

            site = self.find_site_by_url(self.store.get_site_collections() or [], selected_key_sub)
            self.store.set_subsite_selected(site if site else ISiteCollection(Title="", Url=""))

            if self.store.subsite_selected and self.store.subsite_selected.Url:
                subsite = await self.store.helper.cargar_datos_sites()
                updated_collections = self.store.helper._replace_site_in_tree(
                    self.store.get_site_collections(), subsite[0]
                )
                self.store.set_site_collections(updated_collections)

            # Quitar loader
            dd_subsites.disabled = False

            # Pintar panel derecho
            self.store._lista_control.controls.clear()
            panel_list = panels_renderer(self.store, self.page)  # type: ignore
            self.store._lista_control.controls.append(panel_list.render_lists_panels())
            
            self.sidebar.select_item(1)
            
            self.page.update() # type: ignore

        async def load_data_site(e):
            # Mostrar loader en subsites
            dd_subsites.disabled = True
            subsites_loader_overlay.visible = True
            self.page.update() # type: ignore

            # Cargar colecciones
            self.store.set_site_collections(await self.store.helper.cargar_datos_sites())
            nonlocal_sites = await self.store.helper.obtener_datos_site(site_info, es_subsite=False)

            # Sites en dropdown
            dd_sites.options = [ft.dropdown.Option(key=s.Url, text=s.Title) for s in nonlocal_sites]
            dd_sites.value = self.store.site_selected.Url if self.store.site_selected else None

            # Subsites
            subsite_filtrados = [
                obj for obj in (self.store.get_site_collections() or [])
                if getattr(obj, "SubSites", None) and obj.Title == self.store._site_selected.Title # type: ignore
            ]
            subsites_flat = []
            for site_obj in subsite_filtrados:
                subsites_flat.extend(site_obj.SubSites or [])

            dd_subsites.options = [ft.dropdown.Option(key=sub.Url, text=sub.Title) for sub in subsites_flat]
            dd_subsites.value = None

            # Quitar loader
            subsites_loader_overlay.visible = False
            dd_subsites.disabled = False

            # Pintar panel derecho
            self.store._lista_control.controls.clear()
            panel_list = panels_renderer(self.store, self.page)  # type: ignore
            self.store._lista_control.controls.append(panel_list.render_lists_panels())
            self.page.update() # type: ignore

        # --- Asignar eventos ---
        dd_sites.on_change = on_site_change
        dd_subsites.on_change = on_subsite_change

        # --- Layout de filtros ---
        filtros_row = ft.Container(
            content=ft.ResponsiveRow(
                controls=[
                    ft.Column(col={"xs": 12, "sm": 6, "md": 3}, controls=[dd_sites]),
                    ft.Column(col={"xs": 12, "sm": 6, "md": 1}, controls=[btnLinkSite]),
                    ft.Column(col={"xs": 12, "sm": 6, "md": 3}, controls=[subsites_stack]),
                    ft.Column(
                        col={"xs": 12, "sm": 6, "md": 2},
                        controls=[ft.Row([btnLinkSubSite, btn_upsite], spacing=5)]
                    ),
                ],
                spacing=0,
            ),
            bgcolor=ft.Colors.GREY_100,
            border_radius=8,
            padding=10,
            margin=ft.margin.only(left=5, right=5, top=5, bottom=10),
        )

        # --- Layout principal ---
        contenido_row = ft.Row(
            [
                ft.Container(content=self.store._menu_control, expand=1, padding=10),
                ft.VerticalDivider(thickness=1, width=20),
                ft.Container(content=self.store._lista_control, expand=6, padding=10),
            ],
            spacing=0,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        self.mostrar_opciones_menu()
        self.page.add(ft.Column([filtros_row, contenido_row], expand=True)) # type: ignore
        self.page.update()  # type: ignore # 👈 usuario ve loader inmediatamente

        # 🔹 lanzar carga inicial en background
        self.page.run_task(load_data_site, None) # type: ignore


def on_actualizar_multi_edit(
    state,
    data: List[RoleDefinition],
    lista: Optional[IList],
    entities: List[Union[IUser, IGroup]]
):
    if not entities:
        return

    nuevos_sites: List[ISiteCollection] = []

    for site in state.site_collections:
        # Copia profunda de listas
        nuevas_listas = []
        for l in site.Lists:
            if lista and l.Id == lista.Id:
                nuevos_grupos = []
                for grp in l.Groups:
                    if any(isinstance(e, IGroup) and e.Id == grp.Id for e in entities):
                        entidad = next(e for e in entities if isinstance(e, IGroup) and e.Id == grp.Id)
                        grp = IGroup(
                            Id=grp.Id,
                            Users=entidad.Users,
                            Roles=[RoleDefinition(r.Id, r.Name, r.Description, r.odata_id) for r in data]
                        )
                    nuevos_grupos.append(grp)

                nuevos_users = []
                for usr in l.Users:
                    if any(isinstance(e, IUser) and e.Id == usr.Id for e in entities):
                        entidad = next(e for e in entities if isinstance(e, IUser) and e.Id == usr.Id)
                        usr = IUser(
                            Id=usr.Id,
                            Email=entidad.Email,
                            Roles=[RoleDefinition(r.Id, r.Name, r.Description, r.odata_id) for r in data]
                        )
                    nuevos_users.append(usr)

                nuevas_listas.append(IList(l.Id, Groups=nuevos_grupos, Users=nuevos_users))
            else:
                nuevas_listas.append(l)

        # Copia profunda de grupos y usuarios a nivel de site
        nuevos_grupos_site = []
        for grp in site.Groups:
            if not lista and any(isinstance(e, IGroup) and e.Id == grp.Id for e in entities):
                entidad = next(e for e in entities if isinstance(e, IGroup) and e.Id == grp.Id)
                grp = IGroup(
                    Id=grp.Id,
                    Users=entidad.Users,
                    Roles=[RoleDefinition(r.Id, r.Name, r.Description, r.odata_id) for r in data]
                )
            nuevos_grupos_site.append(grp)

        nuevos_users_site = []
        for usr in site.Users:
            if not lista and any(isinstance(e, IUser) and e.Id == usr.Id for e in entities):
                entidad = next(e for e in entities if isinstance(e, IUser) and e.Id == usr.Id)
                usr = IUser(
                    Id=usr.Id,
                    Email=entidad.Email,
                    Roles=[RoleDefinition(r.Id, r.Name, r.Description, r.odata_id) for r in data]
                )
            nuevos_users_site.append(usr)

        nuevos_sites.append(
            ISiteCollection(site.Id, Lists=nuevas_listas, Groups=nuevos_grupos_site, Users=nuevos_users_site)
        )

    # Guardar en el "state"
    state.site_collections = nuevos_sites

def resync_selected_items(state):
    
    nuevos_selected = []
    
    for item in state.selected_items:
        if isinstance(item, IGroup):
            nuevo = next(
                (grp for site in state.site_collections for grp in site.Groups if grp.Id == item.Id),
                None
            )
            nuevos_selected.append(nuevo or item)
        elif isinstance(item, IUser):
            nuevo = next(
                (usr for site in state.site_collections for usr in site.Users if usr.Id == item.Id),
                None
            )
            nuevos_selected.append(nuevo or item)
        else:
            nuevos_selected.append(item)

    # Filtra None
    state.selected_items = [x for x in nuevos_selected if x is not None]
            
