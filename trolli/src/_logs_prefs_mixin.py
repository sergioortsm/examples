"""LogsPreferencesMixin — gestión de preferencias y almacenamiento de Logs.

Extraído de TrelloApp en main.py. Se mezcla vía herencia múltiple; no define
__init__ propio y accede a self._prefs_path, self.logs_state, etc. que son
inicializados en TrelloApp.__init__.
"""
import asyncio
import inspect
import json
import logging
import os

logger = logging.getLogger("trolli")


class LogsPreferencesMixin:
    # ------------------------------------------------------------------
    # Almacenamiento (SharedPreferences / client_storage / fallback dict)
    # ------------------------------------------------------------------

    def _storage_get(self, key: str, default=None):
        # Compatibilidad entre versiones de Flet (sync/async) y distintos backends.
        for storage in (self._shared_preferences, getattr(self._page, "client_storage", None), getattr(self._page, "session", None)):
            if storage is None:
                continue
            for getter_name in ("get", "get_async"):
                getter = getattr(storage, getter_name, None)
                if not callable(getter):
                    continue
                try:
                    value = getter(key)
                    if inspect.isawaitable(value):
                        # En contexto sync no bloqueamos para resolver getters async.
                        # Se cierra la coroutine para evitar RuntimeWarning y se prueba fallback.
                        if inspect.iscoroutine(value):
                            value.close()
                        logger.debug("Storage getter async omitido para key=%s", key)
                        continue
                    return default if value is None else value
                except Exception:
                    continue
        return self._fallback_storage.get(key, default)

    def _storage_set(self, key: str, value):
        for storage in (self._shared_preferences, getattr(self._page, "client_storage", None), getattr(self._page, "session", None)):
            if storage is None:
                continue
            for setter_name in ("set", "set_async"):
                setter = getattr(storage, setter_name, None)
                if not callable(setter):
                    continue
                try:
                    result = setter(key, value)
                    if inspect.isawaitable(result):
                        try:
                            task = asyncio.get_running_loop().create_task(result)
                            task.add_done_callback(lambda t, k=key: self._on_storage_set_task_done(k, t))
                        except RuntimeError:
                            # Sin loop activo (o en thread), no intentamos ejecutar la coroutine.
                            # La cerramos para evitar warning y dejamos persistencia en fallback.
                            if inspect.iscoroutine(result):
                                result.close()
                            logger.debug("Storage setter async omitido sin loop activo para key=%s", key)
                            continue
                    return
                except Exception:
                    continue
        self._fallback_storage[key] = value

    def _on_storage_set_task_done(self, key: str, task: asyncio.Task):
        try:
            task.result()
        except Exception:
            logger.debug("Storage set_async fallo para key=%s", key, exc_info=True)

    # ------------------------------------------------------------------
    # Preferencias de logs (archivo JSON + fallback storage)
    # ------------------------------------------------------------------

    def _default_logs_preferences(self) -> dict[str, object]:
        return {
            "search_text": "",
            "level_filter": "All",
            "sort_by": None,
            "sort_desc": False,
            "page_size": 100,
            "visible_columns": [],
            "column_widths": {},
            "watch_folder": "",
            "watch_pattern": r".+\.log$",
        }

    def _ensure_logs_preferences_file(self) -> dict[str, object]:
        defaults = self._default_logs_preferences()
        if self._prefs_path.exists():
            return defaults

        self._write_prefs_file_atomic(defaults)
        if self._prefs_path.exists():
            logger.info("[PREFS] logs_prefs.json creado con valores por defecto en %s", self._prefs_path)
        else:
            logger.warning("[PREFS] no se pudo crear logs_prefs.json en %s", self._prefs_path)
        return defaults

    def _read_prefs_file(self) -> dict[str, object]:
        try:
            if not self._prefs_path.exists():
                return {}
            raw = self._prefs_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            logger.exception("[PREFS] Error al leer logs_prefs.json desde %s", self._prefs_path)
            return {}

    def _write_prefs_file_atomic(self, data: dict[str, object]):
        try:
            self._prefs_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self._prefs_path.with_suffix(".tmp")
            temp_path.write_text(
                json.dumps(data, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
            os.replace(temp_path, self._prefs_path)
        except Exception:
            logger.exception("[PREFS] Error al escribir logs_prefs.json en %s", self._prefs_path)

    def _restore_logs_preferences(self):
        defaults = self._default_logs_preferences()
        self._ensure_logs_preferences_file()
        file_prefs = self._read_prefs_file()
        for key, default_value in defaults.items():
            stored_value = file_prefs.get(key, None)
            if stored_value is None:
                stored_value = self._storage_get(f"logs_{key}", None)
            if key == "sort_by" and stored_value == "":
                stored_value = None
            self.logs_state[key] = default_value if stored_value is None else stored_value

        if not isinstance(self.logs_state.get("visible_columns"), list):
            self.logs_state["visible_columns"] = []
        if not isinstance(self.logs_state.get("column_widths"), dict):
            self.logs_state["column_widths"] = {}
        self.logs_state["visible_columns_pending"] = list(self.logs_state.get("visible_columns", []))

        normalized_widths: dict[str, int] = {}
        for key, value in dict(self.logs_state.get("column_widths", {})).items():
            try:
                width = int(value)
            except (TypeError, ValueError):
                continue
            if width > 0:
                normalized_widths[str(key)] = width
        self.logs_state["column_widths"] = normalized_widths

        try:
            self.logs_state["page_size"] = int(self.logs_state.get("page_size", 100))
        except (TypeError, ValueError):
            self.logs_state["page_size"] = 100

        self.logs_state["sort_desc"] = bool(self.logs_state.get("sort_desc", False))
        self._persist_logs_preferences_if_needed()

    def _persist_logs_preferences(self):
        prefs_to_persist: dict[str, object] = {
            "search_text": self.logs_state["search_text"],
            "level_filter": self.logs_state["level_filter"],
            "sort_by": self.logs_state["sort_by"],
            "sort_desc": self.logs_state["sort_desc"],
            "page_size": self.logs_state["page_size"],
            "visible_columns": self.logs_state["visible_columns"],
            "column_widths": self.logs_state.get("column_widths", {}),
            "watch_folder": self.logs_state.get("watch_folder", ""),
            "watch_pattern": self.logs_state.get("watch_pattern", ""),
        }
        self._write_prefs_file_atomic(prefs_to_persist)

        self._storage_set("logs_search_text", self.logs_state["search_text"])
        self._storage_set("logs_level_filter", self.logs_state["level_filter"])
        self._storage_set("logs_sort_by", self.logs_state["sort_by"] or "")
        self._storage_set("logs_sort_desc", self.logs_state["sort_desc"])
        self._storage_set("logs_page_size", self.logs_state["page_size"])
        self._storage_set("logs_visible_columns", self.logs_state["visible_columns"])
        self._storage_set("logs_column_widths", self.logs_state.get("column_widths", {}))
        self._storage_set("logs_watch_folder", self.logs_state.get("watch_folder", ""))
        self._storage_set("logs_watch_pattern", self.logs_state.get("watch_pattern", ""))

    def _persist_logs_preferences_if_needed(self):
        current_signature = self._logs_prefs_signature()
        if current_signature == self._logs_prefs_signature_last_saved:
            return
        self._persist_logs_preferences()
        self._logs_prefs_signature_last_saved = current_signature
