"""LogsDetailMixin — diálogo de detalle de mensaje y copia al portapapeles.

Extraído de TrelloApp en main.py.
"""
import asyncio
import inspect
import logging

import flet as ft

from dialog import DialogSizer
from log_service import col_names

logger = logging.getLogger("trolli")


class LogsDetailMixin:

    def _on_clipboard_task_done(self, task: asyncio.Task):
        try:
            task.result()
        except Exception:
            logger.debug("[CLIP] set async fallo", exc_info=True)

    # ------------------------------------------------------------------
    # Diálogo de detalle de mensaje
    # ------------------------------------------------------------------

    def on_logs_open_message_detail(self, row: dict, visible_columns: list):
        self.logs_state["message_dialog_open"] = True
        self.logs_state["message_dialog_row"] = row
        self.logs_state["message_dialog_columns"] = visible_columns
        # visible_columns puede ser list[ColumnSpec] o list[str]; normalizar
        col_name_list = col_names(visible_columns)

        DialogSizer.fit_container(
            self._page,
            self.logs_message_dialog_container,
            width_ratio=0.88,
            min_width=480,
            max_width=1100,
            height_ratio=0.75,
            min_height=300,
            max_height=800,
        )

        container_width = self.logs_message_dialog_container.width
        if not isinstance(container_width, (int, float)):
            container_width = 860
        detail_field_width = max(320, int(container_width) - 24)

        # Reconstruir el contenido dinámico: un bloque por cada columna visible.
        self.logs_message_dialog_content.controls.clear()
        for col in col_name_list:
            value = str(row.get(col, ""))
            is_message = col.strip().lower() == "message"
            self.logs_message_dialog_content.controls.append(
                ft.Container(
                    width=detail_field_width,
                    content=ft.Column(
                        [
                            ft.Text(
                                col,
                                size=11,
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.BLUE_GREY_700,
                            ),
                            ft.TextField(
                                value=value,
                                width=detail_field_width,
                                min_lines=8 if is_message else 2,
                                read_only=True,
                                multiline=True,
                                border=ft.InputBorder.NONE,
                                dense=True,
                                content_padding=ft.padding.Padding(left=0, top=2, right=0, bottom=2),
                            ),
                            ft.Divider(height=1, thickness=1, color=ft.Colors.BLUE_GREY_50),
                        ],
                        spacing=0,
                    ),
                )
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

    # ------------------------------------------------------------------
    # Portapapeles
    # ------------------------------------------------------------------

    def _copy_to_clipboard(self, text: str) -> bool:
        """Copia ``text`` al portapapeles tolerando varias APIs de Flet.

        Flet 0.80+ expone `ft.Clipboard` como servicio (`page.services`) y se
        usa con `page.clipboard.set(value)`. Algunas versiones intermedias
        siguen aceptando `page.set_clipboard(value)`. Probamos en cascada y
        logueamos el error si ninguna funciona.
        """
        if text is None:
            text = ""

        def _invoke(candidate) -> bool:
            if not callable(candidate):
                return False
            try:
                result = candidate(text)
                if inspect.isawaitable(result):
                    try:
                        task = asyncio.get_running_loop().create_task(result)
                        task.add_done_callback(self._on_clipboard_task_done)
                        return True
                    except RuntimeError:
                        if inspect.iscoroutine(result):
                            result.close()
                        logger.debug("[CLIP] setter async omitido sin loop activo")
                        return False
                return True
            except Exception as exc:  # noqa: BLE001
                logger.debug("[CLIP] setter fallo: %s", exc)
                return False

        # 1) Servicio Clipboard explicitamente registrado.
        clip = getattr(self, "_clipboard", None)
        if clip is not None and _invoke(getattr(clip, "set", None)):
            return True

        # 2) page.clipboard.set (atajo cuando el servicio esta registrado).
        page_clip = getattr(self._page, "clipboard", None)
        if page_clip is not None and _invoke(getattr(page_clip, "set", None)):
            return True

        # 3) API antigua page.set_clipboard.
        legacy = getattr(self._page, "set_clipboard", None)
        if _invoke(legacy):
            return True

        logger.warning("[CLIP] No se pudo copiar al portapapeles (ninguna API disponible).")
        return False

    def on_logs_copy_message_detail(self, e=None):
        row = self.logs_state.get("message_dialog_row", {}) or {}
        if not row:
            self._show_snack_bar("No hay datos para copiar.")
            self._page.update()
            return

        # "Copiar todo" debe incluir TODOS los campos del registro, no solo las
        # columnas visibles. Se respeta primero el orden de las columnas conocidas
        # (`logs_state["columns"]`) y luego se agregan cualesquiera claves extra
        # que pueda traer la fila (ej. campos parseados no mapeados a columnas).
        all_columns = list(self.logs_state.get("columns", []) or [])
        ordered_keys: list[str] = []
        seen: set[str] = set()
        for col in all_columns:
            if col in row and col not in seen:
                ordered_keys.append(col)
                seen.add(col)
        for key in row.keys():
            if key not in seen:
                ordered_keys.append(key)
                seen.add(key)

        lines = [f"{col}: {row.get(col, '')}" for col in ordered_keys]
        text = "\n".join(lines)
        if self._copy_to_clipboard(text):
            self._show_snack_bar(f"Registro copiado al portapapeles ({len(ordered_keys)} campos).")
        else:
            self._show_snack_bar("No se pudo copiar el registro al portapapeles.")
        self._page.update()

    def on_logs_copy_row(self, row: dict, columns: list):
        """Copia la fila visible al portapapeles como TSV (cabecera + valores).

        Disparado por clic derecho sobre una DataRow2 en LogsView.
        """
        if not row or not columns:
            self._show_snack_bar("Fila vacia, nada que copiar.")
            self._page.update()
            return
        header = "\t".join(columns)
        values = "\t".join(str(row.get(c, "")).replace("\t", " ").replace("\n", " ") for c in columns)
        tsv = f"{header}\n{values}"
        if self._copy_to_clipboard(tsv):
            self._show_snack_bar("Fila copiada al portapapeles (TSV).")
        else:
            self._show_snack_bar("No se pudo copiar la fila al portapapeles.")
        self._page.update()
