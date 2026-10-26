const TEXT = new Map(Object.entries({
  Stream: '信息流', Analytics: '数据分析', Vault: '凭据库', Listeners: '监听器', Logs: '日志',
  '● Live': '● 实时', '● Offline': '● 离线', 'Start All': '全部启动', 'Stop All': '全部停止',
  All: '全部', Posts: '帖子', Comments: '评论', 'Any status': '全部状态', New: '新线索',
  Reviewing: '审核中', Replied: '已回复', 'Converted ✓': '已转化 ✓', Converted: '已转化', Skipped: '已忽略',
  History: '历史', Board: '看板', 'Auto AI': '自动 AI 筛选', 'Hide rejected': '隐藏未通过', Clear: '清空',
  POST: '帖子', COMMENT: '评论', CMT: '评论', Analyzing: '分析中', '⚠ Error': '⚠ 错误',
  '✓ Passed': '✓ 已通过', '✗ Rejected': '✗ 未通过', 'Draft saved': '草稿已保存',
  Open: '打开', '📖 Thread': '📖 讨论串', '✍ Reply': '✍ 回复', '🤖 Analyze': '🤖 分析',
  'No hits yet': '还没有命中',
  'Add credentials in Vault, create a listener, then click Start All': '先在“凭据库”添加账号，再创建监听器并点击“全部启动”',
  'No hits match your filters.': '没有符合当前筛选条件的结果。', Empty: '暂无内容', Search: '搜索',
  'All listeners': '全部监听器', 'Posts & Comments': '帖子和评论', 'Posts only': '仅帖子', 'Comments only': '仅评论',
  'Total saved': '已保存总数', Today: '今天', 'AI Passed': 'AI 通过',
  'Draft Reply': '生成回复草稿', 'Claude writes a context-aware, non-spammy reply': 'AI 会根据上下文生成自然、不过度推广的回复',
  'Your product / context': '产品与推广背景', 'saved automatically': '自动保存', Tone: '语气',
  helpful: '有帮助', casual: '轻松', professional: '专业', direct: '直接',
  'Generate Reply': '生成回复', 'Generating…': '生成中…', 'Generated reply': '生成的回复',
  '— edit before using': '— 使用前请检查修改', 'Copy to clipboard': '复制到剪贴板', 'Save draft': '保存草稿',
  '↗ Open post': '↗ 打开原帖', Thread: '讨论串', 'Loading thread…': '正在加载讨论串…',
  'Open on Reddit': '在 Reddit 打开', 'Top comments': '热门评论', '← matched': '← 命中内容',
  'No listeners have run yet.': '监听器尚未运行。', stopped: '已停止', 'no hits yet': '尚无命中', 'just now': '刚刚',
  'No data yet': '暂无数据', 'Start a listener and wait for hits to appear here': '启动监听器后，命中数据会显示在这里',
  'Insights from your saved hit history.': '根据已保存的命中记录生成分析。', 'Total hits': '命中总数',
  'Pass rate': '通过率', Subreddits: '子版块', 'Unique authors': '独立作者', 'Hits over time': '命中趋势',
  'Daily volume breakdown': '每日数量变化', Total: '总计', Passed: '已通过', Rejected: '未通过',
  'Passed AI': 'AI 通过', 'Type split': '类型分布', 'Posts vs Comments': '帖子与评论',
  'Top subreddits': '热门子版块', 'By hit volume': '按命中数量', Hits: '命中',
  'Top keywords matched': '热门命中关键词', 'Which patterns triggered most hits': '触发次数最多的规则',
  'Hits by hour (UTC)': '按小时统计（UTC）', 'Best times to engage': '适合参与讨论的时间',
  'By listener': '按监听器', 'Volume, passed, rejected per listener': '每个监听器的命中、通过和未通过数量',
  'By day of week': '按星期', 'Which days are most active': '活跃度最高的日期',
  'Subreddit quality': '子版块质量', 'Best subreddits for relevant leads': '最容易产生相关线索的子版块',
  'Top authors': '活跃作者', 'Most active users mentioning your keywords': '提及关键词最多的用户',
  Author: '作者', Month: '月份', 'Monthly breakdown': '月度统计',
  'Reddit Accounts': 'Reddit 账号', 'One credential per Reddit app.': '每个 Reddit 应用对应一套凭据。',
  'Add Account': '添加账号', 'AI Keys': 'AI 密钥',
  'Anthropic Claude, OpenAI, or local Ollama for filter pipelines.': '用于筛选与回复生成的 Claude、OpenAI 或本地 Ollama。',
  Edit: '编辑', Save: '保存', Cancel: '取消', Name: '名称', 'Client ID': '客户端 ID',
  'Client Secret': '客户端密钥', 'User Agent': 'User Agent', 'API Key': 'API 密钥', Model: '模型',
  Local: '本地', 'Base URL': '服务地址',
  'Listeners': '监听器', 'Each listener runs its own Reddit stream.': '每个监听器独立监控一组 Reddit 内容。',
  'New Listener': '新建监听器', 'No listeners yet': '还没有监听器', 'Click "New Listener" to get started': '点击“新建监听器”开始配置',
  Start: '启动', Stop: '停止', '⚠ No Reddit account': '⚠ 未配置 Reddit 账号',
  Credentials: '凭据', 'Reddit Account': 'Reddit 账号', '— Select —': '— 请选择 —',
  'No accounts — add in Vault': '没有账号 — 请先到凭据库添加', 'AI Key': 'AI 密钥', '(for filters)': '（用于筛选）', None: '无',
  '⚠ Missing credentials — go to Vault to add them': '⚠ 缺少凭据 — 请前往“凭据库”添加',
  Configuration: '基本配置', Webhook: 'Webhook', '(optional)': '（可选）',
  Keywords: '关键词', '(Python regex)': '（Python 正则表达式）', 'No keywords yet.': '还没有关键词。', Add: '添加',
  '⚠ Restart listener after changing keywords.': '⚠ 修改关键词后需要重启监听器。', 'Pattern tester': '规则测试器',
  Notifications: '通知', '(sent on every keyword match)': '（每次关键词命中时发送）',
  'Telegram Bot Token': 'Telegram 机器人令牌', 'Telegram Chat ID': 'Telegram 会话 ID',
  'Negative Keywords': '排除关键词', '(drop hit if any match)': '（命中任意一项即丢弃）',
  'None — all keyword matches pass through.': '无 — 所有关键词命中都会进入下一步。',
  'Author Quality Filter': '作者质量筛选', 'Skip posts from brand-new or low-karma accounts. Set to 0 to disable.': '跳过新注册或低 Karma 账号；设为 0 表示关闭。',
  'Min karma': '最低 Karma', 'Min account age (days)': '账号最短注册天数', 'Schedule Window': '运行时段',
  Timezone: '时区', 'Active days': '运行日期', 'Start hour': '开始时间', 'End hour': '结束时间',
  'Enable to restrict when this listener is active (e.g. business hours only).': '启用后可限制监听器的运行时间，例如仅在工作时段运行。',
  'AI Filter Pipeline': 'AI 筛选流程', 'Add Step': '添加步骤',
  'No filter steps yet. Each hit can be evaluated by Claude before being marked passed/rejected.': '尚未添加筛选步骤。可以让 AI 判断每条命中是否值得跟进。',
  'Step name': '步骤名称', System: '系统', Webhooks: 'Webhook', Console: '控制台', Refresh: '刷新',
  'Loading…': '加载中…', 'No logs found.': '没有日志。', Time: '时间', Level: '级别', Source: '来源',
  Listener: '监听器', Message: '消息', Status: '状态', Type: '类型', Tries: '尝试次数', Error: '错误',
  '← Prev': '← 上一页', 'Next →': '下一页 →', 'All statuses': '全部状态', Pending: '等待中',
  Success: '成功', Retrying: '重试中', Failed: '失败', 'No webhook logs yet.': '还没有 Webhook 日志。',
  'No log files found.': '没有日志文件。'
}));

const PLACEHOLDERS = new Map(Object.entries({
  'Search title, excerpt, author, subreddit…': '搜索标题、摘要、作者或子版块…',
  'What are you selling? What problem does it solve? Who is it for? (used in all replies)': '你推广什么？解决什么问题？适合谁？（用于所有回复）',
  'Filter source…': '筛选来源…', 'Paste sample text here to test all patterns above…': '粘贴示例文本，测试上方全部规则…',
  'Step name': '步骤名称', 'Prompt. Tell Claude to reply YES to pass or NO to reject.': '提示词：要求 AI 以 YES 表示通过、NO 表示拒绝。'
}));

const ATTRS = new Map(Object.entries({
  'Browser notifications': '浏览器通知', 'Toggle dark mode': '切换深色模式', 'Stream health': '监听状态'
}));

function translated(value) {
  const clean = value.trim();
  if (TEXT.has(clean)) return value.replace(clean, TEXT.get(clean));
  let match = clean.match(/^(\d+) new hits$/);
  if (match) return value.replace(clean, `${match[1]} 条新命中`);
  match = clean.match(/^(\d+) listeners?$/);
  if (match) return value.replace(clean, `${match[1]} 个监听器`);
  match = clean.match(/^(\d+) comments$/);
  if (match) return value.replace(clean, `${match[1]} 条评论`);
  match = clean.match(/^(\d+) kw$/);
  if (match) return value.replace(clean, `${match[1]} 个关键词`);
  match = clean.match(/^(\d+) filters?$/);
  if (match) return value.replace(clean, `${match[1]} 个筛选步骤`);
  return value;
}

function translateNode(root) {
  if (root.nodeType === Node.TEXT_NODE) {
    const parent = root.parentElement;
    if (parent && !['SCRIPT', 'STYLE', 'CODE'].includes(parent.tagName)) {
      const current = root.nodeValue || '';
      const next = translated(current);
      if (next !== current) root.nodeValue = next;
    }
    return;
  }
  if (!(root instanceof Element)) return;
  for (const attr of ['title', 'aria-label']) {
    const value = root.getAttribute(attr);
    if (value && ATTRS.has(value) && ATTRS.get(value) !== value) root.setAttribute(attr, ATTRS.get(value));
  }
  if ('placeholder' in root && root.placeholder && PLACEHOLDERS.has(root.placeholder)) {
    const next = PLACEHOLDERS.get(root.placeholder);
    if (next !== root.placeholder) root.placeholder = next;
  }
  for (const node of root.childNodes) translateNode(node);
}

export function installChineseUI() {
  // ponytail: RedSignal is English-only upstream; exact-label translation keeps this fork small.
  // If multilingual switching is needed later, replace this with component-level i18n keys.
  document.documentElement.lang = 'zh-CN';
  document.title = 'RedSignal 线索监控';
  const run = () => translateNode(document.body);
  run();
  new MutationObserver(records => records.forEach(record => {
    if (record.type === 'characterData') translateNode(record.target);
    record.addedNodes.forEach(translateNode);
  })).observe(document.body, { childList: true, characterData: true, subtree: true });
}
