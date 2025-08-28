from typing import List, Optional, Union
import flet as ft
from common.app_state import app_state
from common.interfaces import IGroup, IList, ISiteCollection, IUser, RoleDefinition
from common.utils import Utils
from controls.render_loading import render_loading
from controls.panels_renderer import panels_renderer
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
        page.fonts = {"Pacifico": "Pacifico-Regular.ttf"}
        self.page.padding = 20
        self.page.fonts = {
            "Roboto": "https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap"
        }
        page.theme = ft.Theme(font_family="Roboto")
        
        # Inicializar sp_service & helper si aún no están
        if not self.store.helper:
            self.store._sp_service = shp_service()
            self.store._helper = shp_helper(self.store._sp_service.sp, self.store, cache=self.store._cache)

        # Controles persistentes
        # self.menu_control = ft.Column()
        # self.lista_control = ft.Column(spacing=5, expand=3, scroll=ft.ScrollMode.AUTO)

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
            self.store._menu_control.controls.append(
                ft.ListTile(
                    title=ft.Text(opt["Title"]),
                    on_click=lambda e, opt=opt: self.cargar_datos_opcion(opt["Id"]),
                    bgcolor=ft.Colors.GREY_100,
                    horizontal_spacing=10,
                    shape=ft.RoundedRectangleBorder(radius=5),
                )
        )
            
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
    
    async def show_main_page(self):
        self.page.clean()    # type: ignore
         
        # Cargar site inicial
        site_info = ISiteCollection(
                        Title="Prueba",
                        Url="https://sortsactivedev.sharepoint.com/sites/prueba")
        
        sites = await self.store.helper.obtener_datos_site(site_info, es_subsite=False)

        self.store.set_site_collections(await self.store.helper.cargar_datos_sites())
        
        # Dropdowns
        dd_sites = ft.Dropdown(
            label="Selecciona un site",
            width=450,
            options=[
                ft.dropdown.Option(key=s.Url, text=s.Title) for s in sites # type: ignore
            ]
        )

        # Definimos el loader pero oculto al inicio
        subsites_loader = ft.ProgressRing(visible=False, width=20, height=20)


        dd_subsites = ft.Dropdown(
            label="Selecciona un subsite",
            width=400,
            disabled=True,
            options=[]
        )

        # Loader que se superpone encima del dropdown
        subsites_loader_overlay = ft.Container(
            content=ft.ProgressRing(width=24, height=24),
            alignment=ft.alignment.center,
            visible=False,      # visible solo mientras se cargan subsites
        )

        # Stack: primero el dropdown, arriba el loader superpuesto
        subsites_stack = ft.Stack(
            controls=[dd_subsites, subsites_loader_overlay],
            width=400,
            height=56,  # alto aproximado del campo para centrar el loader
        )
        
        # Evento cambio de site
        async def on_site_change(e):
            selected_key = dd_sites.value
            self.store.set_site_selected(next(
                (ISiteCollection(Title=s.Title, Url=s.Url) for s in sites if s.Url == selected_key),
                ISiteCollection(Title="", Url="")
            ))
            self.store.set_subsite_selected(ISiteCollection(Title="", Url=""))

            # Mostrar loader sobre el dropdown y deshabilitarlo
            dd_subsites.disabled = True
            subsites_loader_overlay.visible = True
            self.page.update() # type: ignore

            # (Opcional) muestra loading también en el área derecha
            self.store._lista_control.controls.clear()
            self.store._lista_control.controls.append(
                ft.Row([ft.ProgressRing(), ft.Text("Cargando datos del site...")],
                    alignment=ft.MainAxisAlignment.CENTER)
            )
            self.page.update() # type: ignore

            # Cargar datos (tu función existente)
            self.store.set_site_collections(await self.store.helper.cargar_datos_sites())

            # Construir opciones de subsites
            subsite_filtrados = [
                obj for obj in (self.store.get_site_collections() or [])
                if getattr(obj, "SubSites", None) and obj.Title == self.store._site_selected.Title # type: ignore
            ]
            subsites_flat = []
            for site_obj in subsite_filtrados:
                subsites_flat.extend(site_obj.SubSites or [])

            dd_subsites.options = [
                ft.dropdown.Option(key=sub.Url, text=sub.Title)
                for sub in subsites_flat
            ]
            
            dd_subsites.value = None

            # Ocultar loader y habilitar dropdown
            subsites_loader_overlay.visible = False
            dd_subsites.disabled = False

            # (Opcional) limpiar el área derecha
            self.store._lista_control.controls.clear()
            panel_list = panels_renderer(self.store, self.page) # type: ignore
            self.store._lista_control.controls.append(panel_list.render_lists_panels())
            #self.store.lista_control.controls.append(ft.Text("Selecciona una opción del menú de la izquierda"))
            self.page.update() # type: ignore
            
        # 🟢 mostrar dropdown con datos y ocultar loader
        subsites_loader.visible = False
        dd_subsites.visible = True
        dd_subsites.disabled = False
        self.page.update() # type: ignore

        dd_sites.on_change = on_site_change

        # Evento cambio de subsite
        async def on_subsite_change(e):
            selected_key = dd_sites.value
            selected_key_sub = dd_subsites.value

            # Mostrar loader sobre el dropdown mientras procesa
            dd_subsites.disabled = True
            #subsites_loader_overlay.visible = True

            # (Opcional) loading en el área derecha
            self.store._lista_control.controls.clear()
            self.store._lista_control.controls.append(render_loading())
            self.page.update() # type: ignore

            site = self.find_site_by_url(self.store.get_site_collections() or [], selected_key_sub)
            # Establecer subsite seleccionado a partir de site_collections
            self.store.set_subsite_selected(
                site if site else ISiteCollection(Title="", Url="")
            )
            
            if self.store.subsite_selected and self.store.subsite_selected.Url:
                subsite = await self.store.helper.cargar_datos_sites()                
                # Obtienes el árbol actual
                site_collections = self.store.get_site_collections()
                # Reemplazas el subsite en el árbol
                updated_collections = self.store.helper._replace_site_in_tree(site_collections, subsite[0])
                # Guardas el nuevo árbol en store
                self.store.set_site_collections(updated_collections)

            # Ocultar loader y habilitar dropdown
           # subsites_loader_overlay.visible = False
            dd_subsites.disabled = False

            # (Ejemplo) pintar algo en el área derecha una vez cargado
            self.store._lista_control.controls.clear()
            panel_list = panels_renderer(self.store, self.page) # type: ignore
            #panel_list = render_lists_panels(self.store, self.page) # type: ignore
            self.store._lista_control.controls.append(panel_list.render_lists_panels())
            self.page.update() # type: ignore
        
        dd_subsites.on_change = on_subsite_change

        t = ft.Text()

        def button_clicked(e):
            t.value = f"Dropdown value is: {dd_sites.value}"
            t.update()

        #b = ft.ElevatedButton(text="Submit", on_click=button_clicked)

        if self.store.site_selected:
            list_url = f"{getattr(self.store.site_selected, "Url")}"
        else:
            list_url = f"{getattr(self.store.helper.sp, "site_url")}"
 
        btnLinkSite = ft.IconButton(
            icon=ft.Icons.OPEN_IN_NEW,
            tooltip="Open in Sharepoint",
            on_click=lambda e, url=list_url: Utils.open_list_url(url, e) # type: ignore
        )
        
        t2 = ft.Text()

        def button_sub_clicked(e):
            t2.value = f"Dropdown value is: {dd_subsites.value}"
            t2.update()

        if not self.store.subsite_selected:
            list_url = f"{getattr(self.store.helper.sp, "site_url")}"
        
        btnLinkSubSite = ft.IconButton(
            icon=ft.Icons.OPEN_IN_NEW,
            tooltip="Open in Sharepoint",
            on_click=lambda e, url=list_url: Utils.open_list_url(url, e) # type: ignore
        )
        
        #b2 = ft.ElevatedButton(text="Submit", on_click=button_sub_clicked)

                            
        async def on_upsite(e):
            
            def on_upsite_click(e):
                dd_subsites.value = None   # <-- quitar selección
                for opt in dd_subsites.options:  # type: ignore # <-- asegurarse que ninguna quedó marcada
                    opt.selected = False # type: ignore
                dd_subsites.update()
            
            # 1. Resetear subsite
            self.store.set_subsite_selected(ISiteCollection(Title="", Url=""))
            # dd_subsites.options = []
            on_upsite_click(e)

            # 2. Mostrar loading mientras se recarga
            self.store._lista_control.controls.clear()
            self.store._lista_control.controls.append(render_loading())
            self.page.update()  # type: ignore

            # 3. Recargar datos del site raíz
            if self.store.site_selected and self.store.site_selected.Url:
                site = await self.store.helper.cargar_datos_sites()
                # Reemplazo en el árbol
                updated_collections = self.store.helper._replace_site_in_tree(
                    self.store.get_site_collections(),
                    site[0]
                )
                self.store.set_site_collections(updated_collections)

            # 4. Repintar panel derecho
            self.store._lista_control.controls.clear()
            panel_list = panels_renderer(self.store, self.page)  # type: ignore
            self.store._lista_control.controls.append(panel_list.render_lists_panels())

            # 5. Ocultar botón si ya no hay subsite
            btn_upsite.visible = False
            self.page.update()  # type: ignore


        # Botón “subir nivel”
        btn_upsite = ft.IconButton(
            icon=ft.Icons.ARROW_UPWARD,
            icon_size=19,
            tooltip="Up level",
            #on_click=on_upsite,
            on_click=lambda e: self.page.run_task(on_upsite, e),  # 🔹 así se llama async # type: ignore
            style=ft.ButtonStyle(
                bgcolor={ft.ControlState.HOVERED: "transparent"}
            ),    
           # visible=bool(self.store.subsite_selected and self.store.subsite_selected.Url)
        )
                
        
         #Cómo funciona este layout
        # ResponsiveRow divide la fila en una rejilla de 12 columnas.
        # col={"xs": 12} → ocupa todo el ancho en móviles.
        # col={"sm": 6} → ocupa media fila en tablet.
        # col={"md": 4} → ocupa 4 columnas de 12 en escritorio.
        # Si no cabe, el control automáticamente baja a la siguiente fila.
        # run_spacing añade espacio vertical entre las filas cuando hacen wrap.

        # Contenedor con estilo para los filtros
        filtros_row =  ft.Container(
            content=ft.ResponsiveRow(
                controls=[
                    ft.Column(col={"xs": 12, "sm": 6, "md": 3}, controls=[dd_sites]),
                    ft.Column(col={"xs": 12, "sm": 6, "md": 1}, controls=[btnLinkSite]),
                    ft.Column(col={"xs": 12, "sm": 6, "md": 1}, controls=[t]),
                    ft.Column(col={"xs": 12, "sm": 6, "md": 3}, controls=[subsites_stack]),
                    ft.Column(col={"xs": 12, "sm": 6, "md": 1}, controls=[btnLinkSubSite]),
                    ft.Column(col={"xs": 12, "sm": 6, "md": 1}, controls=[btn_upsite]),
                ],
                spacing=10,
                run_spacing=10
            ),
            bgcolor=ft.Colors.GREY_100,
            border_radius=8,
            padding=10,
            margin=ft.margin.only(left=5, right=5, top=5, bottom=10),
        )
        self.store._lista_control = ft.Column(spacing=5, expand=3, scroll=ft.ScrollMode.AUTO)
        
        if self.store.is_loading():
            self.store._lista_control.controls.clear()
            self.store._lista_control.controls.append(render_loading())
        else:       
            self.store._lista_control.controls.clear()
        
        self.page.update() # type: ignore

        contenido_row = ft.Row(
            [
                ft.Container(
                    content=self.store._menu_control,
                    expand=1,
                    padding=10
                ),
                ft.VerticalDivider(thickness=1, width=20),
                ft.Container(
                    content=self.store._lista_control,
                    expand=3,
                    padding=10
                )
            ],
            spacing=0,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START
        )
        
        # Layout principal
        self.page.add( # type: ignore
            ft.Column([
                filtros_row,
                contenido_row
            ], expand=True, spacing=20)
        )
    
        self.mostrar_opciones_menu()
     
    # -----------------------
    # Evento cambio de site
    # -----------------------
    async def on_site_change(self, e: ft.ControlEvent):
        site_url = e.control.value
        site = next((s for s in self.store.get_site_collections() if s.Url == site_url), None)
        if not site:
            return
        self.store.set_site_selected(site)
        self.mostrar_opciones_menu()
        self.page.update() # type: ignore
        
    # -----------------------
    # Evento click subsite
    # -----------------------
    def on_subsite_click(self, subsite: ISiteCollection):
        self.store.set_subsite_selected(subsite)
        # Vuelvo a mostrar menú, pero del subsite
        #self.page.add(render_loading("Cargando subsite...")) # type: ignore
        self.page.update() # type: ignore
        self.page.run_task(self.mostrar_opciones_menu, subsite) # type: ignore

    # -----------------------------
    # Cargar datos en lista principal
    # -----------------------------
    def cargar_datos_opcion(self, opcion_id):
        # Aquí se carga la información según la opción seleccionada
       
        self.store._lista_control.controls.clear()

        if opcion_id == "users":
            for users in self.store.get_site_collections() or []: 
                for u in users.Users or []: 
                    self.store._lista_control.controls.append(render_card(u, self.page, self.store.get_roles_definiciones()))
        
        elif opcion_id == "admins":
            for users in self.store.get_site_collections() or []: 
                for u in users.Admins or []: 
                    self.store._lista_control.controls.append(render_card(u, self.page,self.store.get_roles_definiciones()))
        elif opcion_id == "groups":
            for users in self.store.get_site_collections() or []: 
                for u in users.Groups or []: 
                    self.store._lista_control.controls.append(render_card(u, self.page,self.store.get_roles_definiciones()))
        elif opcion_id == "libraries":
            panel_list = panels_renderer(self.store, self.page) # type: ignore
            self.store._lista_control.controls.append(panel_list.render_lists_panels())
        else:
            self.store._lista_control.controls.append(ft.Text("Opción no reconocida."))

        self.page.update() # type: ignore


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
            
