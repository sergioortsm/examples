from urllib.parse import urljoin
import msal
import requests
import os
import json
import time
from typing import Dict, Any, Union, cast
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates

TOKEN_CACHE_FILE = "token_cache.bin"

class sharepoint_client:
    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        site_url: str,
        client_secret: str = "",
        username: str = "",
        pfx_path: str = "",
        pfx_password: Union[bytes, str] = "",
        pfx_thumbprint: str = ""
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

        self.token: Dict[str, Any] = {}

        # -----------------------------
        # Crear app según flujo
        # -----------------------------
        if pfx_path and pfx_password and pfx_thumbprint:
            # --- APP-ONLY con PFX ---
            if isinstance(pfx_password, str):
                pfx_password = pfx_password.encode("utf-8")
            with open(pfx_path, "rb") as f:
                pfx_data = f.read()
            private_key, cert, _ = load_key_and_certificates(pfx_data, pfx_password, backend=default_backend())
            pem_private_key = private_key.private_bytes( # type: ignore
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            self.app = msal.ConfidentialClientApplication(
                client_id=self.client_id,
                authority=self.authority,
                client_credential={
                    "private_key": pem_private_key.decode("utf-8"),
                    "thumbprint": pfx_thumbprint
                },
                token_cache=self.token_cache
            )

        elif self.client_secret:
            # --- APP-ONLY con client secret ---
            self.app = msal.ConfidentialClientApplication(
                client_id=self.client_id,
                authority=self.authority,
                client_credential=self.client_secret,
                token_cache=self.token_cache
            )
        else:
            # --- Usuario interactivo ---
            self.app = msal.PublicClientApplication(
                client_id=self.client_id,
                authority=self.authority,
                token_cache=self.token_cache
            )

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

        if isinstance(self.app, msal.ConfidentialClientApplication):
            # APP-ONLY
            result = self.app.acquire_token_silent(scopes, account=None, force_refresh=True)
            if not result:
                result = self.app.acquire_token_for_client(scopes=scopes)
        else:
            # USER / INTERACTIVE
            accounts = self.app.get_accounts(username=self.username)
            result = self.app.acquire_token_silent(scopes, account=accounts[0] if accounts else None)
            if not result:
                result = self.app.acquire_token_interactive(scopes=scopes, login_hint=self.username)

        if not result or "access_token" not in result:
            raise Exception(f"Error obteniendo token: {result.get('error_description') if result else 'Respuesta vacía'}")

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

    def post(self, endpoint: str,payload=Any) -> Dict[str, Any]:
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
