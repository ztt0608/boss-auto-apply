# -*- coding: utf-8 -*-
"""主窗口：三个页签（配置 / 运行 / 状态）+ 底部状态条。"""
import tkinter as tk
from tkinter import ttk

from . import store, theme
from .page_config import ConfigPage
from .page_run import RunPage
from .page_status import StatusPage

APP_TITLE = "Boss 自动投递 · 控制台"
APP_SIZE = "900x680"


class App(tk.Tk):
    def __init__(self):
        tk.Tk.__init__(self)
        self.title(APP_TITLE)
        self.geometry(APP_SIZE)
        self.minsize(820, 560)
        self.configure(background=theme.COLOR_BG)
        theme.configure(self)

        self.status_var = tk.StringVar(value="就绪")

        self.notebook = notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        self.config_page = ConfigPage(notebook, on_status=self.set_status)
        self.run_page = RunPage(notebook, on_status=self.set_status)
        self.status_page = StatusPage(notebook, on_status=self.set_status)

        notebook.add(self.config_page, text="  配置  ")
        notebook.add(self.run_page, text="  运行  ")
        notebook.add(self.status_page, text="  状态  ")
        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        bar = ttk.Frame(self, padding=(12, 6))
        bar.pack(fill="x")
        ttk.Label(bar, textvariable=self.status_var, style="Muted.TLabel").pack(side="left")
        ttk.Label(bar, text="目录：%s" % store.BASE_DIR,
                  style="Muted.TLabel").pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------ 行为
    def set_status(self, message):
        self.status_var.set(message)

    def _on_tab_changed(self, _event):
        """切到「状态」页时自动刷新一次，避免看到过期数据。"""
        try:
            index = self.notebook.index(self.notebook.select())
        except Exception:
            return
        if index == 2:
            self.status_page.refresh()

    def _on_close(self):
        if self.run_page.runner.running:
            from tkinter import messagebox
            if not messagebox.askyesno("任务还在跑",
                                       "投递任务正在执行，关掉窗口会中断它。确定退出吗？"):
                return
            self.run_page.runner.stop()
        self.destroy()
