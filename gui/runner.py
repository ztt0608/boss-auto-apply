# -*- coding: utf-8 -*-
"""子进程运行器：后台线程跑命令，逐行把输出回调给界面。

回调都在工作线程里触发，界面侧必须自行 `after(0, ...)` 切回主线程。
"""
import os
import subprocess
import threading

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class CommandRunner:
    """一次只跑一条命令；重复 start 会被拒绝。"""

    def __init__(self, on_line, on_finish):
        self._on_line = on_line
        self._on_finish = on_finish
        self._proc = None
        self._thread = None
        self.running = False
        self.started_at = None

    def start(self, cmd, cwd, env):
        if self.running:
            return False
        try:
            self._proc = subprocess.Popen(
                cmd, cwd=cwd, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=1, universal_newlines=True,
                encoding="utf-8", errors="replace",
                creationflags=_CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception as exc:
            self._on_line("!! 启动失败：%r" % exc)
            self._on_finish(-1)
            return False
        self.running = True
        self.started_at = __import__("time").time()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()
        return True

    def _pump(self):
        try:
            for line in iter(self._proc.stdout.readline, ""):
                self._on_line(line.rstrip("\r\n"))
            self._proc.stdout.close()
            code = self._proc.wait()
        except Exception as exc:
            self._on_line("!! 读取输出中断：%r" % exc)
            code = -1
        self.running = False
        self._on_finish(code)

    def stop(self):
        """请求停止；返回是否真的发出了终止信号。"""
        if not self.running or not self._proc:
            return False
        try:
            self._proc.terminate()
            return True
        except Exception:
            return False
