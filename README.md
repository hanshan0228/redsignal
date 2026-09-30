# RedSignal (AI Agentic 社媒截流、联盟营销与全品类转化控制中枢)

[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-D97706?style=flat-square&logo=anthropic)](https://docs.anthropic.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-4a4a44?style=flat-square&logo=python)](https://python.org)

> **“公域建立权威与搜索占坑，私域完成高客单与联盟返佣深度收割。”**
>
> 告别单一垂类限制与机械化号海战术。RedSignal 融合哥飞低搜高转化心法、藤壶 SEO 与 Promotion Warrior 的“公开造势+私信深度收割”双轨模型，支持自营独立站、SaaS 软件、数码硬件及 Affiliate 联盟营销项目的多品类多 Campaign 矩阵。
> 实现从“商机探测 -> 商业意图研判 -> 公开回帖埋钩 -> 1v1 私信攻坚 -> 异议化解 -> 频控发射”的全链路闭环。

---

## 🌟 核心特性与架构亮点

1. **5 大低搜高转化商业金矿意图研判器 (`references/commercial_intent_archetypes.md`)**：
   - 告别高竞争大词内卷，聚焦零月搜、低搜但交易意图极强的“最后一公里”真实买家；
   - 包含：🔥 **替代弃用**、⚖️ **选型对比**、⭐ **真实口碑**、🏷️ **折扣防线**、🛠️ **痛点排查**。
2. **双轨转化攻坚模型 (`references/dual_track_dm_playbook.md`)**：
   - **轨道 1：公域老炮评论（公开引水 · 藤壶 SEO 占坑）**：0 外链硬核诊断，嵌入**逆向私信邀请钩子（Inbound DM Hook）**，诱导潜客主动发信，彻底规避平台 Spam 风险；
   - **轨道 2：1v1 私信 3 轮深度攻坚**：Round 1 破冰共情兑现承诺 → Round 2 痛点诊断场景实测 → Round 3 精准逼单（联盟与自营工具直达 + FTC 合规披露）；
   - **异议抗拒化解库 (Objection Killers)**：价格敏感、冗余功能、迁移顾虑、信赖度等 4 大高频异议的高情商化解方案。
3. **80/20 安全洗号与硬风控死线 (`references/anti_ban_and_quota_rules.md`)**：
   - 80% 纯干货洗号积攒 Karma + 20% 软植入引流；
   - 单账号单日发帖上限 **8 篇**，发帖后强制进入 **45 分钟** 倒计时冷却期；
   - 严格遵循 **人机协同确认机制 (Human-in-the-Loop)**，未获用户明示绝不真实向外发射。
4. **多 Campaign 项目矩阵与垂直工具路由**：
   - 针对自营独立站、垂直工具站、SaaS 订阅或 Affiliate Offer 一键切换并分配专属承接点。

---

## 📂 项目结构

```text
redsignal/
├── SKILL.md                                 # Claude Code 核心 Skill 定义与 SOP 执行规范
├── README.md                                # 项目说明与快速上手文档
├── .gitignore                               # Git 忽略配置规则
└── references/                              # 模块化知识库与参考指引
    ├── commercial_intent_archetypes.md      # 5 大金矿商业意图详细剖析与实操范例
    ├── dual_track_dm_playbook.md            # 公开逆向私信钩子、1v1 聊单心智流与异议化解库
    └── anti_ban_and_quota_rules.md          # 80/20 洗号法则、45 分钟冷却期与社媒防封红线
```

---

## 🚀 安装与配置

### 1. 安装 Skill 到 Claude Code

克隆本项目到本地 Claude Code Skills 目录：

```bash
git clone https://github.com/hanshan0228/redsignal.git ~/.claude/skills/redsignal
```

### 2. 本地引擎协同配置（可选）

如需联动本地 RedSignal 自动化监听与发帖引擎：

1. 部署并启动本地 RedSignal 服务（支持 Reddit API 会话与 SQLite 数据库持久化）；
2. 确保本地可执行路径（如 `~/redsignal/.venv/bin/python3 ~/redsignal/redsignal_cli.py`）可用；
3. 在 Claude Code 会话中直接输入触发词或使用 `/redsignal`。

---

## 🎯 触发词 (Triggers)

在 Claude Code 中输入以下任一指令即可触发：

- `/redsignal`、`截流`、`看线索`、`发帖`、`社媒雷达`、`reddit发帖`
- `截流雷达`、`雷达扫描`、`藤壶引流`、`洗号`、`回帖`、`私信`、`聊单`
- `RedSignal聊单`、`私信获客`、`跟进`、`异议化解`、`affiliate`、`联盟营销`、`替代品截流`

---

## 🛠️ CLI 常用命令索引

| 动作 | 核心命令 | 说明 |
|---|---|---|
| **扫描最新线索** | `redsignal_cli.py radar --limit 5` | 查看最新高意向商机 |
| **金矿意向筛选** | `redsignal_cli.py radar --intent affiliate --limit 5` | 筛选替代、选型、口碑、折扣等高转化帖子 |
| **项目专属扫描** | `redsignal_cli.py radar --campaign <id> --limit 5` | 针对特定营销/联盟项目专属雷达扫描 |
| **实时抓取刷新** | `redsignal_cli.py radar --sync --limit 5` | 通过 Cookie 会话即时聚合抓取最新帖子 |
| **联盟攻坚收割** | `redsignal_cli.py affiliate <hit_id> [--product <name>] [--url <link>]` | 生成针对竞品弃用/对比的公开藤壶回帖与 1v1 私信攻坚闭环 |
| **自营私信攻坚** | `redsignal_cli.py dm <hit_id>` | 针对自营独立站/工具生成公开私信钩子与官方发信直达链接 |
| **项目矩阵列表** | `redsignal_cli.py campaigns` | 查看当前所有运行中的自营与联盟营销项目 |
| **风控配额巡检** | `redsignal_cli.py quota` | 检查今日已发条数、剩余配额与 45m 冷却倒计时 |
| **发帖安全预演** | `redsignal_cli.py post <hit_id> --text "..." --dry-run` | 验证风控、匹配落地页与短链，不发网 |
| **确认真实发射** | `redsignal_cli.py post <hit_id> --text "..." --mode brand_search` | 用户批准后正式发送回复并扣减配额 |

---

## 📋 标准 4 步作业流程 (SOP)

1. **步骤 1：雷达探测与意图研判**：执行 `radar` 扫描，精准识别 5 大高转化意图，展示商机摘要；
2. **步骤 2：双轨生成与闭环设计**：针对联盟营销或自营工具，分别定制“0 外链客观评测 + 逆向私信钩子”及 1v1 聊单攻坚流程；
3. **步骤 3：前置风控核验**：执行 `quota` 检查日发限额（<8 篇）与 45 分钟冷却期；
4. **步骤 4：用户授权与安全发射**：展示拟发送文本与目标帖，获得操作员明示同意后安全发射。

---

## 📄 License

[MIT License](LICENSE)
