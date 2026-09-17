# -*- coding: utf-8 -*-
"""Boss 投递链路体检（只读为主）：CDP 连通 + 登录态 + 前台焦点/可见性 + 滚轮可用性。

用途：
  1) 跑批次前确认 Edge/登录/焦点状态；
  2) 锁屏、切窗口、最小化等场景下判断"点击为什么没反应"（今日已证实：标签不在前台时 Boss 不响应合成输入）。

用法：python cdp_health.py [--try-fix]
  --try-fix：额外复现脚本的 ensure_foreground() 自愈序列（setFocusEmulationEnabled + Page.bringToFront），
             再重测前台/滚轮。用于判断「锁屏/切窗口后脚本还能不能自愈」，零投递额度消耗。
退出码：0 一切正常；2 CDP 不通；3 找不到 zhipin 页面；4 登录态失效；5 前台/滚轮异常（警告级）
"""
import os, sys, json, time, urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "toolchain", "pylibs"))
import websocket

# ★探测必须禁用代理：本环境有 HTTP_PROXY，裸 urlopen 会把 127.0.0.1 送去代理并返回假 502
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _get(path):
    return json.loads(_OP.open("http://127.0.0.1:9223" + path, timeout=6).read())


try:
    ver = _get("/json/version")
    print("[1] CDP 正常：%s" % ver.get("Browser"))
except Exception as e:
    print("[1] CDP 不通：%s" % e)
    print("    → 真断连可用 socket.connect_ex(('127.0.0.1',9223)) 复判：0=在监听 / 10061=真关闭")
    sys.exit(2)

pages = [t for t in _get("/json/list") if t.get("type") == "page"]
target = next((t for t in pages if "zhipin" in (t.get("url") or "")), None)
if target is None:
    print("[2] 未找到 zhipin 页面 target（当前 %d 个 page target）" % len(pages))
    for t in pages:
        print("    - %s" % (t.get("url") or "")[:80])
    print("    → 需整实例重启 Edge（杀命令行含 boss_debug_profile 的进程后重开）")
    sys.exit(3)
print("[2] zhipin 页面：%s" % target["url"][:80])

ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=30,
                                 origin="http://127.0.0.1:9223")
_i = {"n": 0}


def ev(expr, timeout=15):
    _i["n"] += 1
    ws.send(json.dumps({"id": _i["n"], "method": "Runtime.evaluate",
                        "params": {"expression": expr, "returnByValue": True}}))
    end = time.time() + timeout
    while time.time() < end:
        try:
            m = json.loads(ws.recv())
        except Exception:
            continue
        if m.get("id") == _i["n"]:
            return m.get("result", {}).get("result", {}).get("value")
    return None


state = ev("""(function(){
  var isChat = /\\/web\\/geek\\/chat/.test(location.href);
  return JSON.stringify({
    loginBtn: !!document.querySelector('.btn-login, .nav-login, [ka*="login"]'),
    greetBtn: !!document.querySelector('.btn-startchat, .op-btn-chat, a[ka*="chat"]'),
    focus: document.hasFocus(),
    vis: document.visibilityState,
    hidden: document.hidden,
    innerWH: window.innerWidth + 'x' + window.innerHeight,
    outerWH: window.outerWidth + 'x' + window.outerHeight,
    scrollY: Math.round(window.scrollY),
    scrollTop: Math.round(document.documentElement.scrollTop),
    docH: document.documentElement.scrollHeight,
    winH: window.innerHeight,
    url: location.href.slice(0, 70)
  });
})()""")
try:
    st = json.loads(state)
except Exception:
    print("[3] 取页面状态失败：%r" % (state,))
    sys.exit(5)

print("[3] 登录态：loginBtn=%s greetBtn=%s  → %s"
      % (st["loginBtn"], st["greetBtn"], "已登录" if not st["loginBtn"] else "★未登录"))
print("[4] 前台：hasFocus=%s  visibilityState=%s  hidden=%s"
      % (st["focus"], st["vis"], st["hidden"]))
print("    窗口：inner=%s outer=%s（outer 很小或 0 通常意味着最小化）" % (st["innerWH"], st["outerWH"]))

# 滚轮实测：今日已证实「标签不在前台 ⇒ 合成输入被忽略」
# 注意：chat 页面没有文档级滚动条，直接测 documentElement 会得到假阴性 →
#       先找一个真正可滚动的容器（scrollHeight > clientHeight）再测。
_SCROLL_PROBE = """(function(){
  window.__probeEl = null;
  function sc(el){ return el.scrollHeight - el.clientHeight > 40; }
  var all = document.querySelectorAll('div,main,section,ul'); var best = null;
  for (var i=0;i<all.length;i++){
    if (sc(all[i]) && (!best ||
        (all[i].scrollHeight-all[i].clientHeight) > (best.scrollHeight-best.clientHeight))) best = all[i];
  }
  if (best) window.__probeEl = best;
  var d = document.documentElement;
  var r = best ? best.getBoundingClientRect() : {left:0,top:0,width:window.innerWidth,height:window.innerHeight};
  return JSON.stringify({
    docScrollable: sc(d),
    found: !!best,
    cls: best ? String(best.className || best.tagName).slice(0,30) : '',
    top: best ? Math.round(best.scrollTop) : Math.round(d.scrollTop),
    max: best ? (best.scrollHeight - best.clientHeight) : (d.scrollHeight - d.clientHeight),
    cx: Math.round(r.left + r.width / 2),
    cy: Math.round(r.top + Math.min(r.height / 2, 300))
  });
})()"""
_READ_PROBE = """(function(){
  if (window.__probeEl) return Math.round(window.__probeEl.scrollTop);
  return Math.round(document.documentElement.scrollTop);
})()"""

_probe_raw = ev(_SCROLL_PROBE)
try:
    _p = json.loads(_probe_raw) if isinstance(_probe_raw, str) else {}
except Exception:
    _p = {}
print("[5] 滚动容器：%s" % (_p or _probe_raw))


def _wheel_ok():
    if not _p.get("found") and not _p.get("docScrollable"):
        return None  # 页面确实没有可滚动区域，不可判定
    cx, cy = _p.get("cx") or 700, _p.get("cy") or 400
    b = ev(_READ_PROBE) or 0
    ws.send(json.dumps({"id": 0, "method": "Input.dispatchMouseEvent",
                        "params": {"type": "mouseWheel", "x": cx, "y": cy,
                                   "deltaX": 0, "deltaY": 400}}))
    time.sleep(1.2)
    a = ev(_READ_PROBE) or 0
    ws.send(json.dumps({"id": 0, "method": "Input.dispatchMouseEvent",
                        "params": {"type": "mouseWheel", "x": cx, "y": cy,
                                   "deltaX": 0, "deltaY": -1000}}))  # 滚回，避免留下痕迹
    time.sleep(0.6)
    print("    滚轮实测 @(%d,%d)：%s → %s  %s"
          % (cx, cy, b, a, "OK" if a != b else "★无效（被忽略）"))
    return a != b


wheel_ok = _wheel_ok()
if wheel_ok is None:
    print("    （页面无可用滚动区域，滚轮不可判定，仅依据 hasFocus/visibilityState 判断）")
else:
    print("    合成输入：%s" % ("OK" if wheel_ok else "★无效（被忽略）"))


def measure(tag):
    s = ev("""(function(){return JSON.stringify({
      focus: document.hasFocus(), vis: document.visibilityState, hidden: document.hidden,
      outerWH: window.outerWidth + 'x' + window.outerHeight,
      scrollTop: Math.round(document.documentElement.scrollTop)});})()""")
    try:
        return json.loads(s)
    except Exception:
        return {}


if "--try-fix" in sys.argv:
    print()
    print("[6] 复现脚本 ensure_foreground() 自愈序列…")
    ws.send(json.dumps({"id": 0, "method": "Emulation.setFocusEmulationEnabled",
                        "params": {"enabled": True}}))
    ws.send(json.dumps({"id": 0, "method": "Page.enable"}))
    ws.send(json.dumps({"id": 0, "method": "Page.bringToFront"}))
    time.sleep(1.5)
    a = measure("fix")
    print("    自愈后：hasFocus=%s  visibilityState=%s  hidden=%s  outer=%s"
          % (a.get("focus"), a.get("vis"), a.get("hidden"), a.get("outerWH")))
    try:
        _p = json.loads(ev(_SCROLL_PROBE))  # 重新定位可滚动容器 + 坐标
    except Exception:
        pass
    ok2 = _wheel_ok()
    print("    自愈后合成输入：%s" % ("OK（自愈有效）" if ok2 else
                                ("不可判定" if ok2 is None else "★仍无效（自愈救不回来）")))
    if a.get("focus") and a.get("vis") == "visible" and ok2 is not False:
        print("\n结论：✅ ensure_foreground() 能把状态拉回可用（hasFocus/visibilityState 均恢复）→ "
              "锁屏/切窗口后脚本自愈有效。")
        ws.close()
        sys.exit(0)
    print("\n结论：★自愈无效 → 当前状态下 Boss 不会响应点击，必须让 Edge 窗口回到前台"
          "（解锁屏幕 / 取消最小化）。")
    ws.close()
    sys.exit(5)

verdict = []
if st["loginBtn"]:
    verdict.append("未登录")
if not st["focus"] or st["vis"] != "visible" or st["hidden"]:
    verdict.append("标签不在前台")
if wheel_ok is False:
    verdict.append("合成输入被忽略")
print()
if verdict:
    print("结论：★异常 —— %s" % "、".join(verdict))
    print("  → Boss 很可能不响应点击；脚本会靠 ensure_foreground() 强制焦点自愈，"
          "若仍失败请把 Edge 窗口切到前台/取消最小化。")
    print("  → 想验证自愈是否足够：加 --try-fix 重跑（零投递消耗）。")
    sys.exit(5 if not st["loginBtn"] else 4)
else:
    print("结论：✅ 一切正常，点击链路可用。")
ws.close()
