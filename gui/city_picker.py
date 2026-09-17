# -*- coding: utf-8 -*-
"""城市选择对话框：按省份浏览 + 搜索过滤 + 多选。

城市表优先用 Boss 官方在线数据（后台线程拉取），失败自动回退内置表，
界面不会因此卡住。
"""
import threading
import tkinter as tk
from tkinter import ttk

from . import store
from . import theme

ALL = "全部城市"


class CityPicker(tk.Toplevel):
    """返回方式：通过 on_pick(names, target) 回调把选中的城市名交回调用方。"""

    def __init__(self, master, on_pick, target="priority"):
        tk.Toplevel.__init__(self, master)
        self.on_pick = on_pick
        self.target = target
        self.flat = {}
        self.provinces = {}
        self._filtered = []

        self.title("选择城市")
        self.geometry("760x520")
        self.transient(master)
        self.grab_set()
        self.configure(background=theme.COLOR_BG)

        self._build()
        self._load_async()

    # ------------------------------------------------------------ 构建
    def _build(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="省份：").pack(side="left")
        self.province_var = tk.StringVar(value="加载中…")
        self.province_box = ttk.Combobox(top, textvariable=self.province_var, width=14,
                                         state="readonly")
        self.province_box.pack(side="left", padx=(4, 16))
        self.province_box.bind("<<ComboboxSelected>>", lambda _e: self._refresh())

        ttk.Label(top, text="搜索：").pack(side="left")
        self.search_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.search_var, width=22)
        entry.pack(side="left", padx=(4, 0))
        entry.bind("<KeyRelease>", lambda _e: self._refresh())
        entry.focus_set()

        body = ttk.Frame(self, padding=(10, 0))
        body.pack(fill="both", expand=True)

        frame, self.box = theme.listbox_with_scroll(body, height=18,
                                                    select_mode=tk.MULTIPLE)
        frame.pack(fill="both", expand=True)

        side = ttk.Frame(body)
        side.pack(fill="x", pady=(6, 0))
        ttk.Button(side, text="全选当前列表", command=self._select_all).pack(side="left")
        ttk.Button(side, text="清空选择", command=self._clear_selection).pack(side="left",
                                                                             padx=6)
        self.tip_var = tk.StringVar(value="提示：Ctrl / Shift 可多选；输入省份名可整省展开。")
        ttk.Label(side, textvariable=self.tip_var, style="Muted.TLabel").pack(side="left",
                                                                              padx=12)

        bottom = ttk.Frame(self, padding=10)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="加入优先城市", style="Accent.TButton",
                   command=lambda: self._emit("priority")).pack(side="right")
        ttk.Button(bottom, text="加入兜底城市",
                   command=lambda: self._emit("backup")).pack(side="right", padx=8)
        ttk.Button(bottom, text="关闭", command=self.destroy).pack(side="right")

    # ------------------------------------------------------------ 数据
    def _load_async(self):
        """后台拉城市表。

        ★坑：tkinter 的 after() 不能在非主线程调用（会抛
        "main thread is not in main loop"），所以这里用 Event + 主线程轮询。
        """
        self._loaded = threading.Event()

        def work():
            try:
                flat, provinces = store.load_city_table(online=True)
                self.flat, self.provinces = flat, provinces
            finally:
                self._loaded.set()

        threading.Thread(target=work, daemon=True).start()
        self.after(150, self._wait_loaded)

    def _wait_loaded(self):
        if self._loaded.is_set():
            self._on_loaded()
            return
        self.after(150, self._wait_loaded)

    def _on_loaded(self):
        names = [ALL] + sorted(self.provinces.keys())
        self.province_box.configure(values=names)
        self.province_var.set(ALL)
        online = bool(self.provinces)
        self.tip_var.set(
            "城市表已加载（%s）：%d 个城市 / %d 个省份" %
            ("在线" if online else "内置表", len(self.flat), len(self.provinces)))
        self._refresh()

    def _candidates(self):
        """按当前省份 + 搜索词算出待展示的城市名列表。"""
        province = self.province_var.get()
        keyword = self.search_var.get().strip()

        if province and province != ALL and province in self.provinces:
            names = [name for name, _code in self.provinces[province]]
        elif keyword and keyword in self.provinces:
            names = [name for name, _code in self.provinces[keyword]]
        else:
            names = sorted(self.flat.keys())
            if province and province != ALL and province in self.flat:
                names = [province]
        if keyword and not (province and province in self.provinces):
            names = [n for n in names if keyword in n]
        return names

    def _refresh(self):
        names = self._candidates()
        self._filtered = names
        self.box.delete(0, tk.END)
        for name in names:
            self.box.insert(tk.END, name)

    # ------------------------------------------------------------ 交互
    def _select_all(self):
        self.box.selection_set(0, tk.END)

    def _clear_selection(self):
        self.box.selection_clear(0, tk.END)

    def _emit(self, target):
        picked = [self._filtered[i] for i in self.box.curselection()]
        if not picked:
            self.tip_var.set("还没选城市 —— 先在列表里选中（可多选）。")
            return
        resolved, unresolved = store.job_config.resolve_cities(
            picked, self.flat, self.provinces)
        if unresolved:
            self.tip_var.set("这些城市查不到编码，已跳过：%s" % "、".join(unresolved))
        self.on_pick([name for name, _code in resolved], target)
        self.tip_var.set("已加入 %d 个城市到 %s。" % (
            len(resolved), "优先城市" if target == "priority" else "兜底城市"))
