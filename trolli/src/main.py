from importlib.metadata import PackageNotFoundError, version
import asyncio
import inspect
import json
import logging
import os

import flet as ft
from datetime import datetime
from pathlib import Path
from app_layout import AppLayout
from board import Board
from user import User
from data_store import DataStore
from memory_store import InMemoryStore
from dialog import DialogSizer, build_logs_message_dialog
from logs_view import LogsView
from app_logging import (
    install_asyncio_exception_handler,
    install_global_exception_hooks,
    setup_logging,
)
from log_service import (
    apply_filters_sort_paginate,
    export_rows_to_csv,
    filter_sort_rows,
    load_sharepoint_log,
    paginate_rows,
)
from log_buffer import LifoLogBuffer
from log_watcher import LogWatcher


logger = logging.getLogger("trolli")


class TrelloApp(AppLayout):
    def __init__(self, page: ft.Page, store: DataStore):
        self._page: ft.Page = page
        self.store: DataStore = store
        self.user: str | None = None
        self._fallback_storage: dict[str, object] = {}
        self._shared_preferences = ft.SharedPreferences()
        self._prefs_path = Path(os.getenv("APPDATA", str(Path.home()))) / "trolli" / "logs_prefs.json"
        self._page.on_route_change = self.route_change
        self._page.on_error = self._on_page_error
        self.boards = self.store.get_boards()
        self.logs_rows: list[dict[str, str]] = []
        self._logs_query_cache_signature: tuple[object, ...] | None = None
        self._logs_query_cache_rows: list[dict[str, str]] = []
        self._logs_prefs_signature_last_saved: tuple[object, ...] | None = None
        self._logs_refresh_pending = False
        self.logs_state = {
            "file_path": "",
            "file_label": "Sin archivo cargado",
            "is_loading": False,
            "is_applying_columns": False,
            "columns": [],
            "visible_columns": [],
            "visible_columns_pending": [],
            "column_selector_expanded": False,
            "level_options": ["All"],
            "search_text": "",
            "level_filter": "All",
            "sort_by": None,
            "sort_desc": False,
            "page_size": 100,
            "current_page": 1,
            "total_pages": 1,
            "filtered_total": 0,
            "page_rows": [],
            "error": "",
            "message_dialog_open": False,
            "message_dialog_text": "",
            "message_dialog_title": "Detalle de Message",
            # --- modo watcher (live tailing) ---
            "watch_folder": "",
            "watch_pattern": r".+\.log$",
            "is_watching": False,
            "watch_error": "",
            "buffer_count": 0,
            "buffer_max": 100_000,
            "pending_new_count": 0,
            "lines_per_sec": 0.0,
        }
        # Buffer LIFO compartido entre el hilo del watcher y el event loop.
        self._log_buffer = LifoLogBuffer(maxlen=100_000)
        self._watcher: LogWatcher | None = None
        self._watcher_pending_batches: list[tuple[list[dict[str, str]], list[str], list[str]]] = []
        self._watcher_pending_lock = __import__("threading").Lock()
        self._watcher_drain_task: asyncio.Task | None = None
        self._watcher_lines_window: list[tuple[float, int]] = []  # (timestamp, count) ultimos 5s
        self.login_profile_button = ft.PopupMenuItem(content="Log in", on_click=self.login)
        self.appbar_items = [
            self.login_profile_button,
            ft.PopupMenuItem(),  # divider
            ft.PopupMenuItem(content="Open SharePoint LOG", on_click=self.open_log_file_dialog),
            ft.PopupMenuItem(content="Settings"),
        ]
        self.appbar = ft.AppBar(
            leading=ft.Icon(ft.Icons.GRID_GOLDENRATIO_ROUNDED),
            leading_width=100,
            title=ft.Text(
                f"Trolli",
                font_family="Pacifico",
                size=32,
                text_align=ft.TextAlign.START,
            ),
            center_title=False,
            toolbar_height=75,
            bgcolor=ft.Colors.LIGHT_BLUE_ACCENT_700,
            actions=[
                ft.Container(
                    content=ft.PopupMenuButton(items=self.appbar_items),
                    margin=ft.margin.Margin(left=50, right=25),
                )
            ],
        )
        self._page.appbar = self.appbar
        self.file_picker = ft.FilePicker()
        if hasattr(self.file_picker, "on_result"):
            self.file_picker.on_result = self.on_log_file_selected
        self._page.services.append(self.file_picker)
        self._page.services.append(self._shared_preferences)
        (
            self.logs_message_dialog_title,
            self.logs_message_dialog_meta,
            self.logs_message_dialog_body,
            self.logs_message_dialog_container,
            self.logs_message_dialog,
        ) = build_logs_message_dialog(
            on_copy=self.on_logs_copy_message_detail,
            on_close=self.on_logs_close_message_detail,
        )
        self.global_loading_label = ft.Text("Cargando archivo...", color=ft.Colors.WHITE)
        self.global_loading_overlay = ft.Container(
            visible=False,
            width=max(0, int(getattr(self._page, "width", 0) or 0)),
            height=max(0, int(getattr(self._page, "height", 0) or 0)),
            bgcolor="#66000000",
            alignment=ft.Alignment(x=0, y=0),
            content=ft.Column(
                [
                    ft.ProgressRing(width=52, height=52, stroke_width=4, color=ft.Colors.WHITE),
                    self.global_loading_label,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
                spacing=12,
            ),
        )
        self._global_loading_counter = 0
        self._global_loading_registered = False
        self._restore_logs_preferences()
        self.logs_view = LogsView(self)

        self._page.update()
        super().__init__(
            self,
            self._page,
            self.store,
            tight=False,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def _on_page_error(self, e):
        route = getattr(self._page, "route", "")
        event_data = getattr(e, "data", e)
        logger.error("Flet UI error | route=%s | event=%s", route, event_data)

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

    def _read_prefs_file(self) -> dict[str, object]:
        try:
            if not self._prefs_path.exists():
                return {}
            raw = self._prefs_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
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
            pass

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
                            asyncio.get_running_loop().create_task(result)
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

    def initialize(self):
        if not self._global_loading_registered:
            self._page.overlay.append(self.global_loading_overlay)
            self._global_loading_registered = True
        if self not in self._page.controls:
            self._page.add(self)
        self._page.update()
        # Restaura las preferencias de los logs al inicializar
        self._restore_logs_preferences()
        # create an initial board for demonstration if no boards
        if len(self.boards) == 0:
            self.create_new_board("My First Board")
        # Render de logs_view solo si ya está en el árbol de controles
        try:
            self.logs_view.render(self.logs_state)
        except RuntimeError:
            pass
        if self._page.route != "/logs":
            self._page.navigate("/logs")
        else:
            self.set_logs_view()

    def _restore_logs_preferences(self):
        file_prefs = self._read_prefs_file()
        defaults = {
            "search_text": "",
            "level_filter": "All",
            "sort_by": None,
            "sort_desc": False,
            "page_size": 100,
            "visible_columns": [],
            "watch_folder": "",
            "watch_pattern": r".+\.log$",
        }
        for key, default_value in defaults.items():
            stored_value = file_prefs.get(key, None)
            if stored_value is None:
                stored_value = self._storage_get(f"logs_{key}", None)
            self.logs_state[key] = default_value if stored_value is None else stored_value

        if not isinstance(self.logs_state.get("visible_columns"), list):
            self.logs_state["visible_columns"] = []
        self.logs_state["visible_columns_pending"] = list(self.logs_state.get("visible_columns", []))

        try:
            self.logs_state["page_size"] = int(self.logs_state.get("page_size", 100))
        except (TypeError, ValueError):
            self.logs_state["page_size"] = 100

        self.logs_state["sort_desc"] = bool(self.logs_state.get("sort_desc", False))

    def _persist_logs_preferences(self):
        prefs_to_persist: dict[str, object] = {
            "search_text": self.logs_state["search_text"],
            "level_filter": self.logs_state["level_filter"],
            "sort_by": self.logs_state["sort_by"],
            "sort_desc": self.logs_state["sort_desc"],
            "page_size": self.logs_state["page_size"],
            "visible_columns": self.logs_state["visible_columns"],
            "watch_folder": self.logs_state.get("watch_folder", ""),
            "watch_pattern": self.logs_state.get("watch_pattern", ""),
        }
        self._write_prefs_file_atomic(prefs_to_persist)

        self._storage_set("logs_search_text", self.logs_state["search_text"])
        self._storage_set("logs_level_filter", self.logs_state["level_filter"])
        self._storage_set("logs_sort_by", self.logs_state["sort_by"])
        self._storage_set("logs_sort_desc", self.logs_state["sort_desc"])
        self._storage_set("logs_page_size", self.logs_state["page_size"])
        self._storage_set("logs_visible_columns", self.logs_state["visible_columns"])
        self._storage_set("logs_watch_folder", self.logs_state.get("watch_folder", ""))
        self._storage_set("logs_watch_pattern", self.logs_state.get("watch_pattern", ""))

    def _logs_query_signature(self) -> tuple[object, ...]:
        return (
            self.logs_state.get("file_path", ""),
            tuple(self.logs_state.get("columns", [])),
            self.logs_state.get("search_text", ""),
            self.logs_state.get("level_filter", "All"),
            self.logs_state.get("sort_by", None),
            bool(self.logs_state.get("sort_desc", False)),
            int(self.logs_state.get("page_size", 100)),
        )

    def _logs_prefs_signature(self) -> tuple[object, ...]:
        return (
            self.logs_state.get("search_text", ""),
            self.logs_state.get("level_filter", "All"),
            self.logs_state.get("sort_by", None),
            bool(self.logs_state.get("sort_desc", False)),
            int(self.logs_state.get("page_size", 100)),
            tuple(self.logs_state.get("visible_columns", [])),
            self.logs_state.get("watch_folder", ""),
            self.logs_state.get("watch_pattern", ""),
        )

    def _invalidate_logs_query_cache(self):
        self._logs_query_cache_signature = None
        self._logs_query_cache_rows = []

    async def _rebuild_logs_query_cache_in_thread_if_needed(self):
        query_signature = self._logs_query_signature()
        if query_signature == self._logs_query_cache_signature:
            return

        rows = await asyncio.to_thread(
            filter_sort_rows,
            self.logs_rows,
            self.logs_state["columns"],
            self.logs_state["search_text"],
            self.logs_state["level_filter"],
            self.logs_state["sort_by"],
            self.logs_state["sort_desc"],
        )
        self._logs_query_cache_rows = rows
        self._logs_query_cache_signature = query_signature

    def _persist_logs_preferences_if_needed(self):
        current_signature = self._logs_prefs_signature()
        if current_signature == self._logs_prefs_signature_last_saved:
            return
        self._persist_logs_preferences()
        self._logs_prefs_signature_last_saved = current_signature

    def open_log_file_dialog(self, e=None):
        logger.info("[LOGS] open_log_file_dialog llamado")
        async def _pick_and_handle_file():
            files = await self.file_picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["log"],
                dialog_title="Selecciona un archivo .log de SharePoint",
            )
            self._handle_selected_log_files(files)

        try:
            asyncio.get_running_loop().create_task(_pick_and_handle_file())
        except RuntimeError:
            pass

    def _handle_selected_log_files(self, files):
        logger.info("[LOGS] _handle_selected_log_files: files=%s", files)
        if not files:
            logger.info("[LOGS] _handle_selected_log_files: sin archivos, saliendo")
            return

        file_path = getattr(files[0], "path", None)
        logger.info("[LOGS] _handle_selected_log_files: file_path=%r", file_path)
        if not file_path:
            logger.warning("[LOGS] _handle_selected_log_files: ruta vacia, saliendo")
            return

        self.load_log_file(file_path)
        if self._page.route != "/logs":
            self._page.navigate("/logs")
        else:
            self.set_logs_view()

    def on_log_file_selected(self, e):
        self._handle_selected_log_files(getattr(e, "files", None))

    def _sync_global_loading_overlay_size(self):
        self.global_loading_overlay.width = max(0, int(getattr(self._page, "width", 0) or 0))
        self.global_loading_overlay.height = max(0, int(getattr(self._page, "height", 0) or 0))

    def on_layout_resize(self, e=None):
        self._sync_global_loading_overlay_size()
        if self.global_loading_overlay.visible:
            self._page.update()

    def begin_global_loading(self, label: str = "Cargando archivo..."):
        self._global_loading_counter += 1
        self.global_loading_label.value = label
        self._sync_global_loading_overlay_size()
        self.global_loading_overlay.visible = True

    def end_global_loading(self):
        self._global_loading_counter = max(0, self._global_loading_counter - 1)
        if self._global_loading_counter == 0:
            self.global_loading_overlay.visible = False

    def _load_log_file_sync(self, file_path: str):
        self._invalidate_logs_query_cache()
        result = load_sharepoint_log(file_path)
        logger.info(
            "[LOGS] load_sharepoint_log: error=%r rows=%s columns=%s",
            result.error,
            len(result.rows),
            result.columns,
        )
        if result.error:
            self.logs_rows = []
            self.logs_state.update(
                {
                    "file_path": file_path,
                    "file_label": f"Archivo: {Path(file_path).name}",
                    "columns": [],
                    "visible_columns": [],
                    "visible_columns_pending": [],
                    "column_selector_expanded": False,
                    "level_options": ["All"],
                    "current_page": 1,
                    "total_pages": 1,
                    "filtered_total": 0,
                    "page_rows": [],
                    "error": result.error,
                }
            )
            return

        self.logs_rows = result.rows
        visible_columns = self.logs_state.get("visible_columns", [])
        valid_visible = [c for c in visible_columns if c in result.columns]
        if not valid_visible:
            valid_visible = list(result.columns)

        pending_columns = self.logs_state.get("visible_columns_pending", [])
        valid_pending = [c for c in pending_columns if c in result.columns]
        if not valid_pending:
            valid_pending = list(valid_visible)

        sort_by = self.logs_state.get("sort_by")
        if sort_by not in result.columns:
            sort_by = result.columns[0] if result.columns else None

        level_filter = self.logs_state.get("level_filter", "All")
        level_options = ["All"] + result.levels
        if level_filter not in level_options:
            level_filter = "All"

        self.logs_state.update(
            {
                "file_path": file_path,
                "file_label": f"Archivo: {Path(file_path).name}",
                "columns": result.columns,
                "visible_columns": valid_visible,
                "visible_columns_pending": valid_pending,
                "column_selector_expanded": False,
                "level_options": level_options,
                "sort_by": sort_by,
                "level_filter": level_filter,
                "current_page": 1,
                "error": "",
            }
        )

        self.refresh_logs_view(show_loading=False)

    async def _load_log_file_deferred(self, file_path: str, min_loading_seconds: float = 0.15):
        # Cede un ciclo para garantizar que el overlay global se pinte antes del parseo pesado.
        loop = asyncio.get_running_loop()
        started = loop.time()
        await asyncio.sleep(0)
        try:
            # run_in_executor mueve el parseo (CPU/IO intensivo) a un thread del pool,
            # liberando el event loop de Flet durante la carga del fichero.
            await loop.run_in_executor(None, self._load_log_file_sync, file_path)
        finally:
            remaining = min_loading_seconds - (loop.time() - started)
            if remaining > 0:
                await asyncio.sleep(remaining)
            self.end_global_loading()
            try:
                self.logs_view.render(self.logs_state)
            except RuntimeError:
                pass
            self._page.update()

    def load_log_file(self, file_path: str):
        logger.info("[LOGS] load_log_file: iniciando con file_path=%r", file_path)
        self.begin_global_loading("Cargando archivo .log...")
        scheduled_async = False
        self._page.update()

        try:
            asyncio.get_running_loop().create_task(self._load_log_file_deferred(file_path))
            scheduled_async = True
            return
        except RuntimeError:
            # Fallback para entornos sin loop async.
            self._load_log_file_sync(file_path)
        finally:
            if scheduled_async:
                return
            self.end_global_loading()
            try:
                self.logs_view.render(self.logs_state)
            except RuntimeError:
                pass
            self._page.update()

    def _refresh_logs_view_core(self, should_render: bool = True):
        if not self.logs_state.get("columns"):
            self._invalidate_logs_query_cache()
            self.logs_state.update(
                {
                    "page_rows": [],
                    "filtered_total": 0,
                    "total_pages": 1,
                    "current_page": 1,
                }
            )
            if should_render:
                try:
                    self.logs_view.render(self.logs_state)
                except RuntimeError:
                    pass
                self._page.update()
            return

        query_signature = self._logs_query_signature()
        if query_signature != self._logs_query_cache_signature:
            self._logs_query_cache_rows = filter_sort_rows(
                self.logs_rows,
                self.logs_state["columns"],
                self.logs_state["search_text"],
                self.logs_state["level_filter"],
                self.logs_state["sort_by"],
                self.logs_state["sort_desc"],
            )
            self._logs_query_cache_signature = query_signature

        page_rows, filtered_total, total_pages, safe_page = paginate_rows(
            self._logs_query_cache_rows,
            self.logs_state["current_page"],
            int(self.logs_state["page_size"]),
        )

        self.logs_state.update(
            {
                "page_rows": page_rows,
                "filtered_total": filtered_total,
                "total_pages": total_pages,
                "current_page": safe_page,
            }
        )
        self._persist_logs_preferences_if_needed()
        if should_render:
            try:
                self.logs_view.render(self.logs_state)
            except RuntimeError:
                pass
            self._page.update()

    def refresh_logs_view(self, show_loading: bool = True):
        # Centraliza el overlay para cualquier accion que refresque el listado.
        if show_loading:
            if bool(self.logs_state.get("is_loading", False)):
                self._logs_refresh_pending = True
                return

            self.logs_state["is_loading"] = True
            try:
                self.logs_view.refresh_loading_state(self.logs_state)
            except RuntimeError:
                pass
            self._page.update()
            try:
                asyncio.get_running_loop().create_task(self._refresh_logs_view_deferred())
            except RuntimeError:
                # Fallback para contextos sin loop async.
                try:
                    self._refresh_logs_view_core(should_render=False)
                finally:
                    self.logs_state["is_loading"] = False
                    try:
                        self.logs_view.render(self.logs_state)
                    except RuntimeError:
                        pass
                    self._page.update()
            return

        self._refresh_logs_view_core()

    async def _refresh_logs_view_deferred(self, min_loading_seconds: float = 0.15):
        # Cede un ciclo para que Flet pinte el overlay antes del trabajo de filtrado/orden/paginacion.
        loop = asyncio.get_running_loop()
        started = loop.time()
        await asyncio.sleep(0)
        try:
            await self._rebuild_logs_query_cache_in_thread_if_needed()
            self._refresh_logs_view_core(should_render=False)
        finally:
            remaining = min_loading_seconds - (loop.time() - started)
            if remaining > 0:
                await asyncio.sleep(remaining)
            self.logs_state["is_loading"] = False
            try:
                self.logs_view.render(self.logs_state)
            except RuntimeError:
                pass
            self._page.update()
            if self._logs_refresh_pending:
                self._logs_refresh_pending = False
                self.refresh_logs_view(show_loading=True)

    def on_logs_search_change(self, value: str):
        self.logs_state["search_text"] = value or ""
        self.logs_state["current_page"] = 1
        self.refresh_logs_view()

    def on_logs_level_change(self, value: str | None):
        self.logs_state["level_filter"] = value or "All"
        self.logs_state["current_page"] = 1
        self.refresh_logs_view()

    def on_logs_sort_column_change(self, value: str | None):
        if value and value in self.logs_state["columns"]:
            self.logs_state["sort_by"] = value
        self.logs_state["current_page"] = 1
        self.refresh_logs_view()

    def on_logs_toggle_sort_direction(self):
        self.logs_state["sort_desc"] = not self.logs_state["sort_desc"]
        self.logs_state["current_page"] = 1
        self.refresh_logs_view()

    def on_logs_page_size_change(self, value: str | None):
        try:
            self.logs_state["page_size"] = int(value or "100")
        except ValueError:
            self.logs_state["page_size"] = 100
        self.logs_state["current_page"] = 1
        self.refresh_logs_view()

    def on_logs_prev_page(self):
        self.logs_state["current_page"] = max(1, int(self.logs_state["current_page"]) - 1)
        self.refresh_logs_view()

    def on_logs_next_page(self):
        self.logs_state["current_page"] = min(
            int(self.logs_state["total_pages"]), int(self.logs_state["current_page"]) + 1
        )
        self.refresh_logs_view()

    def on_logs_toggle_column(self, column_name: str, is_visible: bool):
        current = list(self.logs_state.get("visible_columns_pending", []))
        if is_visible and column_name not in current:
            current.append(column_name)
        if not is_visible and column_name in current:
            current.remove(column_name)

        if not current and self.logs_state["columns"]:
            current = [self.logs_state["columns"][0]]

        self.logs_state["visible_columns_pending"] = current
        try:
            self.logs_view.refresh_column_selector(self.logs_state)
        except RuntimeError:
            pass

    def on_logs_toggle_column_selector(self):
        if not self.logs_state.get("columns"):
            return
        if bool(self.logs_state.get("is_loading", False)) or bool(self.logs_state.get("is_applying_columns", False)):
            return

        current = bool(self.logs_state.get("column_selector_expanded", False))
        next_state = not current
        self.logs_state["column_selector_expanded"] = next_state
        if next_state:
            self.logs_state["visible_columns_pending"] = list(self.logs_state.get("visible_columns", []))
        try:
            self.logs_view.refresh_column_selector(self.logs_state)
        except RuntimeError:
            pass

    def on_logs_apply_columns(self):
        columns = list(self.logs_state.get("columns", []))
        if not columns:
            return
        if bool(self.logs_state.get("is_applying_columns", False)):
            return

        pending = [c for c in self.logs_state.get("visible_columns_pending", []) if c in columns]
        if not pending:
            pending = [columns[0]]

        self.logs_state["visible_columns_pending"] = pending
        self.logs_state["is_applying_columns"] = True

        try:
            self.logs_view.refresh_column_selector(self.logs_state)
        except RuntimeError:
            pass
        self._page.update()

        try:
            asyncio.get_running_loop().create_task(self._apply_columns_deferred(list(pending)))
        except RuntimeError:
            self._apply_columns_sync(list(pending))

    async def _apply_columns_deferred(self, pending: list[str]):
        # Cede el control para que Flet pinte el estado "Aplicando..." antes del trabajo de UI.
        await asyncio.sleep(0)
        self._apply_columns_sync(pending)

    def _apply_columns_sync(self, pending: list[str]):
        try:
            self.logs_state["visible_columns"] = list(pending)
            # Cambiar columnas visibles no altera filtros, orden ni pagina.
            # Evitamos recomputo pesado y solo repintamos la tabla actual.
            self._persist_logs_preferences_if_needed()
            self.logs_view.refresh_table_only(self.logs_state)
        finally:
            self.logs_state["is_applying_columns"] = False
            # Colapsar al finalizar para que el usuario vea el estado "Aplicando..." mientras corre.
            self.logs_state["column_selector_expanded"] = False
            try:
                self.logs_view.refresh_column_selector(self.logs_state)
            except RuntimeError:
                pass

    # ===== Watcher handlers =====

    def on_logs_watch_folder_change(self, value: str):
        self.logs_state["watch_folder"] = (value or "").strip()
        self._persist_logs_preferences_if_needed()

    def on_logs_watch_pattern_change(self, value: str):
        self.logs_state["watch_pattern"] = (value or "").strip()
        self._persist_logs_preferences_if_needed()

    def _is_view_following_live(self) -> bool:
        """True si la vista esta en modo 'seguir el flujo': pagina 1 sin filtros activos."""
        if int(self.logs_state.get("current_page", 1)) != 1:
            return False
        if (self.logs_state.get("search_text") or "").strip():
            return False
        if (self.logs_state.get("level_filter") or "All") != "All":
            return False
        return True

    def _watcher_on_batch_threadsafe(self, file_path: str, rows: list, levels: list, columns: list):
        """Callback invocado desde el hilo del watcher. Acumula y NO toca la UI."""
        try:
            self._log_buffer.set_columns(columns)
            self._log_buffer.extend(rows, levels)
            with self._watcher_pending_lock:
                self._watcher_pending_batches.append((rows, levels, columns))
        except Exception:
            logger.exception("[WATCHER] Error en callback batch")

    def _watcher_on_status_threadsafe(self, status: dict):
        with self._watcher_pending_lock:
            self._watcher_pending_batches.append(("__status__", status))  # type: ignore[arg-type]

    def _watcher_on_file_changed_threadsafe(self, file_path: str):
        with self._watcher_pending_lock:
            self._watcher_pending_batches.append(("__file_changed__", file_path))  # type: ignore[arg-type]

    async def _watcher_drain_loop(self):
        """Drena los lotes acumulados por el watcher y refresca la UI con coalescing."""
        REFRESH_MS = 250
        try:
            while self._watcher is not None and self._watcher.is_running():
                await asyncio.sleep(REFRESH_MS / 1000.0)
                with self._watcher_pending_lock:
                    pending = self._watcher_pending_batches
                    self._watcher_pending_batches = []

                if not pending:
                    self._update_lines_per_sec(0)
                    continue

                total_new_rows = 0
                columns_seen: list[str] = []
                file_changed: str | None = None
                for item in pending:
                    if isinstance(item, tuple) and len(item) == 2 and item[0] == "__status__":
                        status = item[1] or {}
                        if isinstance(status, dict):
                            for k, v in status.items():
                                if k == "watch_error":
                                    self.logs_state["watch_error"] = v
                        continue
                    if isinstance(item, tuple) and len(item) == 2 and item[0] == "__file_changed__":
                        file_changed = str(item[1])
                        continue
                    if isinstance(item, tuple) and len(item) == 3:
                        rows, _levels, columns = item
                        total_new_rows += len(rows)
                        if columns and not columns_seen:
                            columns_seen = list(columns)

                if file_changed:
                    self.logs_state["file_path"] = file_changed
                    self.logs_state["file_label"] = f"En vivo: {Path(file_changed).name}"

                snap_rows, snap_columns, snap_levels, buf_size, _total = self._log_buffer.snapshot()
                if snap_columns and self.logs_state.get("columns") != snap_columns:
                    self.logs_state["columns"] = snap_columns
                    visible = [c for c in self.logs_state.get("visible_columns", []) if c in snap_columns]
                    if not visible:
                        visible = list(snap_columns)
                    self.logs_state["visible_columns"] = visible
                    self.logs_state["visible_columns_pending"] = list(visible)
                self.logs_state["level_options"] = ["All"] + snap_levels
                self.logs_state["buffer_count"] = buf_size
                self.logs_state["buffer_max"] = self._log_buffer.maxlen
                self._update_lines_per_sec(total_new_rows)

                following = self._is_view_following_live()
                if following and total_new_rows > 0:
                    self.logs_rows = snap_rows
                    self._invalidate_logs_query_cache()
                    self.logs_state["pending_new_count"] = 0
                    self._refresh_logs_view_core(should_render=True)
                else:
                    self.logs_state["pending_new_count"] = int(self.logs_state.get("pending_new_count", 0)) + total_new_rows
                    try:
                        self.logs_view.render(self.logs_state)
                    except RuntimeError:
                        pass
                    self._page.update()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[WATCHER] Drain loop error")

    def _update_lines_per_sec(self, new_count: int):
        import time as _time
        now = _time.monotonic()
        if new_count > 0:
            self._watcher_lines_window.append((now, new_count))
        cutoff = now - 5.0
        self._watcher_lines_window = [(t, c) for t, c in self._watcher_lines_window if t >= cutoff]
        total = sum(c for _, c in self._watcher_lines_window)
        self.logs_state["lines_per_sec"] = total / 5.0

    def on_logs_show_pending_new(self):
        """Forzar consumo del buffer y reset de filtros que estan ocultando lo nuevo."""
        self.logs_state["current_page"] = 1
        snap_rows, snap_columns, snap_levels, buf_size, _ = self._log_buffer.snapshot()
        if snap_columns:
            self.logs_state["columns"] = snap_columns
            visible = [c for c in self.logs_state.get("visible_columns", []) if c in snap_columns]
            if not visible:
                visible = list(snap_columns)
            self.logs_state["visible_columns"] = visible
            self.logs_state["visible_columns_pending"] = list(visible)
        self.logs_state["level_options"] = ["All"] + snap_levels
        self.logs_state["buffer_count"] = buf_size
        self.logs_state["pending_new_count"] = 0
        self.logs_rows = snap_rows
        self._invalidate_logs_query_cache()
        self.refresh_logs_view()

    def on_logs_toggle_watch(self):
        if self.logs_state.get("is_watching", False):
            self._stop_watcher()
        else:
            self._start_watcher()

    def _start_watcher(self):
        folder = (self.logs_state.get("watch_folder") or "").strip()
        pattern = (self.logs_state.get("watch_pattern") or r".+\.log$").strip()
        if not folder:
            self._page.open(ft.SnackBar(ft.Text("Indica una carpeta para vigilar.")))
            self._page.update()
            return
        if not Path(folder).is_dir():
            self.logs_state["watch_error"] = "La carpeta no existe o no es accesible."
            try:
                self.logs_view.render(self.logs_state)
            except RuntimeError:
                pass
            self._page.update()
            return

        # Resetea estado de carga manual previa.
        self._log_buffer = LifoLogBuffer(maxlen=self.logs_state.get("buffer_max", 100_000))
        self.logs_rows = []
        self._invalidate_logs_query_cache()
        self.logs_state.update({
            "is_watching": True,
            "watch_error": "",
            "pending_new_count": 0,
            "buffer_count": 0,
            "lines_per_sec": 0.0,
            "current_page": 1,
            "file_label": "Esperando primer fichero...",
        })
        self._persist_logs_preferences_if_needed()

        try:
            self._watcher = LogWatcher(
                folder=folder,
                pattern=pattern,
                on_batch=self._watcher_on_batch_threadsafe,
                on_status=self._watcher_on_status_threadsafe,
                on_file_changed=self._watcher_on_file_changed_threadsafe,
                start_from_end_for_current=True,
            )
        except ValueError as e:
            self.logs_state["is_watching"] = False
            self.logs_state["watch_error"] = str(e)
            try:
                self.logs_view.render(self.logs_state)
            except RuntimeError:
                pass
            self._page.update()
            return

        self._watcher.start()
        try:
            self._watcher_drain_task = asyncio.get_running_loop().create_task(self._watcher_drain_loop())
        except RuntimeError:
            self._watcher_drain_task = None

        try:
            self.logs_view.render(self.logs_state)
        except RuntimeError:
            pass
        self._page.update()

    def _stop_watcher(self):
        if self._watcher is not None:
            try:
                self._watcher.stop()
            except Exception:
                logger.exception("[WATCHER] Error al detener")
            self._watcher = None
        if self._watcher_drain_task is not None:
            self._watcher_drain_task.cancel()
            self._watcher_drain_task = None
        self.logs_state["is_watching"] = False
        self.logs_state["lines_per_sec"] = 0.0
        try:
            self.logs_view.render(self.logs_state)
        except RuntimeError:
            pass
        self._page.update()

    def on_logs_export_click(self):
        if not self.logs_state.get("file_path"):
            self._page.open(ft.SnackBar(ft.Text("Carga un archivo antes de exportar.")))
            self._page.update()
            return

        visible_columns = self.logs_state.get("visible_columns", [])
        if not visible_columns:
            self._page.open(ft.SnackBar(ft.Text("No hay columnas visibles para exportar.")))
            self._page.update()
            return

        rows_to_export, _, _, _ = apply_filters_sort_paginate(
            self.logs_rows,
            self.logs_state["columns"],
            self.logs_state["search_text"],
            self.logs_state["level_filter"],
            self.logs_state["sort_by"],
            self.logs_state["sort_desc"],
            1,
            max(len(self.logs_rows), 1),
        )

        source = Path(str(self.logs_state["file_path"]))
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        export_file = source.with_name(f"{source.stem}-filtered-{timestamp}.csv")
        output_path = export_rows_to_csv(str(export_file), visible_columns, rows_to_export)
        self._page.open(ft.SnackBar(ft.Text(f"CSV exportado: {output_path}")))
        self._page.update()

    def on_logs_open_message_detail(self, message_text: str, column_name: str = "Message"):
        self.logs_state["message_dialog_open"] = True
        self.logs_state["message_dialog_text"] = message_text or ""
        self.logs_state["message_dialog_title"] = f"{column_name} completo"
        title_text = self.logs_message_dialog_title.controls[1]
        if isinstance(title_text, ft.Text):
            title_text.value = self.logs_state["message_dialog_title"]
        self.logs_message_dialog_body.value = self.logs_state["message_dialog_text"]
        line_count = self.logs_state["message_dialog_text"].count("\n") + (1 if self.logs_state["message_dialog_text"] else 0)
        char_count = len(self.logs_state["message_dialog_text"])
        self.logs_message_dialog_meta.value = f"{line_count} lineas · {char_count} caracteres"

        DialogSizer.fit_container(
            self._page,
            self.logs_message_dialog_container,
            width_ratio=0.88,
            min_width=480,
            max_width=1100,
            height_ratio=0.70,
            min_height=300,
            max_height=760,
        )

        if self.logs_message_dialog not in self._page.overlay:
            self._page.overlay.append(self.logs_message_dialog)
        self.logs_message_dialog.open = True
        self._page.update()

    def on_logs_close_message_detail(self, e=None):
        if not bool(self.logs_state.get("message_dialog_open", False)):
            return
        self.logs_state["message_dialog_open"] = False
        self.logs_message_dialog.open = False
        self._page.update()

    def on_logs_copy_message_detail(self, e=None):
        message_text = str(self.logs_state.get("message_dialog_text", ""))
        if not message_text:
            self._page.open(ft.SnackBar(ft.Text("No hay texto para copiar.")))
            self._page.update()
            return

        self._page.set_clipboard(message_text)
        self._page.open(ft.SnackBar(ft.Text("Mensaje copiado al portapapeles.")))
        self._page.update()

    def login(self, e):
        def close_dlg(e):
            if user_name.value == "" or password.value == "":
                user_name.error_text = "Please provide username"
                password.error_text = "Please provide password"
                self._page.update()
                return
            else:
                user = User(user_name.value, password.value)
                if user not in self.store.get_users():
                    self.store.add_user(user)
                self.user = user_name.value
                self._storage_set("current_user", user_name.value)

            self._page.close(dialog)
            self.appbar_items[0] = ft.PopupMenuItem(
                content=f"{self._storage_get('current_user', '')}'s Profile"
            )
            self._page.update()

        user_name = ft.TextField(label="User name")
        password = ft.TextField(label="Password", password=True)
        dialog = ft.AlertDialog(
            title=ft.Text("Please enter your login credentials"),
            content=ft.Column(
                [
                    user_name,
                    password,
                    ft.Button("Login", on_click=close_dlg),
                ],
                tight=True,
            ),
            on_dismiss=lambda e: logger.debug("Modal dialog dismissed!"),
        )
        self._page.open(dialog)

    def route_change(self, e):
        troute = ft.TemplateRoute(self._page.route)
        if troute.match("/"):
            self.set_all_boards_view()
        elif troute.match("/board/:id"):
            if int(troute.id) >= len(self.store.get_boards()): # type: ignore
                self.set_all_boards_view()
                return
            self.set_board_view(int(troute.id)) # type: ignore
        elif troute.match("/boards"):
            self.set_all_boards_view()
        elif troute.match("/members"):
            self.set_members_view()
        elif troute.match("/logs"):
            self.set_logs_view()
            self.refresh_logs_view()
        self._page.update()

    def add_board(self, e):
        def close_dlg(e):
            if (hasattr(e.control, "text") and not e.control.text == "Cancel") or (
                type(e.control) is ft.TextField and e.control.value != ""
            ):
                self.create_new_board(dialog_text.value)
            self._page.close(dialog)
            self._page.update()

        def textfield_change(e):
            if dialog_text.value == "":
                create_button.disabled = True
            else:
                create_button.disabled = False
            self._page.update()

        dialog_text = ft.TextField(
            label="New Board Name", on_submit=close_dlg, on_change=textfield_change
        )
        create_button = ft.Button(
            "Create", bgcolor=ft.Colors.BLUE_200, on_click=close_dlg, disabled=True
        )
        dialog = ft.AlertDialog(
            title=ft.Text("Name your new board"),
            content=ft.Column(
                [
                    dialog_text,
                    ft.Row(
                        [
                            ft.Button("Cancel", on_click=close_dlg),
                            create_button,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                tight=True,
            ),
            on_dismiss=lambda e: logger.debug("Modal dialog dismissed!"),
        )
        self._page.open(dialog)
        dialog.open = True
        self._page.update()
        dialog_text.focus()

    def create_new_board(self, board_name):
        new_board = Board(self, self.store, board_name, self._page)
        self.store.add_board(new_board)
        self.hydrate_all_boards_view()

    def delete_board(self, e):
        self.store.remove_board(e.control.data)
        self.set_all_boards_view()


def main(page: ft.Page):
    page.window_maximized = True  # Configura la ventana maximizada
    install_asyncio_exception_handler(logger)

    page.title = "Sharepoint ULS Log Viewer"
    page.padding = 0
    page.theme = ft.Theme(font_family="Verdana")
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme.page_transitions.windows = "cupertino" # type: ignore
    page.fonts = {"Pacifico": "Pacifico-Regular.ttf"}
    page.bgcolor = ft.Colors.BLUE_GREY_200    
    app = TrelloApp(page, InMemoryStore())
    app.initialize()


try:
    setup_logging()    
    install_global_exception_hooks(logger)

    flet_version = version("flet")
except PackageNotFoundError:
    flet_version = "unknown"

logger.info("flet version: %s", flet_version)
logger.info("flet path: %s", ft.__file__)
ft.run(main, assets_dir="../assets")
