# -*- coding: utf-8 -*-
"""界面主题：配色变量、字体、通用容器。

规范：颜色与字号统一在此定义，业务页面禁止硬编码色值（对应前端规范第 4 条）。
"""
import tkinter as tk
from tkinter import ttk

# ---------------------------------------------------------------- 配色变量
COLOR_BG = "#f4f5f7"
COLOR_PANEL = "#ffffff"
COLOR_BORDER = "#dcdfe5"
COLOR_TEXT = "#1f2329"
COLOR_MUTED = "#6b7280"
COLOR_PRIMARY = "#2563eb"
COLOR_PRIMARY_ACTIVE = "#1d4ed8"
COLOR_SUCCESS = "#16a34a"
COLOR_WARN = "#d97706"
COLOR_DANGER = "#dc2626"
COLOR_LOG_BG = "#1b1d21"
COLOR_LOG_FG = "#d6d9de"

FONT_FAMILY = "Microsoft YaHei UI"
FONT_MONO = "Consolas"
FONT_SIZE = 10
FONT_SIZE_SMALL = 9


def configure(root):
    """应用全局 ttk 样式；返回 style 便于局部微调。"""
    style = ttk.Style(root)
    # vista / winnative 下 TButton 背景不可控，统一用 clam 保证配色一致
    if "clam" in style.theme_names():
        style.theme_use("clam")

    style.configure(".", background=COLOR_BG, foreground=COLOR_TEXT,
                    font=(FONT_FAMILY, FONT_SIZE))
    style.configure("TFrame", background=COLOR_BG)
    style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT)
    style.configure("Muted.TLabel", background=COLOR_BG, foreground=COLOR_MUTED)
    style.configure("Panel.TLabel", background=COLOR_PANEL, foreground=COLOR_TEXT)
    style.configure("TLabelframe", background=COLOR_BG, bordercolor=COLOR_BORDER)
    style.configure("TLabelframe.Label", background=COLOR_BG, foreground=COLOR_TEXT,
                    font=(FONT_FAMILY, FONT_SIZE, "bold"))
    style.configure("TButton", padding=(12, 5), bordercolor=COLOR_BORDER)
    style.configure("Accent.TButton", foreground="#ffffff", background=COLOR_PRIMARY,
                    bordercolor=COLOR_PRIMARY)
    style.map("Accent.TButton",
              background=[("active", COLOR_PRIMARY_ACTIVE), ("disabled", COLOR_BORDER)])
    style.configure("Danger.TButton", foreground="#ffffff", background=COLOR_DANGER,
                    bordercolor=COLOR_DANGER)
    style.map("Danger.TButton", background=[("active", "#b91c1c")])
    style.configure("TNotebook", background=COLOR_BG, bordercolor=COLOR_BORDER)
    style.configure("TNotebook.Tab", padding=(16, 7))
    style.configure("TCheckbutton", background=COLOR_BG)
    style.configure("TSpinbox", padding=(4, 3))
    style.configure("Status.TLabel", background=COLOR_PANEL, foreground=COLOR_MUTED,
                    font=(FONT_FAMILY, FONT_SIZE_SMALL))
    return style


# ---------------------------------------------------------------- 通用容器
class ScrollableFrame(ttk.Frame):
    """带纵向滚动条的容器；内容超过可视高度时可滚动。"""

    def __init__(self, master, **kwargs):
        ttk.Frame.__init__(self, master, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, background=COLOR_BG,
                                borderwidth=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, style="TFrame")

        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_wheel(self.canvas)

    def _on_inner_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)

    def _bind_wheel(self, widget):
        widget.bind("<MouseWheel>", self._on_wheel, add="+")

    def _on_wheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    def bind_wheel_recursive(self, widget=None):
        """让容器内所有子控件也响应滚轮（Listbox/Text 自带滚动的除外）。"""
        node = widget if widget is not None else self.inner
        for child in node.winfo_children():
            if isinstance(child, (tk.Listbox, tk.Text)):
                continue
            self._bind_wheel(child)
            self.bind_wheel_recursive(child)


def section(parent, title, **pack_kwargs):
    """生成一个带标题的分组框。"""
    frame = ttk.LabelFrame(parent, text=title, padding=10)
    opts = {"fill": "x", "padx": 12, "pady": (10, 0)}
    opts.update(pack_kwargs or {})
    frame.pack(**opts)
    return frame


def hint(parent, text):
    """灰色小字说明。"""
    label = ttk.Label(parent, text=text, style="Muted.TLabel", wraplength=760,
                      justify="left")
    label.pack(anchor="w", pady=(2, 6))
    return label


def listbox_with_scroll(parent, height=6, select_mode=tk.EXTENDED):
    """返回一个 (frame, listbox) —— 列表 + 滚动条的组合。"""
    frame = ttk.Frame(parent)
    vsb = ttk.Scrollbar(frame, orient="vertical")
    box = tk.Listbox(frame, height=height, selectmode=select_mode,
                     activestyle="none", borderwidth=1, relief="solid",
                     font=(FONT_FAMILY, FONT_SIZE), exportselection=False)
    box.configure(yscrollcommand=vsb.set)
    vsb.configure(command=box.yview)
    box.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")
    return frame, box
