# -*- coding: utf-8 -*-
"""在桌面生成「Boss 自动投递控制台」快捷方式（Windows）。

只用标准库 + ctypes 调 IShellLinkW，不需要 pywin32。
用法：python make_shortcut.py
"""
import ctypes
import os
import sys
from ctypes import POINTER, byref, c_int, c_void_p, c_wchar_p

CLSCTX_INPROC_SERVER = 1


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]


CLSID_SHELL_LINK = GUID(0x00021401, 0, 0, (0xC0, 0, 0, 0, 0, 0, 0, 0x46))
IID_ISHELL_LINK_W = GUID(0x000214F9, 0, 0, (0xC0, 0, 0, 0, 0, 0, 0, 0x46))
IID_IPERSIST_FILE = GUID(0x0000010B, 0, 0, (0xC0, 0, 0, 0, 0, 0, 0, 0x46))

_HRESULT = ctypes.HRESULT
_ole32 = ctypes.windll.ole32


class ShellLink(object):
    """IShellLinkW 的极简封装（vtable 下标即方法序号）。"""

    def __init__(self):
        _ole32.CoInitialize(None)
        self.ptr = c_void_p()
        hr = _ole32.CoCreateInstance(byref(CLSID_SHELL_LINK), None, CLSCTX_INPROC_SERVER,
                                     byref(IID_ISHELL_LINK_W), byref(self.ptr))
        if hr:
            raise OSError("CoCreateInstance 失败：0x%08x" % hr)

    def _method(self, index, *argtypes):
        # ★坑：接口指针的第一格才是 vtable 地址，必须再解一层引用，
        # 直接 cast(ptr)[index] 取到的是对象自身的成员，一调用就 access violation。
        self_vptr = ctypes.cast(self.ptr, POINTER(c_void_p))
        vtable = ctypes.cast(self_vptr[0], POINTER(c_void_p))
        proto = ctypes.WINFUNCTYPE(_HRESULT, c_void_p, *argtypes)
        return proto(vtable[index])

    def set_path(self, path):
        self._method(20, c_wchar_p)(self.ptr, path)

    def set_arguments(self, args):
        self._method(11, c_wchar_p)(self.ptr, args)

    def set_working_directory(self, path):
        self._method(9, c_wchar_p)(self.ptr, path)

    def set_description(self, text):
        self._method(7, c_wchar_p)(self.ptr, text)

    def set_icon_location(self, path, index=0):
        self._method(17, c_wchar_p, c_int)(self.ptr, path, index)

    def save(self, lnk_path):
        query = self._method(0, POINTER(GUID), POINTER(c_void_p))
        persist = c_void_p()
        hr = query(self.ptr, byref(IID_IPERSIST_FILE), byref(persist))
        if hr:
            raise OSError("QueryInterface 失败：0x%08x" % hr)
        persist_vptr = ctypes.cast(persist, POINTER(c_void_p))
        persist_vtable = ctypes.cast(persist_vptr[0], POINTER(c_void_p))
        save = ctypes.WINFUNCTYPE(_HRESULT, c_void_p, c_wchar_p, c_int)(
            persist_vtable[6])  # IPersistFile::Save 位于 vtable 第 6 格
        hr = save(persist, lnk_path, 1)
        if hr:
            raise OSError("保存快捷方式失败：0x%08x" % hr)
        return lnk_path


def desktop_dir():
    home = os.path.expanduser("~")
    for name in ("Desktop", "OneDrive\\Desktop", "OneDrive - 个人\\Desktop"):
        candidate = os.path.join(home, name)
        if os.path.isdir(candidate):
            return candidate
    return home


def pythonw():
    """优先用 pythonw（不弹黑窗）；没有就退回 python。"""
    folder = os.path.dirname(sys.executable or "")
    for name in ("pythonw.exe", "python.exe"):
        candidate = os.path.join(folder, name)
        if os.path.exists(candidate):
            return candidate
    return sys.executable or "python.exe"


def main():
    if os.name != "nt":
        print("这个脚本只在 Windows 上需要。")
        return 1
    here = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(here, "boss_gui.py")
    if not os.path.exists(script):
        print("找不到 boss_gui.py：%s" % script)
        return 1

    link = ShellLink()
    link.set_path(pythonw())
    link.set_arguments('"%s"' % script)
    link.set_working_directory(here)
    link.set_description("Boss 自动投递控制台（配置 / 投递 / 体检 / 状态）")
    icon = os.path.join(here, "toolchain", "app.ico")
    if os.path.exists(icon):
        link.set_icon_location(icon, 0)

    target = os.path.join(desktop_dir(), "Boss 自动投递控制台.lnk")
    try:
        link.save(target)
    except Exception as exc:
        print("创建失败：%s" % exc)
        return 1
    print("已创建桌面快捷方式：%s" % target)
    print("解释器：%s" % pythonw())
    return 0


if __name__ == "__main__":
    sys.exit(main())
