# -*- coding: utf-8 -*-
"""配置向导 —— 生成 config.json，让本工具适配你自己的行业与岗位方向。

用法：双击 setup.bat，或在此目录执行  python setup_config.py
随时可以重跑，旧配置会自动备份为 config.json.bak。
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import job_config  # noqa: E402


def ask(prompt, default=None):
    """问一句；直接回车用默认值；非交互环境（管道/EOF）自动用默认值。"""
    suffix = "" if default is None else " [%s]" % default
    try:
        raw = input("%s%s: " % (prompt, suffix)).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default if default is not None else ""
    if not raw:
        return default if default is not None else ""
    return raw


def ask_yes_no(prompt, default=True):
    d = "Y/n" if default else "y/N"
    try:
        raw = input("%s [%s]: " % (prompt, d)).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    if not raw:
        return default
    return raw[0] in ("y", "1", "是", "t")


def ask_list(prompt, default_list):
    """逗号分隔的列表输入，支持多行（直接空行结束）。"""
    cur = "、".join(default_list) if default_list else ""
    print("\n%s" % prompt)
    print("  当前：%s" % (cur or "（空）"))
    print("  直接回车保持不变；输入 - 清空；多项用逗号分隔，也可再敲一行继续补充。")
    try:
        raw = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return list(default_list)
    if not raw:
        return list(default_list)
    if raw == "-":
        return []
    items = [x.strip() for x in raw.replace("；", ",").replace("，", ",").split(",") if x.strip()]
    while True:
        try:
            more = input("  继续补充（回车结束）> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not more:
            break
        if more == "-":
            items = []
            continue
        items += [x.strip() for x in more.replace("；", ",").replace("，", ",").split(",") if x.strip()]
    return items


def ask_number(prompt, default, cast=int):
    raw = ask(prompt, default)
    try:
        return cast(raw)
    except (TypeError, ValueError):
        print("  ! 输入不是数字，使用 %s" % default)
        return default


def resolve_city_input(label, current, table_flat, table_prov):
    """让用户输入城市，自动查编码；返回 (城市列表, 编码覆盖 dict)。"""
    cities = ask_list(label, current)
    if not cities:
        return [], {}

    resolved, unresolved = job_config.resolve_cities(cities, table_flat, table_prov)

    if unresolved:
        print("\n  ! 以下名称没查到对应城市编码：%s" % "、".join(unresolved))
        print("    可能原因：城市名写法不同（试试「市」结尾或简称），或需要联网才能查到全国城市。")
        print("    你可以这样手动指定编码：某某市=101230100（编码在 Boss 网页搜索该城市时网址里 city= 后面那串数字）")
        retry = ask_list("  请重新输入这些城市（直接回车表示跳过）",
                         [u + "=" for u in unresolved])
        retry = [x for x in retry if not x.endswith("=")]
        extra_res, still = job_config.resolve_cities(retry, table_flat, table_prov)
        resolved += extra_res
        if still:
            print("  ! 仍然无法解析，已跳过：%s" % "、".join(still))

    # 去重（保序）
    seen, out, codes = set(), [], {}
    for name, code in resolved:
        codes[name] = code
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out, codes


def main():
    print("=" * 68)
    print(" Boss 直聘自动沟通助手 · 配置向导")
    print("=" * 68)
    print(" 本向导会生成 config.json，把岗位方向、城市、薪资等改成你自己的需求。")
    print(" 全程直接回车即采用方括号里的默认值；随时 Ctrl+C 可退出（不会写入）。")
    print()

    cfg_path = job_config.config_path(HERE)
    if os.path.exists(cfg_path):
        print("检测到已有 config.json，将基于它修改（旧文件会备份为 config.json.bak）。\n")
        cur = job_config.load(HERE, quiet=True)
    else:
        cur = job_config.validate({}, [])
        print("未检测到 config.json，将从内置默认值开始（默认是 IT 运维方向）。\n")

    cfg = dict(cur)

    # ---- 1. 岗位方向 ----
    print("-" * 68)
    print("【1/7】岗位方向关键词 —— 决定去搜什么岗位")
    print(" 例：后端开发 / 数据分析 / 新媒体运营 / 医药代表 / 电气工程师 ……")
    cfg["keywords"] = ask_list("搜索关键词：", cur["keywords"])

    print()
    print("【2/7】排除词（可选）—— 职位标题里出现这些词就跳过")
    print(" 例：销售 / 外包 / 驻场 / 中介 / 培训 —— 用来挡掉你不想要的岗位类型")
    cfg["exclude_keywords"] = ask_list("排除关键词：", cur["exclude_keywords"])

    # ---- 2. 城市 ----
    print("\n" + "-" * 68)
    print("【3/7】城市 —— 正在加载城市表（联网可查全国城市）…")
    table_flat, table_prov = job_config.load_city_table(HERE, online=True, quiet=True)
    print(" 已加载 %d 个城市" % len(table_flat)
          + ("，并支持直接输入省份名（会展开成该省所有城市）"
             if table_prov else "（离线模式，仅支持内置表中的城市）"))

    pri, pri_codes = resolve_city_input("优先城市（会优先投递这里的岗位）：",
                                        cur["cities_priority"], table_flat, table_prov)
    cfg["cities_priority"] = pri

    bak, bak_codes = resolve_city_input("兜底城市（优先城市招不满时才会用到，可以留空）：",
                                        cur["cities_backup"], table_flat, table_prov)
    cfg["cities_backup"] = bak

    city_codes = dict(cur.get("city_codes") or {})
    city_codes.update(pri_codes)
    city_codes.update(bak_codes)
    cfg["city_codes"] = city_codes

    # ---- 3. 薪资 ----
    print("\n" + "-" * 68)
    print("【4/7】薪资范围 —— 不符合的不投")
    sal = dict(cur["salary"])
    sal["enabled"] = ask_yes_no("启用薪资筛选？", sal.get("enabled", True))
    if sal["enabled"]:
        print("  月薪区间（单位：K，即千元）")
        sal["min_month"] = ask_number("    最低月薪(K)", sal["min_month"], float)
        sal["max_month"] = ask_number("    最高月薪(K)", sal["max_month"], float)
        print("  日薪区间（单位：元/天；兼职/日结岗适用）")
        sal["min_day"] = ask_number("    最低日薪(元)", sal["min_day"], float)
        sal["max_day"] = ask_number("    最高日薪(元)", sal["max_day"], float)
    cfg["salary"] = sal

    # ---- 4. HR 活跃度 ----
    print("\n" + "-" * 68)
    print("【5/7】HR 活跃度 —— 只投最近在线的 HR（活跃度太老 = 多半不看消息）")
    cfg["hr_active_days"] = ask_number("  只投 N 天内活跃的岗位(N)", cur["hr_active_days"], int)

    # ---- 5. 投递节奏 ----
    print("\n" + "-" * 68)
    print("【6/7】投递节奏 —— 建议控制在每天 50 以内，分 2~3 批，避免触发风控")
    cfg["daily_target"] = ask_number("  每日投递目标总数", cur["daily_target"], int)
    print("  分批数量：每天要发的量拆成几批、每批多少个（逗号分隔，总和建议等于上面的目标）")
    batches = ask_list("  每批数量：", [str(x) for x in cur["batch_counts"]])
    try:
        cfg["batch_counts"] = [int(x) for x in batches if str(x).strip().isdigit()] or cur["batch_counts"]
    except Exception:
        cfg["batch_counts"] = cur["batch_counts"]
    if sum(cfg["batch_counts"]) != cfg["daily_target"]:
        print("  ! 分批之和 %d 与每日目标 %d 不一致 —— 不影响运行，"
              "但建议改成一致以方便对账。" % (sum(cfg["batch_counts"]), cfg["daily_target"]))

    # ---- 6. 实习/应届 ----
    print("\n" + "-" * 68)
    print("【7/7】实习 / 应届岗 —— 主要给在校生、毕业生用；已工作多年可关闭")
    cfg["intern_priority"] = ask_yes_no("  优先投实习/应届岗？", cur["intern_priority"])
    if cfg["intern_priority"]:
        print("  判定用的关键词（命中即视为实习/应届岗，逗号分隔）")
        cfg["intern_keywords"] = ask_list("  实习/应届关键词：", cur["intern_keywords"])

    # ---- 写入 ----
    warnings = []
    cfg = job_config.validate(cfg, warnings)
    path = job_config.write(HERE, cfg)

    print("\n" + "=" * 68)
    print(" 配置完成，已写入：%s" % path)
    print("=" * 68)
    for line in job_config.summary_lines(cfg):
        print("  " + line)

    if city_codes:
        need = [c for c in (cfg["cities_priority"] + cfg["cities_backup"])
                if c not in job_config.DEFAULTS["cities_priority"]
                and c not in job_config.DEFAULTS["cities_backup"]]
        if need:
            print("\n  本次新增的城市编码（已写入 config.json 的 city_codes）：")
            for c in need:
                if c in city_codes:
                    print("    %s = %s" % (c, city_codes[c]))

    if warnings:
        print("\n  提醒：")
        for w in warnings:
            print("    - %s" % w)

    print("\n下一步：")
    print("  1) 双击 start_edge.bat 启动调试版 Edge，并在里面登录 Boss 直聘")
    print("  2) 双击 health_check.bat 体检")
    print("  3) 双击 run_batch.bat 0 首次建立候选池（约 80~90 分钟）")
    print("\n想改配置随时重跑本向导，或直接用记事本编辑 config.json。")
    try:
        input("\n按回车键关闭…")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
