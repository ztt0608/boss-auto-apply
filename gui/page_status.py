# -*- coding: utf-8 -*-
"""状态页：一眼看清现在能不能跑 —— 浏览器、登录、今日进度、候选池。"""
import tkinter as tk
from tkinter import ttk

from . import store, theme

AUTO_REFRESH_MS = 10000


class StatusPage(ttk.Frame):
    def __init__(self, master, on_status=None):
        ttk.Frame.__init__(self, master, style="TFrame")
        self.on_status = on_status or (lambda _msg: None)
        self._job = None

        head = ttk.Frame(self, padding=(12, 10))
        head.pack(fill="x")
        ttk.Button(head, text="立即刷新", command=self.refresh).pack(side="left")
        self.auto = tk.BooleanVar(value=False)
        ttk.Checkbutton(head, text="每 10 秒自动刷新", variable=self.auto,
                        command=self._toggle_auto).pack(side="left", padx=12)
        self.updated = tk.StringVar(value="还没刷新过")
        ttk.Label(head, textvariable=self.updated, style="Muted.TLabel").pack(side="left")

        wrap = ttk.Frame(self, padding=(12, 0))
        wrap.pack(fill="x")
        self.cards = {}
        for key, title in (("cdp", "调试端口 9223"), ("page", "Boss 页面"),
                           ("login", "登录状态"), ("today", "今日投递"),
                           ("pool", "候选池"), ("config", "当前配置")):
            self.cards[key] = self._card(wrap, title)

        self.detail = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.detail, style="Muted.TLabel",
                  padding=(12, 12), wraplength=760, justify="left").pack(anchor="w")

        self.refresh()

    def _card(self, parent, title):
        frame = ttk.LabelFrame(parent, text=title, padding=10)
        frame.pack(fill="x", pady=(0, 8))
        value = tk.StringVar(value="—")
        ttk.Label(frame, textvariable=value, font=(theme.FONT_FAMILY, 11, "bold"),
                  background=theme.COLOR_BG).pack(anchor="w")
        return value

    def _set(self, key, text, color=None):
        self.cards[key].set(text)

    # ---------------------------------------------------------- 刷新
    def _toggle_auto(self):
        if self.auto.get():
            self._loop()
        elif self._job:
            self.after_cancel(self._job)
            self._job = None

    def _loop(self):
        self.refresh()
        if self.auto.get():
            self._job = self.after(AUTO_REFRESH_MS, self._loop)

    def refresh(self):
        data = store.probe_status()

        self._set("cdp", "已就绪" if data["cdp"] else "未连通")
        if data["cdp"]:
            self._set("page", "已打开（%d 个标签页）" % data["pages"])
        else:
            self._set("page", "—")

        login = data["login"]
        self._set("login", {True: "已登录", False: "已掉登录，需人工登录",
                            None: "测不出来（页面没开？）"}[login])

        today = data["today"]
        if today is None:
            self._set("today", "还没有投递记录")
        else:
            self._set("today", "已投 %d 个（失败 %d / 重复 %d / 死岗 %d）" % (
                today["sent"], today["failed"], today["already"], today["dead"]))

        pool = data["pool"]
        self._set("pool", "未建档" if pool is None else
                  "共 %d 个，未投 %d 个（建档于 %s）" % (
                      pool["total"], pool["remain"], pool["date"]))

        cfg = store.load_config()
        self._set("config", "%d 个关键词 / %d 个优先城市 / 每日 %d 个" % (
            len(cfg["keywords"]), len(cfg["cities_priority"]), cfg["daily_target"]))

        tips = []
        if not data["cdp"]:
            tips.append("· 先点「运行」页里的「打开调试浏览器」，确认 Edge 起来了。")
        if data["cdp"] and not data["pages"]:
            tips.append("· 9223 通了但没有标签页 —— 关掉所有用本项目 profile 的 Edge 后重开。")
        if login is False:
            tips.append("· 掉登录了：在 Edge 里手动登录 Boss（脚本绝不会替你登录）。")
        if pool is None:
            tips.append("· 还没有候选池，第一次投递前会先自动扫描（约 60-90 分钟）。")
        elif pool["remain"] == 0:
            tips.append("· 候选池已投完，下次投递会自动重扫。")
        if not store.has_config():
            tips.append("· 还没生成 config.json，当前用的是内置的 IT 运维方向默认值。")
        self.detail.set("\n".join(tips) if tips else "一切正常，可以直接投递。")

        import time
        self.updated.set("更新于 %s" % time.strftime("%H:%M:%S"))
