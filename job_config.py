# -*- coding: utf-8 -*-
"""用户配置加载器 —— 让本工具适用于任何行业 / 任何岗位方向。

设计原则
--------
1. **缺省即原状**：没有 config.json 时，行为与原版脚本完全一致（内置默认值）。
2. **不猜不猜**：配置项非法时给出明确中文提示并回退默认值，绝不静默失败。
3. **与脚本同目录**：config.json 放在脚本旁边，整个文件夹依然便携。

用法（脚本内部）：:

    import job_config
    cfg = job_config.load(_HERE)          # 返回已合并默认值、已校验的 dict
    cfg = job_config.load(_HERE, quiet=True)

用户视角：双击 ``setup.bat`` 生成 config.json，或直接编辑 config.json。
"""

import ast
import json
import os
import re

CONFIG_NAME = "config.json"
EXAMPLE_NAME = "config.example.json"

# ----------------------------------------------------------------------------
# 内置默认值：与脚本原始行为保持一致（IT 运维方向）。
# 任何用户都可以用 config.json 覆盖，无需改代码。
# ----------------------------------------------------------------------------
DEFAULTS = {
    "daily_target": 50,
    "batch_counts": [17, 17, 16],
    "intern_priority": True,
    "intern_keywords": ["实习", "应届", "在校", "校招", "毕业生", "校园招聘", "实习生"],
    "intern_regex": r"\d+届",
    "keywords": [
        "桌面运维", "网络工程师", "系统运维", "运维", "弱电", "网络管理员",
        "Linux运维", "云计算运维", "云原生", "SRE", "平台运维", "服务器运维", "IT运维",
    ],
    "exclude_keywords": [],
    "cities_priority": [
        "北京",
        "福州", "厦门", "宁德", "莆田", "泉州", "漳州", "龙岩", "三明", "南平",
        "广州", "韶关", "惠州", "梅州", "汕头", "深圳", "珠海", "佛山", "肇庆", "湛江",
        "江门", "河源", "清远", "云浮", "潮州", "东莞", "中山", "阳江", "揭阳", "茂名", "汕尾",
        "杭州", "湖州", "嘉兴", "宁波", "绍兴", "台州", "温州", "丽水", "金华", "衢州", "舟山",
    ],
    "cities_backup": [
        "上海", "成都", "武汉", "长沙", "苏州", "重庆", "天津", "西安",
        "南京", "郑州", "青岛", "合肥", "昆明", "沈阳", "济南",
    ],
    "city_codes": {},
    "salary": {
        "enabled": True,
        "min_month": 3,
        "max_month": 8,
        "min_day": 100,
        "max_day": 1500,
    },
    "hr_active_days": 3,
    "pool_max_age_days": 2,
    "pool_capacity": 110,
    "max_scan_pages": 500,
    "throttle_stop": 8,
    "shuffle": True,
}

# 直辖市：本身就是一个可搜索的市，不做省份展开
MUNICIPALITIES = {"北京", "上海", "天津", "重庆"}

CITY_JSON_URL = "https://www.zhipin.com/wapi/zpCommon/data/city.json"


# ============================================================================
# 配置读取
# ============================================================================
def config_path(base_dir):
    return os.path.join(base_dir, CONFIG_NAME)


def example_path(base_dir):
    return os.path.join(base_dir, EXAMPLE_NAME)


def _merge(base, override):
    """递归合并（dict 深合并，其余直接覆盖）。"""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _as_list_of_str(value, field, warnings):
    if value is None:
        return None
    if isinstance(value, str):
        parts = [p.strip() for p in re.split(r"[,\uFF0C;；\n]+", value) if p.strip()]
        return parts
    if isinstance(value, (list, tuple)):
        return [str(x).strip() for x in value if str(x).strip()]
    warnings.append("配置项 %s 应为列表或逗号分隔的字符串，已忽略。" % field)
    return None


def _positive_int(value, field, warnings, minimum=1):
    try:
        n = int(value)
    except (TypeError, ValueError):
        warnings.append("配置项 %s 应为整数，已忽略（用默认值）。" % field)
        return None
    if n < minimum:
        warnings.append("配置项 %s 至少为 %d，已忽略（用默认值）。" % (field, minimum))
        return None
    return n


def validate(raw, warnings):
    """把用户配置规整成安全可用的形态；非法项回退默认值并记录警告。"""
    cfg = _merge(DEFAULTS, raw)

    for field in ("daily_target", "hr_active_days", "pool_max_age_days",
                  "pool_capacity", "max_scan_pages", "throttle_stop"):
        n = _positive_int(cfg.get(field), field, warnings)
        if n is not None:
            cfg[field] = n
        else:
            cfg[field] = DEFAULTS[field]

    for field in ("keywords", "cities_priority", "cities_backup",
                  "exclude_keywords", "intern_keywords"):
        lst = _as_list_of_str(cfg.get(field), field, warnings)
        if lst is not None:
            cfg[field] = lst
        else:
            cfg[field] = list(DEFAULTS[field])

    # 分批数量是整数列表（用于展示与对账），不做字符串化
    batches = _as_list_of_str(cfg.get("batch_counts"), "batch_counts", warnings)
    parsed = []
    for x in (batches or []):
        try:
            parsed.append(int(x))
        except (TypeError, ValueError):
            pass
    cfg["batch_counts"] = parsed or list(DEFAULTS["batch_counts"])

    cfg["intern_priority"] = bool(cfg.get("intern_priority", DEFAULTS["intern_priority"]))
    cfg["shuffle"] = bool(cfg.get("shuffle", DEFAULTS["shuffle"]))

    # 关键词不能为空 —— 否则整个扫描没有意义
    if not cfg["keywords"]:
        warnings.append("配置项 keywords 为空，已回退为内置默认关键词（IT 运维方向）。")
        cfg["keywords"] = list(DEFAULTS["keywords"])

    # 至少要有可搜索的城市
    if not cfg["cities_priority"] and not cfg["cities_backup"]:
        warnings.append("cities_priority 与 cities_backup 都为空，已回退为内置默认城市。")
        cfg["cities_priority"] = list(DEFAULTS["cities_priority"])
        cfg["cities_backup"] = list(DEFAULTS["cities_backup"])

    # 正则在用户填错时要能兜住
    rx = cfg.get("intern_regex") or ""
    if rx:
        try:
            re.compile(rx)
            cfg["intern_regex"] = rx
        except re.error as e:
            warnings.append("配置项 intern_regex 不是合法正则（%s），已忽略。" % e)
            cfg["intern_regex"] = ""
    else:
        cfg["intern_regex"] = ""

    # 城市编码表
    codes = cfg.get("city_codes")
    if not isinstance(codes, dict):
        warnings.append("配置项 city_codes 应为 {\"城市名\": \"编码\"} 形式，已忽略。")
        codes = {}
    cfg["city_codes"] = {str(k).strip(): str(v).strip() for k, v in codes.items()}

    # 薪资区间
    sal = cfg.get("salary")
    if not isinstance(sal, dict):
        warnings.append("配置项 salary 应为对象，已忽略。")
        sal = {}
    merged_sal = _merge(DEFAULTS["salary"], sal)
    for k in ("min_month", "max_month", "min_day", "max_day"):
        try:
            v = float(merged_sal[k])
        except (TypeError, ValueError):
            warnings.append("salary.%s 应为数字，已用默认值 %s。" % (k, DEFAULTS["salary"][k]))
            v = float(DEFAULTS["salary"][k])
        merged_sal[k] = int(v) if v.is_integer() else v
    merged_sal["enabled"] = bool(merged_sal.get("enabled", True))
    if merged_sal["min_month"] > merged_sal["max_month"]:
        warnings.append("salary.min_month 大于 max_month，已对调。")
        merged_sal["min_month"], merged_sal["max_month"] = \
            merged_sal["max_month"], merged_sal["min_month"]
    if merged_sal["min_day"] > merged_sal["max_day"]:
        warnings.append("salary.min_day 大于 max_day，已对调。")
        merged_sal["min_day"], merged_sal["max_day"] = \
            merged_sal["max_day"], merged_sal["min_day"]
    cfg["salary"] = merged_sal

    return cfg


def load(base_dir, quiet=False):
    """读取 config.json（缺失则用内置默认值），返回校验后的 dict。"""
    path = config_path(base_dir)
    raw, warnings = {}, []
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                warnings.append("config.json 顶层应为 JSON 对象，已忽略整个文件。")
                raw = {}
        except Exception as e:
            warnings.append("config.json 解析失败（%s），已改用内置默认值。" % e)
            raw = {}
    else:
        warnings.append("未找到 config.json，正在使用内置默认值（IT 运维方向）。"
                        "建议先运行 setup.bat 生成你自己的配置。")

    cfg = validate(raw, warnings)
    if not quiet:
        for w in warnings:
            print("[config] %s" % w, flush=True)
    return cfg


def summary_lines(cfg):
    """给日志/向导用的人类可读摘要。"""
    sal = cfg["salary"]
    if sal["enabled"]:
        sal_txt = "月薪 %g-%gK 或 日薪 %g-%g 元" % (
            sal["min_month"], sal["max_month"], sal["min_day"], sal["max_day"])
    else:
        sal_txt = "不筛选薪资"
    intern_txt = "优先" if cfg["intern_priority"] else "不特殊处理"
    return [
        "每日目标：%d（分批 %s）" % (cfg["daily_target"], "/".join(str(x) for x in cfg["batch_counts"])),
        "关键词（%d 个）：%s" % (len(cfg["keywords"]), "、".join(cfg["keywords"])),
        "排除词（%d 个）：%s" % (len(cfg["exclude_keywords"]),
                              "、".join(cfg["exclude_keywords"]) or "（无）"),
        "优先城市（%d 个）：%s" % (len(cfg["cities_priority"]),
                              "、".join(cfg["cities_priority"][:12])
                              + ("…" if len(cfg["cities_priority"]) > 12 else "")),
        "兜底城市（%d 个）：%s" % (len(cfg["cities_backup"]),
                              "、".join(cfg["cities_backup"][:12])
                              + ("…" if len(cfg["cities_backup"]) > 12 else "")),
        "薪资：%s" % sal_txt,
        "HR 活跃度：%d 天内在线" % cfg["hr_active_days"],
        "实习/应届：%s" % intern_txt,
    ]


def write(base_dir, cfg, backup=True):
    """写出 config.json（旧文件自动备份为 config.json.bak）。"""
    path = config_path(base_dir)
    if backup and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                old = f.read()
            with open(path + ".bak", "w", encoding="utf-8") as f:
                f.write(old)
        except Exception:
            pass
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


# ============================================================================
# 城市编码表：优先在线取 Boss 官方数据，离线时回退到主脚本内置表
# ============================================================================
def _city_table_online(timeout=15):
    """从 Boss 官方 city.json 取全量城市（含省份下的所有市）。"""
    import urllib.request
    req = urllib.request.Request(CITY_JSON_URL, headers={
        "User-Agent": "Mozilla/5.0", "Referer": "https://www.zhipin.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    flat, provinces = {}, {}
    for top in (data.get("zpData") or data).get("cityList", []):
        name, code = top.get("name"), top.get("code")
        subs = top.get("subLevelModelList") or []
        if name and code:
            if name in MUNICIPALITIES:
                flat[name] = code
            elif subs:
                provinces[name] = [(s.get("name"), s.get("code")) for s in subs
                                   if s.get("name") and s.get("code")]
                flat.setdefault(name, code)
            else:
                flat[name] = code
        for s in subs:
            if s.get("name") and s.get("code"):
                flat.setdefault(s["name"], s["code"])
    return flat, provinces


def _city_table_builtin(base_dir):
    """从主脚本源码里解析 CITY 字典（AST），离线可用、始终与脚本同步。"""
    src_path = os.path.join(base_dir, "boss_batch.py")
    if not os.path.exists(src_path):
        return {}, {}
    try:
        tree = ast.parse(open(src_path, encoding="utf-8").read())
    except Exception:
        return {}, {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "CITY":
                    try:
                        return dict(ast.literal_eval(node.value)), {}
                    except Exception:
                        return {}, {}
    return {}, {}


def load_city_table(base_dir, online=True, quiet=False):
    """返回 (flat_name_to_code, provinces_name_to_children)。

    先试官方在线数据（覆盖全国），失败则回退主脚本内置表。
    """
    if online:
        try:
            flat, prov = _city_table_online()
            if flat:
                return flat, prov
        except Exception as e:
            if not quiet:
                print("[config] 在线获取城市表失败（%s），改用内置表。" % e)
    return _city_table_builtin(base_dir)


def resolve_cities(tokens, flat, provinces):
    """把用户输入的城市/省份解析为 (城市名, 编码) 列表。

    支持三种写法：
      · 城市名      -> 福州            （查表）
      · 省份名      -> 福建            （展开为该省所有市；Boss 不支持省份聚合码）
      · 城市=编码   -> 某某市=101230100（表里没有的城市，手动指定）
    返回 (resolved, unresolved)；resolved 为 [(name, code), ...]，unresolved 为原始输入串。
    """
    resolved, unresolved, seen = [], [], set()
    for raw in tokens:
        tok = str(raw).strip()
        if not tok:
            continue
        if "=" in tok or ":" in tok or "\uFF1A" in tok:
            parts = re.split(r"[=:\uFF1A]", tok, maxsplit=1)
            name = parts[0].strip()
            code = parts[1].strip() if len(parts) > 1 else ""
            if name and code.isdigit():
                if name not in seen:
                    seen.add(name)
                    resolved.append((name, code))
            else:
                unresolved.append(tok)
            continue
        if tok in provinces:
            for name, code in provinces[tok]:
                if name not in seen:
                    seen.add(name)
                    resolved.append((name, code))
            continue
        if tok in flat:
            if tok not in seen:
                seen.add(tok)
                resolved.append((tok, flat[tok]))
            continue
        unresolved.append(tok)
    return resolved, unresolved
