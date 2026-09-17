# -*- coding: utf-8 -*-
"""数据层：配置读写 + 运行状态探测。

本模块只做「取数」，不做任何界面相关的事。
"""
import json
import os
import socket
import sqlite3
import sys
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import job_config  # noqa: E402  依赖注入：必须在 sys.path 处理之后

DB_NAME = "boss_sends.db"
POOL_NAME = "candidates.json"
CDP_PORT = 9223


# ============================================================ 配置
def load_config():
    """读取并校验配置（缺文件时返回内置默认值，不弹错）。"""
    return job_config.load(BASE_DIR, quiet=True)


def save_config(cfg):
    """写出 config.json（旧文件自动备份）。"""
    return job_config.write(BASE_DIR, cfg)


def summary_lines(cfg):
    return job_config.summary_lines(cfg)


def config_path():
    return job_config.config_path(BASE_DIR)


def has_config():
    return os.path.exists(config_path())


def load_city_table(online=True):
    """返回 (flat, provinces)；在线失败会自动回退内置表。"""
    return job_config.load_city_table(BASE_DIR, online=online, quiet=True)


# ============================================================ 运行命令
def python_exe():
    """当前解释器；pythonw 时换成同目录 python.exe（否则子进程拿不到输出）。"""
    exe = sys.executable or "python"
    folder, name = os.path.split(exe)
    if name.lower() == "pythonw.exe":
        cand = os.path.join(folder, "python.exe")
        if os.path.exists(cand):
            return cand
    return exe


def build_env(batch=None, extra=None):
    """子进程环境：强制 UTF-8 输出 + 无缓冲，保证日志实时且中文不乱码。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    if batch is not None:
        env["BOSS_BATCH"] = str(batch)
    for key, value in (extra or {}).items():
        env[key] = str(value)
    return env


def archive_pool():
    """把候选池改名归档 —— 逼脚本走「首次扫描」分支（只扫不点的前提）。

    BOSS_BATCH=0 在有 candidates.json 时是「什么都不做」而不是「只扫」，
    必须先把池子挪走。返回归档后的文件名，没有池子时返回 None。
    """
    src = os.path.join(BASE_DIR, POOL_NAME)
    if not os.path.exists(src):
        return None
    dst = os.path.join(BASE_DIR, "candidates.archived_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
    os.rename(src, dst)
    return os.path.basename(dst)


# ============================================================ 环境探测
def _opener():
    """探测本机 CDP 必须绕开代理（否则 502 会被误判成「Edge 没开」）。"""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def probe_cdp(port=CDP_PORT, timeout=3):
    """返回 True/False —— 9223 端口是否在监听。"""
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        return sock.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


def probe_pages(port=CDP_PORT):
    """返回 page target 列表；探测失败返回 None（区别于「连上了但没页面」的 []）。"""
    try:
        raw = _opener().open("http://127.0.0.1:%d/json/list" % port, timeout=5).read()
        data = json.loads(raw)
        return [t for t in data if t.get("type") == "page"]
    except Exception:
        return None


def probe_login(port=CDP_PORT):
    """登录态探测：True 已登录 / False 掉登录 / None 测不出来。

    红线对齐主脚本：只检测、只告警，绝不做任何登录动作。
    """
    pages = probe_pages(port)
    if not pages:
        return None
    target = next((t for t in pages if "zhipin" in (t.get("url") or "")), None)
    if not target or not target.get("webSocketDebuggerUrl"):
        return None
    expr = (r"(function(){var u=location.href;"
            r"if(u.indexOf('/login')>=0||u.indexOf('passport')>=0) return false;"
            r"var t=document.body.textContent||'';"
            r"var needLogin=(t.indexOf('密码登录')>=0||t.indexOf('短信登录')>=0"
            r"||t.indexOf('扫码登录')>=0)&&document.querySelector('input[type=password]')!=null;"
            r"return !needLogin;})()")
    try:
        sys.path.insert(0, os.path.join(BASE_DIR, "toolchain", "pylibs"))
        import websocket
        ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=10,
                                         origin="http://127.0.0.1:%d" % port)
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": expr, "returnByValue": True}}))
        deadline = time.time() + 8
        while time.time() < deadline:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                ws.close()
                value = (msg.get("result") or {}).get("result", {}).get("value")
                return bool(value)
        ws.close()
    except Exception:
        return None
    return None


# ============================================================ 数据统计
def pool_stats():
    """候选池概况；无池子返回 None。"""
    path = os.path.join(BASE_DIR, POOL_NAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        cands = data.get("candidates") or []
        return {
            "date": data.get("date") or "未知",
            "total": len(cands),
            "remain": sum(1 for c in cands if not c.get("clicked")),
            "clicked": sum(1 for c in cands if c.get("clicked")),
        }
    except Exception:
        return None


def today_stats(date_str=None):
    """今日投递统计；缺库返回 None。"""
    db = os.path.join(BASE_DIR, DB_NAME)
    if not os.path.exists(db):
        return None
    date_str = date_str or time.strftime("%Y-%m-%d")
    try:
        con = sqlite3.connect(db)
        rows = dict(con.execute(
            "SELECT status, COUNT(*) FROM sends WHERE date=? GROUP BY status",
            (date_str,)))
        total = con.execute("SELECT COUNT(*) FROM sends").fetchone()[0]
        con.close()
    except Exception:
        return None
    return {
        "date": date_str,
        "sent": rows.get("sent", 0),
        "failed": rows.get("failed", 0),
        "already": rows.get("already", 0),
        "dead": rows.get("dead", 0),
        "all_time": total,
    }


def probe_status():
    """一次性取回状态面板需要的全部数据。"""
    pages = probe_pages() if probe_cdp() else None
    zhipin_url = ""
    if pages:
        hit = next((t for t in pages if "zhipin" in (t.get("url") or "")), None)
        zhipin_url = (hit or pages[0]).get("url", "") if pages else ""
    return {
        "cdp": pages is not None,
        "pages": len(pages or []),
        "zhipin_url": zhipin_url,
        "login": probe_login() if pages else None,
        "pool": pool_stats(),
        "today": today_stats(),
    }


# ============================================================ Edge 启动
def edge_path():
    """定位 Edge 可执行文件；找不到返回 None。"""
    candidates = [
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge",
                     "Application", "msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge",
                     "Application", "msedge.exe"),
        os.path.join(os.environ.get("ProgramW6432", ""), "Microsoft", "Edge",
                     "Application", "msedge.exe"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def launch_edge():
    """以调试端口启动独立 profile 的 Edge（与 start_edge.bat 行为一致）。

    返回 (ok, message)。
    """
    exe = edge_path()
    if not exe:
        return False, "没找到 Edge，请确认已安装 Microsoft Edge。"
    profile = os.path.join(BASE_DIR, "edge_profile")
    args = [
        exe,
        "--remote-debugging-port=%d" % CDP_PORT,
        "--remote-allow-origins=*",
        "--user-data-dir=%s" % profile,
        "https://www.zhipin.com/web/geek/job",
    ]
    try:
        import subprocess
        subprocess.Popen(args, close_fds=True)
    except Exception as exc:
        return False, "启动 Edge 失败：%r" % exc
    return True, "Edge 已启动（调试端口 %d），请在弹出的窗口里确认已登录 Boss。" % CDP_PORT
