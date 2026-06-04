"""
analytics_view.py
Dashboard de cobertura de reglas Smart Rules sobre el log ULS activo.

Muestra:
  - Tarjetas KPI: filas totales, cubiertas, % cobertura, reglas activas, dominios con match.
  - Gráfica de barras (top-N reglas por match count).
  - Gráfica de donut (cobertura vs no cobertura).
  - Chips por dominio con matches y porcentaje.

Requiere flet-charts para las gráficas nativas.
Si el paquete no está instalado muestra una versión de barras puras con ft.Container.
"""
from __future__ import annotations

import asyncio
import threading
from collections import defaultdict

import flet as ft

try:
    import flet_charts as fch

    _HAS_CHARTS = True
except ImportError:
    _HAS_CHARTS = False

from smart_rules import ALL_DOMAINS, DOMAIN_COLORS, rules_engine
from ui_tokens import (
    APP_BORDER,
    APP_SHELL_ACCENT,
    APP_SURFACE,
    APP_TEXT_MUTED,
    APP_TEXT_PRIMARY,
    surface_shadow,
)

_MAX_BAR_RULES: int = 20  # máximo de reglas mostradas en el bar chart


# ─────────────────────────────────────────────────────────────────────────────
# Funciones helper (module-level para mantener la clase liviana)
# ─────────────────────────────────────────────────────────────────────────────


def _kpi_card(label: str, value: str, subtitle: str = "", color: str = APP_SHELL_ACCENT) -> ft.Container:
    return ft.Container(
        width=155,
        padding=ft.padding.Padding(left=16, top=12, right=16, bottom=12),
        bgcolor=APP_SURFACE,
        border_radius=ft.BorderRadius(12, 12, 12, 12),
        shadow=surface_shadow(offset_y=4, blur_radius=14),
        content=ft.Column(
            [
                ft.Text(label, size=9, color=APP_TEXT_MUTED, weight=ft.FontWeight.W_500),
                ft.Text(value, size=24, weight=ft.FontWeight.W_700, color=color),
                ft.Text(subtitle, size=9, color=APP_TEXT_MUTED)
                if subtitle
                else ft.Container(height=0),
            ],
            spacing=2,
            tight=True,
        ),
    )


def _compute_stats(rows: list[dict[str, str]]) -> dict:
    """Ejecuta el motor de reglas para todos los dominios. Seguro desde hilo secundario."""
    rule_hits: dict[str, int] = {}
    rule_domain: dict[str, str] = {}
    covered_indices: set[int] = set()
    domain_covered: dict[str, set[int]] = defaultdict(set)

    for domain in ALL_DOMAINS:
        matches = rules_engine.apply(rows, domain)
        for idx, rules_list in matches.items():
            covered_indices.add(idx)
            domain_covered[domain].add(idx)
            for r in rules_list:
                rule_hits[r.name] = rule_hits.get(r.name, 0) + 1
                rule_domain.setdefault(r.name, domain)

    domain_hits = {d: len(idxs) for d, idxs in domain_covered.items()}
    top_rules = sorted(rule_hits.items(), key=lambda x: x[1], reverse=True)[:_MAX_BAR_RULES]

    return {
        "total": len(rows),
        "covered": len(covered_indices),
        "rule_hits": rule_hits,
        "rule_domain": rule_domain,
        "top_rules": top_rules,
        "domain_hits": domain_hits,
    }


def _build_bar_chart(
    top_rules: list[tuple[str, int]], rule_domain: dict[str, str]
) -> ft.Control:
    """BarChart con flet_charts."""
    max_val = top_rules[0][1] if top_rules else 1
    groups: list = []
    bottom_labels: list = []

    for i, (name, count) in enumerate(top_rules):
        domain = rule_domain.get(name, "")
        color = DOMAIN_COLORS.get(domain, APP_SHELL_ACCENT)
        short = name.split(":", 1)[-1].strip()[:22]
        groups.append(
            fch.BarChartGroup(
                x=i,
                rods=[
                    fch.BarChartRod(
                        from_y=0,
                        to_y=float(count),
                        width=16,
                        color=color,
                        border_radius=ft.BorderRadius(4, 4, 0, 0),
                    )
                ],
            )
        )
        bottom_labels.append(
            fch.ChartAxisLabel(
                value=i,
                label=ft.Container(
                    content=ft.Text(short, size=8, color=APP_TEXT_MUTED, no_wrap=True),
                    rotate=ft.Rotate(angle=0.5),
                    width=80,
                ),
            )
        )

    return ft.Column(
        [
            ft.Text(
                "Top reglas por matches",
                size=12,
                weight=ft.FontWeight.W_600,
                color=APP_TEXT_PRIMARY,
            ),
            ft.Container(
                height=260,
                content=fch.BarChart(
                    expand=True,
                    interactive=True,
                    min_y=0,
                    max_y=float(max_val) * 1.2,
                    groups=groups,
                    border=ft.Border.all(1, APP_BORDER),
                    horizontal_grid_lines=fch.ChartGridLines(
                        color=APP_BORDER, width=1, dash_pattern=[4, 4]
                    ),
                    left_axis=fch.ChartAxis(label_size=40),
                    bottom_axis=fch.ChartAxis(labels=bottom_labels, label_size=70),
                ),
            ),
        ],
        spacing=8,
        tight=True,
        expand=True,
    )


def _build_bar_fallback(
    top_rules: list[tuple[str, int]], rule_domain: dict[str, str]
) -> ft.Control:
    """Barras horizontales puras con ft.Container (sin flet_charts)."""
    max_val = top_rules[0][1] if top_rules else 1
    bar_rows: list[ft.Control] = []
    for name, count in top_rules:
        domain = rule_domain.get(name, "")
        color = DOMAIN_COLORS.get(domain, APP_SHELL_ACCENT)
        short = name.split(":", 1)[-1].strip()
        bar_w = max(4, int(count / max_val * 220))
        bar_rows.append(
            ft.Row(
                [
                    ft.Container(
                        content=ft.Text(short, size=9, color=APP_TEXT_PRIMARY, no_wrap=True),
                        width=145,
                    ),
                    ft.Container(
                        bgcolor=color,
                        width=bar_w,
                        height=11,
                        border_radius=ft.BorderRadius(3, 3, 3, 3),
                    ),
                    ft.Text(f"{count:,}", size=9, color=APP_TEXT_MUTED),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    return ft.Column(
        [
            ft.Text(
                "Top reglas por matches",
                size=12,
                weight=ft.FontWeight.W_600,
                color=APP_TEXT_PRIMARY,
            ),
            *bar_rows,
        ],
        spacing=3,
        scroll=ft.ScrollMode.AUTO,
        tight=True,
    )


def _build_pie_chart(covered: int, not_covered: int, total: int) -> ft.Control:
    """Donut PieChart con flet_charts."""
    pct = round(covered / total * 100, 1)
    return ft.Column(
        [
            ft.Text(
                "Cobertura global",
                size=12,
                weight=ft.FontWeight.W_600,
                color=APP_TEXT_PRIMARY,
            ),
            ft.Container(
                height=180,
                content=fch.PieChart(
                    expand=True,
                    sections_space=2,
                    center_space_radius=44,
                    sections=[
                        fch.PieChartSection(
                            value=float(covered),
                            color=APP_SHELL_ACCENT,
                            radius=56,
                            title=f"{pct}%",
                            title_style=ft.TextStyle(
                                size=11,
                                color="#FFFFFF",
                                weight=ft.FontWeight.W_700,
                            ),
                        ),
                        fch.PieChartSection(
                            value=float(not_covered),
                            color="#D6DEE8",
                            radius=48,
                            title="",
                        ),
                    ],
                ),
            ),
            ft.Row(
                [
                    ft.Container(
                        bgcolor=APP_SHELL_ACCENT,
                        width=9,
                        height=9,
                        border_radius=ft.BorderRadius(2, 2, 2, 2),
                    ),
                    ft.Text(f"Cubiertas: {covered:,}", size=9, color=APP_TEXT_MUTED),
                ],
                spacing=4,
            ),
            ft.Row(
                [
                    ft.Container(
                        bgcolor="#D6DEE8",
                        width=9,
                        height=9,
                        border_radius=ft.BorderRadius(2, 2, 2, 2),
                    ),
                    ft.Text(f"No cubiertas: {not_covered:,}", size=9, color=APP_TEXT_MUTED),
                ],
                spacing=4,
            ),
        ],
        spacing=8,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _build_pie_fallback(covered: int, not_covered: int, total: int) -> ft.Control:
    """ProgressBar + texto (sin flet_charts)."""
    pct = round(covered / total * 100, 1)
    return ft.Column(
        [
            ft.Text(
                "Cobertura global",
                size=12,
                weight=ft.FontWeight.W_600,
                color=APP_TEXT_PRIMARY,
            ),
            ft.Text(
                f"{pct} %",
                size=30,
                weight=ft.FontWeight.W_700,
                color=APP_SHELL_ACCENT,
            ),
            ft.ProgressBar(
                value=covered / total,
                bgcolor=APP_BORDER,
                color=APP_SHELL_ACCENT,
                height=10,
                border_radius=ft.BorderRadius(5, 5, 5, 5),
            ),
            ft.Row(
                [
                    ft.Container(
                        bgcolor=APP_SHELL_ACCENT,
                        width=9,
                        height=9,
                        border_radius=ft.BorderRadius(2, 2, 2, 2),
                    ),
                    ft.Text(f"Cubiertas: {covered:,}", size=9, color=APP_TEXT_MUTED),
                ],
                spacing=4,
            ),
            ft.Row(
                [
                    ft.Container(
                        bgcolor=APP_BORDER,
                        width=9,
                        height=9,
                        border_radius=ft.BorderRadius(2, 2, 2, 2),
                    ),
                    ft.Text(f"No cubiertas: {not_covered:,}", size=9, color=APP_TEXT_MUTED),
                ],
                spacing=4,
            ),
        ],
        spacing=6,
        tight=True,
    )


def _build_domain_chips(domain_hits: dict[str, int], total: int) -> list[ft.Control]:
    chips: list[ft.Control] = []
    for domain in ALL_DOMAINS:
        count = domain_hits.get(domain, 0)
        color = DOMAIN_COLORS.get(domain, APP_SHELL_ACCENT)
        pct = round(count / total * 100, 1) if total else 0.0
        border_color = color if count else APP_BORDER
        chips.append(
            ft.Container(
                padding=ft.padding.Padding(left=10, top=6, right=10, bottom=6),
                bgcolor=APP_SURFACE,
                border=ft.Border.all(2, border_color),
                border_radius=ft.BorderRadius(20, 20, 20, 20),
                content=ft.Row(
                    [
                        ft.Container(
                            bgcolor=color,
                            width=9,
                            height=9,
                            border_radius=ft.BorderRadius(5, 5, 5, 5),
                        ),
                        ft.Text(
                            domain,
                            size=10,
                            color=APP_TEXT_PRIMARY,
                            weight=ft.FontWeight.W_500,
                        ),
                        ft.Text(
                            f"{count:,}  ({pct} %)",
                            size=10,
                            color=APP_TEXT_MUTED,
                        ),
                    ],
                    spacing=5,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )
        )
    return chips


# ─────────────────────────────────────────────────────────────────────────────
# Vista principal
# ─────────────────────────────────────────────────────────────────────────────


class AnalyticsView(ft.Column):
    """Vista dashboard de cobertura de Smart Rules sobre el log activo."""

    def __init__(self, app) -> None:
        super().__init__(
            expand=True,
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            scroll=ft.ScrollMode.AUTO,
        )
        self.app = app
        self._computing: bool = False
        self._last_row_count: int = -1

        # ── Slots de UI actualizables ─────────────────────────────────────────
        self._kpi_row = ft.Row(spacing=12, wrap=True)
        self._spinner = ft.Container(
            visible=False,
            padding=ft.padding.Padding(left=0, top=0, right=10, bottom=0),
            content=ft.Row(
                [
                    ft.ProgressRing(
                        width=18, height=18, stroke_width=2.5, color=APP_SHELL_ACCENT
                    ),
                    ft.Text("Analizando…", color=APP_TEXT_MUTED, size=11),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        self._no_data_banner = ft.Container(
            visible=True,
            padding=ft.padding.Padding(left=24, top=18, right=24, bottom=0),
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.INFO_OUTLINE, color=APP_TEXT_MUTED, size=18),
                    ft.Text(
                        "Carga un archivo de log para ver el dashboard de cobertura.",
                        color=APP_TEXT_MUTED,
                        size=12,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        self._bar_panel = ft.Container(
            expand=True,
            bgcolor=APP_SURFACE,
            border_radius=ft.BorderRadius(12, 12, 12, 12),
            padding=ft.padding.Padding(left=16, top=14, right=16, bottom=14),
            shadow=surface_shadow(offset_y=4, blur_radius=14),
            content=ft.Text("Sin datos", color=APP_TEXT_MUTED, size=12),
        )
        self._pie_panel = ft.Container(
            width=230,
            bgcolor=APP_SURFACE,
            border_radius=ft.BorderRadius(12, 12, 12, 12),
            padding=ft.padding.Padding(left=14, top=14, right=14, bottom=14),
            shadow=surface_shadow(offset_y=4, blur_radius=14),
            content=ft.Text("Sin datos", color=APP_TEXT_MUTED, size=12),
        )
        self._domain_row = ft.Row(spacing=8, wrap=True)

        self.controls = self._build_skeleton()

    # ── Esqueleto de la vista ─────────────────────────────────────────────────

    def _build_skeleton(self) -> list[ft.Control]:
        extra: list[ft.Control] = []
        if not _HAS_CHARTS:
            extra = [
                ft.Container(
                    padding=ft.padding.Padding(left=24, top=2, right=24, bottom=4),
                    content=ft.Text(
                        "Instala flet-charts para ver las gráficas: pip install flet-charts",
                        color=APP_TEXT_MUTED,
                        size=10,
                        italic=True,
                    ),
                )
            ]
        return [
            # ── Header ───────────────────────────────────────────────────────
            ft.Container(
                content=ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(
                                    "Dashboard de cobertura",
                                    size=17,
                                    weight=ft.FontWeight.W_700,
                                    color=APP_TEXT_PRIMARY,
                                ),
                                ft.Text(
                                    "Cobertura de reglas Smart Rules sobre el log cargado",
                                    size=11,
                                    color=APP_TEXT_MUTED,
                                ),
                            ],
                            spacing=2,
                            tight=True,
                        ),
                        ft.Row(
                            [
                                self._spinner,
                                ft.FilledTonalButton(
                                    "Actualizar",
                                    icon=ft.Icons.REFRESH,
                                    on_click=self._on_refresh,
                                ),
                            ],
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.padding.Padding(left=24, top=16, right=24, bottom=10),
            ),
            # ── Divisor ───────────────────────────────────────────────────────
            ft.Container(
                bgcolor=APP_BORDER,
                height=1,
                margin=ft.margin.Margin(left=24, top=0, right=24, bottom=0),
            ),
            # ── Sin datos ─────────────────────────────────────────────────────
            self._no_data_banner,
            # ── KPI cards ─────────────────────────────────────────────────────
            ft.Container(
                content=self._kpi_row,
                padding=ft.padding.Padding(left=24, top=14, right=24, bottom=0),
            ),
            # ── Charts row ────────────────────────────────────────────────────
            ft.Container(
                content=ft.Row(
                    [self._bar_panel, self._pie_panel],
                    spacing=14,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                padding=ft.padding.Padding(left=24, top=12, right=24, bottom=0),
            ),
            # ── Domain chips ──────────────────────────────────────────────────
            ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Cobertura por dominio",
                            size=11,
                            weight=ft.FontWeight.W_600,
                            color=APP_TEXT_PRIMARY,
                        ),
                        self._domain_row,
                    ],
                    spacing=6,
                    tight=True,
                ),
                padding=ft.padding.Padding(left=24, top=14, right=24, bottom=24),
            ),
            *extra,
        ]

    # ── API pública ───────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Lanza el cómputo si hay filas cargadas. Llamado al navegar a /analytics."""
        rows: list[dict[str, str]] = getattr(self.app, "logs_rows", [])
        if not rows:
            self._show_no_data()
            return
        if len(rows) == self._last_row_count and not self._computing:
            return  # datos sin cambios, evitar recomputo redundante
        self._start_compute(list(rows))  # copia defensiva

    # ── Callbacks de UI ──────────────────────────────────────────────────────

    def _on_refresh(self, e) -> None:
        self._last_row_count = -1  # fuerza recomputo
        self.refresh()

    # ── Estado "sin datos" ────────────────────────────────────────────────────

    def _show_no_data(self) -> None:
        self._no_data_banner.visible = True
        self._kpi_row.controls = []
        self._bar_panel.content = ft.Text("Sin datos", color=APP_TEXT_MUTED, size=12)
        self._pie_panel.content = ft.Text("Sin datos", color=APP_TEXT_MUTED, size=12)
        self._domain_row.controls = []
        try:
            self.app._page.update()
        except Exception:
            pass

    # ── Cómputo en hilo secundario ────────────────────────────────────────────

    def _start_compute(self, rows: list[dict[str, str]]) -> None:
        if self._computing:
            return
        self._computing = True
        self._spinner.visible = True
        self._no_data_banner.visible = False
        # Capturar el event loop ANTES de lanzar el hilo.
        # page.update() desde un threading.Thread nativo no garantiza repaint en Flet;
        # call_soon_threadsafe programa la llamada en el loop de asyncio donde sí se pinta.
        try:
            _loop = asyncio.get_running_loop()
        except RuntimeError:
            _loop = None
        try:
            self.app._page.update()
        except Exception:
            pass

        def _safe_update() -> None:
            try:
                if _loop is not None:
                    _loop.call_soon_threadsafe(self.app._page.update)
                else:
                    self.app._page.update()
            except Exception:
                pass

        def _work() -> None:
            try:
                stats = _compute_stats(rows)
                self._apply_stats(stats, len(rows))
            except Exception:
                self._computing = False
                self._spinner.visible = False
                _safe_update()
                return
            _safe_update()

        threading.Thread(target=_work, daemon=True).start()

    def _apply_stats(self, stats: dict, total: int) -> None:
        """Aplica los resultados del cómputo a los slots de UI. Llamado desde hilo secundario."""
        covered: int = stats["covered"]
        not_covered: int = total - covered
        pct: float = round(covered / total * 100, 1) if total else 0.0
        n_active: int = sum(1 for r in rules_engine.get_rules() if r.enabled)

        # KPI cards
        self._kpi_row.controls = [
            _kpi_card("Filas cargadas", f"{total:,}", color=APP_TEXT_PRIMARY),
            _kpi_card("Filas cubiertas", f"{covered:,}", color=APP_SHELL_ACCENT),
            _kpi_card(
                "Cobertura",
                f"{pct} %",
                subtitle="del total de filas",
                color="#2E7D32" if pct >= 10 else APP_TEXT_MUTED,
            ),
            _kpi_card("Reglas activas", str(n_active), color=APP_TEXT_PRIMARY),
            _kpi_card(
                "Dominios con match",
                str(len(stats["domain_hits"])),
                color="#B71C1C",
            ),
        ]

        # Bar chart
        top_rules: list[tuple[str, int]] = stats["top_rules"]
        rule_domain: dict[str, str] = stats["rule_domain"]
        if top_rules:
            if _HAS_CHARTS:
                self._bar_panel.content = _build_bar_chart(top_rules, rule_domain)
            else:
                self._bar_panel.content = _build_bar_fallback(top_rules, rule_domain)
        else:
            self._bar_panel.content = ft.Column(
                [
                    ft.Icon(ft.Icons.SEARCH_OFF, color=APP_TEXT_MUTED, size=28),
                    ft.Text(
                        "Ninguna regla hizo match en este log.",
                        color=APP_TEXT_MUTED,
                        size=12,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            )

        # Pie / donut
        if total > 0:
            if _HAS_CHARTS:
                self._pie_panel.content = _build_pie_chart(covered, not_covered, total)
            else:
                self._pie_panel.content = _build_pie_fallback(covered, not_covered, total)
        else:
            self._pie_panel.content = ft.Text("Sin datos", color=APP_TEXT_MUTED, size=12)

        # Domain chips
        self._domain_row.controls = _build_domain_chips(stats["domain_hits"], total)

        # Estado final
        self._spinner.visible = False
        self._no_data_banner.visible = False
        self._last_row_count = total
        self._computing = False
        # El page.update() lo realiza _work vía _safe_update() con call_soon_threadsafe.
