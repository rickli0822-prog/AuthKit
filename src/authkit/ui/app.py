from __future__ import annotations

import json
import argparse
import re
import sys
import textwrap
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from authkit import __version__
from authkit.brand import APP_NAME, APP_TAGLINE_KEY, ICON_ICO, ICON_PNG_48
from authkit.checks.login import LoginStatus, check_login_status
from authkit.checks.network import probe_chatgpt_api
from authkit.checks.network_profile import collect_network_profile
from authkit.clients import CLIENT_LABELS
from authkit.core.diagnose import run_diagnosis
from authkit.core.scan import scan_installed_clients
from authkit.i18n import case_title, get_locale, init_locale, layer_name, locale_label, set_locale, t
from authkit.models import DiagnosisReport, FixAction
from authkit.platform.proxy import primary_env_proxy, read_env_proxy, read_system_proxy
from authkit.repair.actions import launch_codex_device_auth
from authkit.repair.audit import RepairAuditRecord, latest_rollbackable_record, load_audit_records
from authkit.repair.fixer import apply_auto_fixes, apply_fix, rollback_latest_repair, sync_proxy
from authkit.report import render_human, render_json
from authkit.ui.fonts import FontSet, resolve_fonts
from authkit.ui.theme import (
    Theme,
    apply_theme,
    attach_list_scrollbars,
    attach_tree_scrollbars,
    bind_mousewheel,
    make_scroll_text,
    set_text,
)

STATUS_KEYS = {
    "healthy": "status.healthy",
    "unhealthy": "status.unhealthy",
    "warning": "status.warning",
}

CLIENT_SEPARATOR = " - "
META_SEPARATOR = "  |  "
FIX_SEPARATOR = " - "
MIN_WINDOW_WIDTH = 1120
MIN_WINDOW_HEIGHT = 760
INITIAL_SCREEN_RATIO = 2 / 3
URL_RE = re.compile(r"https?://[^\s<>\"]+")
AUDIT_ROW_LIMIT = 80
URL_TRAILING_PUNCTUATION = ".,;:!?)]}，。；：！？）】》"


def _asset_path(name: str) -> Path:
    package_asset = Path(__file__).resolve().parents[1] / "assets" / name
    if package_asset.is_file():
        return package_asset
    return Path(__file__).resolve().parents[3] / "assets" / name


def _initial_window_geometry(*, screen_width: int, screen_height: int) -> tuple[int, int, int, int]:
    width = max(MIN_WINDOW_WIDTH, int(screen_width * INITIAL_SCREEN_RATIO))
    height = max(MIN_WINDOW_HEIGHT, int(screen_height * INITIAL_SCREEN_RATIO))
    width = min(width, screen_width)
    height = min(height, screen_height)
    x = max((screen_width - width) // 2, 0)
    y = max((screen_height - height) // 2, 0)
    return width, height, x, y


def _enable_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _format_gui_rollback_preview(record: RepairAuditRecord) -> str:
    changed = ", ".join(record.changed_keys) if record.changed_keys else "-"
    lines = [
        f"ID: {record.repair_id}",
        f"{t('audit.time')}: {record.timestamp}",
        f"{t('audit.client')}: {record.client or '-'}",
        f"{t('audit.action')}: {record.fix_id}",
        f"{t('audit.changed')}: {changed}",
        f"{t('audit.risk')}: {record.risk}",
        f"{t('audit.admin')}: {t('audit.yes') if record.admin_required else t('audit.no')}",
        f"{t('audit.restart')}: {t('audit.yes') if record.restart_required else t('audit.no')}",
        f"{t('audit.rollback')}: {t('audit.yes') if record.rollback_supported else t('audit.no')}",
    ]
    if record.message:
        lines.append(record.message)
    return "\n".join(lines)


class AuthKitApp(tk.Tk):
    def __init__(self) -> None:
        _enable_windows_dpi_awareness()
        super().__init__()
        init_locale()
        self.title(APP_NAME)
        self.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self._set_initial_window_geometry()
        self._window_icon_photo: tk.PhotoImage | None = None
        self._logo_photo: tk.PhotoImage | None = None
        self._side_logo_photo: tk.PhotoImage | None = None
        self._set_window_icon()
        self._report: DiagnosisReport | None = None
        self._reports: list[DiagnosisReport] = []
        self._report_by_item: dict[str, DiagnosisReport] = {}
        self._fix_actions: list[tuple[DiagnosisReport, FixAction]] = []
        self._analysis_generation = 0
        self._last_selected_client = "codex"
        self._busy = False
        self._busy_kind = ""
        self._busy_started_at: float | None = None
        self._busy_message = ""
        self._timer_after_id: str | None = None
        self._pulse_after_id: str | None = None
        self._pulse_index = 0
        self._fonts = resolve_fonts(self, get_locale())
        self._colors = Theme.COLORS
        self._sections: dict[str, ttk.Labelframe] = {}
        self._toolbar_labels: list[ttk.Label] = []
        self._outer: ttk.Frame | None = None
        self._main_paned: ttk.Panedwindow | None = None
        self._middle_paned: ttk.Panedwindow | None = None
        self._upper_frame: ttk.Frame | None = None
        self._detail_tabs: ttk.Notebook | None = None
        self._summary_labels: dict[str, tk.Label] = {}
        self._network_facts: dict[str, object] | None = None
        self._network_profile_loading = False
        self._network_summary_labels: dict[str, tk.Label] = {}
        self._network_summary_static_labels: dict[str, tk.Label] = {}
        self._audit_records_by_item: dict[str, RepairAuditRecord] = {}

        apply_theme(self, self._fonts)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_ui()
        self._apply_ui_texts()
        self._show_idle_state()
        self.bind("<Configure>", self._on_window_configure)
        self.after(120, self._init_pane_sizes)
        self.after(200, self._start_startup_network_profile)

    def _set_initial_window_geometry(self) -> None:
        width, height, x, y = _initial_window_geometry(
            screen_width=self.winfo_screenwidth(),
            screen_height=self.winfo_screenheight(),
        )
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _assets_dir(self) -> Path:
        return _asset_path(ICON_PNG_48).parent

    def _set_window_icon(self) -> None:
        png = _asset_path(ICON_PNG_48)
        if png.is_file():
            try:
                self._window_icon_photo = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self._window_icon_photo)
            except tk.TclError:
                pass
        icon = _asset_path(ICON_ICO)
        if icon.is_file():
            try:
                self.iconbitmap(str(icon))
            except tk.TclError:
                pass

    def _load_header_logo(self) -> tk.PhotoImage | None:
        png = _asset_path(ICON_PNG_48)
        if not png.is_file():
            return None
        try:
            return tk.PhotoImage(file=str(png))
        except tk.TclError:
            return None

    def _build_ui(self) -> None:
        shell = ttk.Frame(self, style="App.TFrame", padding=(24, 22, 24, 20))
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)

        outer_shell = tk.Frame(
            shell,
            bg=self._colors["surface"],
            highlightthickness=1,
            highlightbackground=self._colors["border"],
        )
        outer_shell.grid(row=0, column=0, sticky="nsew")
        outer_shell.columnconfigure(0, weight=1)
        outer_shell.rowconfigure(0, weight=1)

        outer = ttk.Frame(outer_shell, style="Card.TFrame", padding=(18, 16, 18, 14))
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        for row in range(6):
            outer.rowconfigure(row, weight=0)
        outer.rowconfigure(4, weight=1, minsize=320)
        self._outer = outer

        self._build_header(outer, row=0)
        self._build_toolbar(outer, row=1)
        self._build_overview_row(outer, row=2)
        self._build_network_summary(outer, row=3)
        self._build_main_pane(outer, row=4)
        self._build_status_bar(outer, row=5)

    def _on_window_configure(self, event: tk.Event) -> None:
        if event.widget is not self or not self._outer:
            return
        wrap = max(event.width - 620, 280)
        self.case_label.configure(wraplength=wrap)

    def _build_overview_row(self, parent: ttk.Frame, *, row: int) -> None:
        overview = ttk.Frame(parent, style="Card.TFrame")
        overview.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        overview.columnconfigure(0, weight=1)
        overview.columnconfigure(1, weight=0, minsize=380)

        self._build_summary_cards(overview, row=0)
        self._build_status_card(overview, row=0, column=1)

    def _build_summary_cards(self, parent: ttk.Frame, *, row: int) -> None:
        band = ttk.Frame(parent, style="Card.TFrame")
        band.grid(row=row, column=0, sticky="ew", padx=(0, 12))
        for col in range(4):
            band.columnconfigure(col, weight=1)
        cards = [
            ("client", "TARGET", "Codex", self._colors["accent"]),
            ("status", "STATE", "Waiting", self._colors["warning"]),
            ("fixes", "FIXES", "0", self._colors["primary"]),
            ("login", "LOGIN", "Unchecked", self._colors["text"]),
        ]
        for col, (key, title, value, value_color) in enumerate(cards):
            card = tk.Frame(
                band,
                bg=self._colors["surface"],
                highlightthickness=1,
                highlightbackground=self._colors["border_soft"],
            )
            card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 10, 0))
            tk.Label(
                card,
                text=title,
                bg=self._colors["surface"],
                fg=self._colors["text_secondary"],
                anchor=tk.W,
                font=self._fonts.ui_font(self._fonts.size_caption, bold=True),
                padx=12,
                pady=7,
            ).pack(fill=tk.X)
            value_label = tk.Label(
                card,
                text=value,
                bg=self._colors["surface"],
                fg=value_color,
                anchor=tk.W,
                font=self._fonts.ui_font(25 if key != "fixes" else 32, bold=True),
                padx=12,
                pady=8,
            )
            value_label.pack(fill=tk.X)
            self._summary_labels[key] = value_label

    def _set_summary(self, *, client: str | None = None, status: str | None = None, fixes: str | None = None, login: str | None = None) -> None:
        updates = {"client": client, "status": status, "fixes": fixes, "login": login}
        for key, value in updates.items():
            if value is not None and key in self._summary_labels:
                self._summary_labels[key].configure(text=value)

    def _build_network_summary(self, parent: ttk.Frame, *, row: int) -> None:
        strip = tk.Frame(
            parent,
            bg=self._colors["surface_alt"],
            highlightthickness=1,
            highlightbackground=self._colors["border_soft"],
        )
        strip.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        strip.columnconfigure(0, weight=0)
        for col in range(1, 7):
            strip.columnconfigure(col, weight=1)
        strip.columnconfigure(7, weight=0)

        title = tk.Label(
            strip,
            text=t("network_strip.title"),
            bg=self._colors["surface_alt"],
            fg=self._colors["text"],
            anchor=tk.W,
            font=self._fonts.ui_font(self._fonts.size_small, bold=True),
            padx=12,
            pady=9,
        )
        title.grid(row=0, column=0, sticky="w")
        self._network_summary_static_labels["title"] = title

        items = [
            ("ip", "network_strip.ip"),
            ("location", "network_strip.location"),
            ("isp", "network_strip.isp"),
            ("risk", "network_strip.risk"),
            ("score", "network_strip.score"),
            ("path", "network_strip.path"),
        ]
        for col, (key, label_key) in enumerate(items, start=1):
            cell = tk.Frame(strip, bg=self._colors["surface_alt"])
            cell.grid(row=0, column=col, sticky="ew", padx=(0, 8), pady=5)
            label = tk.Label(
                cell,
                text=t(label_key),
                bg=self._colors["surface_alt"],
                fg=self._colors["text_muted"],
                anchor=tk.W,
                font=self._fonts.ui_font(self._fonts.size_caption, bold=True),
            )
            label.pack(fill=tk.X)
            self._network_summary_static_labels[key] = label
            value = tk.Label(
                cell,
                text="--",
                bg=self._colors["surface_alt"],
                fg=self._colors["text"],
                anchor=tk.W,
                font=self._fonts.ui_font(self._fonts.size_small, bold=True),
            )
            value.pack(fill=tk.X)
            self._network_summary_labels[key] = value

        self.network_detail_btn = ttk.Button(
            strip,
            text=t("network_strip.details"),
            style="Ghost.TButton",
            command=self._show_network_popup,
        )
        self.network_detail_btn.grid(row=0, column=7, sticky="e", padx=(4, 10))

    def _set_network_facts(self, facts: dict[str, object] | None = None, *, waiting: bool = False) -> None:
        self._network_facts = facts
        self._network_profile_loading = waiting
        values = self._network_display_values(facts, waiting=waiting)
        for key, value in values.items():
            if key in self._network_summary_labels:
                self._network_summary_labels[key].configure(text=value)

    def _network_display_values(self, facts: dict[str, object] | None, *, waiting: bool = False) -> dict[str, str]:
        if waiting:
            return {
                "ip": t("network_strip.checking"),
                "location": "--",
                "isp": "--",
                "risk": "--",
                "score": "--",
                "path": "--",
            }
        if not facts:
            return {key: "--" for key in ("ip", "location", "isp", "risk", "score", "path")}
        risk_text = self._network_risk_text(facts)
        asn = facts.get("asn") or ""
        isp = str(facts.get("isp") or facts.get("as_organization") or "--")
        if asn:
            isp = f"{isp} / AS{asn}"
        score = facts.get("score", "--")
        quality = str(facts.get("quality") or "")
        path = str(facts.get("probe_path") or "--")
        endpoint = t("network_strip.endpoint_ok") if facts.get("ai_endpoint_ok") else t("network_strip.endpoint_blocked")
        return {
            "ip": f"{facts.get('ip') or '--'} {facts.get('ip_version') or ''}".strip(),
            "location": str(facts.get("location") or facts.get("cloudflare_location") or "--"),
            "isp": isp,
            "risk": risk_text,
            "score": f"{score} {quality}".strip(),
            "path": f"{path} / {endpoint}",
        }

    def _network_facts_from_report(self, report: DiagnosisReport) -> dict[str, object] | None:
        for layer in report.layers:
            if layer.name != "network_profile":
                continue
            facts = layer.details.get("key_facts") if isinstance(layer.details, dict) else None
            if isinstance(facts, dict):
                return facts
            return layer.details if isinstance(layer.details, dict) else None
        return None

    def _show_network_popup(self) -> None:
        if not self._network_facts:
            if self._network_profile_loading:
                messagebox.showinfo(t("dialog.network_info.title"), t("dialog.network_info.loading"))
                return
            messagebox.showinfo(t("dialog.network_info.title"), t("dialog.network_info.empty"))
            return
        facts = self._network_facts
        values = self._network_display_values(facts)
        popup = tk.Toplevel(self)
        popup.title(t("dialog.network_info.title"))
        popup.transient(self)
        popup.configure(bg=self._colors["surface"])
        popup.minsize(520, 360)

        body = ttk.Frame(popup, style="Card.TFrame", padding=(20, 18, 20, 18))
        body.pack(fill=tk.BOTH, expand=True)
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        tk.Label(
            body,
            text=t("dialog.network_info.heading"),
            bg=self._colors["surface"],
            fg=self._colors["text"],
            font=self._fonts.ui_font(self._fonts.size_section, bold=True),
            anchor=tk.W,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 14))

        content_frame = ttk.Frame(body, style="Card.TFrame")
        content_frame.grid(row=1, column=0, sticky="nsew")
        content_frame.rowconfigure(0, weight=1)
        content_frame.columnconfigure(0, weight=1)

        canvas = tk.Canvas(content_frame, bg=self._colors["surface"], highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll_y = ttk.Scrollbar(content_frame, orient=tk.VERTICAL, command=canvas.yview)
        scroll_y.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scroll_y.set)

        rows_frame = tk.Frame(canvas, bg=self._colors["surface"])
        rows_window = canvas.create_window((0, 0), window=rows_frame, anchor="nw")
        rows_frame.columnconfigure(1, weight=1)

        def _configure_scroll_region(_event: tk.Event | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _configure_rows_width(event: tk.Event) -> None:
            canvas.itemconfigure(rows_window, width=event.width)

        rows_frame.bind("<Configure>", _configure_scroll_region)
        canvas.bind("<Configure>", _configure_rows_width)
        bind_mousewheel(canvas, canvas)

        rows = [
            ("dialog.network_info.trust", self._network_trust_text(facts)),
            ("dialog.network_info.ai_region", self._network_ai_region_text(facts)),
            ("network_strip.ip", values["ip"]),
            ("dialog.network_info.country", str(facts.get("country") or facts.get("cloudflare_location") or "--")),
            ("dialog.network_info.city", str(facts.get("city") or "--")),
            ("network_strip.location", values["location"]),
            ("dialog.network_info.ip_attribute", self._network_ip_attribute_text(facts)),
            ("network_strip.isp", values["isp"]),
            ("dialog.network_info.asn", self._network_asn_text(facts)),
            ("dialog.network_info.operator", str(facts.get("as_organization") or facts.get("isp") or "--")),
            ("network_strip.risk", values["risk"]),
            ("network_strip.score", values["score"]),
            ("network_strip.path", values["path"]),
            ("dialog.network_info.availability", self._network_availability_text(facts)),
            ("dialog.network_info.vpn", self._network_security_text(facts, "vpn")),
            ("dialog.network_info.proxy", self._network_security_text(facts, "proxy")),
            ("dialog.network_info.tor", self._network_security_text(facts, "tor")),
            ("dialog.network_info.crawler", self._network_yes_no_text(facts, "crawler")),
            ("dialog.network_info.abuse_record", self._network_abuse_record_text(facts)),
            ("dialog.network_info.abuse", str(facts.get("abuser_score") or "--")),
            ("dialog.network_info.dns_leak", self._network_desktop_limited_text("dns_leak", facts)),
            ("dialog.network_info.webrtc_leak", self._network_desktop_limited_text("webrtc_udp_leak", facts)),
            ("dialog.network_info.rdns", str(facts.get("rdns") or "--")),
            ("dialog.network_info.cloudflare", self._cloudflare_text(facts)),
            ("dialog.network_info.url", str(facts.get("net_coffee_url") or "https://ip.net.coffee/ip/")),
        ]
        value_wrap = max(520, self.winfo_screenwidth() - 520)
        for row, (label_key, value) in enumerate(rows):
            tk.Label(
                rows_frame,
                text=t(label_key),
                bg=self._colors["surface"],
                fg=self._colors["text_muted"],
                font=self._fonts.ui_font(self._fonts.size_small, bold=True),
                anchor=tk.W,
                padx=0,
                pady=5,
            ).grid(row=row, column=0, sticky="nw", padx=(0, 18))
            tk.Label(
                rows_frame,
                text=self._popup_display_value(str(value)),
                bg=self._colors["surface"],
                fg=self._colors["text"],
                font=self._fonts.ui_font(self._fonts.size_small, bold=True),
                anchor=tk.W,
                justify=tk.LEFT,
                wraplength=value_wrap,
                pady=5,
            ).grid(row=row, column=1, sticky="ew")

        actions = ttk.Frame(body, style="Card.TFrame")
        actions.grid(row=2, column=0, sticky="ew", pady=(18, 0))
        ttk.Button(
            actions,
            text=t("dialog.network_info.open"),
            style="Primary.TButton",
            command=lambda: webbrowser.open(str(facts.get("net_coffee_url") or "https://ip.net.coffee/ip/")),
        ).pack(side=tk.LEFT)
        ttk.Button(actions, text=t("dialog.close"), style="Ghost.TButton", command=popup.destroy).pack(side=tk.LEFT, padx=(10, 0))
        popup.update_idletasks()
        content_width = rows_frame.winfo_reqwidth() + 84
        content_height = rows_frame.winfo_reqheight() + actions.winfo_reqheight() + 128
        screen_width = popup.winfo_screenwidth()
        screen_height = popup.winfo_screenheight()
        popup_width = min(max(520, content_width), max(520, screen_width - 80))
        popup_height = min(max(360, content_height), max(360, screen_height - 100))
        popup_x = min(max(self.winfo_rootx() + 70, 20), max(20, screen_width - popup_width - 20))
        popup_y = min(max(self.winfo_rooty() + 35, 20), max(20, screen_height - popup_height - 40))
        popup.geometry(f"{popup_width}x{popup_height}+{popup_x}+{popup_y}")
        popup.update_idletasks()

    @staticmethod
    def _popup_display_value(value: str) -> str:
        if len(value) <= 56:
            return value
        return "\n".join(textwrap.wrap(value, width=56, break_long_words=True, break_on_hyphens=False))

    def _cloudflare_text(self, facts: dict[str, object]) -> str:
        loc = str(facts.get("cloudflare_location") or "")
        colo = str(facts.get("cloudflare_colo") or "")
        if loc and colo:
            return f"{loc} / {colo}"
        return loc or colo or "--"

    def _network_risk_text(self, facts: dict[str, object]) -> str:
        risk_flags = facts.get("risk_flags") if isinstance(facts.get("risk_flags"), list) else []
        if not risk_flags:
            return t("network_strip.risk_clean")
        return ", ".join(self._network_value_label(str(item)) for item in risk_flags)

    def _network_value_label(self, value: str) -> str:
        key = f"network.value.{value}"
        translated = t(key)
        return translated if translated != key else value

    def _network_trust_text(self, facts: dict[str, object]) -> str:
        trust = facts.get("trust_score")
        quality = self._network_value_label(str(facts.get("quality") or "unknown"))
        if trust not in ("", None):
            return f"{trust} / {quality}"
        score = facts.get("score")
        return f"{score} / {quality}" if score not in ("", None) else "--"

    def _network_ai_region_text(self, facts: dict[str, object]) -> str:
        return t("network.value.endpoint_reachable") if facts.get("ai_endpoint_ok") else t("network.value.endpoint_blocked")

    def _network_ip_attribute_text(self, facts: dict[str, object]) -> str:
        return self._network_value_label(str(facts.get("ip_attribute") or facts.get("company_type") or "unknown"))

    def _network_asn_text(self, facts: dict[str, object]) -> str:
        asn = facts.get("asn")
        if not asn:
            return "--"
        text = str(asn)
        return text if text.upper().startswith("AS") else f"AS{text}"

    def _network_security_text(self, facts: dict[str, object], key: str) -> str:
        checks = facts.get("security_checks") if isinstance(facts.get("security_checks"), dict) else {}
        return t("network.value.detected") if checks.get(key) else t("network.value.not_detected")

    def _network_yes_no_text(self, facts: dict[str, object], key: str) -> str:
        checks = facts.get("security_checks") if isinstance(facts.get("security_checks"), dict) else {}
        return t("network.value.yes") if checks.get(key) else t("network.value.no")

    def _network_abuse_record_text(self, facts: dict[str, object]) -> str:
        checks = facts.get("security_checks") if isinstance(facts.get("security_checks"), dict) else {}
        return t("network.value.detected") if checks.get("abuse") else t("network.value.no_record")

    def _network_availability_text(self, facts: dict[str, object]) -> str:
        availability = facts.get("availability") if isinstance(facts.get("availability"), dict) else {}
        ok = bool(availability.get("ok") or facts.get("ai_endpoint_ok"))
        latency = availability.get("best_latency_ms")
        label = t("network.value.endpoint_reachable") if ok else t("network.value.endpoint_blocked")
        if isinstance(latency, int):
            return f"{label} / {latency} ms"
        return label

    def _network_desktop_limited_text(self, key: str, facts: dict[str, object]) -> str:
        value = facts.get(key) if isinstance(facts.get(key), dict) else {}
        status = value.get("status") if isinstance(value, dict) else ""
        if status == "not_checked_desktop":
            return t("network.value.desktop_not_checked")
        return str(status or "--")

    def _start_startup_network_profile(self) -> None:
        self._set_network_facts(waiting=True)

        def worker() -> None:
            try:
                facts = self._collect_startup_network_facts()
                self.after(0, lambda: self._show_startup_network_facts(facts))
            except Exception:
                self.after(0, lambda: None if self._network_facts else self._set_network_facts())

        threading.Thread(target=worker, daemon=True).start()

    def _collect_startup_network_facts(self) -> dict[str, object] | None:
        system = read_system_proxy()
        env = read_env_proxy("user")
        system_endpoint = system["endpoint"]
        env_endpoint = primary_env_proxy(env)
        proxy = env_endpoint if env_endpoint.is_set else system_endpoint if system_endpoint.is_set else None
        api_probe = probe_chatgpt_api(proxy, timeout=2.0)
        profile = collect_network_profile(
            client=self._selected_client(),
            env_endpoint=env_endpoint,
            system_endpoint=system_endpoint,
            endpoint_probes={
                "api_via_env": api_probe if env_endpoint.is_set else {"ok": False},
                "api_via_system": api_probe if not env_endpoint.is_set and system_endpoint.is_set else {"ok": False},
                "oauth_direct": {"ok": bool(api_probe.get("ok"))},
            },
            timeout=2.0,
        )
        facts = profile.get("key_facts")
        return facts if isinstance(facts, dict) else None

    def _show_startup_network_facts(self, facts: dict[str, object] | None) -> None:
        if facts:
            self._set_network_facts(facts)
        elif not self._network_facts:
            self._set_network_facts()

    def _init_pane_sizes(self) -> None:
        if not self._main_paned or not self._upper_frame:
            return
        try:
            height = max(self._main_paned.winfo_height(), 360)
            self._main_paned.sashpos(0, int(height * 0.58))
        except tk.TclError:
            pass
        try:
            self._main_paned.paneconfigure(self._upper_frame, minsize=220)
            self._main_paned.paneconfigure(self._sections["detail"], minsize=135)
        except tk.TclError:
            pass
        if self._middle_paned:
            try:
                self._middle_paned.paneconfigure(self._sections["layers"], minsize=520)
                self._middle_paned.paneconfigure(self._sections["fixes"], minsize=260)
            except tk.TclError:
                pass

    def _build_header(self, parent: ttk.Frame, *, row: int) -> None:
        header_shell = tk.Frame(
            parent,
            bg=self._colors["header_bg"],
            highlightthickness=1,
            highlightbackground=self._colors["border"],
        )
        header_shell.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        header_shell.columnconfigure(1, weight=1)

        accent = tk.Frame(header_shell, width=5, bg=self._colors["header_rule"])
        accent.grid(row=0, column=0, sticky="ns")

        header = ttk.Frame(header_shell, style="Header.TFrame", padding=(16, 13, 16, 13))
        header.grid(row=0, column=1, sticky="ew")
        header.columnconfigure(0, weight=1)

        left = ttk.Frame(header, style="Header.TFrame")
        left.grid(row=0, column=0, sticky="w")

        title_row = ttk.Frame(left, style="Header.TFrame")
        title_row.pack(anchor=tk.W)

        self._logo_photo = self._load_header_logo()
        if self._logo_photo:
            self.logo_label = tk.Label(title_row, image=self._logo_photo, bg=self._colors["header_bg"], bd=0)
            self.logo_label.pack(side=tk.LEFT, padx=(0, 12))

        text_col = ttk.Frame(title_row, style="Header.TFrame")
        text_col.pack(side=tk.LEFT)
        self.title_label = ttk.Label(text_col, text=APP_NAME, style="Title.TLabel")
        self.title_label.pack(anchor=tk.W)
        self.tagline_label = ttk.Label(text_col, text="", style="Subtitle.TLabel")
        self.tagline_label.pack(anchor=tk.W, pady=(2, 0))

        right = ttk.Frame(header, style="Header.TFrame")
        right.grid(row=0, column=1, sticky="ne")
        ttk.Label(right, text=f"v{__version__}", style="Badge.TLabel", padding=(10, 4)).pack(anchor=tk.E)
        ttk.Label(right, text="Local desktop repair", style="Subtitle.TLabel").pack(anchor=tk.E, pady=(6, 0))

    def _build_toolbar(self, parent: ttk.Frame, *, row: int) -> None:
        toolbar = tk.Frame(
            parent,
            bg=self._colors["toolbar"],
            highlightthickness=1,
            highlightbackground=self._colors["border"],
        )
        toolbar.grid(row=row, column=0, sticky="ew", pady=(0, 12))

        inner = ttk.Frame(toolbar, style="Toolbar.TFrame", padding=(14, 12, 14, 12))
        inner.pack(fill=tk.X)
        for col in range(6):
            inner.columnconfigure(col, weight=0)
        inner.columnconfigure(5, weight=1)

        client_lbl = ttk.Label(inner, text="", style="FieldLabel.TLabel")
        client_lbl.grid(row=0, column=0, sticky="w")
        self._toolbar_labels.append(client_lbl)

        self.client_var = tk.StringVar(value="codex")
        self.client_box = ttk.Combobox(
            inner,
            textvariable=self.client_var,
            values=[f"{key}{CLIENT_SEPARATOR}{CLIENT_LABELS[key]}" for key in CLIENT_LABELS],
            state="readonly",
            width=22,
        )
        self.client_box.grid(row=0, column=1, padx=(8, 18), sticky="w")
        self.client_box.current(0)
        self.client_box.bind("<<ComboboxSelected>>", self._on_client_change)

        lang_lbl = ttk.Label(inner, text="", style="FieldLabel.TLabel")
        lang_lbl.grid(row=0, column=2, padx=(0, 8), sticky="w")
        self._toolbar_labels.append(lang_lbl)

        self.locale_var = tk.StringVar(value=locale_label(get_locale()))
        self.locale_box = ttk.Combobox(
            inner,
            textvariable=self.locale_var,
            values=[locale_label("zh"), locale_label("en")],
            state="readonly",
            width=11,
        )
        self.locale_box.grid(row=0, column=3, sticky="w")
        self.locale_box.bind("<<ComboboxSelected>>", self._on_locale_change)

        self.diagnose_btn = ttk.Button(
            inner,
            text="",
            style="Primary.TButton",
            command=self._run_diagnosis,
        )
        self.diagnose_btn.grid(row=0, column=4, padx=(18, 0), sticky="w")
        self.scan_btn = ttk.Button(
            inner,
            text="",
            style="Ghost.TButton",
            command=self._run_installed_scan,
        )
        self.scan_btn.grid(row=0, column=5, padx=(8, 0), sticky="w")

        secondary = ttk.Frame(inner, style="Toolbar.TFrame")
        secondary.grid(row=1, column=0, columnspan=6, sticky="w", pady=(10, 0))

        self.login_btn = ttk.Button(secondary, text="", style="Ghost.TButton", command=self._check_login_only)
        self.login_btn.pack(side=tk.LEFT)

        self.sync_btn = ttk.Button(secondary, text="", style="Ghost.TButton", command=self._sync_system_proxy)
        self.sync_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.fix_btn = ttk.Button(secondary, text="", style="Ghost.TButton", command=self._apply_auto_fixes)
        self.fix_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.device_auth_btn = ttk.Button(secondary, text="", style="Ghost.TButton", command=self._launch_device_auth)
        self.device_auth_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.copy_btn = ttk.Button(secondary, text="", style="Ghost.TButton", command=self._copy_report)
        self.copy_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.about_btn = ttk.Button(secondary, text="", style="Ghost.TButton", command=self._show_about)
        self.about_btn.pack(side=tk.LEFT, padx=(8, 0))

    def _build_status_card(self, parent: ttk.Frame, *, row: int, column: int = 0) -> None:
        self.status_frame = tk.Frame(
            parent,
            bg=self._colors["surface_alt"],
            highlightthickness=1,
            highlightbackground=self._colors["border"],
            width=380,
        )
        self.status_frame.grid(row=row, column=column, sticky="nsew")
        self.status_frame.grid_propagate(False)

        inner = tk.Frame(self.status_frame, bg=self._colors["surface_alt"], padx=14, pady=10)
        inner.pack(fill=tk.BOTH, expand=True)
        inner.columnconfigure(0, weight=1)

        top = tk.Frame(inner, bg=self._colors["surface_alt"])
        top.pack(fill=tk.X)

        self.status_dot = tk.Canvas(top, width=12, height=12, bg=self._colors["surface_alt"], highlightthickness=0)
        self.status_dot.pack(side=tk.LEFT, padx=(0, 9), pady=6)
        self._status_dot_id = self.status_dot.create_oval(2, 2, 10, 10, fill=self._colors["text_muted"], outline="")

        self.status_label = tk.Label(
            top,
            text="",
            bg=self._colors["surface_alt"],
            fg=self._colors["text"],
            font=self._fonts.ui_font(bold=True),
        )
        self.status_label.pack(side=tk.LEFT, anchor=tk.W, fill=tk.X, expand=True)

        self.case_label = tk.Label(
            inner,
            text="",
            bg=self._colors["surface_alt"],
            fg=self._colors["text_secondary"],
            font=self._fonts.ui_font(bold=True),
            justify=tk.LEFT,
            anchor="w",
            wraplength=340,
        )
        self.case_label.pack(fill=tk.X, anchor=tk.W, pady=(2, 0))

    def _build_cause_card(self, parent: ttk.Frame, *, row: int) -> None:
        card = ttk.Labelframe(parent, text="", style="Section.TLabelframe", padding=10)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        card.columnconfigure(0, weight=1)
        self._sections["cause"] = card
        self.cause_text = make_scroll_text(self._sections["cause"], height=2, fonts=self._fonts, expand=False)
        bind_mousewheel(self.cause_text, self.cause_text)

    def _build_main_pane(self, parent: ttk.Frame, *, row: int) -> None:
        self._main_paned = ttk.Panedwindow(parent, orient=tk.VERTICAL)
        self._main_paned.grid(row=row, column=0, sticky="nsew")

        upper = ttk.Frame(self._main_paned)
        upper.columnconfigure(0, weight=1)
        upper.rowconfigure(0, weight=1)
        self._upper_frame = upper
        self._main_paned.add(upper, weight=4)

        middle = ttk.Panedwindow(upper, orient=tk.HORIZONTAL)
        middle.grid(row=0, column=0, sticky="nsew")
        self._middle_paned = middle

        layer_card = ttk.Labelframe(middle, text="", style="Section.TLabelframe", padding=10)
        fix_card = ttk.Labelframe(middle, text="", style="Section.TLabelframe", padding=10)
        layer_card.columnconfigure(0, weight=1)
        layer_card.rowconfigure(0, weight=1)
        fix_card.columnconfigure(0, weight=1)
        fix_card.rowconfigure(0, weight=1)
        self._sections["layers"] = layer_card
        self._sections["fixes"] = fix_card
        middle.add(layer_card, weight=3)
        middle.add(fix_card, weight=2)

        layer_body = ttk.Frame(layer_card)
        layer_body.pack(fill=tk.BOTH, expand=True)
        columns = ("status", "name", "summary")
        self.layer_tree = ttk.Treeview(layer_body, columns=columns, show="headings", selectmode="browse")
        self.layer_tree.heading("status", text="")
        self.layer_tree.heading("name", text="")
        self.layer_tree.heading("summary", text="")
        self.layer_tree.column("status", width=112, anchor=tk.CENTER, stretch=False, minwidth=96)
        self.layer_tree.column("name", width=190, stretch=False, minwidth=156)
        self.layer_tree.column("summary", width=520, stretch=True, minwidth=260)
        self.layer_tree.tag_configure("ok", foreground=self._colors["success"])
        self.layer_tree.tag_configure("fail", foreground=self._colors["error"])
        self.layer_tree.tag_configure("progress", foreground=self._colors["warning"])
        attach_tree_scrollbars(self.layer_tree, layer_body)
        self.layer_tree.bind("<<TreeviewSelect>>", self._on_layer_select)

        fix_body = ttk.Frame(fix_card)
        fix_body.pack(fill=tk.BOTH, expand=True)
        self.fix_list = tk.Listbox(
            fix_body,
            font=self._fonts.ui_font(bold=True),
            activestyle=tk.NONE,
            bg=self._colors["surface"],
            fg=self._colors["text"],
            selectbackground=self._colors["selection"],
            selectforeground=self._colors["text"],
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=self._colors["border_soft"],
            borderwidth=0,
        )
        attach_list_scrollbars(self.fix_list, fix_body)
        self.fix_list.bind("<Double-Button-1>", self._on_fix_double_click)

        detail_card = ttk.Frame(self._main_paned, style="Card.TFrame", padding=(0, 8, 0, 0))
        detail_card.columnconfigure(0, weight=1)
        detail_card.rowconfigure(0, weight=1)
        self._main_paned.add(detail_card, weight=2)

        tabs = ttk.Notebook(detail_card)
        tabs.grid(row=0, column=0, sticky="nsew")
        self._detail_tabs = tabs

        cause_tab = ttk.Frame(tabs, padding=10)
        cause_tab.columnconfigure(0, weight=1)
        cause_tab.rowconfigure(0, weight=1)
        tabs.add(cause_tab, text="Root Cause")
        self._sections["cause"] = cause_tab

        detail_tab = ttk.Frame(tabs, padding=10)
        detail_tab.columnconfigure(0, weight=1)
        detail_tab.rowconfigure(0, weight=1)
        tabs.add(detail_tab, text="Detailed Logs")
        self._sections["detail"] = detail_tab

        audit_tab = ttk.Frame(tabs, padding=10)
        audit_tab.columnconfigure(0, weight=1)
        audit_tab.rowconfigure(1, weight=1, minsize=180)
        tabs.add(audit_tab, text="Repair Audit")
        self._sections["audit"] = audit_tab

        audit_toolbar = ttk.Frame(audit_tab)
        audit_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.audit_refresh_btn = ttk.Button(audit_toolbar, text="", style="Ghost.TButton", command=self._refresh_repair_audit)
        self.audit_refresh_btn.pack(side=tk.LEFT)
        self.audit_rollback_btn = ttk.Button(audit_toolbar, text="", style="Ghost.TButton", command=self._rollback_latest_repair)
        self.audit_rollback_btn.pack(side=tk.LEFT, padx=(8, 0))

        audit_split = ttk.Panedwindow(audit_tab, orient=tk.HORIZONTAL)
        audit_split.grid(row=1, column=0, sticky="nsew")

        audit_table_body = ttk.Frame(audit_split)
        audit_detail_body = ttk.Frame(audit_split)
        audit_split.add(audit_table_body, weight=3)
        audit_split.add(audit_detail_body, weight=2)

        audit_columns = ("time", "client", "action", "status", "risk", "admin", "restart", "changed", "rollback")
        self.audit_tree = ttk.Treeview(audit_table_body, columns=audit_columns, show="headings", selectmode="browse", height=4)
        for column in audit_columns:
            self.audit_tree.heading(column, text="")
        self.audit_tree.column("time", width=210, minwidth=160, stretch=False)
        self.audit_tree.column("client", width=100, minwidth=80, stretch=False)
        self.audit_tree.column("action", width=180, minwidth=150, stretch=False)
        self.audit_tree.column("status", width=100, minwidth=80, stretch=False)
        self.audit_tree.column("risk", width=90, minwidth=70, stretch=False)
        self.audit_tree.column("admin", width=90, minwidth=70, stretch=False)
        self.audit_tree.column("restart", width=90, minwidth=70, stretch=False)
        self.audit_tree.column("changed", width=260, minwidth=180, stretch=True)
        self.audit_tree.column("rollback", width=120, minwidth=90, stretch=False)
        self.audit_tree.tag_configure("success", foreground=self._colors["success"])
        self.audit_tree.tag_configure("failed", foreground=self._colors["error"])
        self.audit_tree.tag_configure("rollback", foreground=self._colors["accent"])
        attach_tree_scrollbars(self.audit_tree, audit_table_body)
        self.audit_tree.bind("<<TreeviewSelect>>", self._on_audit_select)

        self.audit_detail_text = make_scroll_text(
            audit_detail_body,
            height=4,
            mono=True,
            fonts=self._fonts,
            wrap=tk.NONE,
        )

        self.cause_text = make_scroll_text(
            cause_tab,
            height=5,
            fonts=self._fonts,
            wrap=tk.WORD,
        )
        bind_mousewheel(self.cause_text, self.cause_text)

        self.detail_text = make_scroll_text(
            detail_tab,
            height=8,
            mono=True,
            fonts=self._fonts,
            wrap=tk.NONE,
        )
        bind_mousewheel(self.detail_text, self.detail_text)

    def _build_status_bar(self, parent: ttk.Frame, *, row: int) -> None:
        bar = tk.Frame(
            parent, bg=self._colors["surface_alt"], highlightthickness=1, highlightbackground=self._colors["border"]
        )
        bar.grid(row=row, column=0, sticky="ew", pady=(10, 0))
        bar.columnconfigure(0, weight=1)
        bar.columnconfigure(1, weight=0)
        bar.columnconfigure(2, weight=0)
        self.status_bar = tk.Label(
            bar,
            text="",
            bg=self._colors["surface_alt"],
            fg=self._colors["text_muted"],
            font=self._fonts.ui_font(self._fonts.size_caption, bold=True),
            anchor=tk.W,
            padx=12,
            pady=8,
        )
        self.status_bar.grid(row=0, column=0, sticky="ew")
        self.elapsed_label = tk.Label(
            bar,
            text="",
            bg=self._colors["surface_alt"],
            fg=self._colors["text_muted"],
            font=self._fonts.ui_font(self._fonts.size_small, bold=True),
            anchor=tk.E,
            padx=10,
            pady=8,
        )
        self.elapsed_label.grid(row=0, column=1, sticky="e")
        self.busy_progress = ttk.Progressbar(
            bar,
            mode="indeterminate",
            length=150,
            style="Busy.Horizontal.TProgressbar",
        )
        self.busy_progress.grid(row=0, column=2, sticky="e", padx=(0, 12))
        self.busy_progress.grid_remove()

    def _apply_ui_texts(self) -> None:
        self.title(APP_NAME)
        self.tagline_label.configure(text=t(APP_TAGLINE_KEY))
        if self._toolbar_labels:
            self._toolbar_labels[0].configure(text=t("toolbar.client"))
            self._toolbar_labels[1].configure(text=t("toolbar.language"))
        self.diagnose_btn.configure(text=t("toolbar.diagnose"))
        self.scan_btn.configure(text=t("toolbar.scan_installed"))
        self.sync_btn.configure(text=t("toolbar.sync"))
        self.fix_btn.configure(text=t("toolbar.autofix"))
        self.login_btn.configure(text=t("toolbar.check_login"))
        self.device_auth_btn.configure(text=t("toolbar.device_auth"))
        self.copy_btn.configure(text=t("toolbar.copy_json"))
        self.about_btn.configure(text=t("toolbar.about"))
        if hasattr(self, "network_detail_btn"):
            self.network_detail_btn.configure(text=t("network_strip.details"))
        self._sections["layers"].configure(text=t("section.layers"))
        self._sections["fixes"].configure(text=t("section.fixes"))
        if self._detail_tabs:
            self._detail_tabs.tab(0, text=t("section.cause"))
            self._detail_tabs.tab(1, text=t("section.detail"))
            self._detail_tabs.tab(2, text=t("section.audit"))
        self.layer_tree.heading("status", text=t("layer.status"))
        self.layer_tree.heading("name", text=t("layer.name"))
        self.layer_tree.heading("summary", text=t("layer.summary"))
        self.audit_refresh_btn.configure(text=t("audit.refresh"))
        self.audit_rollback_btn.configure(text=t("audit.rollback_latest"))
        self.audit_tree.heading("time", text=t("audit.time"))
        self.audit_tree.heading("client", text=t("audit.client"))
        self.audit_tree.heading("action", text=t("audit.action"))
        self.audit_tree.heading("status", text=t("audit.status"))
        self.audit_tree.heading("risk", text=t("audit.risk"))
        self.audit_tree.heading("admin", text=t("audit.admin"))
        self.audit_tree.heading("restart", text=t("audit.restart"))
        self.audit_tree.heading("changed", text=t("audit.changed"))
        self.audit_tree.heading("rollback", text=t("audit.rollback"))
        network_titles = {
            "title": "network_strip.title",
            "ip": "network_strip.ip",
            "location": "network_strip.location",
            "isp": "network_strip.isp",
            "risk": "network_strip.risk",
            "score": "network_strip.score",
            "path": "network_strip.path",
        }
        for key, label_key in network_titles.items():
            if key in self._network_summary_static_labels:
                self._network_summary_static_labels[key].configure(text=t(label_key))
    def _apply_fonts(self) -> None:
        """语言切换时同步 Cursor 风格中英文字体。"""
        self._fonts = resolve_fonts(self, get_locale())
        apply_theme(self, self._fonts)
        self.status_label.configure(font=self._fonts.ui_font(bold=True))
        self.case_label.configure(font=self._fonts.ui_font(bold=True))
        self.status_bar.configure(font=self._fonts.ui_font(self._fonts.size_caption, bold=True))
        self.elapsed_label.configure(font=self._fonts.ui_font(self._fonts.size_caption, bold=True))
        self.fix_list.configure(font=self._fonts.ui_font(bold=True))
        self.cause_text.configure(font=self._fonts.ui_font(bold=True))
        self.detail_text.configure(font=self._fonts.mono_font())
        self.audit_detail_text.configure(font=self._fonts.mono_font())
        for key, label in self._summary_labels.items():
            label.configure(font=self._fonts.ui_font(25 if key != "fixes" else 32, bold=True))
        for key, label in self._network_summary_static_labels.items():
            label.configure(font=self._fonts.ui_font(self._fonts.size_small if key == "title" else self._fonts.size_caption, bold=True))
        for label in self._network_summary_labels.values():
            label.configure(font=self._fonts.ui_font(self._fonts.size_small, bold=True))

    def _on_locale_change(self, _event: tk.Event | None = None) -> None:
        selected = self.locale_var.get()
        new_locale = "zh" if selected == locale_label("zh") else "en"
        if new_locale == get_locale():
            return
        set_locale(new_locale)
        self.title(APP_NAME)
        self._apply_fonts()
        self._apply_ui_texts()
        if self._busy:
            self._refresh_busy_locale()
            return
        if self._report:
            self._show_report(self._report, refreshed=True)
        else:
            self._show_idle_state()

    def _refresh_busy_locale(self) -> None:
        if self._busy_kind == "scan":
            self._set_summary(client=t("scan.installed_clients"), status=t("status.diagnosing"), fixes="0", login="--")
            message = t("busy.scanning")
        else:
            client = self._selected_client()
            label = CLIENT_LABELS.get(client, client)
            self._set_summary(client=label, status=t("status.diagnosing"))
            message = t("busy.diagnosing", client=label)
        self._busy_message = message
        self._apply_status_theme("warning", t("status.diagnosing"))
        self.status_bar.configure(text=message)
        if self._busy_started_at is not None:
            self.elapsed_label.configure(text=t("status.elapsed", seconds=self._elapsed_seconds()))
        self._retranslate_progress_rows()

    def _retranslate_progress_rows(self) -> None:
        for iid in self.layer_tree.get_children():
            if not str(iid).startswith("progress:"):
                continue
            values = list(self.layer_tree.item(iid, "values"))
            if len(values) < 3:
                continue
            tags = set(self.layer_tree.item(iid, "tags"))
            values[0] = t("progress.done") if "ok" in tags else t("progress.running")
            values[1] = layer_name(str(iid).split(":", 1)[1])
            self.layer_tree.item(iid, values=values)

    def _show_idle_state(self) -> None:
        self._apply_status_theme("warning", t("status.waiting"))
        self._set_summary(
            client=CLIENT_LABELS.get(self._selected_client(), "Codex"),
            status=t("status.waiting"),
            fixes="0",
            login=t("login.summary.unchecked"),
        )
        if not self._network_facts:
            self._set_network_facts()
        self._report = None
        self._reports = []
        self._report_by_item = {}
        self._fix_actions = []
        self.case_label.configure(text=t("idle.case_hint"))
        set_text(self.cause_text, t("idle.cause"))
        self.layer_tree.delete(*self.layer_tree.get_children())
        self.layer_tree.insert("", tk.END, values=(t("status.waiting"), t("diagnosis.system_scan"), t("toolbar.diagnose")))
        self.fix_list.delete(0, tk.END)
        self.fix_list.insert(tk.END, t("idle.no_fixes"))
        self.fix_list.itemconfigure(0, foreground=self._colors["text_muted"])
        self._set_detail_text(t("idle.detail"))
        self._refresh_repair_audit()
        self.status_bar.configure(text=t("status.ready"))
        self.elapsed_label.configure(text="")

    def _selected_client(self) -> str:
        raw = self.client_var.get().split(CLIENT_SEPARATOR, 1)[0]
        return raw if raw in CLIENT_LABELS else "codex"

    def _on_client_change(self, _event: tk.Event | None = None) -> None:
        client = self._selected_client()
        if client == self._last_selected_client and not self._reports:
            self._set_summary(client=CLIENT_LABELS.get(client, "Codex"))
            return
        self._last_selected_client = client
        self._invalidate_current_analysis()
        self._show_idle_state()

    def _start_analysis_generation(self) -> int:
        self._analysis_generation += 1
        return self._analysis_generation

    def _invalidate_current_analysis(self) -> None:
        self._analysis_generation += 1
        if self._busy:
            self._set_busy(False, t("status.ready"))

    def _is_current_analysis(self, generation: int, client: str | None = None) -> bool:
        if generation != self._analysis_generation:
            return False
        return client is None or client == self._selected_client()

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.diagnose_btn.configure(state=state)
        self.scan_btn.configure(state=state)
        self.sync_btn.configure(state=state)
        self.fix_btn.configure(state=state)
        self.login_btn.configure(state=state)
        if message:
            self._busy_message = message
            self.status_bar.configure(text=message)
        if busy:
            self._start_busy_feedback(message)
        else:
            self._stop_busy_feedback(message)
            self._busy_kind = ""

    def _start_busy_feedback(self, message: str = "") -> None:
        self._busy_started_at = time.monotonic()
        self._pulse_index = 0
        if message:
            self._busy_message = message
        self.busy_progress.grid()
        self.busy_progress.start(12)
        self._tick_elapsed()
        self._pulse_status_dot()

    def _stop_busy_feedback(self, message: str = "") -> None:
        if self._timer_after_id:
            self.after_cancel(self._timer_after_id)
            self._timer_after_id = None
        if self._pulse_after_id:
            self.after_cancel(self._pulse_after_id)
            self._pulse_after_id = None
        try:
            self.busy_progress.stop()
        except tk.TclError:
            pass
        self.busy_progress.grid_remove()
        if self._busy_started_at is not None:
            self.elapsed_label.configure(text=t("status.elapsed", seconds=self._elapsed_seconds()))
        else:
            self.elapsed_label.configure(text="")
        self._busy_started_at = None
        if message:
            self.status_bar.configure(text=message)

    def _elapsed_seconds(self) -> int:
        if self._busy_started_at is None:
            return 0
        return max(0, int(time.monotonic() - self._busy_started_at))

    def _tick_elapsed(self) -> None:
        if not self._busy or self._busy_started_at is None:
            return
        self.elapsed_label.configure(text=t("status.elapsed", seconds=self._elapsed_seconds()))
        if self._busy_message:
            dots = "." * ((self._elapsed_seconds() % 3) + 1)
            base = self._busy_message.rstrip(".… ")
            self.status_bar.configure(text=f"{base}{dots}")
        self._timer_after_id = self.after(1000, self._tick_elapsed)

    def _pulse_status_dot(self) -> None:
        if not self._busy:
            return
        palette = (self._colors["warning"], self._colors["primary"], self._colors["accent"])
        self.status_dot.itemconfigure(self._status_dot_id, fill=palette[self._pulse_index % len(palette)])
        self._pulse_index += 1
        self._pulse_after_id = self.after(360, self._pulse_status_dot)

    def _run_diagnosis(self) -> None:
        if self._busy:
            return
        client = self._selected_client()
        label = CLIENT_LABELS.get(client, client)
        generation = self._start_analysis_generation()
        self._last_selected_client = client
        self._busy_kind = "diagnosis"
        self._set_summary(client=label, status=t("status.diagnosing"))
        self._set_busy(True, t("busy.diagnosing", client=label))
        self._apply_status_theme("warning", t("status.diagnosing"))
        self._prepare_progress_view(label)

        def progress(event: dict[str, str]) -> None:
            self.after(0, lambda event=event: self._show_progress_if_current(event, generation, client))

        def worker() -> None:
            try:
                report = run_diagnosis(client=client, locale=get_locale(), progress=progress)
                self.after(0, lambda: self._show_report_if_current(report, generation, client, refreshed=False))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self._show_error_if_current(str(exc), generation, client))

        threading.Thread(target=worker, daemon=True).start()

    def _run_installed_scan(self) -> None:
        if self._busy:
            return
        generation = self._start_analysis_generation()
        self._busy_kind = "scan"
        self._set_summary(client=t("scan.installed_clients"), status=t("status.diagnosing"), fixes="0", login="--")
        self._set_busy(True, t("busy.scanning"))
        self._apply_status_theme("warning", t("status.diagnosing"))
        self.case_label.configure(text=t("busy.scanning"))
        set_text(self.cause_text, t("busy.cause"))

        def worker() -> None:
            try:
                reports = scan_installed_clients(locale=get_locale(), fast=True)
                self.after(0, lambda: self._show_scan_reports_if_current(reports, generation))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self._show_error_if_current(str(exc), generation))

        threading.Thread(target=worker, daemon=True).start()

    def _show_error(self, message: str) -> None:
        self._set_busy(False, t("status.failed"))
        self._apply_status_theme("unhealthy", t("status.failed"))
        set_text(self.cause_text, message)
        messagebox.showerror(t("dialog.error.title"), message)

    def _show_error_if_current(self, message: str, generation: int, client: str | None = None) -> None:
        if not self._is_current_analysis(generation, client):
            return
        self._show_error(message)

    def _prepare_progress_view(self, client_label: str) -> None:
        self._report = None
        self._reports = []
        self._report_by_item = {}
        self._fix_actions = []
        self._set_network_facts(waiting=True)
        self.layer_tree.delete(*self.layer_tree.get_children())
        self.fix_list.delete(0, tk.END)
        self.fix_list.insert(tk.END, t("progress.no_fixes_until_done"))
        self.fix_list.itemconfigure(0, foreground=self._colors["text_muted"])
        self.case_label.configure(text=t("busy.case_progress"))
        set_text(self.cause_text, f"{t('busy.cause')}\n{t('progress.live_hint')}")
        self._set_detail_text(t("progress.log_start", client=client_label))

    def _show_progress_if_current(self, event: dict[str, str], generation: int, client: str) -> None:
        if not self._is_current_analysis(generation, client):
            return
        name = event.get("name", "")
        if not name:
            return
        state = event.get("state", "running")
        summary = event.get("summary", "")
        status = t("progress.done") if state == "done" else t("progress.running")
        tag = "ok" if state == "done" else "progress"
        iid = f"progress:{name}"
        values = (status, layer_name(name), summary)
        if self.layer_tree.exists(iid):
            self.layer_tree.item(iid, values=values, tags=(tag,))
        else:
            self.layer_tree.insert("", tk.END, iid=iid, values=values, tags=(tag,))
        self.layer_tree.see(iid)
        self.case_label.configure(text=summary)
        self.status_bar.configure(text=summary)
        self._append_detail_log(f"[{self._elapsed_seconds():>3}s] {status} - {layer_name(name)} - {summary}")

    def _append_detail_log(self, line: str) -> None:
        self.detail_text.configure(state=tk.NORMAL)
        existing = self.detail_text.get("1.0", tk.END).strip()
        if existing:
            self.detail_text.insert(tk.END, "\n")
        self.detail_text.insert(tk.END, line)
        self._linkify_text(self.detail_text)
        self.detail_text.see(tk.END)
        self.detail_text.configure(state=tk.DISABLED)

    def _set_detail_text(self, content: str, *, readonly: bool = True) -> None:
        set_text(self.detail_text, content, readonly=readonly)
        self._linkify_text(self.detail_text)

    def _linkify_text(self, widget: tk.Text) -> None:
        content = widget.get("1.0", "end-1c")
        for tag in widget.tag_names():
            if tag.startswith("hyperlink_"):
                widget.tag_delete(tag)
        for index, match in enumerate(URL_RE.finditer(content)):
            url = match.group(0).rstrip(URL_TRAILING_PUNCTUATION)
            if not url:
                continue
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.start() + len(url)}c"
            tag = f"hyperlink_{index}"
            widget.tag_add(tag, start, end)
            widget.tag_configure(tag, foreground=self._colors["accent"], underline=True)
            widget.tag_bind(tag, "<Button-1>", lambda _event, url=url: webbrowser.open(url))
            widget.tag_bind(tag, "<Enter>", lambda _event: widget.configure(cursor="hand2"))
            widget.tag_bind(tag, "<Leave>", lambda _event: widget.configure(cursor=""))

    def _refresh_repair_audit(self) -> None:
        records = load_audit_records()
        visible = list(reversed(records[-AUDIT_ROW_LIMIT:]))
        self._audit_records_by_item = {}
        self.audit_tree.delete(*self.audit_tree.get_children())
        if not visible:
            self.audit_tree.insert(
                "",
                tk.END,
                values=("", "", t("audit.empty"), "", "", "", "", "", ""),
                tags=("empty",),
            )
            set_text(self.audit_detail_text, t("audit.empty_detail"))
            return

        for index, record in enumerate(visible):
            iid = f"audit:{record.repair_id}:{index}"
            self._audit_records_by_item[iid] = record
            tag = "rollback" if record.fix_id.startswith("rollback:") else record.status
            self.audit_tree.insert(
                "",
                tk.END,
                iid=iid,
                values=self._audit_row_values(record),
                tags=(tag,),
            )
        first = self.audit_tree.get_children()[0]
        self.audit_tree.selection_set(first)
        self.audit_tree.focus(first)
        self._show_audit_detail(visible[0])

    def _audit_row_values(self, record: RepairAuditRecord) -> tuple[str, str, str, str, str, str, str, str, str]:
        changed = ", ".join(record.changed_keys)
        if len(changed) > 80:
            changed = changed[:77] + "..."
        return (
            self._format_audit_time(record.timestamp),
            record.client or "--",
            record.fix_id,
            self._audit_status_text(record.status),
            record.risk or "--",
            t("audit.yes") if record.admin_required else t("audit.no"),
            t("audit.yes") if record.restart_required else t("audit.no"),
            changed or "--",
            t("audit.yes") if record.rollback_supported else t("audit.no"),
        )

    def _format_audit_time(self, value: str) -> str:
        return value.replace("T", " ").split("+", 1)[0].split(".", 1)[0] if value else "--"

    def _audit_status_text(self, status: str) -> str:
        if status == "success":
            return t("audit.status_success")
        if status == "failed":
            return t("audit.status_failed")
        return status or "--"

    def _on_audit_select(self, _event: tk.Event) -> None:
        selection = self.audit_tree.selection()
        if not selection:
            return
        record = self._audit_records_by_item.get(selection[0])
        if record:
            self._show_audit_detail(record)

    def _show_audit_detail(self, record: RepairAuditRecord) -> None:
        detail = json.dumps(record.to_dict(), ensure_ascii=False, indent=2)
        set_text(self.audit_detail_text, detail)

    def _rollback_latest_repair(self) -> None:
        record = latest_rollbackable_record()
        if record is None:
            messagebox.showwarning(t("dialog.rollback.failed"), t("audit.empty_detail"))
            return
        preview = _format_gui_rollback_preview(record)
        if not messagebox.askyesno(t("dialog.rollback.title"), f"{t('dialog.rollback.confirm')}\n\n{preview}"):
            return
        try:
            message = rollback_latest_repair()
            messagebox.showinfo(t("dialog.rollback.done"), t("dialog.fix_done.body", message=message))
            self._refresh_repair_audit()
        except ValueError as exc:
            messagebox.showwarning(t("dialog.rollback.failed"), str(exc))

    def _show_report_if_current(
        self,
        report: DiagnosisReport,
        generation: int,
        client: str,
        *,
        refreshed: bool,
    ) -> None:
        if not self._is_current_analysis(generation, client):
            return
        self._show_report(report, refreshed=refreshed)

    def _show_scan_reports_if_current(self, reports: list[DiagnosisReport], generation: int) -> None:
        if not self._is_current_analysis(generation):
            return
        self._show_scan_reports(reports)

    def _show_report(self, report: DiagnosisReport, *, refreshed: bool) -> None:
        self._report = report
        self._reports = [report]
        self._report_by_item = {}
        self._set_busy(False, t("status.refreshed") if refreshed else t("status.done"))

        status_key = report.status.value if report.status.value in STATUS_KEYS else "warning"
        self._apply_status_theme(status_key, t(STATUS_KEYS[status_key]))
        failed_count = sum(1 for layer in report.layers if not layer.ok)
        self._set_summary(
            client=CLIENT_LABELS.get(report.client, report.client),
            status=t(STATUS_KEYS[status_key]),
            fixes=str(len(report.fixes)),
            login=t("login.summary.blocked") if failed_count else t("login.summary.available"),
        )
        self._set_network_facts(self._network_facts_from_report(report))

        title = case_title(report.case.value)
        client_label = CLIENT_LABELS.get(report.client, report.client)
        self.case_label.configure(
            text=(
                f"{title}{META_SEPARATOR}{t('report.confidence')} {report.confidence}"
                f"{META_SEPARATOR}{t('report.client')} {client_label}"
            )
        )

        cause_lines = [report.root_cause, "", report.browser_explanation]
        if report.notes:
            cause_lines.extend(["", t("report.notes")])
            cause_lines.extend(f"- {note}" for note in report.notes)
        if report.official_guidance:
            cause_lines.extend(["", t("report.official_guidance")])
            for guidance in report.official_guidance:
                cause_lines.append(f"- {guidance.title}")
                cause_lines.extend(f"  {index}. {step}" for index, step in enumerate(guidance.steps, start=1))
                cause_lines.append(f"  {guidance.source}: {guidance.url}")
        set_text(self.cause_text, "\n".join(cause_lines))

        self.layer_tree.delete(*self.layer_tree.get_children())
        for layer in report.layers:
            status = t("layer.pass") if layer.ok else t("layer.fail")
            tag = "ok" if layer.ok else "fail"
            display_name = layer_name(layer.name)
            self.layer_tree.insert("", tk.END, iid=layer.name, values=(status, display_name, layer.summary), tags=(tag,))

        self.fix_list.delete(0, tk.END)
        self._fix_actions = []
        if report.fixes:
            for fix in report.fixes:
                prefix = t("fix.auto") if fix.auto_applicable else t("fix.manual")
                self.fix_list.insert(tk.END, f"{prefix}{FIX_SEPARATOR}{fix.description}")
                self._fix_actions.append((report, fix))
        else:
            self.fix_list.insert(
                tk.END,
                t("fix.none_needed", client=CLIENT_LABELS.get(report.client, report.client)),
            )
            self.fix_list.itemconfigure(0, foreground=self._colors["text_muted"])

        self._set_detail_text(render_human(report, locale=get_locale()))

    def _show_scan_reports(self, reports: list[DiagnosisReport]) -> None:
        self._reports = reports
        self._report = reports[0] if reports else None
        self._report_by_item = {}
        self._fix_actions = []
        self._set_busy(False, t("status.scan_done") if reports else t("status.no_installed"))

        if not reports:
            self._apply_status_theme("warning", t("status.no_installed"))
            self._set_summary(client=t("scan.installed_clients"), status=t("status.no_installed"), fixes="0", login="0")
            if not self._network_facts:
                self._set_network_facts()
            self.case_label.configure(text=t("scan.no_installed"))
            set_text(self.cause_text, t("scan.no_installed"))
            self.layer_tree.delete(*self.layer_tree.get_children())
            self.fix_list.delete(0, tk.END)
            self.fix_list.insert(tk.END, t("scan.no_installed"))
            self._set_detail_text(t("scan.no_installed"))
            self.status_bar.configure(text=t("status.no_installed"))
            return

        any_unhealthy = any(report.status.value != "healthy" for report in reports)
        status_key = "unhealthy" if any_unhealthy else "healthy"
        self._apply_status_theme(status_key, t(STATUS_KEYS[status_key]))
        total_fixes = sum(len(report.fixes) for report in reports)
        healthy_count = sum(1 for report in reports if report.status.value == "healthy")
        self._set_summary(
            client=t("scan.installed_clients"),
            status=t(STATUS_KEYS[status_key]),
            fixes=str(total_fixes),
            login=f"{healthy_count}/{len(reports)}",
        )
        self._set_network_facts(self._network_facts_from_report(self._report) if self._report else None)
        self.case_label.configure(text=t("scan.summary", count=len(reports)))

        cause_lines = []
        self.layer_tree.delete(*self.layer_tree.get_children())
        for report in reports:
            label = CLIENT_LABELS.get(report.client, report.client)
            status = t("layer.pass") if report.status.value == "healthy" else t("layer.fail")
            tag = "ok" if report.status.value == "healthy" else "fail"
            iid = f"scan:{report.client}"
            self._report_by_item[iid] = report
            failed_count = sum(1 for layer in report.layers if not layer.ok)
            summary = t("scan.row_summary", case=case_title(report.case.value), failed=failed_count, fixes=len(report.fixes))
            self.layer_tree.insert("", tk.END, iid=iid, values=(status, label, summary), tags=(tag,))
            cause_lines.extend([f"[{label}] {report.root_cause}", ""])
            if report.official_guidance:
                cause_lines.append(f"{t('report.official_guidance')}: {report.official_guidance[0].title}")
                cause_lines.append("")

        self.fix_list.delete(0, tk.END)
        if total_fixes:
            for report in reports:
                label = CLIENT_LABELS.get(report.client, report.client)
                for fix in report.fixes:
                    prefix = t("fix.auto") if fix.auto_applicable else t("fix.manual")
                    self.fix_list.insert(tk.END, f"{label}{FIX_SEPARATOR}{prefix}{FIX_SEPARATOR}{fix.description}")
                    self._fix_actions.append((report, fix))
        else:
            self.fix_list.insert(tk.END, t("fix.none_needed_scan"))
            self.fix_list.itemconfigure(0, foreground=self._colors["text_muted"])

        set_text(self.cause_text, "\n".join(cause_lines).strip())
        self._set_detail_text("\n\n" + ("=" * 72 + "\n\n").join(render_human(report, locale=get_locale()) for report in reports))
        self.status_bar.configure(text=t("status.scan_done"))

    def _apply_status_theme(self, status: str, label: str) -> None:
        bg_key, fg_key, border_key, _default = Theme.STATUS.get(status, Theme.STATUS["warning"])
        bg = self._colors[bg_key]
        fg = self._colors[fg_key]
        border = self._colors[border_key]

        self.status_frame.configure(bg=bg, highlightbackground=border)
        for widget in (self.status_frame, *self.status_frame.winfo_children()):
            try:
                widget.configure(bg=bg)
            except tk.TclError:
                pass
        for widget in self.status_frame.winfo_children():
            for child in widget.winfo_children():
                try:
                    child.configure(bg=bg)
                except tk.TclError:
                    pass

        self.status_label.configure(text=label, bg=bg, fg=fg)
        self.case_label.configure(bg=bg)
        self.status_dot.configure(bg=bg)
        self.status_dot.itemconfigure(self._status_dot_id, fill=fg)

    def _on_layer_select(self, _event: tk.Event) -> None:
        if not self._report:
            return
        selected = self.layer_tree.selection()
        if not selected:
            return
        layer_name_key = selected[0]
        if layer_name_key in self._report_by_item:
            report = self._report_by_item[layer_name_key]
            self._report = report
            self._set_network_facts(self._network_facts_from_report(report))
            self._set_detail_text(render_human(report, locale=get_locale()))
            return
        for layer in self._report.layers:
            if layer.name == layer_name_key:
                detail = json.dumps(layer.details, ensure_ascii=False, indent=2)
                self._set_detail_text(f"{layer.summary}\n\n{detail}", readonly=False)
                break

    def _on_fix_double_click(self, _event: tk.Event) -> None:
        if not self._fix_actions:
            return
        selection = self.fix_list.curselection()
        if not selection:
            return
        report, fix = self._fix_actions[selection[0]]
        self._execute_fix(fix, report=report)

    def _check_login_only(self) -> None:
        client = self._selected_client()
        login = check_login_status(client, locale=get_locale())
        status, theme = self._login_status_display(login)
        self._set_summary(client=CLIENT_LABELS.get(client, client), status=t("login.summary.checked"), login=status)
        self._apply_status_theme(theme, status)
        self.case_label.configure(text=login.summary)
        path = login.auth_path or t("login_check.path_na")
        set_text(
            self.cause_text,
            f"{t('login_check.note')}\n{t('login_check.path', path=path)}",
        )
        self._set_detail_text(json.dumps(login.to_dict(), ensure_ascii=False, indent=2), readonly=False)
        self.status_bar.configure(text=t("status.login_check_done"))

    def _login_status_display(self, login: LoginStatus) -> tuple[str, str]:
        if login.logged_in:
            return t("status.logged_in"), "healthy"
        if login.details.get("supported") is False:
            return t("status.check_in_app"), "warning"
        return t("status.not_logged_in"), "warning"

    def _launch_device_auth(self) -> None:
        if self._selected_client() != "codex":
            messagebox.showinfo(t("dialog.hint.title"), t("dialog.device_auth.unsupported"))
            return
        if not messagebox.askyesno(t("dialog.device_auth.title"), t("dialog.device_auth.confirm")):
            return
        try:
            message = launch_codex_device_auth()
            messagebox.showinfo(t("dialog.device_auth.started"), message)
        except FileNotFoundError as exc:
            messagebox.showerror(t("dialog.device_auth.launch_failed"), str(exc))

    def _execute_fix(self, fix: FixAction, *, report: DiagnosisReport | None = None) -> None:
        report = report or self._report
        if fix.fix_id == "device-auth-fallback":
            if not messagebox.askyesno(t("dialog.device_auth.title"), t("dialog.device_auth.confirm")):
                return
            try:
                message = launch_codex_device_auth()
                messagebox.showinfo(t("dialog.device_auth.started"), message)
            except FileNotFoundError as exc:
                messagebox.showerror(t("dialog.device_auth.launch_failed"), str(exc))
            return
        if not fix.auto_applicable:
            messagebox.showinfo(
                t("dialog.manual_fix.title"),
                t("dialog.manual_fix.body", description=fix.description, command=fix.command),
            )
            return
        if not messagebox.askyesno(t("dialog.confirm_fix.title"), t("dialog.confirm_fix.body", description=fix.description)):
            return
        if not report:
            messagebox.showwarning(t("dialog.cannot_fix.title"), t("dialog.hint.run_first"))
            return
        try:
            message = apply_fix(report, fix)
            messagebox.showinfo(t("dialog.fix_done.title"), t("dialog.fix_done.body", message=message))
            self._refresh_repair_audit()
            self._run_diagnosis()
        except ValueError as exc:
            messagebox.showwarning(t("dialog.cannot_fix.title"), str(exc))

    def _apply_auto_fixes(self) -> None:
        if not self._report:
            messagebox.showinfo(t("dialog.hint.title"), t("dialog.hint.run_first"))
            return
        applicable = [fix for fix in self._report.fixes if fix.auto_applicable]
        if not applicable:
            messagebox.showinfo(t("dialog.hint.title"), t("fix.none_after_diag"))
            return
        if not messagebox.askyesno(t("dialog.autofix.title"), t("dialog.autofix.confirm", count=len(applicable))):
            return
        messages = apply_auto_fixes(self._report)
        messagebox.showinfo(t("dialog.fix_done.title"), t("dialog.fix_done.body", message="\n".join(messages)))
        self._refresh_repair_audit()
        self._run_diagnosis()

    def _sync_system_proxy(self) -> None:
        system = read_system_proxy()
        endpoint = system["endpoint"]
        if not endpoint.is_set:
            messagebox.showwarning(t("dialog.sync_fail.title"), t("dialog.sync_fail.no_proxy"))
            return
        if not messagebox.askyesno(t("dialog.sync.title"), t("dialog.sync.confirm", url=endpoint.url)):
            return
        try:
            message = sync_proxy(endpoint.url, clear=False)
            messagebox.showinfo(t("dialog.sync_done.title"), t("dialog.fix_done.body", message=message))
            self._refresh_repair_audit()
            self._run_diagnosis()
        except ValueError as exc:
            messagebox.showerror(t("dialog.sync_fail.title"), str(exc))

    def _copy_report(self) -> None:
        if not self._report and not self._reports:
            messagebox.showinfo(t("dialog.hint.title"), t("dialog.hint.run_first"))
            return
        self.clipboard_clear()
        if len(self._reports) > 1:
            self.clipboard_append(json.dumps([report.to_dict() for report in self._reports], ensure_ascii=False, indent=2))
        else:
            self.clipboard_append(render_json(self._report))
        self.status_bar.configure(text=t("status.copied_json"))

    def _show_about(self) -> None:
        popup = tk.Toplevel(self)
        popup.title(t("about.title"))
        popup.transient(self)
        popup.configure(bg=self._colors["surface"])
        popup.resizable(False, False)

        body = ttk.Frame(popup, style="Card.TFrame", padding=(28, 24, 28, 20))
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=1)

        if self._logo_photo:
            tk.Label(body, image=self._logo_photo, bg=self._colors["surface"], bd=0).grid(row=0, column=0, pady=(0, 12))

        tk.Label(
            body,
            text=APP_NAME,
            bg=self._colors["surface"],
            fg=self._colors["text"],
            font=self._fonts.ui_font(self._fonts.size_section, bold=True),
        ).grid(row=1, column=0, pady=(0, 4))

        tk.Label(
            body,
            text=t("about.description"),
            bg=self._colors["surface"],
            fg=self._colors["text_muted"],
            font=self._fonts.ui_font(self._fonts.size_small, bold=True),
        ).grid(row=2, column=0, pady=(0, 18))

        info = ttk.Frame(body, style="Card.TFrame")
        info.grid(row=3, column=0, sticky="ew")
        info.columnconfigure(0, weight=0)
        info.columnconfigure(1, weight=1)

        rows = [
            (t("about.author"), "Rick"),
            (t("about.version"), f"v{__version__}"),
            (t("about.copyright"), t("about.copyright_body")),
        ]
        for i, (label, value) in enumerate(rows):
            tk.Label(
                info,
                text=label,
                bg=self._colors["surface"],
                fg=self._colors["text_muted"],
                font=self._fonts.ui_font(self._fonts.size_small, bold=True),
                anchor=tk.W,
            ).grid(row=i, column=0, sticky="w", padx=(0, 16), pady=3)
            tk.Label(
                info,
                text=value,
                bg=self._colors["surface"],
                fg=self._colors["text"],
                font=self._fonts.ui_font(self._fonts.size_small, bold=True),
                anchor=tk.W,
            ).grid(row=i, column=1, sticky="w", pady=3)

        ttk.Button(
            body,
            text=t("dialog.close"),
            style="Primary.TButton",
            command=popup.destroy,
        ).grid(row=4, column=0, pady=(20, 0))

        popup.update_idletasks()
        popup_w = max(body.winfo_reqwidth() + 56, 360)
        popup_h = body.winfo_reqheight() + 48
        x = self.winfo_rootx() + (self.winfo_width() - popup_w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - popup_h) // 2
        popup.geometry(f"{popup_w}x{popup_h}+{max(x, 0)}+{max(y, 0)}")
        popup.grab_set()
        popup.focus_set()


def _run_gui_smoke() -> int:
    app = AuthKitApp()
    try:
        app.update_idletasks()
        icon_png = _asset_path(ICON_PNG_48)
        icon_ico = _asset_path(ICON_ICO)
        if not icon_png.is_file():
            raise RuntimeError(f"missing GUI PNG icon: {icon_png}")
        if not icon_ico.is_file():
            raise RuntimeError(f"missing GUI ICO icon: {icon_ico}")
        print("AuthKit GUI smoke passed.")
        print(f"- title: {app.title()}")
        print(f"- geometry: {app.geometry()}")
        print(f"- icon_png: {icon_png}")
        print(f"- icon_ico: {icon_ico}")
        return 0
    finally:
        app.destroy()


def main(argv: list[str] | None = None) -> int:
    if sys.platform != "win32":
        return 2
    parser = argparse.ArgumentParser(description="Open AuthKit GUI")
    parser.add_argument("--smoke", action="store_true", help="start and close the GUI for release smoke verification")
    args = parser.parse_args(argv)
    if args.smoke:
        return _run_gui_smoke()
    app = AuthKitApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
