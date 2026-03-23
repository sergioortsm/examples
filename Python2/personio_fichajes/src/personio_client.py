from __future__ import annotations

from typing import Any, Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from .config import Configuracion
except ImportError:
    from config import Configuracion # pyright: ignore[reportAttributeAccessIssue]


class PersonioApiError(RuntimeError):
    pass


class PersonioClient:
    def __init__(
        self,
        cfg: Configuracion,
        session: requests.Session,
        logger,
        reauth_callback: Callable[[], None] | None = None,
    ):
        self.cfg = cfg
        self.base_url = cfg.base_url.rstrip("/")
        self.session = session
        self.logger = logger
        self.reauth_callback = reauth_callback
        self._configurar_reintentos()

    def _configurar_reintentos(self):
        retry = Retry(
            total=self.cfg.max_retries,
            connect=self.cfg.max_retries,
            read=self.cfg.max_retries,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}{path}"

    def _es_sesion_expirada(self, response: requests.Response) -> bool:
        if response.status_code in (401, 403):
            return True

        ctype = response.headers.get("Content-Type", "")
        if "text/html" in ctype and "login" in response.text.lower():
            return True

        return False

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        url = self._url(path)

        response = self.session.request(
            method,
            url,
            params=params,
            json=json_payload,
            timeout=self.cfg.request_timeout_sec,
        )

        if self._es_sesion_expirada(response) and self.reauth_callback:
            self.logger.warning("Sesion expirada. Reautenticando...")
            self.reauth_callback()
            response = self.session.request(
                method,
                url,
                params=params,
                json=json_payload,
                timeout=self.cfg.request_timeout_sec,
            )

        if response.status_code not in expected:
            msg = (
                f"Error API {method} {path} | status={response.status_code} | "
                f"body={response.text[:500]}"
            )
            raise PersonioApiError(msg)

        ctype = response.headers.get("Content-Type", "")
        if "application/json" in ctype:
            return response.json()

        try:
            return response.json()
        except Exception:
            return {"raw": response.text, "content_type": ctype, "status": response.status_code}

    def obtener_pagina_attendance(self, employee_id: int) -> dict[str, Any]:
        """GET /attendance/employee/{id} con la sesion autenticada.
        Devuelve JSON si el servidor responde con JSON, o {"raw": html, ...} si es HTML."""
        path = f"/attendance/employee/{employee_id}"
        self.logger.info(f"Solicitando: {self._url(path)}?hideEmployeeHeader=true")
        return self._request("GET", path, params={"hideEmployeeHeader": "true"})


