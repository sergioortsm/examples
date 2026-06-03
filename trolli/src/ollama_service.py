"""
Adaptador puro para la API local de Ollama.
No importa nada del proyecto Trolli — es un módulo autónomo.
Usa únicamente stdlib (urllib, json, threading).
"""
from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Callable

_log = logging.getLogger("trolli.ollama")

OLLAMA_BASE_URL = "http://localhost:11434"

# ---------------------------------------------------------------------------
# System prompt embebido
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """Eres un filtro de logs técnicos. Tu único trabajo es eliminar el ruido y sacar lo que importa.

PASO 1 — FILTRA. Descarta completamente líneas con nivel: Verbose, Debug, Information, Monitorable, High.
Quédate solo con: Error, Critical, Unexpected, Warning (solo si precede a un error), Exception, Failed, Access denied, Timeout.

PASO 2 — AGRUPA. Si hay Correlation IDs repetidos, agrupa los errores bajo el mismo ID. El primer error del grupo es el más importante.

PASO 3 — RESPONDE en este formato exacto, sin añadir nada más:

**Qué falla:** (1 línea)
**Causa probable:** (1-2 líneas, solo con lo que dicen los logs)
**Líneas clave:**
- (copia literal las 2-5 líneas del log más relevantes)
**Pasos a seguir:**
- (máximo 3 pasos concretos)

Si los logs no contienen errores reales, responde solo: "No se detectaron errores relevantes."
Si falta contexto para diagnosticar, responde solo: "Logs insuficientes — adjunta más contexto."
"""


class OllamaService:
    """Adaptador ligero para la API REST de Ollama (http://localhost:11434)."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL, timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Conexión y modelos
    # ------------------------------------------------------------------

    def check_connection(self) -> bool:
        """Devuelve True si Ollama responde en el puerto local."""
        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5):
                return True
        except Exception:
            return False

    def get_models(self) -> list[str]:
        """Devuelve la lista de nombres de modelos instalados en Ollama."""
        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Análisis asíncrono
    # ------------------------------------------------------------------

    def analyze(
        self,
        text: str,
        model: str,
        on_result: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        """
        Envía `text` a Ollama para análisis en un thread separado.
        Llama `on_result(respuesta)` o `on_error(mensaje)` al terminar.
        No bloquea el hilo principal (UI thread).
        """
        thread = threading.Thread(
            target=self._run_analyze,
            args=(text, model, on_result, on_error),
            daemon=True,
        )
        thread.start()

    def _run_analyze(
        self,
        text: str,
        model: str,
        on_result: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> None:
        prompt = f"{_SYSTEM_PROMPT}\n\n---\n\nLogs a analizar:\n\n{text}"
        payload = json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
            }
        ).encode("utf-8")

        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode())
                on_result(data.get("response", ""))
        except urllib.error.URLError as exc:
            # URLError puede envolver un socket.timeout
            reason = exc.reason
            if isinstance(reason, (TimeoutError, OSError)) and "timed out" in str(reason).lower():
                msg = f"Ollama tardó demasiado en responder (timeout >{self.timeout}s)."
            else:
                msg = f"No se pudo conectar con Ollama: {reason}"
            _log.error("[OLLAMA] %s", msg)
            on_error(msg)
        except TimeoutError:
            msg = f"Ollama tardó demasiado en responder (timeout >{self.timeout}s)."
            _log.error("[OLLAMA] %s", msg)
            on_error(msg)
        except Exception as exc:
            msg = f"Error inesperado al llamar a Ollama: {exc}"
            _log.error("[OLLAMA] %s", msg, exc_info=True)
            on_error(msg)
