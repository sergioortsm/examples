import flet as ft
from typing import Any, Dict, List, Optional
from diskcache import Cache
from common.interfaces import IList, ISiteCollection
from common.shp_helper import shp_helper
from services.shp_service import shp_service


CACHE_DIR = "./site_cache"


class app_state:
    def __init__(self):
        # Servicios y utilidades
        self._sp_service = shp_service()
        self._cache = Cache(CACHE_DIR)
        self._cache.clear()
        self._helper: shp_helper = shp_helper(self._sp_service.sp, self, cache=self._cache)        
        self._site_selected: Optional[ISiteCollection] = None
        self._subsite_selected: Optional[ISiteCollection] = None
        self._list_selected: Optional[IList] = None
        self._selected_items: Optional[Any] = None
        self._sites_options: List[Dict[str, Any]] = []
        self._subsites_options: List[Dict[str, Any]] = []
        self._site_collections: List[ISiteCollection] = []
        self._auth_token: Dict[str, str] = {"token": ""}
        self._loading: bool = True
        self._roles_definiciones: List[Dict[str, Any]] = []

        # Controles UI
        self._lista_control: ft.Column = ft.Column(
            spacing=5, expand=3, scroll=ft.ScrollMode.AUTO
        )
        self._menu_control: ft.Column = ft.Column()
        self._btnLinkSite: ft.IconButton = ft.IconButton()
        self._btnLinkSubSite: ft.IconButton = ft.IconButton()

    # -------------------------
    # Métodos de acceso (getters/setters)
    # -------------------------
    
   # Getter
    @property
    def helper(self) -> shp_helper:
        return self._helper

    # Setter
    @helper.setter
    def helper(self, value: shp_helper) -> None:
        if not isinstance(value, shp_helper):
            raise TypeError("helper debe ser una instancia de shp_helper")
        self._helper = value
  
    @property
    def site_selected(self) -> Optional[ISiteCollection]:
        return self._site_selected

    def set_site_selected(self, site: ISiteCollection) -> None:
        self._site_selected = site

    @property
    def subsite_selected(self) -> Optional[ISiteCollection]:
        return self._subsite_selected

    def set_subsite_selected(self, subsite: ISiteCollection) -> None:
        self._subsite_selected = subsite

    @property
    def list_selected(self) -> Optional[IList]:
        return self._list_selected

    def set_list_selected(self, lst: IList) -> None:
        self._list_selected = lst

    @property
    def selected_items(self) -> Optional[Any]:
        return self._selected_items

    def set_selected_items(self, items: Any) -> None:
        self._selected_items = items

    # -------------------------
    # Sitios y subsitios
    # -------------------------
    def set_sites_options(self, options: List[Dict[str, Any]]) -> None:
        self._sites_options = options

    def get_sites_options(self) -> List[Dict[str, Any]]:
        return self._sites_options

    def set_subsites_options(self, options: List[Dict[str, Any]]) -> None:
        self._subsites_options = options

    def get_subsites_options(self) -> List[Dict[str, Any]]:
        return self._subsites_options

    def add_site_collection(self, site: ISiteCollection) -> None:
        self._site_collections.append(site)
        
    def set_site_collections(self, sites: List[ISiteCollection]) -> None:
        self._site_collections = sites

    def get_site_collections(self) -> List[ISiteCollection]:
        return self._site_collections

    # -------------------------
    # Roles
    # -------------------------
    def set_roles_definiciones(self, roles: List[Dict[str, Any]]) -> None:
        self._roles_definiciones = roles

    def get_roles_definiciones(self) -> List[Dict[str, Any]]:
        return self._roles_definiciones

    # -------------------------
    # Token y loading
    # -------------------------
    def get_auth_token(self) -> Dict[str, str]:
        return self._auth_token

    def set_auth_token(self, token: str) -> None:
        self._auth_token["token"] = token

    def is_loading(self) -> bool:
        return self._loading

    def set_loading(self, value: bool) -> None:
        self._loading = value

    # -------------------------
    # Controles UI
    # -------------------------
    def get_lista_control(self) -> ft.Column:
        return self._lista_control

    def get_menu_control(self) -> ft.Column:
        return self._menu_control

    def btnLinkSite(self) -> ft.IconButton:
        return self._btnLinkSite
    
    def btnLinkSubSite(self) -> ft.IconButton:
        return self._btnLinkSubSite