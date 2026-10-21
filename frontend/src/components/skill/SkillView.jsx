import { useState, useEffect } from 'react';
import { apiFetch } from '../../api.js';

export default function SkillView() {
  const [skillData, setSkillData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copiedKey, setCopiedKey] = useState(null);
  const [activeSubTab, setActiveSubTab] = useState('overview'); // overview, archetypes, dual_track, cli, raw_markdown

  useEffect(() => {
    loadSkill();
  }, []);

  async function loadSkill() {
    setLoading(true);
    try {
      const res = await apiFetch('/api/skill');
      if (res && res.ok) {
        setSkillData(res);
      }
    } catch (e) {
      console.error('Failed to load skill', e);
    } finally {
      setLoading(false);
    }
  }

  function copyText(key, text) {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  }

  const cliCommands = [
    {
      name: '扫描最新线索',
      cmd: '/Users/han/redsignal/.venv/bin/python3 /Users/han/redsignal/redsignal_cli.py radar --limit 5',
      desc: '查看最新高意向商机（支持 --intent 与 --campaign 筛选）'
    },
    {
      name: '金矿意向筛选',
      cmd: '/Users/han/redsignal/.venv/bin/python3 /Users/han/redsignal/redsignal_cli.py radar --intent affiliate --limit 5',
      desc: '精准筛选替代、选型、口碑、折扣等高转化帖子'
    },
    {
      name: '藤壶存活巡检 🆕',
      cmd: '/Users/han/redsignal/.venv/bin/python3 /Users/han/redsignal/redsignal_cli.py audit --limit 10',
      desc: '巡检公域已发回帖存活状态 (LIVE/LOCKED/REMOVED) 与 Google SERP 占坑健康度'
    },
    {
      name: '联盟营销攻坚 🆕',
      cmd: '/Users/han/redsignal/.venv/bin/python3 /Users/han/redsignal/redsignal_cli.py affiliate 3 --product "LemonSqueezy" --url "https://lemonsqueezy.com?aff=test"',
      desc: '生成 0 外链藤壶回帖、逆向私信钩子、Lead Magnet 诱饵与带 UTM 的 3 轮攻坚闭环'
    },
    {
      name: '自营私信攻坚',
      cmd: '/Users/han/redsignal/.venv/bin/python3 /Users/han/redsignal/redsignal_cli.py dm 3',
      desc: '针对自营独立站/垂直工具生成公开钩子、一键直达发信链接与 3 轮心智流'
    },
    {
      name: '私信全自动代聊 🆕',
      cmd: '/Users/han/redsignal/.venv/bin/python3 /Users/han/redsignal/redsignal_cli.py inbox --platform all --dry-run',
      desc: '轮询 Reddit 与 X (Twitter) 未读私信，AI 研判意图并全自动多轮跟进回复+Bark播报'
    },
    {
      name: '长线资产大盘 🆕',
      cmd: '/Users/han/redsignal/.venv/bin/python3 /Users/han/redsignal/redsignal_cli.py status',
      desc: '查看长线项目健康度、代码库状态、系统 Crontab 调度与官方镜像连通性'
    },
    {
      name: '凭证健康体检 🆕',
      cmd: '/Users/han/redsignal/.venv/bin/python3 /Users/han/redsignal/redsignal_cli.py doctor',
      desc: '一键检测 Reddit、X、Bark 与 AI 凭证连通性，失效自动预警'
    },
    {
      name: '风控配额巡检',
      cmd: '/Users/han/redsignal/.venv/bin/python3 /Users/han/redsignal/redsignal_cli.py quota',
      desc: '检查今日已发条数、剩余配额与 45m 冷却倒计时'
    },
    {
      name: '发帖安全预演',
      cmd: '/Users/han/redsignal/.venv/bin/python3 /Users/han/redsignal/redsignal_cli.py post 3 --text "..." --dry-run',
      desc: '验证风控、匹配落地页与短链，不发网'
    }
  ];

  const archetypes = [
    {
      icon: '🔥',
      title: '替代弃用 (Switching / Churn Intent)',
      roots: '[竞品] alternative, too expensive, cancel [竞品], price hike, replace [竞品]',
      mindset: '用户已被竞品教育过，因涨价、功能阉割或客服差产生强烈迁徙冲动，处于换工具临门一脚。',
      strategy: '客观拆解竞品隐形成本，提供迁移对照表与性价比平替方案。'
    },
    {
      icon: '⚖️',
      title: '选型对比 (Comparison Dilemma)',
      roots: '[Tool A] vs [Tool B] for [niche scenario], which is better, difference between',
      mindset: '预算已审批，正在 A 和 B 之间纠结。',
      strategy: '公开中立给出实测 Benchmarks（不偏不倚），私信送出更具 ROI 的第三方案或专属优惠。'
    },
    {
      icon: '⭐',
      title: '真实口碑 (Authentic Review & Proof)',
      roots: 'is [产品] legit, honest review after 1 year reddit, worth the money, scam or legit',
      mindset: '准备刷卡前搜索真实评价，寻找同行背书以打消风险疑虑。',
      strategy: '以资深老玩家/同行身份拆解优缺点（9 分赞扬 + 1 分客观瑕疵），极大建立信任。'
    },
    {
      icon: '🏷️',
      title: '折扣防线 (Last-Mile Deal & Promo)',
      roots: '[Product] promo code that works reddit, discount, coupon code, lifetime deal',
      mindset: '已经准备付款，正在 Google/Reddit 找有效折扣码或返利入口。',
      strategy: '提供真实可用的专属优惠码与联盟返佣直达链接。'
    },
    {
      icon: '🛠️',
      title: '痛点排查 (Troubleshooting / High-Pain)',
      roots: '[Tool/Car] error code, wont start, broken, failed, how to fix [issue]',
      mindset: '遇到紧急技术故障，急需专家图纸或排查诊断工具。',
      strategy: '提供专业排查建议，顺承引入自营检测工具或高匹配配件。'
    }
  ];

  return (
    <div className="flex flex-col h-full bg-slate-50/60 overflow-hidden">
      {/* ── Top Header ─────────────────────────────────────── */}
      <div className="bg-white border-b border-slate-200/80 px-6 py-4 flex-shrink-0 shadow-2xs">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-rose-600 to-indigo-600 flex items-center justify-center text-white text-xl shadow-sm">
              ⚡
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-lg font-bold text-slate-900 tracking-tight">RedSignal Skill 控制台与心法中枢</h1>
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200/70">
                  v5.1 Unified Growth Hub
                </span>
                <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200/70">
                  哥飞 SEO + CRO 双轨
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                融合“公开权威藤壶回帖 + 1v1 私信 Lead Magnet 诱饵 + 动态 UTM 归因闭环”的海外社媒截流营销战法。
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => copyText('url', 'https://s.hanzhe.dpdns.org/SKILL.md')}
              className="px-3.5 py-2 text-xs font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-lg hover:bg-indigo-100 transition shadow-2xs flex items-center gap-1.5 cursor-pointer"
            >
              {copiedKey === 'url' ? '✓ 已复制公开链接' : '🔗 复制 Skill 托管地址'}
            </button>
            <a
              href="/SKILL.md"
              target="_blank"
              rel="noopener noreferrer"
              className="px-3.5 py-2 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition shadow-2xs flex items-center gap-1.5"
            >
              📥 下载原始 SKILL.md
            </a>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center gap-1.5 mt-4 pt-3 border-t border-slate-100 text-xs">
          <button
            onClick={() => setActiveSubTab('overview')}
            className={`px-3 py-1.5 rounded-lg font-semibold transition cursor-pointer ${
              activeSubTab === 'overview' ? 'bg-indigo-600 text-white shadow-xs' : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            🌟 战法总览
          </button>
          <button
            onClick={() => setActiveSubTab('archetypes')}
            className={`px-3 py-1.5 rounded-lg font-semibold transition cursor-pointer ${
              activeSubTab === 'archetypes' ? 'bg-indigo-600 text-white shadow-xs' : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            💰 5 大商业金矿词根
          </button>
          <button
            onClick={() => setActiveSubTab('dual_track')}
            className={`px-3 py-1.5 rounded-lg font-semibold transition cursor-pointer ${
              activeSubTab === 'dual_track' ? 'bg-indigo-600 text-white shadow-xs' : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            🎯 双轨转化与 UTM 漏斗
          </button>
          <button
            onClick={() => setActiveSubTab('cli')}
            className={`px-3 py-1.5 rounded-lg font-semibold transition cursor-pointer ${
              activeSubTab === 'cli' ? 'bg-indigo-600 text-white shadow-xs' : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            🛠️ CLI 武器库速查
          </button>
          <button
            onClick={() => setActiveSubTab('raw_markdown')}
            className={`px-3 py-1.5 rounded-lg font-semibold transition cursor-pointer ${
              activeSubTab === 'raw_markdown' ? 'bg-indigo-600 text-white shadow-xs' : 'text-slate-600 hover:bg-slate-100'
            }`}
          >
            📄 SKILL.md 完整源码
          </button>
        </div>
      </div>

      {/* ── Main Content Area ─────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* SubTab 1: Overview */}
        {activeSubTab === 'overview' && (
          <div className="space-y-6 max-w-5xl">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs space-y-2">
                <div className="text-2xl">🌾</div>
                <h3 className="font-bold text-slate-900 text-sm">【哥飞视角】养站防老与藤壶占坑</h3>
                <p className="text-xs text-slate-600 leading-relaxed">
                  借高权重 Reddit/论坛帖子出海，抢占 Google 搜索首页常青树排位。零外链、纯干货建立权威，末尾埋下逆向私信邀请，安全合规沉淀长效资产。
                </p>
              </div>

              <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs space-y-2">
                <div className="text-2xl">🤖</div>
                <h3 className="font-bold text-slate-900 text-sm">【Claude AI 视角】CRO 与零方数据漏斗</h3>
                <p className="text-xs text-slate-600 leading-relaxed">
                  Round 1 破冰交付；Round 2 赠送 1-Page Checklist / Benchmark 诱饵打消防备；Round 3 附带精准动态 UTM 追踪与 FTC 披露链接，实现确定性转化闭环。
                </p>
              </div>

              <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs space-y-2">
                <div className="text-2xl">🛡️</div>
                <h3 className="font-bold text-slate-900 text-sm">80/20 反封号与风控死线</h3>
                <p className="text-xs text-slate-600 leading-relaxed">
                  80% 纯干货技术解答洗号，20% 软植入引流；单账号每日最多 8 帖，强制 45 分钟发帖冷却；严禁假装说已发私信，仅用被动邀请机制。
                </p>
              </div>
            </div>

            {/* Quick Trigger Words */}
            <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs space-y-3">
              <h3 className="font-bold text-slate-900 text-sm flex items-center gap-2">
                <span>💬 Claude 对话触发词 (Triggers)</span>
              </h3>
              <p className="text-xs text-slate-500">在任意 Claude 对话中输入以下关键词即可自动调用 RedSignal 截流与转化中枢：</p>
              <div className="flex flex-wrap gap-2 text-xs">
                {['/redsignal', '/redsignal-chat', '截流', '看线索', '发帖', '社媒雷达', 'reddit发帖', '藤壶引流', '私信', '聊单', 'affiliate', '联盟营销', '转化策略'].map(k => (
                  <span key={k} className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 font-mono font-medium rounded-lg transition">
                    {k}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* SubTab 2: Archetypes */}
        {activeSubTab === 'archetypes' && (
          <div className="space-y-4 max-w-5xl">
            <div className="bg-amber-50/70 border border-amber-200/80 rounded-2xl p-4 text-xs text-amber-900">
              💡 <strong>低搜高转化心法</strong>: 海外社媒大词竞争惨烈充斥水军；而搜索量极小、甚至零月搜但交易意图极强的长尾讨论，才是真实买家下单前的“最后一公里”。
            </div>

            <div className="grid grid-cols-1 gap-3.5">
              {archetypes.map((a, idx) => (
                <div key={idx} className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs space-y-2.5 hover:border-indigo-300 transition">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 font-bold text-slate-900 text-sm">
                      <span className="text-lg">{a.icon}</span>
                      <span>{a.title}</span>
                    </div>
                  </div>
                  <div className="text-xs font-mono bg-slate-50 text-indigo-700 px-3 py-1.5 rounded-lg border border-slate-200/60">
                    <strong>金矿词根:</strong> {a.roots}
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs pt-1">
                    <div className="bg-slate-50/50 p-2.5 rounded-xl border border-slate-100">
                      <strong className="text-slate-700 block mb-0.5">🧠 真实买家心智:</strong>
                      <span className="text-slate-600">{a.mindset}</span>
                    </div>
                    <div className="bg-indigo-50/30 p-2.5 rounded-xl border border-indigo-100/50">
                      <strong className="text-indigo-800 block mb-0.5">🎯 推荐截流战法:</strong>
                      <span className="text-indigo-900">{a.strategy}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* SubTab 3: Dual-Track */}
        {activeSubTab === 'dual_track' && (
          <div className="space-y-5 max-w-5xl">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs space-y-3">
                <div className="flex items-center gap-2 font-bold text-slate-900 text-sm">
                  <span className="text-lg">📢</span>
                  <span>轨道 1: 公开老炮评论（公开引水 · 藤壶占坑）</span>
                </div>
                <ul className="text-xs text-slate-600 space-y-2 list-disc pl-4 leading-relaxed">
                  <li><strong>核心定位</strong>: 以资深玩家/行业实操者视角提供硬核诊断，抢占 Google 搜索长尾排名前列。</li>
                  <li><strong>0 外链原则</strong>: 公开回复坚决不直接发推广链接，避免被 AutoMod 静默折叠或版主封号。</li>
                  <li><strong>逆向私信钩子 (Inbound DM Hook)</strong>: 严禁在公开帖说“我已发私信你”！必须真诚邀请：“我整理了一份 1-Page 对比清单/排查表，如果你需要随时私信我，我发你”。对方主动发信 100% 免除 Spam 举报！</li>
                </ul>
              </div>

              <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs space-y-3">
                <div className="flex items-center gap-2 font-bold text-slate-900 text-sm">
                  <span className="text-lg">✉️</span>
                  <span>轨道 2: 1v1 私信深度攻坚（私域收割 · 3 轮递进）</span>
                </div>
                <div className="space-y-2 text-xs">
                  <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-200/60">
                    <strong className="text-indigo-700">Round 1 (破冰共情)</strong>: 0 推销、0 废话，直接交付公开帖承诺的排查指南或对比文档，消除防备。
                  </div>
                  <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-200/60">
                    <strong className="text-indigo-700">Round 2 (痛点诊断 · Lead Magnet)</strong>: 排查客户核心瓶颈，附送 1-Page Setup Checklist 或 Benchmark Sheet，防止过早甩链接导致 70%+ 跳出。
                  </div>
                  <div className="p-2.5 bg-slate-50 rounded-xl border border-slate-200/60">
                    <strong className="text-indigo-700">Round 3 (精准逼单 · 动态 UTM 链接)</strong>: 顺承送出自营或联盟推荐链接，附带动态 UTM 矩阵 (<code>utm_source</code>/<code>utm_medium=dm</code>/<code>utm_content=round3</code>) 与 FTC 规范披露。
                  </div>
                </div>
              </div>
            </div>

            {/* UTM Attribution Matrix */}
            <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-2xs space-y-3">
              <h3 className="font-bold text-slate-900 text-sm flex items-center gap-2">
                <span>🎯 细粒度 UTM 转化归因规范</span>
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                      <th className="py-2.5 px-3 font-semibold">参数</th>
                      <th className="py-2.5 px-3 font-semibold">规范取值</th>
                      <th className="py-2.5 px-3 font-semibold">作用与说明</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    <tr>
                      <td className="py-2 px-3 font-mono font-bold text-indigo-700">utm_source</td>
                      <td className="py-2 px-3 font-mono">reddit / x</td>
                      <td className="py-2 px-3">识别触达平台来源</td>
                    </tr>
                    <tr>
                      <td className="py-2 px-3 font-mono font-bold text-indigo-700">utm_medium</td>
                      <td className="py-2 px-3 font-mono">dm</td>
                      <td className="py-2 px-3">媒介固定为 1v1 私信渠道</td>
                    </tr>
                    <tr>
                      <td className="py-2 px-3 font-mono font-bold text-indigo-700">utm_campaign</td>
                      <td className="py-2 px-3 font-mono">[campaign_name]</td>
                      <td className="py-2 px-3">关联具体的自营或联盟 Offer 项目</td>
                    </tr>
                    <tr>
                      <td className="py-2 px-3 font-mono font-bold text-indigo-700">utm_content</td>
                      <td className="py-2 px-3 font-mono">round3 / lead_magnet</td>
                      <td className="py-2 px-3">标记是在第 3 轮推荐送出还是由 Lead Magnet 诱饵促发</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* SubTab 4: CLI Commands */}
        {activeSubTab === 'cli' && (
          <div className="space-y-4 max-w-5xl">
            <div className="flex items-center justify-between text-xs text-slate-500">
              <span>在终端直接运行以下 RedSignal CLI 命令即可执行全功能调度：</span>
              <span>共收录 10 个高频指令</span>
            </div>

            <div className="grid grid-cols-1 gap-3">
              {cliCommands.map((c, idx) => (
                <div key={idx} className="bg-white border border-slate-200/80 rounded-2xl p-4 shadow-2xs space-y-2 hover:border-indigo-300 transition">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-900 text-xs flex items-center gap-1.5">
                      <span>📌</span>
                      <span>{c.name}</span>
                    </span>
                    <button
                      onClick={() => copyText(`cmd_${idx}`, c.cmd)}
                      className="px-2.5 py-1 text-[11px] font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg transition cursor-pointer"
                    >
                      {copiedKey === `cmd_${idx}` ? '✓ 已复制' : '复制命令'}
                    </button>
                  </div>
                  <p className="text-[11px] text-slate-500">{c.desc}</p>
                  <pre className="text-xs font-mono bg-slate-900 text-slate-100 p-2.5 rounded-xl overflow-x-auto">
                    {c.cmd}
                  </pre>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* SubTab 5: Raw Markdown */}
        {activeSubTab === 'raw_markdown' && (
          <div className="space-y-3 max-w-5xl">
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-500 font-medium">
                托管于: <code className="text-indigo-700 bg-indigo-50 px-1.5 py-0.5 rounded">https://s.hanzhe.dpdns.org/SKILL.md</code>
              </span>
              <button
                onClick={() => copyText('raw', skillData?.content || '')}
                className="px-3.5 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition shadow-2xs cursor-pointer"
              >
                {copiedKey === 'raw' ? '✓ 已复制全文' : '📋 复制 Markdown 全文'}
              </button>
            </div>
            {loading ? (
              <div className="py-20 text-center text-slate-400 text-xs">正在载入 SKILL.md…</div>
            ) : (
              <pre className="bg-white border border-slate-200 rounded-2xl p-5 text-xs font-mono text-slate-800 leading-relaxed overflow-x-auto whitespace-pre-wrap max-h-[65vh]">
                {skillData?.content || '暂无内容'}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
