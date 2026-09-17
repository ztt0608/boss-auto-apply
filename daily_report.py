# -*- coding: utf-8 -*-
"""从 boss_sends.db 生成当日投递日报（markdown），可选推送飞书。

用法：
  python daily_report.py                # 生成「今天」的日报
  python daily_report.py 2026-09-16     # 生成指定日期
  BOSS_REPORT_DATE=2026-09-16 python daily_report.py
配置（可选，与 boss_batch.py 同源环境变量）：
  FEISHU_WEBHOOK / FEISHU_SECRET —— 未配置则只写文件、静默跳过推送；推送异常不影响生成。
"""
import os, sys, json, time, sqlite3, hashlib, base64, hmac, urllib.request, collections

D = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(D, "boss_sends.db")
CAND = os.path.join(D, "candidates.json")
PLAN = {"07": 17, "13": 17, "19": 16}  # 三批计划份数（脚本 TARGET=50）

TODAY = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BOSS_REPORT_DATE", "")).strip() \
    or time.strftime("%Y-%m-%d")

con = sqlite3.connect(DB)
rows = con.execute("""SELECT ts, batch, city, title, salary, is_intern, status, note
                      FROM sends WHERE date=? ORDER BY ts""", (TODAY,)).fetchall()
by = dict(con.execute("SELECT status,COUNT(*) FROM sends WHERE date=? GROUP BY status", (TODAY,)))
allc = con.execute("SELECT COUNT(*) FROM sends").fetchone()[0]
con.close()

sent = [r for r in rows if r[6] == "sent"]
intern_n = sum(1 for r in sent if r[5] == 1)

pool = {}
cands = []
if os.path.exists(CAND):
    _c = json.load(open(CAND, encoding="utf-8"))
    cands = _c.get("candidates", [])
    pool = {"total": len(cands), "clicked": sum(1 for x in cands if x.get("clicked"))}
    pool["left"] = pool["total"] - pool["clicked"]
    pool["date"] = _c.get("date", "")

L = []
L.append("# Boss 投递日报 · %s" % TODAY)
L.append("")
L.append("| 指标 | 数值 |")
L.append("| --- | --- |")
L.append("| 今日实际发出（已沟通） | **%d** |" % len(sent))
L.append("| 其中实习/应届 | %d |" % intern_n)
L.append("| 已沟通/死岗（未重复发） | %d |" % by.get("already", 0))
if by.get("failed"):
    L.append("| 失败 | %d |" % by["failed"])
L.append("| 全天目标 | 50（07/13/19 三批 17/17/16） |")
L.append("| 达成率 | %.0f%% |" % (len(sent) / 50 * 100))
if pool:
    L.append("| 候选池（%s） | 总 %d，已点 %d，待点 %d |"
             % (pool.get("date", "?"), pool["total"], pool["clicked"], pool["left"]))
L.append("| 数据库累计 | %d 条 |" % allc)
L.append("| 展示口径 | `sent` + `already` 计入池内消耗；`failed` 不计（失败不标 clicked，可留待重试） |")
L.append("")

# ---------- 批次复盘（按 DB 的 batch 标签自动汇总） ----------
L.append("## 批次复盘")
L.append("")
L.append("| 批次 | 时段（首 → 末） | 计划 | 实际发出 | 其他 | 说明 |")
L.append("| --- | --- | --- | --- | --- | --- |")
grp = collections.OrderedDict()
for ts, batch, city, title, salary, isin, status, note in rows:
    grp.setdefault(batch or "?", []).append((ts, status))

def _slot(batch):
    b = (batch or "").strip()
    if b.isdigit():
        n = int(b)
        if n >= 16:
            return "19:00 末批"
        if n >= 10:
            return "13:00 第2批"
        if n >= 6:
            return "07:00 第1批"
        return "临时验证批"
    if b == "backfill":
        return "日志回填（历史）"
    return "手工批"

for batch, items in grp.items():
    t0, t1 = items[0][0][11:16], items[-1][0][11:16]
    n_sent = sum(1 for _, s in items if s == "sent")
    other = collections.Counter(s for _, s in items if s != "sent")
    other_s = "、".join("%s %d" % (k, v) for k, v in other.items()) or "-"
    plan = int(batch) if (batch or "").isdigit() else "-"
    note = ""
    if plan != "-" and n_sent < plan:
        note = "未达标（差 %d）" % (plan - n_sent)
    elif plan != "-":
        note = "达标"
    L.append("| %s | %s → %s | %s | %d | %s | %s |"
             % (_slot(batch), t0, t1, plan, n_sent, other_s, note))
L.append("")
L.append("> 说明：本表由 `boss_sends.db` 的 `batch` 字段自动汇总，`batch=backfill` 为历史数据回填，"
         "非当日真实排班记录。")
L.append("")

L.append("## 今日发出明细（%d 条）" % len(sent))
L.append("")
L.append("| # | 时间 | 城市 | 薪资 | 岗位 | 实习/应届 |")
L.append("| --- | --- | --- | --- | --- | --- |")
for i, (ts, batch, city, title, salary, isin, status, note) in enumerate(sent, 1):
    L.append("| %d | %s | %s | %s | %s | %s |"
             % (i, ts[11:16], city, salary, (title or "").replace("|", "/")[:30], "是" if isin else "否"))

if by.get("already"):
    L.append("")
    L.append("## 已沟通/跳过（%d 条）" % by["already"])
    L.append("")
    for ts, batch, city, title, salary, isin, status, note in rows:
        if status == "already":
            L.append("- %s · %s · %s · %s"
                     % (city, salary, (title or "").replace("|", "/")[:30], note or ""))

if pool and pool.get("left") is not None and cands:
    un = [x for x in cands if not x.get("clicked")]
    L.append("")
    L.append("## 候选池余量（%s）" % pool.get("date", "?"))
    L.append("")
    L.append("- 总 %d / 已点 %d / **待点 %d**" % (pool["total"], pool["clicked"], pool["left"]))
    L.append("- 待点中实习/应届：%d" % sum(1 for x in un if x.get("is_intern")))
    top = collections.Counter(x.get("city", "?") for x in un).most_common(8)
    if top:
        L.append("- 待点城市分布：" + "、".join("%s %d" % (c, n) for c, n in top))
    L.append("- 池龄判断：脚本 `POOL_MAX_AGE_DAYS=2`，超龄后 19:00 末批会自动重扫；待点数不足当日剩余批次时会提前重扫。")

L.append("")
L.append("> 数据来源：`boss_sends.db`（SQLite）。落库由 `boss_batch.py` 在每次点击结果确定后写入。")
out = os.path.join(D, "日报_%s.md" % TODAY)
open(out, "w", encoding="utf-8").write("\n".join(L))
print("written:", out, "| rows:", len(rows), "| sent:", len(sent))


# ---------- 飞书推送（可选，未配置则静默跳过；任何异常不阻塞） ----------
def _cfg(name):
    """配置取值：环境变量优先，其次读项目目录下同名 .txt 文件（与 boss_batch.py 同源）。"""
    v = os.environ.get(name, "").strip()
    if v:
        return v
    try:
        f = os.path.join(D, "%s.txt" % name.lower())
        if os.path.exists(f):
            return open(f, encoding="utf-8").read().strip()
    except Exception:
        pass
    return ""


def push_feishu(text):
    url = _cfg("FEISHU_WEBHOOK")
    if not url:
        print("（未配置 FEISHU_WEBHOOK，跳过飞书推送）")
        return False
    try:
        payload = {"msg_type": "text", "content": {"text": text}}
        secret = _cfg("FEISHU_SECRET")
        if secret:  # 飞书官方签名：sign = base64(HMAC-SHA256(key="{ts}\n{secret}", msg=""))
            ts = str(int(time.time()))
            s = "%s\n%s" % (ts, secret)
            sign = base64.b64encode(hmac.new(s.encode("utf-8"), b"", digestmod=hashlib.sha256).digest()).decode()
            payload["timestamp"] = ts
            payload["sign"] = sign
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        # 先按系统代理发；失败再直连重试一次（部分环境 HTTP_PROXY 会吃掉出站请求返 502）
        try:
            urllib.request.urlopen(req, timeout=10).read()
        except Exception:
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=10).read()
        print("feishu: ok")
        return True
    except Exception as e:
        print("feishu push failed (ignored):", e)
        return False


if len(sent) or by.get("already"):
    push_feishu("Boss 投递日报 %s\n发出 %d / 目标 50（实习/应届 %d）\n已沟通跳过 %d%s\n详情见本地 %s"
                % (TODAY, len(sent), intern_n, by.get("already", 0),
                   ("\n候选池待点 %d" % pool["left"]) if pool else "", os.path.basename(out)))
