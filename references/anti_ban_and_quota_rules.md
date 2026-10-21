# 社媒风控规则、动态频控配额与账号安全体系 (Anti-Ban & Quota Rules)

社媒截流营销的生命线在于**账号存活率与社区声誉**。机械化群发、短时间高频刷帖与无脑堆砌外链会在极短时间内引发社区举报、AutoMod 拦截与平台封禁。RedSignal 基于底层代码实现建立了一套分级动态风控机制。

---

## 1. 80/20 安全洗号配比 (80/20 Warmup & Safe Ratio)

- **80% 纯干货洗号贴 (Community Karma Builder)**：
  - 零外链、零品牌提及、零商业诱导；
  - 专注于客观解答社区疑问、排查技术故障、分享真实配置心得；
  - 核心目标：积累账号历史活跃度、获得社区 Upvotes 与 Karma、建立版主信赖。
- **20% 软植入引流贴 (Strategic Value Harvest)**：
  - 仅针对精准命中 5 大高转化商业金矿意图的潜客帖子；
  - 优先采用品牌直搜词模式（`brand_search` 模式，如建议在 Google 搜索 `[Brand Name] [Tool Name]`），不在公域直接暴露裸链接；
  - 若确需带链接，仅允许官方验证过的单一垂直工具短链或项目着陆页。

---

## 2. 动态频控配额与平台差异化限制 (Dynamic Rate Quotas)

频控限制**并非全平台全局固定单一数值**，系统依据当前操作账号的凭据类型与通道特征动态实施不同的频控与冷却约束：

| 平台 / 凭据类型 | 单日发帖上限 (`daily_limit`) | 发帖后冷却时间 (`cooldown`) | 代码实现位置 |
|---|---|---|---|
| **Reddit** (Web Session / Cookie) | **8 篇 / 日** | **45 分钟** | `redsignal_cli.py:273`, `auto_responder.py:375` |
| **X / Twitter** (Web Cookie / auth_token) | **5 篇 / 日** | **45 分钟** | `redsignal_cli.py:276`, `cmd_post:402` |
| **论坛类** (Forum / phpBB / XenForo) | **15 篇 / 日** | **15 分钟** | `redsignal_cli.py:279` |
| **X 官方 API / 其他通道** | **25 篇 / 日** | **15 分钟** | `redsignal_cli.py:282` |

### 账号熔断与隔离保护状态 (Quarantine & Rate Limit Protection)
- **Shadowban 隔离静默期 (`quarantine_until`)**：若账号在特定社区或平台触发异常标记（如 75s 后公开视角评论被 AutoMod 移除或不可见），系统自动进入隔离期（通常为 24~72 小时）。**隔离计数严格绑定到具体的 `credential_id`**，单账号触发隔离不会误伤多账号池中的其他健康凭据。
- **官方频控冷却保护 (`rate_limit_until`)**：若 𝕏 发帖返回 344、226、429、daily limit 或 automated detection 错误码，系统自动记录 `rate_limit_until`，进入强制 24 小时安全静默冷却，杜绝频繁撞墙导致永久封号。
- **Reddit HTTP 429 智能顺延**：捕获 Reddit Web HTTP 429 (Too Many Requests)，解析响应头中的 `Retry-After`（默认 600 秒），自动置位 `is_rate_limited` 并触发任务智能顺延。
- **立即发射强制前置门禁**：所有即时发射入口（Web UI `submit_now`、`/api/reply` `immediate=true`、CLI `post`）在网络提交前均强制执行 `check_rate_limits`，处于冷却或隔离状态的任务会被自动拦截并顺延，绝不向平台盲目施压。

---

## 3. 账号成熟度梯度与外链策略 (Account Maturity Tiers)

系统根据账号历史积累的 Karma 与声誉动态划分成熟度等级（`auto_responder.py:511`）：

1. **🌱 新号孵化期 (COLD, Karma < 10)**：
   - 强制采用 100% 纯干货洗号模式，外链上限为 0%；
   - 严禁在公域携带任何外部链接，避免触发 AutoMod 秒删或账号被封。
2. **🌿 账号成长期 (WARMING, 10 <= Karma < 100)**：
   - 账号处于培育过渡期，外链率建议控制在 10% 以内；
   - 绝大多数回复仍应以纯文本专业解答为主。
3. **🌲 成熟权重号 (MATURE, Karma >= 100)**：
   - 账号享有标准社区信誉，滚动外链比例上限为 20%。

---

## 4. 滚动外链比例守卫与自动安全降级 (Rolling Link Ratio Guardian)

- **统计窗口**：系统检查该账号最近 10 次已提交或发布的回复（`window_size = 10`，见 `auto_responder.py:421`）。
- **门禁机制**：若本次发帖携带外链且将导致最近 10 次回复的外链比例超过 20%，系统判定触发外链门禁。
- **自动安全降级**：
  - 在非 `--force-link` 模式下，系统自动将文案中的 Markdown 链接和裸链接降级为自然品牌搜索建议（例如将链接转为 `(search for '<Brand>' online)`）；
  - 保留回复的核心专业信息，消除因直接留链引发的封禁风险。
- **𝕏 连续外链守卫 (Consecutive Link Guard)**：
  - 针对 𝕏 (Twitter) Web Cookie 凭据，系统额外实施连续外链审查：若检测到该账号**上一条成功发布的推文已包含外链**，本次带链回复将自动降级为“主页/置顶外链引流”（如改写为 `(see bio for link)` 或 `(check profile)`），杜绝背靠背连续外链被 𝕏 算法直接标记为外链垃圾号。

---

## 5. 𝕏 (Twitter) Web GraphQL 浏览器级指纹伪装与串推反自动化

针对 𝕏 平台极其严苛的自动化防御（Error 344 / 226 等）：
- **`curl_cffi` Chrome 131 指纹伪装**：
  - Web Cookie 会话通过 `curl_cffi` 完整模拟真实 Chrome 131 TLS Client Hello 与 HTTP/2 握手协议；
  - 携带完整的 `sec-ch-ua`、`sec-fetch-dest: empty`、`sec-fetch-mode: cors`、`sec-fetch-site: same-origin`、真实 Referer 与 CSRF `ct0` 认证链，彻底根治因 Python Requests TLS 指纹泄露导致的 Error 344。
- **2-Tweet Thread 串推自然抖动与连带熔断**：
  - 采用主推（价值解答）+ 次推（垂直落地工具短链）的 2-Tweet Thread 模式时，生产环境下在发完主推后自动注入 **2.5s ~ 4.5s 自然延迟**，模拟人类打字思考；
  - 若次推遭遇 344 / 226 / 429 报错，系统自动对该凭据触发 24 小时安全静默冷却，保护主号安全。

---

## 6. CLI 命令副作用与 `--dry-run` 边界清单 (Side Effects & Dry-Run Boundaries)

不同命令在 `--dry-run`、网络请求与数据持久化方面的行为边界必须准确理解，不可混淆：

1. **`post --dry-run` (纯本地安全预演)**：
   - **网络状态**：纯本地离线执行，不向 Reddit、X 或任何社交平台发起外发请求；
   - **数据写入**：不向 SQLite 数据库写入队列或更新线索状态，不扣减当日配额；
   - **执行行为**：校验本地线索有效性、匹配可用发帖凭据、检查冷却与配额、计算滚动外链比并输出降级文本预览。
2. **`inbox --dry-run` (线上拉取与草稿试运行)**：
   - **网络状态**：**会连接网络**，通过 Reddit / X API 获取未读私信消息；
   - **数据写入**：**会写入数据库**，将生成的 AI 对话草稿存入本地 SQLite（状态标记为 `drafted`），并会触发 Bark 手机推送通知；
   - **安全边界**：仅跳过实际向对方发送私信的网络调用。
3. **`radar` (商机雷达)**：
   - **默认状态**：纯离线检索本地 SQLite 数据库中已有线索；
   - **`--sync` 模式**：会发起已认证的网络拉取，并将新增线索持久化写入本地数据库。
4. **`status` (系统状态)**：
   - 查询本地 SQLite 数据库、Crontab 调度器与 Git 仓库状态；
   - **会发起网络探针**：向官方镜像链接发送 HTTP HEAD/GET 请求以测试可用性。
5. **`doctor` (凭据健康体检)**：
   - **会发起外部网络请求**：主动测试 Reddit 会话、X 接口、Bark 推送通道与 AI 服务端点的实时连通性。
6. **`audit` (藤壶存活巡检)**：
   - **默认状态**：会发起外部网络请求检测回帖存活与 SERP 排名；
   - **`--fast` 模式**：跳过网络外发检测，纯基于本地记录快速生成审计摘要。

---

## 7. 特权参数使用规范与人机协同原则 (Privilege Flags & Safety Guardrails)

- **`--force` (绕过冷却倒计时)**：
  - 仅可绕过单次发帖后的 45 分钟或 15 分钟冷却计时；
  - **仍然受到每日发帖上限（8篇/5篇/15篇/25篇）的硬性熔断保护**；
  - 严禁作为默认参数使用，使用前必须获得操作员明确授权。
- **`--force-link` (强制携带外链)**：
  - 仅用于跳过 20% Rolling Link Ratio 门禁强制保留链接；
  - 强行带链会显著提高被社区版主或 AutoMod 拦截惩罚的概率；
  - 严禁作为默认参数使用，仅在操作员明确确认风险并授权后方可执行。
- **免责与合规声明**：
  - 任何技术策略均无法提供 100% 免封或 100% 免 Spam 判定的绝对保证；
  - 所有自动化操作必须严格遵守各社交平台的官方服务条款（Terms of Service）与所在 Subreddit / 社区的版规；
  - 正式向公域或私信发射真实内容前，必须经过人工复核与显式授权。
