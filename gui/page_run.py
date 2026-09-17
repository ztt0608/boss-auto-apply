# -*- coding: utf-8 -*-
"""运行页：一键投递 / 只扫建池 / 环境体检 / 日报，外加实时日志。"""
import os
import queue
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from . import store, theme
from .runner import CommandRunner

SCRIPT = "boss_batch.py"
HEALTH = "cdp_health.py"
REPORT = "daily_report.py"


class RunPage(ttk.Frame):
    def __init__(self, master, on_status=None):
        ttk.Frame.__init__(self, master, style="TFrame")
        self.on_status = on_status or (lambda _msg: None)
        self._start_time = None
        self._tick_job = None
        self._drain_job = None
        self._queue = queue.Queue()

        self.runner = CommandRunner(self._emit_line, self._emit_finish)

        self._build_controls()
        self._build_log()

    # ---------------------------------------------------------- 构建
    def _build_controls(self):
        top = ttk.Frame(self, padding=(12, 10))
        top.pack(fill="x")

        ttk.Label(top, text="本批投递：").pack(side="left")
        self.batch_var = tk.IntVar(value=17)
        ttk.Spinbox(top, from_=0, to=200, width=6,
                    textvariable=self.batch_var).pack(side="left", padx=(4, 12))

        ttk.Label(top, text="快捷：", style="Muted.TLabel").pack(side="left")
        for value in (17, 17, 16):
            ttk.Button(top, text=str(value), width=3,
                       command=lambda v=value: self.batch_var.set(v)).pack(side="left")

        self.scan_after = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="投完顺便重扫池子",
                        variable=self.scan_after).pack(side="left", padx=12)

        bar = ttk.Frame(self, padding=(12, 0))
        bar.pack(fill="x")
        self.btn_send = ttk.Button(bar, text="开始投递", style="Accent.TButton",
                                   command=self.do_send)
        self.btn_send.pack(side="left")
        self.btn_scan = ttk.Button(bar, text="只扫描建池", command=self.do_scan)
        self.btn_scan.pack(side="left", padx=8)
        self.btn_health = ttk.Button(bar, text="环境体检", command=self.do_health)
        self.btn_health.pack(side="left")
        self.btn_report = ttk.Button(bar, text="生成日报", command=self.do_report)
        self.btn_report.pack(side="left", padx=8)
        self.btn_edge = ttk.Button(bar, text="打开调试浏览器", command=self.do_edge)
        self.btn_edge.pack(side="left")
        self.btn_stop = ttk.Button(bar, text="停止", style="Danger.TButton",
                                   command=self.do_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=8)

        self.try_fix = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="体检含自愈复现(--try-fix)",
                        variable=self.try_fix).pack(side="left", padx=8)

        self.state_var = tk.StringVar(value="空闲")
        ttk.Label(self, textvariable=self.state_var, style="Muted.TLabel",
                  padding=(12, 6)).pack(anchor="w")

    def _build_log(self):
        frame = ttk.Frame(self, padding=(12, 0))
        frame.pack(fill="both", expand=True, pady=(0, 10))

        holder = ttk.Frame(frame)
        holder.pack(fill="both", expand=True)
        self.log = tk.Text(holder, height=18, wrap="none", undo=False,
                           background=theme.COLOR_LOG_BG, foreground=theme.COLOR_LOG_FG,
                           insertbackground=theme.COLOR_LOG_FG, relief="solid",
                           borderwidth=1, font=(theme.FONT_MONO, theme.FONT_SIZE))
        ysb = ttk.Scrollbar(holder, orient="vertical", command=self.log.yview)
        xsb = ttk.Scrollbar(holder, orient="horizontal", command=self.log.xview)
        self.log.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.log.configure(state="disabled")

        bottom = ttk.Frame(frame)
        bottom.pack(fill="x", pady=(6, 0))
        self.auto_scroll = tk.BooleanVar(value=True)
        ttk.Checkbutton(bottom, text="自动滚动", variable=self.auto_scroll).pack(side="left")
        ttk.Button(bottom, text="清空", command=self.clear_log).pack(side="left", padx=8)
        ttk.Button(bottom, text="保存日志", command=self.save_log).pack(side="left")

    # ---------------------------------------------------------- 日志
    def _emit_line(self, text):
        """由工作线程调用 —— 只入队，不碰控件。"""
        self._queue.put(("line", text))

    def _emit_finish(self, code):
        self._queue.put(("done", code))

    def _drain(self):
        """主线程定时把队列里的输出倒进日志框。

        ★坑：tkinter 控件只能由主线程操作，after() 也不能在子线程里调，
        所以子进程输出统一走「队列 + 主线程轮询」。
        """
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "line":
                    self._append(payload)
                else:
                    self._finish(payload)
        except queue.Empty:
            pass
        if self.runner.running or not self._queue.empty():
            self._drain_job = self.after(120, self._drain)
        else:
            self._drain_job = None

    def _append(self, text):
        self.log.configure(state="normal")
        self.log.insert(tk.END, text + "\n")
        self.log.configure(state="disabled")
        if self.auto_scroll.get():
            self.log.see(tk.END)

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", tk.END)
        self.log.configure(state="disabled")

    def save_log(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".log", initialfile="boss_gui_%s.log" % time.strftime("%Y%m%d_%H%M%S"),
            filetypes=[("日志文件", "*.log"), ("文本", "*.txt")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.log.get("1.0", tk.END))
            self.on_status("日志已保存到 %s" % path)
        except Exception as exc:
            messagebox.showerror("保存失败", "%r" % exc)

    # ---------------------------------------------------------- 运行控制
    def _set_running(self, running):
        state = "disabled" if running else "normal"
        for btn in (self.btn_send, self.btn_scan, self.btn_health,
                    self.btn_report, self.btn_edge):
            btn.configure(state=state)
        self.btn_stop.configure(state="normal" if running else "disabled")
        if running:
            self._start_time = time.time()
            self._tick()
            if self._drain_job:
                self.after_cancel(self._drain_job)
            self._drain_job = self.after(120, self._drain)
        else:
            self._start_time = None
            if self._tick_job:
                self.after_cancel(self._tick_job)
                self._tick_job = None

    def _tick(self):
        if self._start_time is None:
            return
        used = int(time.time() - self._start_time)
        self.state_var.set("运行中… 已用时 %d 分 %02d 秒" % (used // 60, used % 60))
        self._tick_job = self.after(1000, self._tick)

    def _finish(self, code):
        self._set_running(False)
        self._append("—— 进程结束，退出码 %d ——" % code)
        if code == 0:
            self.state_var.set("完成（退出码 0）")
            self.on_status("任务完成。")
        else:
            self.state_var.set("结束（退出码 %d，看日志定位原因）" % code)
            self.on_status("任务结束，退出码 %d。" % code)

    def _run(self, script, env_extra, title):
        if self.runner.running:
            messagebox.showinfo("正在跑", "已有一个任务在执行，先等它结束或点「停止」。")
            return
        cmd = [store.python_exe(), os.path.join(store.BASE_DIR, script)]
        if script == HEALTH and self.try_fix.get():
            cmd.append("--try-fix")
        self._append("=== %s ===\n$ %s" % (title, " ".join(cmd)))
        for key, value in (env_extra or {}).items():
            self._append("    env %s=%s" % (key, value))
        self._append("")
        self._set_running(True)
        self.state_var.set("运行中…")
        self.on_status("%s 已启动。" % title)
        if not self.runner.start(cmd, cwd=store.BASE_DIR,
                                 env=store.build_env(extra=env_extra)):
            self._set_running(False)

    # ---------------------------------------------------------- 各按钮
    def do_send(self):
        count = self.batch_var.get()
        if count <= 0:
            messagebox.showinfo("数量不对", "投递数量要大于 0；只想建池请点「只扫描建池」。")
            return
        if not store.probe_cdp():
            if not messagebox.askyesno(
                    "浏览器没开",
                    "9223 端口没响应 —— 通常是调试用的 Edge 还没启动。\n"
                    "仍要继续吗？（会立刻失败，日志里能看到原因）"):
                return
        extra = {"BOSS_BATCH": count}
        if self.scan_after.get():
            extra["BOSS_SCAN_AFTER"] = "1"
        self._run(SCRIPT, extra, "开始投递 %d 个" % count)

    def do_scan(self):
        if not messagebox.askyesno(
                "只扫描建池",
                "会把现有 candidates.json 改名归档，然后重新扫描一遍（不投递）。\n"
                "全程约 60-90 分钟，期间别动那个 Edge 窗口。\n\n继续吗？"):
            return
        archived = store.archive_pool()
        self._append("已归档旧池子：%s" % (archived or "（原本就没有池子）"))
        self._run(SCRIPT, {"BOSS_BATCH": 0}, "只扫描建池（不投递）")

    def do_health(self):
        self._run(HEALTH, None, "环境体检（零投递消耗）")

    def do_report(self):
        self._run(REPORT, None, "生成日报")

    def do_edge(self):
        ok, message = store.launch_edge()
        self._append("[启动浏览器] %s" % message)
        self.on_status(message)

    def do_stop(self):
        if self.runner.stop():
            self._append("!! 已发送停止信号（子进程会在当前操作后退出）")
            self.on_status("正在停止…")
        else:
            self.on_status("当前没有在跑的任务。")
