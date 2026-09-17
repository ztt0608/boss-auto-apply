# Boss 直聘自动沟通助手（boss_batch.py）

基于 CDP（Chrome DevTools Protocol）控制**你自己的真实 Edge 浏览器**，自动筛选职位并批量点击「立即沟通」。
不用 Playwright/Selenium 启动浏览器（避免 `navigator.webdriver` 被风控识别），登录全部由本人人工完成。

> ⚠️ **免责声明**：本工具仅供学习交流与个人求职辅助使用。频繁自动化操作可能违反 Boss 直聘用户协议、存在账号被限制的风险，请自行评估并控制使用强度（脚本已内置低频策略：每天 ≤50、分 3 批、候选池两天扫一次）。使用者对账号安全自负其责。

---

## 一、它做什么

1. **扫描**（两天一次，约 80~90 分钟）：按关键词 × 城市枚举搜索职位，逐个打开详情页核实薪资与 HR 活跃度，筛出 ~110 个合格候选存入 `candidates.json`。
2. **投递**（每天 ≤50 个，建议分早/中/晚 3 批）：从候选池按「实习/应届优先 + 重点城市优先」取一批，模拟人工滚动 + 点击「立即沟通」（使用 Boss 默认招呼语，不自动打字）。
3. **落库与日报**：每笔投递写入 SQLite（`boss_sends.db`）；`daily_report.py` 汇总生成 `日报_YYYY-MM-DD.md`；可选推送飞书。

## 二、环境要求

- Windows 10/11 + Edge 浏览器
- Python 3.8+：**没装也没关系**，双击 `install_python.bat` 可自动安装（优先 winget，兜底官方安装包静默装，无需管理员；下载走华为云镜像）。装完后重新双击 `check_env.bat` 验证。
- 依赖只有 `websocket-client`，**包内已自带**在 `toolchain/pylibs/`，无需 pip 安装；如果你删掉了这个目录，就 `pip install -r requirements.txt`
- 一个能正常登录 Boss 直聘的账号

## 三、快速开始（3 步）

```
1. 双击 start_edge.bat
   → 打开带调试口的 Edge（独立 profile，不影响你日常用的 Edge）
   → 在里面登录 Boss 直聘；退出手机端 Boss（互踢）
2. 双击 run_batch.bat
   → 默认投 17 个，约 25~30 分钟；日志实时写入 boss_run_latest.log
   → 最后一行出现 ===DONE=== 才算跑完
3. 双击 run_report.bat 查看今日日报（日报_YYYY-MM-DD.md）
```

首次建议顺序：先双击 `health_check.bat` 体检（零消耗），显示「已登录 + 合成输入有效」再跑批。

## 四、日常使用建议

- **每天一批 17 个、最多 3 批（合计 ~50）**，批次间隔 ≥4 小时。别贪多：实测连发 ~25–29 条后 Boss 会静默限流（不报错但点不动），次日恢复。
- 投递期间 **Edge 窗口别最小化、别锁屏切走**：页面不在前台时系统级合成输入会被丢弃。脚本内置了自动拉前台的自愈逻辑（实测锁屏下也能自愈），但保持前台最稳。
- 候选池两天自动扫一次；想手动刷新：删除 `candidates.json` 后运行 `run_batch.bat 0`（只扫不投）。
- 每天投递前确认：网页版已登录、手机版 Boss 已退出。

## 五、自定义配置（都在 boss_batch.py 里，用记事本改）

| 想改什么 | 位置（行号约） | 默认值 |
|---|---|---|
| 每日总投递上限 | 第 19 行 `TARGET` | 50 |
| 关键词 | 第 254 行 `KEYWORDS` | 桌面运维/网络工程师/系统运维/运维/弱电/网络管理员 等 |
| 重点城市（优先+逐市枚举） | 第 263 行 `TIER1` | 北京+福建/广东/浙江各市 |
| 普通城市 | 第 274 行 `TIER2` | 上海/成都/武汉/长沙 等 |
| 候选池复用天数 | 第 519 行 `POOL_MAX_AGE_DAYS` | 2 天 |
| 薪资/活跃度过滤 | 搜索 `薪资` / `活跃` 相关函数 | 月薪 3–8K 或日薪 ≥100；HR 三天内在线 |

城市名参考 Boss 官方城市表：`https://www.zhipin.com/wapi/zpCommon/data/city.json`（注意：Boss 网页端**不支持省份聚合码**，必须一个市一个市写）。

## 六、命令行用法（进阶）

```bat
:: 投一批 17 个
set BOSS_BATCH=17 && python boss_batch.py
:: 只扫不投（需先删除 candidates.json）
set BOSS_BATCH=0 && python boss_batch.py
:: 点完本批后若候选池≥2天自动全量重扫
set BOSS_SCAN_AFTER=1 && set BOSS_BATCH=16 && python boss_batch.py
```

| 环境变量 | 作用 |
|---|---|
| `BOSS_BATCH` | 本批目标数量（默认 = TARGET） |
| `BOSS_SCAN_AFTER` | 设为 1 时，点完后自动判断是否需要全量重扫 |
| `BOSS_THROTTLE_STOP` | 连续 N 次无响应即停止（默认 8） |
| `FEISHU_WEBHOOK` / `FEISHU_SECRET` | 可选，配置后日报自动推飞书；也可放同目录 `feishu_webhook.txt` / `feishu_secret.txt` |

## 七、故障排查（先跑 health_check.bat）

| 现象 | 原因与处理 |
|---|---|
| 体检「未找到 zhipin 页面 target」 | 重新双击 start_edge.bat；还不行就关掉所有由它启动的 Edge 窗口再试 |
| 脚本能读职位但点了没反应 | 页面不在前台（最小化/被遮挡/锁屏）。把 Edge 切到前台再跑；脚本一般能自愈 |
| 连续「继续沟通=False」且无报错 | Boss 静默限流，今天到此为止，明天自动恢复 |
| 提示登录失效 | 在 Edge 里重新登录（脚本绝不自动登录），退出手机端 Boss |
| Edge 完全打不开调试口 | 确认没有第二个日常 Edge 抢占；本包已用独立 profile 规避 |

体检退出码：`0` 正常；`2` CDP 不通；`3` 无 zhipin 页面；`4` 未登录；`5` 前台/合成输入异常。

## 八、已知限制（诚实版）

- **只点「立即沟通」用默认招呼语**，不会自动打字、不会跟进回复；回复/已读跟踪尚未实现。
- 依赖「真实 Edge + 人工登录」，无法全自动无人值守：登录失效、Edge 被关、电脑关机都会中断。
- Boss 页面改版（按钮文案、字体混淆方案）可能导致脚本失效，需同步更新选择器。
- 每台机器首次使用需跑一次完整扫描（80~90 分钟）建立候选池。

## 九、目录结构

```
boss_auto_release/
├── check_env.bat         # ⓪ 新设备环境自检（Python/依赖/Edge，30 秒）
├── install_python.bat    # ⓪' 没装 Python 时自动安装（winget 优先→官方包静默装，免管理员）
├── start_edge.bat        # ① 拉起带调试口的 Edge（便携：自动找 Edge、profile 存本目录）
├── run_batch.bat         # ② 跑一批投递（可传数量参数）
├── run_report.bat        # ③ 生成今日日报
├── health_check.bat      #    零消耗体检（--try-fix 可验证自愈）
├── boss_batch.py         # 主脚本：扫描+投递
├── daily_report.py       # 日报生成（SQLite 汇总）
├── cdp_health.py         # 链路体检工具
├── requirements.txt      # 唯一依赖 websocket-client（包内已自带）
└── toolchain/pylibs/     # 内置依赖（仅 websocket-client，0.3MB）
```

运行后生成：`candidates.json`（候选池）、`boss_sends.db`（投递记录）、`boss_run_latest.log`（日志）、`日报_*.md`。

## 十、更换设备 / 迁移到新电脑

整个包是便携的（无盘符硬编码、依赖内置、Edge 路径自动探测），换设备流程：

1. 把整个 `boss_auto_release` 文件夹（或 zip）拷到新电脑任意位置（**U 盘/网盘都行，0.2MB**）。
2. 新电脑装 Python：**没装就双击 `install_python.bat` 自动装**（需联网）；已装则跳过。Windows + Edge 一般都自带。
3. 双击 `check_env.bat` —— 30 秒自检 Python / 内置依赖 / Edge 三项。
4. 双击 `start_edge.bat` → **在新 Edge 里重新登录 Boss**，退出手机端 Boss。
5. 双击 `health_check.bat` 体检 → 全绿后 `run_batch.bat 0` 先重建候选池（首次约 80~90 分钟）→ 之后正常 `run_batch.bat` 投递。

**什么能带走、什么要重来：**

| 项目 | 能否迁移 | 说明 |
|---|---|---|
| 脚本 + 内置依赖 | ✅ 直接拷 | 无需安装任何东西 |
| `boss_sends.db`（投递历史） | ✅ 可拷 | 放回包根目录即可，日报能接上历史 |
| `candidates.json`（候选池） | ⚠️ 可拷但意义不大 | 职位时效性强，新机建议直接重扫 |
| Boss 登录态（`edge_profile/`） | ❌ **不要拷** | 含登录 Cookie，跨设备搬运既容易失效又有泄露风险；新机重新扫码登录一次即可 |
| 你改过的配置（关键词/城市等） | ✅ 手动带走 | 用记事本对比旧机 `boss_batch.py` 里改过的几行 |
| WorkBuddy 自动化（每天 3 批定时） | ❌ 不随包迁移 | 那是本机 WorkBuddy 的定时任务；新电脑上就靠手动双击 bat（或在那台机器也装 WorkBuddy 重建） |

## 十一、给想上 GitHub 的你

- 可以直接把本目录推上去；建议先在 `.gitignore` 里排除运行产物：`candidates.json`、`boss_sends.db`、`*.log`、`edge_profile/`、`日报_*.md`、`feishu_*.txt`。
- `edge_profile/` 含你的登录 Cookie，**绝对不要上传**。
- 仓库描述里写清免责声明（见顶部），避免被当成恶意爬虫工具。
