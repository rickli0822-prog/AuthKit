"""GUI 主题与字体配置。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from authkit.ui.fonts import FontSet


class Theme:
    COLORS = {
        "bg": "#f3f7fb",
        "surface": "#ffffff",
        "surface_alt": "#f8fbfd",
        "surface_warm": "#f2f8f7",
        "border": "#dbe5ea",
        "border_soft": "#edf2f5",
        "text": "#132327",
        "text_secondary": "#405158",
        "text_muted": "#64737a",
        "code": "#08745f",
        "code_dim": "#1f8c78",
        "primary": "#0b7a75",
        "primary_hover": "#075f5b",
        "primary_soft": "#e1f4f2",
        "primary_border": "#98d8d2",
        "success_bg": "#e9f8f1",
        "success": "#087b58",
        "success_border": "#a8decc",
        "error_bg": "#fff0f0",
        "error": "#b4232e",
        "error_border": "#f0b8bd",
        "warning_bg": "#fff8e5",
        "warning": "#9a6700",
        "warning_border": "#f2d58a",
        "accent": "#2669b8",
        "accent_soft": "#e8f1fb",
        "selection": "#d9ece9",
        "toolbar": "#ffffff",
        "header_bg": "#ffffff",
        "header_rule": "#0b7a75",
    }

    STATUS = {
        "healthy": ("success_bg", "success", "success_border", "系统状态正常"),
        "unhealthy": ("error_bg", "error", "error_border", "检测到登录障碍"),
        "warning": ("warning_bg", "warning", "warning_border", "正在检查"),
    }


def apply_theme(root: tk.Tk, fonts: FontSet) -> ttk.Style:
    colors = Theme.COLORS
    root.configure(bg=colors["bg"])

    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(".", background=colors["bg"], foreground=colors["text"], font=fonts.ui_font())
    style.configure("App.TFrame", background=colors["bg"])
    style.configure("Card.TFrame", background=colors["surface"])
    style.configure("Toolbar.TFrame", background=colors["toolbar"])
    style.configure("Header.TFrame", background=colors["header_bg"])
    style.configure("Panel.TFrame", background=colors["surface"])
    style.configure("PanelAlt.TFrame", background=colors["surface_alt"])
    style.configure("TNotebook", background=colors["surface"], borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        background=colors["surface_alt"],
        foreground=colors["text_secondary"],
        font=fonts.ui_font(fonts.size_small, bold=True),
        padding=(14, 8),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", colors["surface"]), ("active", colors["primary_soft"])],
        foreground=[("selected", colors["primary"]), ("active", colors["text"])],
    )

    style.configure(
        "Title.TLabel",
        background=colors["header_bg"],
        foreground=colors["text"],
        font=fonts.ui_font(fonts.size_title, bold=True),
    )
    style.configure(
        "Subtitle.TLabel",
        background=colors["header_bg"],
        foreground=colors["text_muted"],
        font=fonts.ui_font(fonts.size_small, bold=True),
    )
    style.configure(
        "Badge.TLabel",
        background=colors["primary_soft"],
        foreground=colors["primary"],
        font=fonts.ui_font(fonts.size_caption, bold=True),
    )
    style.configure(
        "Caption.TLabel",
        background=colors["surface"],
        foreground=colors["text_muted"],
        font=fonts.ui_font(fonts.size_caption, bold=True),
    )
    style.configure(
        "FieldLabel.TLabel",
        background=colors["toolbar"],
        foreground=colors["text_secondary"],
        font=fonts.ui_font(fonts.size_caption, bold=True),
    )
    style.configure("Section.TLabelframe", background=colors["surface"], borderwidth=1, relief="solid")
    style.configure(
        "Section.TLabelframe.Label",
        background=colors["surface"],
        foreground=colors["text"],
        font=fonts.ui_font(fonts.size_section, bold=True),
    )
    style.configure(
        "StatusBar.TLabel",
        background=colors["surface_alt"],
        foreground=colors["text_muted"],
        font=fonts.ui_font(fonts.size_caption, bold=True),
    )
    style.configure(
        "Busy.Horizontal.TProgressbar",
        troughcolor=colors["surface"],
        background=colors["primary"],
        bordercolor=colors["border"],
        lightcolor=colors["primary"],
        darkcolor=colors["primary"],
    )

    style.configure(
        "Primary.TButton",
        font=fonts.ui_font(bold=True),
        padding=(22, 11),
        background=colors["primary"],
        foreground="#ffffff",
        borderwidth=0,
    )
    style.map("Primary.TButton", background=[("active", colors["primary_hover"]), ("disabled", "#9ac9c4")])

    style.configure(
        "Ghost.TButton",
        font=fonts.ui_font(bold=True),
        padding=(14, 9),
        background=colors["surface"],
        foreground=colors["text"],
        bordercolor=colors["border"],
        lightcolor=colors["surface"],
        darkcolor=colors["border"],
    )
    style.map("Ghost.TButton", background=[("active", colors["surface_alt"])])

    style.configure(
        "TCombobox",
        padding=10,
        font=fonts.ui_font(bold=True),
        fieldbackground=colors["surface_alt"],
        readonlybackground=colors["surface_alt"],
        background=colors["surface_alt"],
        foreground=colors["text"],
        selectbackground=colors["surface_alt"],
        selectforeground=colors["text"],
        arrowcolor=colors["code"],
        bordercolor=colors["border"],
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", colors["surface_alt"]), ("disabled", colors["surface"])],
        foreground=[("readonly", colors["text"]), ("disabled", colors["text_muted"])],
        background=[("readonly", colors["surface_alt"])],
    )
    style.configure(
        "Treeview",
        background=colors["surface"],
        fieldbackground=colors["surface"],
        foreground=colors["text"],
        rowheight=42,
        font=fonts.mono_font(),
        bordercolor=colors["border_soft"],
        lightcolor=colors["surface"],
        darkcolor=colors["border_soft"],
    )
    style.configure(
        "Treeview.Heading",
        background=colors["surface_alt"],
        foreground=colors["text_secondary"],
        font=fonts.ui_font(fonts.size_small, bold=True),
    )
    style.map("Treeview", background=[("selected", colors["selection"])], foreground=[("selected", colors["text"])])

    return style


def make_text(
    parent: tk.Misc,
    *,
    fonts: FontSet,
    mono: bool = False,
    height: int = 4,
    readonly: bool = True,
    wrap: str = tk.WORD,
) -> tk.Text:
    colors = Theme.COLORS
    widget_font = fonts.mono_font() if mono else fonts.ui_font()
    text_color = colors["code"] if mono else colors["text"]
    widget = tk.Text(
        parent,
        height=height,
        wrap=wrap,
        font=widget_font,
        bg=colors["surface"],
        fg=text_color,
        insertbackground=colors["code"],
        relief=tk.FLAT,
        padx=14,
        pady=12,
        highlightthickness=1,
        highlightbackground=colors["border"],
        highlightcolor=colors["code"],
        borderwidth=0,
    )
    if readonly:
        widget.configure(state=tk.DISABLED)
    return widget


def make_scroll_text(
    parent: tk.Misc,
    *,
    fonts: FontSet,
    mono: bool = False,
    height: int = 4,
    readonly: bool = True,
    wrap: str = tk.WORD,
    expand: bool = True,
) -> tk.Text:
    """带垂直滚动条的文本区；内容超出时仍可完整查看。"""
    container = ttk.Frame(parent)
    pack_kwargs = {"fill": tk.BOTH}
    if expand:
        pack_kwargs["expand"] = True
    container.pack(**pack_kwargs)
    container.grid_rowconfigure(0, weight=1)
    container.grid_columnconfigure(0, weight=1)

    text = make_text(
        container,
        fonts=fonts,
        mono=mono,
        height=height,
        readonly=readonly,
        wrap=wrap,
    )
    text.grid(row=0, column=0, sticky="nsew")

    scroll_y = ttk.Scrollbar(container, orient=tk.VERTICAL, command=text.yview)
    scroll_y.grid(row=0, column=1, sticky="ns")
    text.configure(yscrollcommand=scroll_y.set)

    if wrap == tk.NONE:
        scroll_x = ttk.Scrollbar(container, orient=tk.HORIZONTAL, command=text.xview)
        scroll_x.grid(row=1, column=0, sticky="ew")
        text.configure(xscrollcommand=scroll_x.set)

    return text


def bind_mousewheel(text: tk.Text, widget: tk.Misc) -> None:
    """在 Windows 上为文本区绑定滚轮。"""

    def _on_mousewheel(event: tk.Event) -> None:
        if event.delta:
            text.yview_scroll(int(-1 * (event.delta / 120)), "units")

    widget.bind("<Enter>", lambda _e: widget.bind_all("<MouseWheel>", _on_mousewheel))
    widget.bind("<Leave>", lambda _e: widget.unbind_all("<MouseWheel>"))


def attach_tree_scrollbars(tree: ttk.Treeview, parent: tk.Misc) -> None:
    parent.grid_rowconfigure(0, weight=1)
    parent.grid_columnconfigure(0, weight=1)
    tree.grid(row=0, column=0, sticky="nsew")
    scroll_y = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
    scroll_y.grid(row=0, column=1, sticky="ns")
    scroll_x = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=tree.xview)
    scroll_x.grid(row=1, column=0, sticky="ew")
    tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)


def attach_list_scrollbars(listbox: tk.Listbox, parent: tk.Misc) -> None:
    parent.grid_rowconfigure(0, weight=1)
    parent.grid_columnconfigure(0, weight=1)
    listbox.grid(row=0, column=0, sticky="nsew")
    scroll_y = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=listbox.yview)
    scroll_y.grid(row=0, column=1, sticky="ns")
    scroll_x = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=listbox.xview)
    scroll_x.grid(row=1, column=0, sticky="ew")
    listbox.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)


def set_text(widget: tk.Text, content: str, *, readonly: bool = True) -> None:
    widget.configure(state=tk.NORMAL)
    widget.delete("1.0", tk.END)
    widget.insert(tk.END, content)
    widget.configure(state=tk.DISABLED if readonly else tk.NORMAL)
