# -*- coding: utf-8 -*-
"""配置页：把 config.json 的每一项都做成可视化控件。

任何行业都能在这里改岗位方向，不需要碰代码。
"""
import tkinter as tk
from tkinter import ttk, messagebox

from . import store, theme

# 行业预设：选一个即可一键套用关键词，服务非 IT 用户
INDUSTRY_PRESETS = {
    "IT运维 / 网络工程": ["桌面运维", "网络工程师", "系统运维", "运维", "弱电", "网络管理员",
                          "Linux运维", "云计算运维", "云原生", "SRE", "服务器运维", "IT运维"],
    "后端开发": ["后端开发", "Java", "Python", "Go", "Golang", "服务端开发", "微服务"],
    "前端开发": ["前端开发", "Web前端", "React", "Vue", "JavaScript", "小程序开发"],
    "软件测试": ["软件测试", "测试工程师", "自动化测试", "测试开发", "QA"],
    "产品经理": ["产品经理", "产品助理", "需求分析", "产品运营"],
    "UI / 设计": ["UI设计", "视觉设计", "平面设计", "交互设计", "网页设计"],
    "销售 / 商务": ["销售代表", "客户经理", "商务拓展", "BD", "渠道销售"],
    "人力 / 行政": ["人事专员", "招聘专员", "HRBP", "行政专员", "前台"],
    "财务 / 会计": ["会计", "财务专员", "出纳", "成本会计", "财务分析"],
    "新媒体 / 运营": ["新媒体运营", "内容运营", "短视频运营", "社群运营", "电商运营"],
    "机械 / 电气": ["机械设计", "电气工程师", "自动化工程师", "PLC", "结构设计"],
    "教师 / 培训": ["教师", "助教", "培训讲师", "教务管理", "课程顾问"],
}


class ConfigPage(ttk.Frame):
    def __init__(self, master, on_status=None):
        ttk.Frame.__init__(self, master, style="TFrame")
        self.on_status = on_status or (lambda _msg: None)
        self.cfg = store.load_config()

        self.scroll = theme.ScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True)
        body = self.scroll.inner

        self._build_industry(body)
        self._build_cities(body)
        self._build_filters(body)
        self._build_pace(body)
        self._build_actions(body)

        self.scroll.bind_wheel_recursive()

    # ---------------------------------------------------------- 小工具
    def _say(self, msg):
        self.on_status(msg)

    @staticmethod
    def _grid(parent, row, label, widget, unit=""):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        widget.grid(row=row, column=1, sticky="w", pady=3, padx=(6, 0))
        if unit:
            ttk.Label(parent, text=unit, style="Muted.TLabel").grid(
                row=row, column=2, sticky="w", padx=(6, 0))

    def _tag_editor(self, parent, title, values, tip):
        """关键词类编辑区：列表 + 输入框 + 增删。"""
        frame = theme.section(parent, title)
        theme.hint(frame, tip)

        holder, box = theme.listbox_with_scroll(frame, height=5)
        holder.pack(fill="x")
        for value in values:
            box.insert(tk.END, value)

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(6, 0))
        var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=var)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _e: add())

        def add():
            text = var.get().strip()
            if not text:
                return
            if text in box.get(0, tk.END):
                self._say("「%s」已经在列表里了。" % text)
                return
            box.insert(tk.END, text)
            var.set("")

        def remove():
            for index in reversed(box.curselection()):
                box.delete(index)

        ttk.Button(row, text="添加", command=add).pack(side="left", padx=6)
        ttk.Button(row, text="删除选中", command=remove).pack(side="left")
        return box

    # ---------------------------------------------------------- 各区块
    def _build_industry(self, parent):
        frame = theme.section(parent, "岗位方向")
        theme.hint(frame, "决定脚本去搜什么岗位。先套一个行业预设，再按需增删，最省事。")

        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text="行业预设：").pack(side="left")
        self.preset_var = tk.StringVar()
        box = ttk.Combobox(top, textvariable=self.preset_var, width=20, state="readonly",
                           values=["（自定义）"] + sorted(INDUSTRY_PRESETS.keys()))
        box.current(0)
        box.pack(side="left", padx=(6, 0))
        ttk.Button(top, text="套用到关键词", command=self._apply_preset).pack(side="left",
                                                                             padx=8)

        self.keyword_box = self._tag_editor(
            frame, "搜索关键词（%d）" % len(self.cfg["keywords"]), self.cfg["keywords"],
            "一行一个，也可以直接在输入框里写完后回车。中文逗号/分号分隔可一次加多个。")
        self.exclude_box = self._tag_editor(
            frame, "排除关键词", self.cfg["exclude_keywords"],
            "岗位标题里出现这些词就跳过。例如不想投销售岗，就填「销售,电销」。")

    def _build_cities(self, parent):
        frame = theme.section(parent, "目标城市")
        theme.hint(frame,
                   "优先城市先搜，搜不够再用兜底城市补。Boss 不支持省份聚合码，"
                   "选省份会自动展开成该省所有市。")

        for attr, title in (("priority_box", "优先城市"), ("backup_box", "兜底城市")):
            holder, box = theme.listbox_with_scroll(frame, height=6)
            ttk.Label(frame, text=title).pack(anchor="w", pady=(8, 2))
            holder.pack(fill="x")
            key = "cities_priority" if attr == "priority_box" else "cities_backup"
            for value in self.cfg[key]:
                box.insert(tk.END, value)
            setattr(self, attr, box)

            bar = ttk.Frame(frame)
            bar.pack(fill="x", pady=(6, 0))
            ttk.Button(bar, text="添加城市",
                       command=lambda b=box: self._pick_city(b)).pack(side="left")
            ttk.Button(bar, text="删除选中",
                       command=lambda b=box: [b.delete(i) for i in reversed(b.curselection())]
                       ).pack(side="left", padx=6)
            ttk.Button(bar, text="清空",
                       command=lambda b=box: b.delete(0, tk.END)).pack(side="left")

    def _build_filters(self, parent):
        frame = theme.section(parent, "筛选条件")
        theme.hint(frame, "不满足条件的岗位会被自动跳过，不消耗投递额度。")

        grid = ttk.Frame(frame)
        grid.pack(fill="x")

        self.sal_on = tk.BooleanVar(value=self.cfg["salary"]["enabled"])
        row = ttk.Frame(grid)
        row.grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Checkbutton(row, text="启用薪资筛选", variable=self.sal_on).pack(side="left")

        self.sal_min_month = tk.StringVar(value=self.cfg["salary"]["min_month"])
        self.sal_max_month = tk.StringVar(value=self.cfg["salary"]["max_month"])
        self.sal_min_day = tk.StringVar(value=self.cfg["salary"]["min_day"])
        self.sal_max_day = tk.StringVar(value=self.cfg["salary"]["max_day"])
        self._grid(grid, 1, "月薪区间",
                   ttk.Entry(grid, textvariable=self.sal_min_month, width=8), "K")
        ttk.Label(grid, text="–").grid(row=1, column=2)
        ttk.Entry(grid, textvariable=self.sal_max_month, width=8).grid(row=1, column=3,
                                                                       sticky="w")
        ttk.Label(grid, text="K", style="Muted.TLabel").grid(row=1, column=4, sticky="w")

        self._grid(grid, 2, "日薪区间",
                   ttk.Entry(grid, textvariable=self.sal_min_day, width=8), "元")
        ttk.Label(grid, text="–").grid(row=2, column=2)
        ttk.Entry(grid, textvariable=self.sal_max_day, width=8).grid(row=2, column=3,
                                                                     sticky="w")
        ttk.Label(grid, text="元", style="Muted.TLabel").grid(row=2, column=4, sticky="w")

        self.hr_days = tk.IntVar(value=self.cfg["hr_active_days"])
        self._grid(grid, 3, "HR 活跃度",
                   ttk.Spinbox(grid, from_=1, to=30, width=6, textvariable=self.hr_days),
                   "天内在线（超过则跳过）")

        self.intern_on = tk.BooleanVar(value=self.cfg["intern_priority"])
        ttk.Checkbutton(grid, text="实习 / 应届岗位优先",
                        variable=self.intern_on).grid(row=4, column=1, sticky="w", pady=3)

        self.intern_words = tk.StringVar(value=",".join(self.cfg["intern_keywords"]))
        self._grid(grid, 5, "实习关键词",
                   ttk.Entry(grid, textvariable=self.intern_words, width=40),
                   "逗号分隔")

        self.intern_regex = tk.StringVar(value=self.cfg["intern_regex"] or "")
        self._grid(grid, 6, "届数正则",
                   ttk.Entry(grid, textvariable=self.intern_regex, width=40),
                   r"如 \d+届，留空表示不启用")

    def _build_pace(self, parent):
        frame = theme.section(parent, "投递节奏")
        theme.hint(frame,
                   "数值越大请求越频繁，被风控的概率也越高。默认 50/天是实测比较稳的量，"
                   "不建议一上来就调高。")
        grid = ttk.Frame(frame)
        grid.pack(fill="x")

        self.daily_target = tk.IntVar(value=self.cfg["daily_target"])
        self._grid(grid, 0, "每日目标",
                   ttk.Spinbox(grid, from_=1, to=200, width=8, textvariable=self.daily_target),
                   "个 / 天")

        self.batch_counts = tk.StringVar(
            value=",".join(str(x) for x in self.cfg["batch_counts"]))
        self._grid(grid, 1, "分批数量",
                   ttk.Entry(grid, textvariable=self.batch_counts, width=20),
                   "如 17,17,16 —— 三批各投多少")

        self.pool_capacity = tk.IntVar(value=self.cfg["pool_capacity"])
        self._grid(grid, 2, "候选池容量",
                   ttk.Spinbox(grid, from_=10, to=500, width=8,
                               textvariable=self.pool_capacity), "个")

        self.pool_age = tk.IntVar(value=self.cfg["pool_max_age_days"])
        self._grid(grid, 3, "池子有效期",
                   ttk.Spinbox(grid, from_=1, to=30, width=8, textvariable=self.pool_age),
                   "天后重新扫描")

        self.max_scan = tk.IntVar(value=self.cfg["max_scan_pages"])
        self._grid(grid, 4, "扫描上限",
                   ttk.Spinbox(grid, from_=50, to=2000, width=8,
                               textvariable=self.max_scan), "页")

        self.throttle = tk.IntVar(value=self.cfg["throttle_stop"])
        self._grid(grid, 5, "止损阈值",
                   ttk.Spinbox(grid, from_=2, to=50, width=8, textvariable=self.throttle),
                   "连续 N 次没反应就停（疑似限流）")

        self.shuffle = tk.BooleanVar(value=self.cfg["shuffle"])
        ttk.Checkbutton(grid, text="打乱扫描顺序（更像真人）",
                        variable=self.shuffle).grid(row=6, column=1, sticky="w", pady=3)

    def _build_actions(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", padx=12, pady=16)
        ttk.Button(frame, text="保存配置", style="Accent.TButton",
                   command=self.save).pack(side="left")
        ttk.Button(frame, text="重新载入", command=self.reload).pack(side="left", padx=8)
        ttk.Button(frame, text="恢复默认", command=self.reset).pack(side="left")
        ttk.Button(frame, text="打开配置文件",
                   command=self.open_file).pack(side="left", padx=8)

        self.info = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.info, style="Muted.TLabel").pack(side="left",
                                                                            padx=12)

    # ---------------------------------------------------------- 行为
    def _apply_preset(self):
        name = self.preset_var.get()
        words = INDUSTRY_PRESETS.get(name)
        if not words:
            self._say("先在左边选一个行业预设。")
            return
        self.keyword_box.delete(0, tk.END)
        for word in words:
            self.keyword_box.insert(tk.END, word)
        self._say("已套用「%s」的 %d 个关键词，记得保存。" % (name, len(words)))

    def _pick_city(self, box):
        from .city_picker import CityPicker

        def on_pick(names, _target):
            current = list(box.get(0, tk.END))
            added = 0
            for name in names:
                if name not in current:
                    box.insert(tk.END, name)
                    current.append(name)
                    added += 1
            self._say("新增 %d 个城市。" % added)

        CityPicker(self.winfo_toplevel(), on_pick)

    def collect(self):
        """把界面上的值收成一个配置字典（未做校验）。"""
        def split(text):
            import re
            return [p.strip() for p in re.split(r"[,\uFF0C;；\n]+", text) if p.strip()]

        return {
            "keywords": list(self.keyword_box.get(0, tk.END)),
            "exclude_keywords": list(self.exclude_box.get(0, tk.END)),
            "cities_priority": list(self.priority_box.get(0, tk.END)),
            "cities_backup": list(self.backup_box.get(0, tk.END)),
            "salary": {
                "enabled": self.sal_on.get(),
                "min_month": self.sal_min_month.get(),
                "max_month": self.sal_max_month.get(),
                "min_day": self.sal_min_day.get(),
                "max_day": self.sal_max_day.get(),
            },
            "hr_active_days": self.hr_days.get(),
            "intern_priority": self.intern_on.get(),
            "intern_keywords": split(self.intern_words.get()),
            "intern_regex": self.intern_regex.get().strip(),
            "daily_target": self.daily_target.get(),
            "batch_counts": self.batch_counts.get(),
            "pool_capacity": self.pool_capacity.get(),
            "pool_max_age_days": self.pool_age.get(),
            "max_scan_pages": self.max_scan.get(),
            "throttle_stop": self.throttle.get(),
            "shuffle": self.shuffle.get(),
        }

    def save(self):
        raw = self.collect()
        if not raw["keywords"]:
            messagebox.showwarning("还不能保存", "至少要有一个搜索关键词。")
            return
        warnings = []
        cfg = store.job_config.validate(raw, warnings)
        store.save_config(cfg)
        self.cfg = cfg
        if warnings:
            messagebox.showwarning("已保存，但有这些调整", "\n".join(warnings))
            self._say("配置已保存（有 %d 条自动修正，看弹窗）。" % len(warnings))
        else:
            self._say("配置已保存到 config.json。")

    def reload(self):
        self.cfg = store.load_config()
        self._fill(self.cfg)
        self._say("已重新载入 config.json。")

    def reset(self):
        if not messagebox.askyesno("恢复默认", "会用内置的 IT 运维方向默认值覆盖当前界面，"
                                               "确定吗？（还没点保存就不会写文件）"):
            return
        import copy
        self._fill(copy.deepcopy(store.job_config.DEFAULTS))
        self._say("已载入默认值，点「保存配置」才生效。")

    def _fill(self, cfg):
        for box, key in ((self.keyword_box, "keywords"),
                         (self.exclude_box, "exclude_keywords"),
                         (self.priority_box, "cities_priority"),
                         (self.backup_box, "cities_backup")):
            box.delete(0, tk.END)
            for value in cfg.get(key, []):
                box.insert(tk.END, value)
        sal = cfg.get("salary", {})
        self.sal_on.set(sal.get("enabled", True))
        self.sal_min_month.set(sal.get("min_month", 3))
        self.sal_max_month.set(sal.get("max_month", 8))
        self.sal_min_day.set(sal.get("min_day", 100))
        self.sal_max_day.set(sal.get("max_day", 1500))
        self.hr_days.set(cfg.get("hr_active_days", 3))
        self.intern_on.set(cfg.get("intern_priority", True))
        self.intern_words.set(",".join(cfg.get("intern_keywords", [])))
        self.intern_regex.set(cfg.get("intern_regex", "") or "")
        self.daily_target.set(cfg.get("daily_target", 50))
        self.batch_counts.set(",".join(str(x) for x in cfg.get("batch_counts", [17, 17, 16])))
        self.pool_capacity.set(cfg.get("pool_capacity", 110))
        self.pool_age.set(cfg.get("pool_max_age_days", 2))
        self.max_scan.set(cfg.get("max_scan_pages", 500))
        self.throttle.set(cfg.get("throttle_stop", 8))
        self.shuffle.set(cfg.get("shuffle", True))

    def open_file(self):
        path = store.config_path()
        if not store.has_config():
            messagebox.showinfo("还没有配置文件", "点「保存配置」后会生成：\n%s" % path)
            return
        try:
            import subprocess
            subprocess.Popen(["notepad.exe", path])
        except Exception as exc:
            messagebox.showerror("打不开", "%r" % exc)
