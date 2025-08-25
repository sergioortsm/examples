import json
import os
import time
from common.sharepoint_client import sharepoint_client

TOKEN_PATH = "token_cache.json"

class shp_service:
    _instance = None    
    USERNAME = ""       # login interactivo si CLIENT_SECRET está vacío
    CLIENT_ID = "0ee25780-948d-4e07-bccf-5457e16d705f"
    TENANT_ID = "a272015e-e187-4c3c-95a6-93cfdba816b8"     
    AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
    SCOPES = ["https://sortsactivedev.sharepoint.com/.default"]
    SHAREPOINT_SITE = "https://sortsactivedev.sharepoint.com/sites/prueba" #"https://sortsactivedev.sharepoint.com/sites/prueba/_api/web/lists?$filter=Hidden eq false"
    SHAREPOINT_ROOT = "https://sortsactivedev.sharepoint.com"    
    CLIENT_SECRET = "xSw8Q~.3X0U8mu7qKBU9QV2zZwdopqeC9nq_CaCI"  # app-only si tiene valor
    PFX_PATH = r"C:\repositorio\examples\pySharepoint\certificado\MiAppSharePointPython.pfx"
    PFX_PASSWORD = b"MiPasswordSegura123"  # como bytes
    PFX_THUMBPRINT = "A2C0322C559E3D70C69FB96A27C76479E7EF22C9"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.sp = None
        return cls._instance

    def _load_token_cache(self):
        if os.path.exists(TOKEN_PATH):
            with open(TOKEN_PATH, "r") as f:
                return json.load(f)
        return None

    def _save_token_cache(self, token):
        with open(TOKEN_PATH, "w") as f:
            json.dump(token, f)

    def _is_token_valid(self, token):
        return token and "expires_on" in token and int(token["expires_on"]) > time.time() + 60

    def _init_client(self):
        print("🔄 Iniciando cliente SharePoint...")

        self.sp = sharepoint_client(
            tenant_id=self.TENANT_ID,
            client_id=self.CLIENT_ID,
            client_secret=self.CLIENT_SECRET,
            username=self.USERNAME,
            site_url=self.SHAREPOINT_ROOT,
            pfx_path=self.PFX_PATH, # type: ignore
            pfx_password=self.PFX_PASSWORD,
            pfx_thumbprint=self.PFX_THUMBPRINT
        )

        # Obtener token        
        access_token = self.sp._get_access_token()
        expires_in = int(self.sp.token.get("expires_in", 3600))
        print("🔄 Obteniendo token...")
        token_info = {
            "access_token": access_token,
            "expires_on": int(time.time()) + expires_in,
            "refresh_token": self.sp.token.get("refresh_token")
        }
        
        print("🔄 Grabando token...")
        self._save_token_cache(token_info)

    def get_client(self):
        if self.sp is None:
            self._init_client()
        return self.sp
