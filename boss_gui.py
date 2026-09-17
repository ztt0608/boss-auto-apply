# -*- coding: utf-8 -*-
"""Boss 自动投递 · 图形控制台入口。

双击本文件（或桌面快捷方式）打开界面 —— 配置、投递、体检、看状态都在一个窗口里，
不用再去点各种 bat。

本文件只是入口，不含业务逻辑；界面代码在 gui/ 包里。
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

def _fatal(message):
    """没有图形环境时也要让人看得懂：先打印，再弹一个系统提示框。"""
    print(message)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, "Boss 控制台", 0x10)
    except Exception:
        pass


def main():
    try:
        import tkinter  # noqa: F401
    except ImportError:
        _fatal("当前 Python 没有 tkinter，打不开图形界面。\n\n"
               "解决办法：用 python.org 官方安装包重装 Python，安装时勾选\n"
               "「tcl/tk and IDLE」（默认已勾选），然后重新双击本文件。\n\n"
               "命令行方式仍然可用：run_batch.bat / setup.bat 不受影响。")
        return

    from gui.app import App  # noqa: E402  需先确认 tkinter 可用
    App().mainloop()


if __name__ == "__main__":
    main()
