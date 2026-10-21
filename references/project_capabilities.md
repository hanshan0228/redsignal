# RedSignal 核心系统能力与 Web 控制台架构 (Project Capabilities & Architecture)

本文档基于 RedSignal 代码实现（包含 `redsignal_cli.py`、`auto_responder.py`、`barnacle.py`、`dm_agent.py`、`routes.py` 及前端组件），概述系统近期核心功能与架构资产。

---

## 1. 待发队列与生命周期管理 (Reply Queue & Lifecycle Engine)

- **核心数据表**：`reply_queue` 表跟踪所有计划、已提交与失败的回帖。
- **凭据智能推断与绑定 (`credential_id` auto-inference)**：
  - 在商机入队 (`enqueue_reply`) 时，自动根据对应监听器绑定的通道凭据（`x_credential_id` / `forum_credential_id` / `reddit_credential_id`）完成凭据识别并持久化入库，保障队列全生命周期的账号上下文一致性。
- **状态流转机制**：
  - `drafted`（草稿生成）-> `pending`（等待调度）-> `submitted`（已提交发网）-> `posted`（验证在线）。
  - 支持异常状态：`failed`（发送失败）、`cancelled`（人工取消）、`quarantined`（触发隔离）。
- **Web UI 队列控制能力**（经由 `routes.py` API 支持）：
  - **立即发送安全门禁 (`submit_now` / `immediate=true`)**：人工介入立即执行发帖时，强制先经过 `check_rate_limits` 预检，若账号处于 24h 官方限频期或隔离期则智能拦截并顺延，杜绝盲目撞墙。
  - **取消排队 (`cancel`)**：放弃当前待发回复。
  - **失败重试与频控自愈 (`retry` / `Retry-After`)**：遭遇 Reddit HTTP 429 时自动解析 `Retry-After` 头并智能顺延重试；遭遇 𝕏 344/226 时自动触发 24 小时熔断并保护性延期。
  - **二次跟进串联 (`follow_up`)**：针对已有对话创建多轮跟进回复。
  - **2-Tweet Thread 串推反自动化**：主推发出后注入 2.5s ~ 4.5s 自然延迟，次推遇频控异常连带触发主号 24h 静默保护。
  - **风格动态切换 (`switch_style`)**：在线无缝切换“老炮技术流”、“痛点共情流”或“极客极简流”回复模版。
  - **安全审查门禁 (`evaluate_safety`)**：在提交前调用 AI 评估回复的社区友好度与 Spam 风险。

---

## 2. 账号健康体检与凭据保险箱 (Vault & Account Health Doctor)

- **多平台凭据管理**：
  - 支持 Reddit（Cookie/Session）、X/Twitter（Web auth_token/ct0 或官方 API）、论坛、AI 服务（OpenAI/Anthropic/DeepSeek/Groq）与 Bark 移动推送通道。
- **底层网络协议栈加固 (`curl_cffi` Chrome 131)**：
  - 针对 𝕏 Web Session GraphQL 调用，采用 `curl_cffi` 完整模拟真实 Chrome 131 TLS Client Hello 指纹与浏览器 Header 链，彻底根治 Error 344。
- **动态成熟度与分级风控 (`get_account_maturity_tier`)**：
  - **新号孵化期 (COLD, Karma < 10)**：强制纯干货洗号，外链上限 0%。
  - **成长期 (WARMING, Karma 10~99)**：适度互动，外链上限 10%。
  - **成熟期 (MATURE, Karma >= 100)**：权重账号，外链上限 20%。
- **多维度隔离与跨日频控状态继承**：
  - 配额大盘与 CLI `quota` 准确继承前日生效中的 `quarantine_until`（Shadowban 隔离静默期）与 `rate_limit_until`（官方频控保护期），精准展示 `rate_limited` 与 `quarantined` 标签。
  - 严格确保 75s 评论可见性检查中的隔离更新只影响对应 `credential_id`，多账号之间完全解耦。
- **实时会话体检 (`cmd_doctor` / `/api/doctor`)**：
  - 主动发起网络探针校验 Reddit me.json、X DM 初始状态、Bark 连通性与 AI 端点响应，发现过期凭据即时预警。

---

## 3. 藤壶 SEO 与 Google 首页占坑雷达 (Barnacle SEO & SERP Tracker)

- **Google Page 1 讨论坑位挖掘 (`barnacle.py` / `cmd_barnacle`)**：
  - 自动化检索指定商业词在 Google 首页的高权重 Reddit / X / Quora 讨论帖。
  - 依据 Google 排名、讨论热度与时效性计算 `opportunity_score`。
- **常青回复起草 (`evergreen_draft`)**：
  - 针对活帖自动生成权威、详实的常青技术解答，借 Google 搜索流量实现长线被动获客。
- **存活巡检与健康审计 (`cmd_audit` / `/api/barnacle/audit`)**：
  - 定期巡检已发公域回帖与 SERP 占坑帖的存活状态（`LIVE`、`LOCKED`、`ARCHIVED`、`REMOVED`）。
  - 支持 `--fast` 本地离线快速审计与全网络状态深度探测。

---

## 4. 动态工具路由与短链转化追踪 (Attribution & Dynamic Routing)

- **上下文感知单点工具匹配 (`resolve_dynamic_tool_url`)**：
  - 根据帖子上下文、痛点描述与 Offer 矩阵，自动匹配自营站中最契合的垂直工具（优先采用英文规范名 `name_en`）。
- **短链分发与点击归因 (`/r/{code}` 与 `short_links` 表)**：
  - 自动生成防风控短链，重定向携带 UTM 参数，实时统计独立点击数（Unique Clicks）与转化链路。
- **商机捕获与转化漏斗 (`/api/leads/capture`)**：
  - 串联私信线索捕获、转化状态标记与多项目矩阵（Campaigns）资产大盘。

---

## 5. 自动化调度与移动推送总线 (Automation & Mobile Push)

- **后台 Crontab 调度监控**：
  - 统一查看与守护系统定时轮询任务（RSS 抓取、未读私信轮询、存活巡检）。
- **Bark 移动端即时通知 (`dm_agent.py`)**：
  - 当收到 Reddit / X 新私信或 AI 自动起草重要回复时，实时推送预览卡片至操作员手机，并提供一键直达处理链接。
