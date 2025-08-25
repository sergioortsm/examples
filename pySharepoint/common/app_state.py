import flet as ft 
from typing import Any, Dict, List, Optional
from diskcache import Cache
from common.interfaces import IList, ISiteCollection
from common.shp_helper import shp_helper
from services.shp_service import shp_service


CACHE_DIR = "./site_cache"
 
# -----------------------------
# Estado centralizado de la app
# -----------------------------
class app_state:
    def __init__(self):
        self.sp_service = shp_service()
        self.cache = Cache(CACHE_DIR)
        self.cache.clear()
        self.helper: shp_helper = shp_helper(self.sp_service.sp, cache=self.cache)
        self.site_selected: Optional[ISiteCollection] = None
        self.subsite_selected: Optional[ISiteCollection] = None
        self.list_selected: Optional[IList] = None
        self.selected_items: Optional[Any] = None
        self.sites_options = []
        self.subsites_options = []
        self.site_collections: List[ISiteCollection] = [] 
        self.auth_token = {"token": ""}
        self.loading = True
        
        # Declarar los controles UI para que Pylance los conozca
        self.lista_control: ft.Column = ft.Column(spacing=5, expand=3, scroll=ft.ScrollMode.AUTO)
        self.menu_control: ft.Column = ft.Column()
        self.roles_definiciones: List[Dict[str, Any]] = []
        