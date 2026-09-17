# -*- coding: utf-8 -*-
"""
Boss 直聘 - 拟人化批量「立即沟通」 v12(两天扫一次·单次扫110·一天投50 + 3时段×17/17/16 + 候选池复用 + 列表页HR预筛 + 拟人节奏)
薪资在详情页为明文，列表页被自定义字体混淆 -> 进详情页读真实薪资再决定是否点击。
城市：四省优先（福建9市/广东21市/浙江11市/北京 全省每一个市都搜，city 码取自 BOSS 官方 city.json），其余全国主要城市兜底（上海/成都/武汉/长沙/苏州/重庆/天津/西安/南京/郑州/青岛/合肥/昆明/沈阳/济南 + BOSS 全国聚合码 100010000）
关键词（13个）：桌面运维 / 网络工程师 / 系统运维 / 运维 / 弱电 / 网络管理员 / Linux运维 / 云计算运维 / 云原生 / SRE / 平台运维 / 服务器运维 / IT运维
薪资：月薪 3-8K 或 日薪 ≥100 元/天 —— 以上均为【默认值】，实际以同目录 config.json 为准（双击 setup.bat 生成）
实习/应届优先：先尽量投面向实习生/应届生的岗位，再用普通岗补足到 TARGET；二者都接受
区域优先：四省城市排在最前，全国城市仅用于兜底补足到 TARGET
HR 活跃度：至少三天内在线（今日/刚刚/昨日/3日内等），超期或未知则跳过
排程：每日 3 批次错峰（07:00/13:00/19:00 各发 17/17/16，合计 50）。候选池两天扫一次（POOL_MAX_AGE_DAYS=2），
      首扫存 candidates.json，后续批次读 json 点「立即沟通」，分散请求、总访问量最低。
环境：连 CDP 127.0.0.1:9223 上已登录的真实 Edge（绝不自动登录）；漏配 FEISHU_WEBHOOK 时静默跳过推送。
"""
import json, sys, time, urllib.parse, random, re, os

_HERE = os.path.dirname(os.path.abspath(__file__))
SAVE_DIR = _HERE  # 自动等于本脚本所在目录（便携设计：不写死盘符，整个文件夹拷到哪都可用）
TARGET = 50  # 每日目标：月薪3-8K或日薪≥100元/天；HR三天内在线；实习/应届优先；最多投50个（两天扫一次、单次扫110，一天投50）
PRIORITY_INTERN = True  # 实习/应届优先：先投实习/应届岗，再用普通岗补足到 TARGET
MAX_SCAN = 500  # 扫描阶段最多打开的候选详情页数上限（收满~110合格约需~450次详情，留余量到500，8/17配合POOL_CAP=110调高）
POOL_CAP = TARGET * 2 + 10  # 每次扫描收集上限 = 110（100 正投两天 + 10 容错，用户方案 8/17）

import urllib.request
# 注意：如果运行环境存在 HTTP_PROXY/HTTPS_PROXY 环境变量（本机装有代理软件时很常见），
# 裸 urlopen 会把 127.0.0.1 也送去代理，返回 502 Bad Gateway，表现为"Edge 未就绪"的假故障。
# 故此处强制禁用代理直连本机调试端口（CDP 永远不该走代理）。
_CDP_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def _cdp_json(path):
    return json.loads(_CDP_OPENER.open("http://127.0.0.1:9223" + path, timeout=5).read())

def _pick_page_ws():
    try:
        lst = _cdp_json("/json/list")
        for t in lst:
            if t.get("type") == "page" and "zhipin" in (t.get("url") or ""):
                return t.get("webSocketDebuggerUrl")
        for t in lst:
            if t.get("type") == "page":
                return t.get("webSocketDebuggerUrl")
    except Exception:
        pass
    return None

WS = sys.argv[1] if len(sys.argv) > 1 else None
if not WS or "devtools/browser" in WS:
    WS = _pick_page_ws()
print("WS =", WS, flush=True)

sys.path.insert(0, os.path.join(_HERE, "toolchain", "pylibs"))  # 依赖 websocket-client，随脚本目录走
import websocket
ws = websocket.create_connection(WS, timeout=40, origin="http://127.0.0.1:9223")
_def = {"id": 0}
def send(method, params=None):
    global _def
    _def["id"] += 1
    ws.send(json.dumps({"id": _def["id"], "method": method, "params": params or {}}))
    return _def["id"]
def recv_match(iid, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        try: raw = ws.recv()
        except Exception: continue
        try: m = json.loads(raw)
        except Exception: continue
        if m.get("id") == iid: return m
    return None
def log(*a):
    print("[%s]" % time.strftime("%H:%M:%S"), *a, flush=True)

_fg = {"t": 0.0, "ok": True}
def ensure_foreground(force=False):
    # === 2026-09-15 全败根因修复 ===
    # 现象：脚本一切"正常"（能开详情页、读到薪资），但点「立即沟通」完全无反应，
    #       日志表现为 `继续沟通=False 聊天框=False 频繁=False`，极易误判为账号风控/静默限流。
    # 真因：被驱动的标签页若不在前台（document.hasFocus()=false / visibilityState='hidden'），
    #       Boss 页面不响应 CDP 合成输入——鼠标滚轮不滚（scrollY 恒为 0）、点击不派发。
    #       用户手动点则正常（窗口在前台）。2026-09-15 经对照实验证实，同一按钮同一坐标，
    #       仅"是否在前台"这一变量即可决定成败。
    # 加固（2026-09-15 锁屏实测）：锁屏/切走后页面会持续处于 hidden，且状态会反复回落，
    #       故：① 上一轮状态不好时不受 25s 节流限制；② 修复后再复核一次；
    #       ③ navigate() 里强制检查（每个候选开页前必过），确保点击前状态是好的。
    now = time.time()
    if not force and _fg["ok"] and now - _fg["t"] < 25:
        return
    _fg["t"] = now
    try:
        send("Emulation.setFocusEmulationEnabled", {"enabled": True})
        _probe = "(document.hasFocus()?1:0)+(document.visibilityState==='visible'?1:0)"
        st = eval_js(_probe, timeout=6)
        if st is None or int(st) < 2:
            send("Page.enable")
            send("Page.bringToFront")
            time.sleep(0.4)
            st2 = eval_js(_probe, timeout=6)   # 复核：锁屏下需要这一拍才真正恢复可见
            _fg["ok"] = bool(st2 and int(st2) >= 2)
            if _fg["ok"]:
                log("   [前台自愈] 标签曾不在前台，已 bringToFront 修复")
        else:
            _fg["ok"] = True
    except Exception:
        _fg["ok"] = False

def navigate(url, wait=6):
    ensure_foreground(force=True)  # 每个候选开页前强制确认前台，避免点击时"看着正常实则无效"
    send("Page.navigate", {"url": url}); time.sleep(wait)
def eval_js(expr, timeout=25):
    iid = send("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": False})
    m = recv_match(iid, timeout)
    if m and "result" in m:
        res = m["result"].get("result", {})
        if res.get("subtype") == "error": return {"__err__": res.get("description","")}
        return res.get("value")
    return None

ensure_foreground(force=True)  # 启动即确保标签在前台，避免首次点击就空洞

# ---------- 拟人输入 ----------
def human_scroll(steps=None, base=400):
    if steps is None: steps = random.randint(3, 6)
    for _ in range(steps):
        h = random.randint(int(base*0.5), int(base*1.4))
        ws.send(json.dumps({"id": 0, "method": "Input.dispatchMouseEvent",
                            "params": {"type": "mouseWheel", "x": random.randint(500, 760),
                                       "y": random.randint(300, 500), "deltaX": 0, "deltaY": h}}))
        time.sleep(random.uniform(0.35, 0.9))
def human_read():
    # 模拟真人阅读详情页：慢速滚动 + 随机停顿（像真的在看岗位描述），降低"直奔按钮"的机器痕迹
    steps = random.randint(3, 6)
    for _ in range(steps):
        h = random.randint(200, 500)
        ws.send(json.dumps({"id": 0, "method": "Input.dispatchMouseEvent",
                            "params": {"type": "mouseWheel", "x": random.randint(500, 760),
                                       "y": random.randint(300, 500), "deltaX": 0, "deltaY": h}}))
        time.sleep(random.uniform(0.5, 1.1))
    time.sleep(random.uniform(6, 16))  # 阅读时长
def _move_to(tx, ty):
    sx, sy = random.randint(200, 900), random.randint(150, 500)
    cx = (sx + tx) / 2 + random.randint(-120, 120)
    cy = (sy + ty) / 2 + random.randint(-90, 90)
    n = random.randint(22, 40)
    for i in range(1, n + 1):
        tt = i / n
        x = int((1-tt)**2 * sx + 2*(1-tt)*tt * cx + tt**2 * tx)
        y = int((1-tt)**2 * sy + 2*(1-tt)*tt * cy + tt**2 * ty)
        ws.send(json.dumps({"id": 0, "method": "Input.dispatchMouseEvent",
                            "params": {"type": "mouseMoved", "x": x + random.randint(-2, 2),
                                       "y": y + random.randint(-2, 2)}}))
        if i % 7 == 0: time.sleep(random.uniform(0.01, 0.04))
    return tx, ty
def human_click(x, y, btn="left"):
    x += random.randint(-3, 3); y += random.randint(-3, 3)
    _move_to(x, y); time.sleep(random.uniform(0.18, 0.5))
    ws.send(json.dumps({"id": 0, "method": "Input.dispatchMouseEvent",
                        "params": {"type": "mousePressed", "x": x, "y": y, "button": btn, "clickCount": 1}}))
    time.sleep(random.uniform(0.04, 0.12))
    ws.send(json.dumps({"id": 0, "method": "Input.dispatchMouseEvent",
                        "params": {"type": "mouseReleased", "x": x, "y": y, "button": btn, "clickCount": 1}}))
    time.sleep(random.uniform(0.2, 0.5))
def get_rect_of(text_in_button):
    # 修复 8/14 全败根因：human_read 滚动后，scrollIntoView({block:'center'}) 在平滑滚动页面上会"动画中"
    # 立即取 getBoundingClientRect 得到的是滚动前(视口外)坐标，导致合成鼠标点击落空。
    # 这里强制 behavior:'instant' 立即归位，再用 elementFromPoint 校验点击点确实落在按钮上；
    # 若不中（被覆盖/仍偏移）则窗口级 scrollTo 兜底再取一次，确保坐标命中真实按钮。
    # 8/17 补强：职位页存在多个同名按钮（主按钮在 .job-op 容器内 + 相关推荐卡片里的可见副本 / w=0 隐藏副本），
    # 滚动后易取到卡片副本导致"点击不生效"（点了跳页而非建会话）。改为在全部可见且 onBtn 的副本里，
    # 优先选 .job-op 主按钮（面积最大者兜底），彻底避开隐藏/卡片副本。
    return eval_js(r'''
    (function(){
      var txt=%s;
      function rectOf(b){
        if(!b) return null;
        var r=b.getBoundingClientRect();
        if(r.width<=0||r.height<=0) return null;
        var cx=Math.round(r.x+r.width/2), cy=Math.round(r.y+r.height/2);
        var el=document.elementFromPoint(cx,cy);
        var onBtn=!!(el&&(el===b||(el.closest&&el.closest('button,a.btn,.btn'))));
        return {x:cx,y:cy,w:Math.round(r.width),h:Math.round(r.height),onBtn:onBtn,b:b};
      }
      var all=[].slice.call(document.querySelectorAll('button, a.btn, .btn')).filter(function(b){
        return (b.textContent||'').indexOf(txt)>=0;
      });
      var cands=[];
      all.forEach(function(b){
        var r=rectOf(b);
        if(r && r.onBtn){
          var p=b, inJobOp=false;
          for(var k=0;k<6 && p;k++){
            if(p.className && typeof p.className==='string' && p.className.indexOf('job-op')>=0){inJobOp=true;break;}
            p=p.parentElement;
          }
          r.score=(inJobOp?100000:0)+r.w*r.h;
          cands.push(r);
        }
      });
      if(!cands.length){
        for(var i=0;i<all.length;i++){var rr=rectOf(all[i]); if(rr&&rr.onBtn) return rr;}
        return null;
      }
      cands.sort(function(a,b){return b.score-a.score;});
      var best=cands[0];
      try{ best.b.scrollIntoView({block:'center', behavior:'instant'}); }catch(e){
        try{ best.b.scrollIntoView({block:'center'}); }catch(e2){}
      }
      var br=best.b.getBoundingClientRect();
      var bx=Math.round(br.x+br.width/2), by=Math.round(br.y+br.height/2);
      var el2=document.elementFromPoint(bx,by);
      var on2=!!(el2&&(el2===best.b||(el2.closest&&el2.closest('button,a.btn,.btn'))));
      return {x:bx,y:by,w:Math.round(br.width),h:Math.round(br.height),onBtn:on2};
    })();
    ''' % json.dumps(text_in_button))
def detail_state():
    r = eval_js(r'''
    (function(){
      var btns=[].slice.call(document.querySelectorAll('button, a.btn, .btn'));
      var imm=false, cont=false;
      for(var i=0;i<btns.length;i++){
        var s=(btns[i].textContent||'');
        if(s.indexOf('立即沟通')>=0) imm=true;
        if(s.indexOf('继续沟通')>=0) cont=true;
      }
      var input=!!document.querySelector('textarea, .chat-input, [contenteditable="true"]');
      var txt=(document.body.textContent||'');
      var freq=(txt.indexOf('操作频繁')>=0)||(txt.indexOf('频繁')>=0)||(txt.indexOf('稍后再试')>=0);
      var greet=(txt.indexOf('已向BOSS发送消息')>=0)||(txt.indexOf('greet-pop')>=0);
      return {hasImmediate:imm, hasContinue:cont, hasChatInput:input, freqLimited:freq, hasGreet:greet};
    })();
    ''')
    # 8/18补：页面未就绪/eval 失败时返回 None（由调用方等待重试），避免 `?号` 和 KeyError
    if not isinstance(r, dict) or r.get("__err__"):
        return None
    return r
def read_salary():
    # 详情页薪资为明文；偶发加载未完成 -> 重试最多3次
    # 支持两种格式：月薪 "X-YK" 与 日薪 "X-Y元/天" / "X元/天"
    js = r'''
    (function(){
      var body=(document.body.textContent||'').replace(/\s+/g,' ');
      var m=body.match(/(\d+)\s*-\s*(\d+)\s*K/);
      if(m) return {type:'month', low:parseInt(m[1],10), high:parseInt(m[2],10), raw:m[0]};
      var d=body.match(/(\d+)\s*-\s*(\d+)\s*元\/天/);
      if(d) return {type:'day', low:parseInt(d[1],10), high:parseInt(d[2],10), raw:d[0]};
      var d2=body.match(/(\d+)\s*元\/天/);
      if(d2) return {type:'day', low:parseInt(d2[1],10), high:parseInt(d2[1],10), raw:d2[0]};
      return null;
    })();
    '''
    for _ in range(3):
        r = eval_js(js)
        if r: return r
        time.sleep(random.uniform(1.2, 2.0))
    return None

KEYWORDS = ["桌面运维", "网络工程师", "系统运维", "运维", "弱电", "网络管理员",
            "Linux运维", "云计算运维", "云原生", "SRE", "平台运维", "服务器运维", "IT运维"]
# 2026-08-16 扩宽候选池：在「HR 三天内活跃」(active_ok 不改) 与薪资 3-8K/日薪≥100 (sal_ok 不改) 前提下，
# 新增「运维」(覆盖 IT运维/应用运维/运维工程师/网络运维等)、「弱电」(安防弱电运维)、「网络管理员」，
# 让三天内活跃的候选池稳定 ≥40（原仅 3 词时池子常不足 40）。
# 2026-08-17 按用户职业方向（系统运维→云原生/SRE 为主、桌面运维兜底、华为代理商数通）新增 7 词：
# Linux运维 / 云计算运维 / 云原生 / SRE / 平台运维 / 服务器运维 / IT运维（明确不加网络安全/渗透）。
# 四省优先区域（福建9市 / 广东21市 / 浙江11市 / 北京），全省每一个市都搜
# city 码取自 BOSS 官方 city.json（wapi/zpCommon/data/city.json），确保准确
TIER1 = [
    "北京",
    # 福建 9 市
    "福州", "厦门", "宁德", "莆田", "泉州", "漳州", "龙岩", "三明", "南平",
    # 广东 21 市（不含东沙群岛）
    "广州", "韶关", "惠州", "梅州", "汕头", "深圳", "珠海", "佛山", "肇庆", "湛江",
    "江门", "河源", "清远", "云浮", "潮州", "东莞", "中山", "阳江", "揭阳", "茂名", "汕尾",
    # 浙江 11 市
    "杭州", "湖州", "嘉兴", "宁波", "绍兴", "台州", "温州", "丽水", "金华", "衢州", "舟山",
]
# 全国兜底区域（其余主要城市 + BOSS 全国聚合码）
TIER2 = ["上海", "成都", "武汉", "长沙", "苏州", "重庆", "天津", "西安",
         "南京", "郑州", "青岛", "合肥", "昆明", "沈阳", "济南", "全国"]
TIER1_SET = set(TIER1)

CITY = {
    # 北京
    "北京": "101010100",
    # 福建 9 市
    "福州": "101230100", "厦门": "101230200", "宁德": "101230300", "莆田": "101230400",
    "泉州": "101230500", "漳州": "101230600", "龙岩": "101230700", "三明": "101230800", "南平": "101230900",
    # 广东 21 市
    "广州": "101280100", "韶关": "101280200", "惠州": "101280300", "梅州": "101280400", "汕头": "101280500",
    "深圳": "101280600", "珠海": "101280700", "佛山": "101280800", "肇庆": "101280900", "湛江": "101281000",
    "江门": "101281100", "河源": "101281200", "清远": "101281300", "云浮": "101281400", "潮州": "101281500",
    "东莞": "101281600", "中山": "101281700", "阳江": "101281800", "揭阳": "101281900", "茂名": "101282000", "汕尾": "101282100",
    # 浙江 11 市
    "杭州": "101210100", "湖州": "101210200", "嘉兴": "101210300", "宁波": "101210400", "绍兴": "101210500",
    "台州": "101210600", "温州": "101210700", "丽水": "101210800", "金华": "101210900", "衢州": "101211000", "舟山": "101211100",
    # 全国兜底主要城市
    "上海": "101020100", "成都": "101270100", "武汉": "101200100", "长沙": "101250100", "苏州": "101190400",
    "重庆": "101040100", "天津": "101030100", "西安": "101110100", "南京": "101190100", "郑州": "101180100",
    "青岛": "101200200", "合肥": "101220100", "昆明": "101290100", "沈阳": "101070100", "济南": "101120100",
    # BOSS 全国聚合搜索码
    "全国": "100010000",
}
# ---------------------------------------------------------------------------
# 过滤参数默认值（下同）。这些值会被同目录的 config.json 覆盖，
# 见文件后部「用户配置注入」一节；不提供 config.json 时即按这里的默认值运行。
# ---------------------------------------------------------------------------
SAL_FILTER_ON = True          # 是否启用薪资筛选
SAL_MIN_MONTH, SAL_MAX_MONTH = 3, 8      # 月薪(K)：整体需落在 [min, max]
SAL_MIN_DAY, SAL_MAX_DAY = 100, 1500     # 日薪(元/天)：整体需落在 [min, max]
HR_ACTIVE_DAYS = 3            # HR 活跃度：只投 N 天内在线
EXCLUDE_KEYWORDS = []         # 职位标题含这些词则跳过（用户可配）
INTERN_KEYWORDS = ["实习", "应届", "在校", "校招", "毕业生", "校园招聘", "实习生"]
INTERN_REGEX = r"\d+届"       # 补充正则，匹配「2027届」这类写法
DO_SHUFFLE = True             # 城市/关键词顺序是否随机打乱（降低机器痕迹）

def sal_ok(s):
    if not s:
        return not SAL_FILTER_ON   # 不筛薪资时，读不到薪资也算通过
    if not SAL_FILTER_ON:
        return True
    if s.get("type") == "day":
        # 日薪：整体落在配置区间内
        return s["low"] >= SAL_MIN_DAY and s["high"] <= SAL_MAX_DAY
    # 月薪：整体落在配置区间内
    return s["low"] >= SAL_MIN_MONTH and s["high"] <= SAL_MAX_MONTH

def read_active():
    # HR 活跃度：详情页 span.boss-active-time，如「3日内活跃」「今日活跃」「本周活跃」
    return eval_js(r'''
    (function(){
      var el=document.querySelector('.boss-active-time');
      if(el) return (el.textContent||'').trim();
      var best=null;
      function walk(n){
        if(n.nodeType===3){
          var t=(n.textContent||'').trim();
          if(/活/.test(t) && t.length<=20){ if(!best) best=t; }
        } else { for(var i=0;i<n.childNodes.length;i++) walk(n.childNodes[i]); }
      }
      walk(document.body);
      return best;
    })();
    ''')
def active_ok(text):
    # HR 活跃度：只投 HR_ACTIVE_DAYS 天内在线（天数可在 config.json 调整）
    if not text: return False
    t = text
    # 明确超期
    if any(k in t for k in ["本周","本月","上周","上月"]): return False
    if "周前" in t or "月前" in t: return False
    m = re.search(r'(\d+)\s*天前', t)
    if m and int(m.group(1)) > HR_ACTIVE_DAYS: return False
    m = re.search(r'(\d+)\s*小时前', t)
    if m and int(m.group(1)) > HR_ACTIVE_DAYS * 24: return False
    # 命中以下任一即为期限内
    if any(k in t for k in ["刚刚","今日","今天","昨日","昨天","前天","天内","小时内","分钟前"]): return True
    if any(k in t for k in ["%d日内" % HR_ACTIVE_DAYS, "近%d日" % HR_ACTIVE_DAYS]): return True
    if m and int(m.group(1)) <= HR_ACTIVE_DAYS * 24: return True
    return False  # 含“活跃”但格式未知 -> 保守跳过

def list_active_ok(text):
    # 列表页 HR 预筛（只用于"省一次详情页打开"）：仅丢弃【明确超期】的岗；
    # 空/未知一律保留，交详情页 active_ok 再判，避免在列表页误杀期限内的岗
    if not text: return True
    if any(k in text for k in ["本周","本月","上周","上月","周前","月前"]): return False
    m = re.search(r'(\d+)\s*天前', text)
    if m and int(m.group(1)) > HR_ACTIVE_DAYS: return False
    m = re.search(r'(\d+)\s*月前', text)
    if m and int(m.group(1)) > 0: return False
    return True

def read_job_text():
    # 读详情页全文，用于判断是否为实习/应届岗
    return eval_js(r'''
    (function(){
      return (document.body.textContent||'').replace(/\s+/g,' ');
    })();
    ''')
def intern_ok(text):
    # 判定是否为「实习 / 应届」类岗位（关键词与正则均可在 config.json 调整）
    if not text: return False
    if any(k in text for k in INTERN_KEYWORDS): return True
    if INTERN_REGEX:
        try:
            return bool(re.search(INTERN_REGEX, text))
        except re.error:
            return False
    return False

PARSE_HREFS = '''
(function(){
  function cardActive(a){
    // 从职位链接向上找卡片容器里的 HR 活跃度标签（列表页存在 .boss-active-time）
    var n=a;
    for(var k=0;k<6;k++){
      if(!n) break;
      var el=(n.querySelector)? n.querySelector('.boss-active-time'):null;
      if(el && (el.textContent||'').trim()) return (el.textContent||'').trim();
      n=n.parentElement;
    }
    return '';  // 找不到 -> 空，预筛时保留，交给详情页再判
  }
  var links=[].slice.call(document.querySelectorAll('a[href*="job_detail"]'));
  var out=[];
  for(var i=0;i<links.length;i++){
    var a=links[i]; var href=a.getAttribute('href');
    if(href && href.indexOf('http')!==0) href='https://www.zhipin.com'+href;
    out.push({title:(a.textContent||'').replace(/\\s+/g,' ').trim(),
              href:href, active:cardActive(a)});
  }
  return out;
})();
'''

def collect_hrefs(capA=320, capB=120, per_combo=2):
    # 四省全部市优先收集；每 (城市,关键词) 组合只取 per_combo 条，确保 42 个市全部被轮到（不漏后段省份）
    # 城市/关键词顺序同层随机打乱，避免固定"按城市顺序遍历"的机器痕迹
    hrefs = []; seen = set()
    def grab(cities, cap, tag):
        cities_shuf = cities[:]; kws_shuf = KEYWORDS[:]
        if DO_SHUFFLE:
            random.shuffle(cities_shuf); random.shuffle(kws_shuf)
        for city in cities_shuf:
            if len(hrefs) >= cap: break
            code = CITY[city]
            for kw in kws_shuf:
                if len(hrefs) >= cap: break
                url = "https://www.zhipin.com/web/geek/jobs?query=" + urllib.parse.quote(kw) + "&city=" + code
                log("收集[%s] %s / %s ..." % (tag, city, kw))
                navigate(url, wait=random.uniform(3, 5))
                human_scroll(steps=random.randint(6, 10))
                st = eval_js(PARSE_HREFS, timeout=20)
                if not isinstance(st, list):
                    time.sleep(1); continue
                added = 0
                for c in st:
                    if added >= per_combo: break
                    if c["href"] in seen: continue
                    if not any(k in c["title"] for k in KEYWORDS): continue
                    if EXCLUDE_KEYWORDS and any(k in c["title"] for k in EXCLUDE_KEYWORDS):
                        continue  # 命中排除词：职位标题里带这些词就不要（如「销售」）
                    # 列表页预筛：HR 明确超3天的不收集，省一次详情页打开（未知/空保留，详情页再判）
                    if not list_active_ok(c.get("active", "")):
                        continue
                    seen.add(c["href"])
                    hrefs.append({"city": city, "kw": kw, "title": c["title"],
                                 "href": c["href"], "pri": tag == "优先"})
                    added += 1
                time.sleep(random.uniform(0.4, 1.0))
    grab(TIER1, capA, "优先")
    log("== 四省（%d 市）收集 %d 个（列表页已预筛HR），开始全国兜底 ==" % (len(TIER1), len(hrefs)))
    grab(TIER2, capA + capB, "全国")
    return hrefs

def scan_candidate(job):
    # 阶段一：打开详情页，读取薪资/活跃度/是否实习应届，不点击；返回元信息或 None（不符）
    navigate(job["href"], wait=random.uniform(4, 7))
    sal = read_salary()
    if not sal or not sal_ok(sal):
        log("   薪资 %s -> 不符" % (sal["raw"] if sal else "未知"))
        return None
    log("   薪资 %s -> 符合" % sal["raw"])
    st0 = detail_state()
    if st0 and st0["hasContinue"]:
        log("   已沟通，跳过")
        return {"skipped": True}
    act = read_active()
    if not active_ok(act):
        log("   活跃度 %s -> 超3天或未知，跳过" % (act if act else "无"))
        return None
    log("   活跃度 %s -> 三天内，符合" % (act if act else "?"))
    jt = read_job_text()
    is_intern = intern_ok(jt)
    return {"href": job["href"], "city": job["city"], "title": job["title"],
            "salary": sal["raw"], "is_intern": is_intern, "pri": job.get("pri", False)}

def wait_btn_ready(timeout=12):
    # 等待详情页「立即沟通/继续沟通」按钮渲染就绪
    # 8/17补：开头候选常因页面冷启动、按钮未渲染就 get_rect_of 导致点击落空/返回 null(?号)
    end = time.time() + timeout
    while time.time() < end:
        st = detail_state()
        if st and (st.get("hasImmediate") or st.get("hasContinue")):
            return True
        time.sleep(1.2)
    return False

def click_candidate(c):
    # 阶段二：重新打开并点击「立即沟通」，返回 (ok, st, rect)
    navigate(c["href"], wait=random.uniform(4, 7))
    if not wait_btn_ready():
        # 8/18补：页面无「立即沟通/继续沟通」按钮（岗位已下线/停招/特殊类型）
        # -> 返回 dead 标记，由 process 标 clicked 跳过，避免每个批次都重复点浪费
        log("   无沟通按钮（岗位可能已下线/停招），标记跳过")
        return False, {"dead": True, "hasContinue": False, "hasChatInput": False, "freqLimited": False, "hasGreet": False}, None
    human_read()  # 像真人一样先阅读岗位详情，再决定是否点
    st0 = detail_state()
    if st0 and st0["hasContinue"]:
        return False, st0, None
    if st0 is None:
        log("   !! 点击前详情页未就绪（重试等待）")
        wait_btn_ready(timeout=15)
        st0 = detail_state() or {"hasContinue": False, "hasChatInput": False, "freqLimited": False, "hasGreet": False}
    human_scroll(steps=random.randint(1, 2), base=200)
    time.sleep(random.uniform(0.4, 1.2))
    rect = get_rect_of("立即沟通")
    if not rect:
        # 按钮未定位：再等待+重试几次（页面未就绪时 get_rect_of 可能返回 null）
        for _ in range(3):
            time.sleep(random.uniform(1.5, 2.5))
            rect = get_rect_of("立即沟通")
            if rect:
                break
        if not rect:
            return False, None, None
    ok = False; st = None
    for attempt in range(3):  # 8/17补：重试 2->3 次，给开头候选多一次机会
        # ★2026-09-15 锁屏加固：自愈必须紧贴点击。锁屏/切窗口后页面会回落到 hidden，
        #   而此时窗口尺寸是异常的（实测锁屏时 outer=160x28），恢复前台后视口会变回 1536x864，
        #   所以「先恢复前台、再重取坐标、最后点击」，顺序不能反（否则拿旧坐标点空）。
        ensure_foreground(force=True)
        rect = get_rect_of("立即沟通")
        if not rect:
            time.sleep(random.uniform(1.5, 2.5))
            continue
        human_click(rect["x"], rect["y"])
        time.sleep(random.uniform(2.0, 4.0))  # 等"已向BOSS发送消息"greet 弹层/按钮态切换稳定
        st = detail_state()
        # 8/18补：点击后页面可能跳转/弹层导致检测失败(None) -> 等页面就绪重试，最多4次
        for _r in range(4):
            if st is not None:
                break
            time.sleep(random.uniform(2, 3.5))
            st = detail_state()
        if st is None:
            st = {"hasContinue": False, "hasChatInput": False, "freqLimited": False, "hasGreet": False}
        ok = st["hasContinue"] or st["hasChatInput"] or st.get("hasGreet")
        if ok:
            break
        log("   第%d次点击未生效（频繁=%s），2秒后重试" % (attempt+1, st.get("freqLimited")))
        time.sleep(random.uniform(2, 4))
    return ok, st, rect

# ---------- 候选持久化（错峰分批：首次全扫存json，后续时段读json点） ----------
CAND_FILE = os.path.join(SAVE_DIR, "candidates.json")
def today_str():
    return time.strftime("%Y-%m-%d")

POOL_MAX_AGE_DAYS = 2  # 候选池复用窗口：两天扫一次（扫描最耗流量，降频以稳风控）

# ===========================================================================
# 用户配置注入：读取同目录下的 config.json，覆盖上面的全部默认值。
#   · 没有 config.json 时 -> 完全按默认值运行（与原始版本行为一致）
#   · 生成配置 -> 双击 setup.bat（交互式向导）或复制 config.example.json 自行编辑
# ===========================================================================
_CFG = None
try:
    sys.path.insert(0, _HERE)
    import job_config as _jc
    _CFG = _jc.load(_HERE)
except Exception as _e:
    print("[config] 配置模块加载失败，改用内置默认值：%r" % (_e,), flush=True)

if _CFG:
    TARGET          = int(_CFG["daily_target"])
    PRIORITY_INTERN = bool(_CFG["intern_priority"])
    MAX_SCAN        = int(_CFG["max_scan_pages"])
    POOL_CAP        = int(_CFG["pool_capacity"])
    POOL_MAX_AGE_DAYS = int(_CFG["pool_max_age_days"])
    KEYWORDS        = list(_CFG["keywords"])
    EXCLUDE_KEYWORDS = list(_CFG["exclude_keywords"])
    INTERN_KEYWORDS = list(_CFG["intern_keywords"])
    INTERN_REGEX    = _CFG["intern_regex"]
    HR_ACTIVE_DAYS  = int(_CFG["hr_active_days"])
    DO_SHUFFLE      = bool(_CFG["shuffle"])
    SAL_FILTER_ON   = bool(_CFG["salary"]["enabled"])
    SAL_MIN_MONTH   = _CFG["salary"]["min_month"]
    SAL_MAX_MONTH   = _CFG["salary"]["max_month"]
    SAL_MIN_DAY     = _CFG["salary"]["min_day"]
    SAL_MAX_DAY     = _CFG["salary"]["max_day"]
    CITY.update(_CFG.get("city_codes") or {})
    TIER1 = list(_CFG["cities_priority"])
    TIER2 = list(_CFG["cities_backup"])

    # 城市必须查得到编码，否则收集阶段会 KeyError -> 这里提前拦下并给人话提示
    _missing = [c for c in (TIER1 + TIER2) if c not in CITY]
    if _missing:
        print("[config] !! 以下城市查不到编码，已跳过：%s" % "、".join(_missing), flush=True)
        print("[config]    解决：重跑 setup.bat（联网可自动查编码），或在 config.json 的 "
              "city_codes 里以 \"城市名\": \"编码\" 补上。", flush=True)
        TIER1 = [c for c in TIER1 if c in CITY]
        TIER2 = [c for c in TIER2 if c in CITY]
    if not TIER1 and not TIER2:
        raise SystemExit("[config] 没有任何可用城市，请运行 setup.bat 重新配置后再运行。")

    log("=== 本次运行配置（来源：config.json）===")
    for _line in _jc.summary_lines(_CFG):
        log("  " + _line)
    log("  实际可用：优先城市 %d 个 / 兜底城市 %d 个" % (len(TIER1), len(TIER2)))

def _days_since(date_str):
    try:
        d = time.strptime(date_str, "%Y-%m-%d")
        return (time.mktime(time.localtime()) - time.mktime(d)) / 86400
    except Exception:
        return 999

def load_candidates():
    global _SCANNED_DATE
    try:
        with open(CAND_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        _SCANNED_DATE = d.get("scanned")
        age = _days_since(d.get("date", ""))
        if 0 <= age <= POOL_MAX_AGE_DAYS and d.get("candidates"):
            return d
    except Exception:
        pass
    return None
_SCANNED_DATE = None  # 上次全量扫描日期（用于 19:00 每两天周期重扫判定，8/17 用户方案；放这避免 load 前置引用）
def save_candidates(cands, is_scan=False):
    global _SCANNED_DATE
    if is_scan:
        _SCANNED_DATE = today_str()
    try:
        with open(CAND_FILE, "w", encoding="utf-8") as f:
            d = {"date": today_str(), "candidates": cands}
            if _SCANNED_DATE:
                d["scanned"] = _SCANNED_DATE
            json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception as e:
        log("   !! 写候选json失败: %s" % repr(e)[:80])

# ==================== P0/P1 增强模块（2026-09-15 按《对话汇总_2026-09-14》落地）====================
# P0：沟通记录归档(SQLite) + 每日飞书汇总
# P1：会话保活/连接自愈 + 断点续跑(扫描中途落盘) + 限流优雅止损 + 运行时登录态校验
# 红线不变：不自动登录；不改写发消息主流程；推送/落库失败绝不阻塞投递。
import sqlite3, hmac, hashlib, base64

DB_FILE = os.path.join(SAVE_DIR, "boss_sends.db")

def db_init():
    try:
        con = sqlite3.connect(DB_FILE, timeout=10)
        con.execute("""CREATE TABLE IF NOT EXISTS sends(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, date TEXT, batch TEXT, city TEXT, title TEXT, salary TEXT,
            is_intern INTEGER, href TEXT UNIQUE, status TEXT, note TEXT)""")
        con.execute("""CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, href TEXT, type TEXT, note TEXT)""")
        con.commit(); con.close(); return True
    except Exception as e:
        log("   !! 数据库初始化失败（不影响投递）: %s" % repr(e)[:80]); return False

def db_log_send(c, batch_no, status, note=""):
    """记录一次沟通结果；同一岗位按 href 去重并更新为最新状态。"""
    try:
        con = sqlite3.connect(DB_FILE, timeout=10)
        con.execute("""INSERT INTO sends(ts,date,batch,city,title,salary,is_intern,href,status,note)
                       VALUES(?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(href) DO UPDATE SET ts=excluded.ts, batch=excluded.batch,
                       status=excluded.status, note=excluded.note""",
                    (time.strftime("%Y-%m-%d %H:%M:%S"), today_str(), str(batch_no),
                     c.get("city", ""), c.get("title", ""), c.get("salary", ""),
                     1 if c.get("is_intern") else 0, c.get("href", ""), status, str(note)[:200]))
        con.commit(); con.close()
    except Exception as e:
        log("   !! 写入沟通记录失败（不影响投递）: %s" % repr(e)[:80])

def db_today(date_str):
    try:
        con = sqlite3.connect(DB_FILE, timeout=10)
        rows = con.execute("SELECT status, COUNT(*) FROM sends WHERE date=? GROUP BY status", (date_str,)).fetchall()
        total = con.execute("SELECT COUNT(*) FROM sends WHERE date=?", (date_str,)).fetchone()[0]
        con.close(); return total, dict(rows)
    except Exception:
        return 0, {}

def _cfg(name):
    """配置取值：环境变量优先，其次读项目目录下同名 .txt 文件（免改 3 条 automation 环境变量）。"""
    v = os.environ.get(name, "").strip()
    if v:
        return v
    try:
        f = os.path.join(SAVE_DIR, "%s.txt" % name.lower())
        if os.path.exists(f):
            return open(f, encoding="utf-8").read().strip()
    except Exception:
        pass
    return ""

def push_feishu(text):
    """每日飞书汇总（P0）。未配 FEISHU_WEBHOOK（环境变量或 feishu_webhook.txt）则静默跳过；
    任何异常都不阻塞主流程。"""
    url = _cfg("FEISHU_WEBHOOK")
    if not url:
        log("（未配置 FEISHU_WEBHOOK，跳过飞书推送）"); return False
    try:
        payload = {"msg_type": "text", "content": {"text": text}}
        secret = _cfg("FEISHU_SECRET")
        if secret:
            # 飞书官方签名：sign = base64(HMAC-SHA256(key="{ts}\n{secret}", msg=""))
            # 注意 key 是 "时间戳\n密钥"、msg 为空串 —— 写反了会导致签名校验失败
            ts = str(int(time.time()))
            sign = base64.b64encode(hmac.new(("%s\n%s" % (ts, secret)).encode("utf-8"), b"",
                                             hashlib.sha256).digest()).decode("utf-8")
            payload["timestamp"] = ts; payload["sign"] = sign
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=10).read()
        except Exception:
            # 部分环境存在 HTTP_PROXY 且会把出站请求吃掉（返 502），这里直连再试一次
            _no_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            _no_proxy.open(req, timeout=10).read()
        log("飞书推送成功"); return True
    except Exception as e:
        log("   !! 飞书推送失败（不影响投递）: %s" % repr(e)[:100]); return False

def ws_healthy(timeout=6):
    """短超时探针。断连时不再让每个操作耗满 25-30s（此前会"慢性死亡"近 10 分钟）。"""
    try:
        return eval_js("1", timeout=timeout) == 1
    except Exception:
        return False

def reconnect_ws():
    """断连自愈：重新取 zhipin 页面 target 并重建连接。"""
    global ws
    try: ws.close()
    except Exception: pass
    new_ws = _pick_page_ws()
    if not new_ws: return False
    try:
        ws = websocket.create_connection(new_ws, timeout=40, origin="http://127.0.0.1:9223")
        ensure_foreground(force=True)
        return ws_healthy()
    except Exception as e:
        log("   !! 重连失败: %s" % repr(e)[:80]); return False

def ensure_alive():
    """每个候选前调用：不健康则重连一次；仍不行返回 False（由调用方优雅退出）。"""
    if ws_healthy(): return True
    log("   !! 检测到 CDP 连接断开，尝试重连 ...")
    time.sleep(2)
    return reconnect_ws()

def is_logged_in():
    """运行时登录态校验。红线：只检测、只告警，绝不自动登录。"""
    try:
        u = eval_js("location.href", timeout=8) or ""
        if "/login" in u or "passport" in u: return False
        r = eval_js(r"""(function(){var t=document.body.textContent||'';
            return (t.indexOf('密码登录')>=0||t.indexOf('短信登录')>=0||t.indexOf('扫码登录')>=0)
                   && document.querySelector('input[type=password]')!=null;})()""", timeout=8)
        return not bool(r)
    except Exception:
        return True  # 探测失败不误杀

def do_scan():
    # 阶段一：扫描，收集合格候选（含是否实习/应届），多存一些（TARGET*2）防后续批次点失败不够
    # 两天扫一次：仅在无可用候选 / 剩余不足 / 18:00 周期触发时全量扫描，避免每日重复扫描、降低请求量
    hrefs = collect_hrefs()
    log("候选链接 %d 个" % len(hrefs))
    qualified = []; scanned = 0
    for idx, job in enumerate(hrefs, 1):
        if scanned >= MAX_SCAN: break
        if len(qualified) >= POOL_CAP: break
        if not ensure_alive():  # 连接自愈：断连不再空转到跑完全程
            log("!! 连接不可恢复，提前结束扫描（先把已合格的 %d 个落盘）" % len(qualified))
            break
        scanned += 1
        try:
            log("(%d/%d) 扫描 %s | %s" % (idx, len(hrefs), job["city"], job["title"]))
            c = scan_candidate(job)
            if c is None:
                time.sleep(random.uniform(1.5, 3)); continue
            if c.get("skipped"):
                time.sleep(random.uniform(1.0, 2.0)); continue
            qualified.append(c)
            log("   合格（实习应届=%s）" % c["is_intern"])
            if len(qualified) % 10 == 0:
                save_candidates(qualified)  # 断点续跑：扫描中途每 10 个回写，防中途崩溃全丢
            time.sleep(random.uniform(1.5, 3))
        except Exception as e:
            log("   !! 扫描异常: %s" % repr(e)[:120]); time.sleep(3); continue
    n_intern = sum(1 for c in qualified if c["is_intern"])
    log("扫描 %d 个，合格 %d 个（其中实习/应届 %d 个）" % (scanned, len(qualified), n_intern))
    # 排序：四省优先（排他，四省不够才补全国）+ 四省内部实习/应届优先；同层随机打散
    # 优先级：四省(实习应届在前) > 四省普通岗 > 全国(仅四省不足TARGET时兜底)
    if PRIORITY_INTERN:
        qualified.sort(key=lambda c: (not c.get("pri", False), not c["is_intern"], random.random()))
    for c in qualified:
        c.setdefault("clicked", False)
    save_candidates(qualified, is_scan=True)  # 扫描完成：记录 scanned=今天（供 19:00 每两天周期重扫判定）
    log("候选已存 %s（扫描刷新，共 %d 个）" % (CAND_FILE, len(qualified)))
    return qualified

def process():
    batch = int(os.environ.get("BOSS_BATCH", TARGET))  # 本次批次目标；不设则默认一次发满 TARGET
    log("本次批次目标 BOSS_BATCH=%d" % batch)
    db_init()
    # 连续"点了没反馈"达到该阈值即优雅止损（此前会一路空点到池子耗尽，约 70 分钟纯空转）
    # 默认值来自 config.json 的 throttle_stop；环境变量优先级更高
    _thr_default = int(_CFG["throttle_stop"]) if _CFG else 8
    THROTTLE_STOP = int(os.environ.get("BOSS_THROTTLE_STOP", _thr_default))
    consec_fail = 0
    login_check_n = 0
    data = load_candidates()
    pool_age = _days_since(data["date"]) if data else None
    if data:
        cands = data["candidates"]
        remain = [c for c in cands if not c.get("clicked")]
        log("复用候选 json（age=%.0f天）：共 %d 个，未点 %d 个" % (pool_age, len(cands), len(remain)))
        if len(remain) < batch:
            log("剩余不足本批(%d<%d)，提前重扫" % (len(remain), batch))
            cands = do_scan(); pool_age = 0
    else:
        log("无可用候选 json，首次扫描")
        cands = do_scan(); pool_age = 0
    # 阶段二（批次点击）：按 json 顺序点接下来 batch 个未点的；首次运行即点首批
    clicked_now = []; sent = 0
    for qi, c in enumerate(cands):
        if sent >= batch: break
        if c.get("clicked"): continue
        need = batch - sent
        left_in_json = sum(1 for x in cands[qi+1:] if not x.get("clicked"))
        # 真人式偶尔跳过：仅当本批候选仍明显富余时才跳（凑不满风险极低）
        if sent >= 4 and left_in_json > need + 3 and random.random() < 0.12:
            log("   （真人式临时跳过 %s | %s，候选仍足）" % (c["city"], c["title"][:24]))
            time.sleep(random.uniform(2, 5))
            continue
        if not ensure_alive():
            log("!! 连接不可恢复，提前结束本批（已发 %d/%d）" % (sent, batch))
            break
        login_check_n += 1
        if login_check_n % 5 == 1 and not is_logged_in():
            log("!! 检测到 Boss 掉登录，停止本批（请人工登录后再跑）")
            push_feishu("Boss 脚本告警：检测到掉登录，本批已停止。请人工登录后再运行。")
            break
        if consec_fail >= THROTTLE_STOP:
            log("!! 连续 %d 次点击无反馈，判定疑似静默限流，优雅止损（不再空耗候选与请求）" % consec_fail)
            break
        try:
            log("点击 %s | %s | %s" % (c["city"], c.get("salary"), c["title"]))
            ok, st, rect = click_candidate(c)
            # 8/18补：无沟通按钮的死岗位（已下线/停招）-> 标 clicked 跳过，避免每个批次重复点
            if st and st.get("dead"):
                c["clicked"] = True
                log("   （无按钮岗位已标记跳过）")
            # 双保险：Boss 已沟通也标记 clicked，避免后续批次重复尝试
            elif st and st.get("hasContinue"):
                c["clicked"] = True
            try:
                p = os.path.join(SAVE_DIR, "batch_%02d.png" % (len(clicked_now)+1))
                send("Page.captureScreenshot", {"format": "png", "path": p}); time.sleep(0.4)
            except Exception: pass
            log("   结果: 继续沟通=%s 聊天框=%s 频繁=%s" % (
                st["hasContinue"] if st else "?", st["hasChatInput"] if st else "?", st.get("freqLimited") if st else "?"))
            if ok:
                c["clicked"] = True
                clicked_now.append(c)
                sent += 1
                consec_fail = 0
                db_log_send(c, batch, "sent", "")
            else:
                if st and st.get("dead"):
                    db_log_send(c, batch, "dead", "岗位无沟通按钮/已下架")
                    consec_fail = 0  # 死岗属正常情形，不计入限流判定
                elif st and st.get("hasContinue"):
                    db_log_send(c, batch, "already", "此前已沟通")
                    consec_fail = 0
                else:
                    consec_fail += 1
                    db_log_send(c, batch, "failed", "继续沟通=%s 频繁=%s" % (
                        st.get("hasContinue") if st else "?", st.get("freqLimited") if st else "?"))
            # 拟人间隔：基础 20-50s；每成功 4 个插 1-3 分钟长停顿；15% 概率再分心 30-90s
            gap = random.uniform(20, 50)
            if sent > 0 and sent % 4 == 0:
                gap += random.uniform(60, 180)
            if random.random() < 0.15:
                gap += random.uniform(30, 90)
            time.sleep(gap)
            save_candidates(cands)  # 边点边存：每处理一个立即回写，防止中断丢回写（8/17补，修数据滞留）
        except Exception as e:
            log("   !! 点击异常: %s" % repr(e)[:120]); time.sleep(3); continue
    save_candidates(cands)  # 回写 clicked 状态，供后续批次复用
    n_c_intern = sum(1 for c in clicked_now if c["is_intern"])
    total_clicked = sum(1 for c in cands if c.get("clicked"))
    log("=== 本批完成：本次成功 %d/%d（实习/应届 %d 个）；今日累计已点 %d/%d ===" % (
        len(clicked_now), batch, n_c_intern, total_clicked, TARGET))
    for i, c in enumerate(clicked_now, 1):
        log("  [批%d] %s %s %s 实习=%s" % (i, c["city"], c.get("salary"), c["title"], c["is_intern"]))
    # ---- P0：沟通记录归档 + 每日汇总（推送失败绝不阻塞；未配 webhook 则只写日志）----
    _today = today_str()
    _n, _by = db_today(_today)
    _lines = ["Boss 投递日报 %s" % _today,
              "本批成功 %d/%d（实习/应届 %d）" % (len(clicked_now), batch, n_c_intern),
              "今日累计已点 %d/%d" % (total_clicked, TARGET),
              "今日记录(SQLite) %d 条：%s" % (_n, " / ".join("%s=%s" % (k, v) for k, v in sorted(_by.items())) or "无")]
    if clicked_now:
        _lines.append("本批岗位：")
        for i, c in enumerate(clicked_now, 1):
            _lines.append("  %d. %s %s %s%s" % (i, c["city"], c.get("salary"), c["title"][:26],
                                                " [实习]" if c["is_intern"] else ""))
    _summary = "\n".join(_lines)
    log("=== 日报 ===\n%s" % _summary)
    push_feishu(_summary)
    navigate("https://www.zhipin.com/web/geek/chat", wait=5)
    # 阶段三：两天周期重扫（仅 19:00 末批设置 BOSS_SCAN_AFTER 时触发；点完再扫，只扫不点刷新池子）
    # 8/17 用户方案：按「距上次扫描≥2天」判定——不再看 date/池龄（save 每次都把 date 刷成当天，池龄永远<2，原条件永不触发）
    if os.environ.get("BOSS_SCAN_AFTER"):
        scan_age = _days_since(_SCANNED_DATE) if _SCANNED_DATE else 999
        if scan_age >= POOL_MAX_AGE_DAYS:
            log("=== 触发两天周期重扫（BOSS_SCAN_AFTER, 距上次扫描=%.0f天）===" % scan_age)
            do_scan()
    return clicked_now

log("=== 开始（v12：两天扫一次·单次扫100·一天投50 + 3时段×17/17/16 + 实习应届优先 + 列表页HR预筛 + 拟人节奏）===")
process()
log("===DONE===")
ws.close()
