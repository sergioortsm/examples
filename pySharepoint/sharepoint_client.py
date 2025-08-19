from urllib.parse import urljoin
import msal
import requests
import os
import json
import time
from typing import Dict, Any, Union, cast

TOKEN_CACHE_FILE = "token_cache.bin"

class SharePointOnlineClient:
    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        site_url: str,
        client_secret: str = "",
        username: str = ""
    ):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret or None
        self.username = username or None
        self.site_url = site_url.rstrip("/")
        self.domain = self.site_url.split("//")[1].split("/")[0]
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"

        # Inicializar token cache
        self.token_cache = msal.SerializableTokenCache()
        self._load_token_cache()

        # Crear app correcta según flujo
        from msal import ConfidentialClientApplication, PublicClientApplication
        self.app: Union[ConfidentialClientApplication, PublicClientApplication]

        if self.client_secret:
            self.app = ConfidentialClientApplication(
                client_id=self.client_id,
                client_credential=self.client_secret,
                authority=self.authority,
                token_cache=self.token_cache
            )
        else:
            self.app = PublicClientApplication(
                client_id=self.client_id,
                authority=self.authority,
                token_cache=self.token_cache
            )

        # Siempre un dict
        self.token: Dict[str, Any] = {}

    # -------------------- Cache --------------------
    def _load_token_cache(self):
        if os.path.exists(TOKEN_CACHE_FILE):
            with open(TOKEN_CACHE_FILE, "r") as f:
                self.token_cache.deserialize(f.read())

    def _save_cache(self):
        if self.token_cache.has_state_changed:
            with open(TOKEN_CACHE_FILE, "w") as f:
                f.write(self.token_cache.serialize())

    def _is_token_valid(self, token: Dict[str, Any]) -> bool:
        return bool(token) and "expires_on" in token and int(token["expires_on"]) > time.time() + 60


    # -------------------- Token --------------------
    def _get_access_token(self) -> str:
        scopes = [f"https://{self.domain}/.default"]

        if self.client_secret:
            # --- APP-ONLY ---
            app = cast(msal.ConfidentialClientApplication, self.app)
            result = app.acquire_token_silent(scopes, account=None)
            if not result:
                result = app.acquire_token_for_client(scopes=scopes)
        else:
            # --- USER / INTERACTIVE ---
            app = cast(msal.PublicClientApplication, self.app)
            accounts = app.get_accounts(username=self.username)
            result = app.acquire_token_silent(
                scopes,
                account=accounts[0] if accounts else None
            )
            if not result:
                result = app.acquire_token_interactive(
                    scopes=scopes,
                    login_hint=self.username
                )

        if not result or "access_token" not in result:
            raise Exception(
                f"Error obteniendo token: {result.get('error_description') if result else 'Respuesta vacía'}"
            )

        self._save_cache()
        self.token = result
        return result["access_token"]

    # -------------------- SharePoint REST --------------------
    def get(self, endpoint: str) -> Dict[str, Any]:
        token = self._get_access_token()
        url = urljoin(f"{self.site_url}/", f"{endpoint.lstrip('/')}")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json;odata=nometadata"
        }
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        token = self._get_access_token()
        url = f"{self.site_url}/_api/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json;odata=nometadata",
            "Content-Type": "application/json"
        }
        resp = requests.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()
