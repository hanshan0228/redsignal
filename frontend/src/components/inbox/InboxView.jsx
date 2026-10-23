import { useState, useEffect } from 'react';
import { apiFetch } from '../../api.js';
import { timeAgo } from '../../utils.js';

export default function InboxView() {
  const [conversations, setConversations] = useState([]);
  const [stats, setStats] = useState({ total: 0, active: 0, replied: 0, closed: 0, reddit: 0, x: 0 });
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);
  const [pollDryRun, setPollDryRun] = useState(true);
  const [platformFilter, setPlatformFilter] = useState('all'); // 'all', 'reddit', 'x'
  const [statusFilter, setStatusFilter] = useState('all'); // 'all', 'active', 'replied', 'closed'
  const [autopilotConfig, setAutopilotConfig] = useState({ autopilot_enabled: false, dry_run: true });
  const [replyingId, setReplyingId] = useState(null);
  const [activeModalConv, setActiveModalConv] = useState(null);
  const [customReplyText, setCustomReplyText] = useState('');
  const [copiedId, setCopiedId] = useState(null);

  useEffect(() => {
    loadInbox();
    loadConfig();
  }, [platformFilter, statusFilter]);

  async function loadInbox() {
    setLoading(true);
    try {
      const q = new URLSearchParams();
      if (platformFilter !== 'all') q.set('platform', platformFilter);
      if (statusFilter !== 'all') q.set('status', statusFilter);
      const res = await apiFetch(`/api/inbox/conversations?${q.toString()}`);
      if (res && res.ok) {
        setConversations(res.conversations || []);
        setStats(res.stats || { total: 0, active: 0, replied: 0, closed: 0, reddit: 0, x: 0 });
      }
    } catch (e) {
      console.error('Failed to load inbox conversations', e);
    } finally {
      setLoading(false);
    }
  }

  async function loadConfig() {
    try {
      const res = await apiFetch('/api/inbox/config');
      if (res && res.ok) {
        setAutopilotConfig({
          autopilot_enabled: Boolean(res.autopilot_enabled),
          dry_run: Boolean(res.dry_run)
        });
      }
    } catch (e) {
      console.error('Failed to load inbox config', e);
    }
  }

  async function handleToggleAutopilot() {
    const nextVal = !autopilotConfig.autopilot_enabled;
    try {
      const res = await apiFetch('/api/inbox/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ autopilot_enabled: nextVal })
      });
      if (res && res.ok) {
        setAutopilotConfig(prev => ({ ...prev, autopilot_enabled: nextVal }));
      }
    } catch (e) {
      alert(`切换失败: ${e}`);
    }
  }

  async function handleToggleAutopilotDryRun() {
    const nextVal = !autopilotConfig.dry_run;
    try {
      const res = await apiFetch('/api/inbox/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dry_run: nextVal })
      });
      if (res && res.ok) {
        setAutopilotConfig(prev => ({ ...prev, dry_run: nextVal }));
      }
    } catch (e) {
      alert(`切换失败: ${e}`);
    }
  }

  async function handlePoll(platform = 'all') {
    setPolling(true);
    try {
      const res = await apiFetch('/api/inbox/poll', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ platform, dry_run: pollDryRun })
      });
      if (res && res.ok) {
        await loadInbox();
        alert(`🎉 轮询完成！共处理 ${res.count || 0} 条未读私信 (${res.dry_run ? 'Dry-Run 预演模式，未实发' : '已自动回复并推送 Bark'})。`);
      } else {
        alert(`轮询异常: ${res?.error || '未知错误'}`);
      }
    } catch (e) {
      alert(`请求异常: ${e}`);
    } finally {
      setPolling(false);
    }
  }

  async function handleSendReply(convId, customText = '') {
    setReplyingId(convId);
    try {
      const res = await apiFetch('/api/inbox/reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_id: convId, custom_text: customText || null, dry_run: false })
      });
      if (res && res.ok) {
        await loadInbox();
        setActiveModalConv(null);
        alert('✅ 回复已记录并推送 Bark 通知！如需在官方页面发送，可点击「直达官方窗口」。');
      } else {
        alert(`发送失败: ${res?.error || '未知错误'}`);
      }
    } catch (e) {
      alert(`请求失败: ${e}`);
    } finally {
      setReplyingId(null);
    }
  }

  async function handleUpdateStatus(convId, newStatus) {
    try {
      const res = await apiFetch(`/api/inbox/conversations/${convId}/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      });
      if (res && res.ok) {
        loadInbox();
      }
    } catch (e) {
      alert(`更新失败: ${e}`);
    }
  }

  async function handleDelete(convId) {
    if (!confirm('确定移除此私信会话吗？')) return;
    try {
      const res = await apiFetch(`/api/inbox/conversations/${convId}`, { method: 'DELETE' });
      if (res && res.ok) {
        loadInbox();
      }
    } catch (e) {
      alert(`删除失败: ${e}`);
    }
  }

  function copyText(key, text) {
    navigator.clipboard.writeText(text);
    setCopiedId(key);
    setTimeout(() => setCopiedId(null), 2000);
  }

  function getComposeUrl(conv, replyText = '') {
    const handle = conv.partner_handle || '';
    const text = replyText || conv.last_outbound_msg || '';
    if (conv.platform === 'reddit') {
      const clean = handle.replace('u/', '').trim();
      const sub = encodeURIComponent(conv.subject || 'Follow-up');
      const msg = encodeURIComponent(text);
      return clean ? `https://www.reddit.com/message/compose?to=${clean}&subject=${sub}&message=${msg}` : 'https://www.reddit.com/message/compose';
    } else {
      const clean = handle.replace('@', '').trim();
      return clean ? `https://x.com/${clean}` : 'https://x.com/messages';
    }
  }

  return (
    <div className="flex flex-col h-full bg-slate-50/60 overflow-hidden">
      {/* ── Top Header ─────────────────────────────────────── */}
      <div className="bg-white border-b border-slate-200/80 px-6 py-4 flex-shrink-0 shadow-2xs">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-600 flex items-center justify-center text-white text-xl shadow-sm">
              ✉️
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-lg font-bold text-slate-900 tracking-tight">私信监控与自动转化中枢 (DM Inbox)</h1>
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200/70">
                  Reddit & 𝕏 多轮攻坚
                </span>
                <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200/70">
                  UTM + Lead Magnet 诱饵
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                轮询海外社媒未读私信，大模型自动研判意图并生成 3 轮递进攻坚草稿，全链路带动态 UTM 与移动端 Bark 实时播报。
              </p>
            </div>
          </div>

          {/* Autopilot & Action Controls */}
          <div className="flex items-center gap-3 flex-wrap">
            {/* Autopilot Toggle */}
            <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs">
              <span className="font-semibold text-slate-700">🤖 全自动代聊:</span>
              <button
                onClick={handleToggleAutopilot}
                className={`px-2.5 py-0.5 rounded-full font-bold text-[11px] transition cursor-pointer ${
                  autopilotConfig.autopilot_enabled ? 'bg-emerald-600 text-white shadow-2xs' : 'bg-slate-200 text-slate-600'
                }`}
              >
                {autopilotConfig.autopilot_enabled ? '已开启' : '已暂停'}
              </button>
              {autopilotConfig.autopilot_enabled && (
                <button
                  onClick={handleToggleAutopilotDryRun}
                  className={`text-[10px] px-1.5 py-0.5 rounded border transition cursor-pointer ${
                    autopilotConfig.dry_run ? 'bg-amber-50 text-amber-700 border-amber-300' : 'bg-rose-50 text-rose-700 border-rose-300'
                  }`}
                  title="Dry-Run: 仅生成草稿并推送到 Bark，不真实外发网络；实发模式: 真实通过 Cookie 发回信"
                >
                  {autopilotConfig.dry_run ? '仅预演 (Dry-Run)' : '真实外发 (Live)'}
                </button>
              )}
            </div>

            {/* Poll Dry-Run Checkbox */}
            <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer">
              <input
                type="checkbox"
                checked={pollDryRun}
                onChange={(e) => setPollDryRun(e.target.checked)}
                className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              />
              <span>预演模式 (不外发)</span>
            </label>

            {/* Poll Button */}
            <button
              onClick={() => handlePoll('all')}
              disabled={polling}
              className="px-4 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 rounded-lg transition shadow-2xs flex items-center gap-1.5 cursor-pointer"
            >
              {polling ? (
                <>
                  <span className="spin">⟳</span>
                  <span>正在扫描未读私信...</span>
                </>
              ) : (
                <>
                  <span>⚡ 立即轮询未读私信</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* ── KPI Cards ─────────────────────────────────────── */}
        <div className="grid grid-cols-2 sm:grid-cols-6 gap-3 mt-4 pt-3 border-t border-slate-100 text-xs">
          <div className="bg-slate-50 rounded-xl p-3 border border-slate-150">
            <div className="text-[11px] text-slate-500 font-medium">📬 监控总会话</div>
            <div className="text-xl font-bold text-slate-900 mt-1">{stats.total}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">Reddit + 𝕏 私信池</div>
          </div>
          <div className="bg-amber-50/70 rounded-xl p-3 border border-amber-200/60">
            <div className="text-[11px] text-amber-700 font-medium">⏳ 待攻坚 / 待跟进</div>
            <div className="text-xl font-bold text-amber-800 mt-1">{stats.active}</div>
            <div className="text-[10px] text-amber-600 mt-0.5">需发送下一轮心智</div>
          </div>
          <div className="bg-emerald-50/70 rounded-xl p-3 border border-emerald-200/60">
            <div className="text-[11px] text-emerald-700 font-medium">💬 已回复进行中</div>
            <div className="text-xl font-bold text-emerald-800 mt-1">{stats.replied}</div>
            <div className="text-[10px] text-emerald-600 mt-0.5">已送出干货或诱饵</div>
          </div>
          <div className="bg-purple-50/70 rounded-xl p-3 border border-purple-200/60">
            <div className="text-[11px] text-purple-700 font-medium">🏆 已闭环 / 成单</div>
            <div className="text-xl font-bold text-purple-800 mt-1">{stats.closed}</div>
            <div className="text-[10px] text-purple-600 mt-0.5">送出带 UTM 联盟链接</div>
          </div>
          <div className="bg-slate-50 rounded-xl p-3 border border-slate-150">
            <div className="text-[11px] text-slate-500 font-medium">🟧 Reddit 会话</div>
            <div className="text-xl font-bold text-slate-800 mt-1">{stats.reddit}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">老版 Reddit 邮箱会话</div>
          </div>
          <div className="bg-slate-50 rounded-xl p-3 border border-slate-150">
            <div className="text-[11px] text-slate-500 font-medium">🐦 𝕏 (Twitter) 会话</div>
            <div className="text-xl font-bold text-slate-800 mt-1">{stats.x}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">DM 对话与通知</div>
          </div>
        </div>
      </div>

      {/* ── Filter Bar ─────────────────────────────────────── */}
      <div className="px-6 py-2.5 bg-slate-100/80 border-b border-slate-200 flex items-center justify-between flex-wrap gap-3 flex-shrink-0 text-xs">
        <div className="flex items-center gap-1.5">
          <span className="font-semibold text-slate-500 mr-1">平台:</span>
          {['all', 'reddit', 'x'].map(p => (
            <button
              key={p}
              onClick={() => setPlatformFilter(p)}
              className={`px-3 py-1 rounded-lg font-medium transition cursor-pointer ${
                platformFilter === p ? 'bg-white text-indigo-700 font-bold shadow-2xs border border-slate-200' : 'text-slate-600 hover:bg-slate-200'
              }`}
            >
              {p === 'all' ? '全部平台' : p === 'reddit' ? 'Reddit' : '𝕏 (Twitter)'}
            </button>
          ))}

          <span className="font-semibold text-slate-500 ml-4 mr-1">状态:</span>
          {[
            { k: 'all', l: '全部状态' },
            { k: 'active', l: '待跟进' },
            { k: 'replied', l: '已回复' },
            { k: 'closed', l: '已闭环' }
          ].map(s => (
            <button
              key={s.k}
              onClick={() => setStatusFilter(s.k)}
              className={`px-3 py-1 rounded-lg font-medium transition cursor-pointer ${
                statusFilter === s.k ? 'bg-white text-indigo-700 font-bold shadow-2xs border border-slate-200' : 'text-slate-600 hover:bg-slate-200'
              }`}
            >
              {s.l}
            </button>
          ))}
        </div>

        <div className="text-slate-400 text-[11px]">
          共显示 {conversations.length} 条会话
        </div>
      </div>

      {/* ── Conversation List ─────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {loading ? (
          <div className="text-center py-20 text-slate-400 text-xs">正在载入私信监控会话...</div>
        ) : conversations.length === 0 ? (
          <div className="text-center py-20 bg-white rounded-2xl border border-dashed border-slate-300 p-8 space-y-3">
            <div className="text-4xl">📬</div>
            <h3 className="font-bold text-slate-800 text-sm">当前暂无监控中的私信会话</h3>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              点击上方「⚡ 立即轮询未读私信」按钮，系统将自动连接 Reddit 与 𝕏 凭证拉取最新受邀私信，并自动生成 3 轮心智回复！
            </p>
            <button
              onClick={() => handlePoll('all')}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 transition shadow-xs cursor-pointer inline-flex items-center gap-1.5"
            >
              <span>⚡ 立即拉取并研判私信</span>
            </button>
          </div>
        ) : (
          conversations.map(conv => {
            const isReddit = conv.platform === 'reddit';
            const authorDisplay = isReddit ? `u/${conv.partner_handle}` : `@${conv.partner_handle}`;
            const round = conv.current_round || 1;
            const isReplied = conv.status === 'replied';
            const isClosed = conv.status === 'closed';

            return (
              <div
                key={conv.id}
                className="bg-white rounded-2xl border border-slate-200/90 hover:border-indigo-300 transition shadow-2xs hover:shadow-xs p-5 space-y-3.5"
              >
                {/* Header Row */}
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2.5">
                    <span className={`px-2 py-0.5 rounded-md text-[11px] font-bold uppercase tracking-wider ${
                      isReddit ? 'bg-orange-50 text-orange-700 border border-orange-200' : 'bg-slate-900 text-white'
                    }`}>
                      {conv.platform}
                    </span>
                    <a
                      href={isReddit ? `https://www.reddit.com/user/${conv.partner_handle}` : `https://x.com/${conv.partner_handle}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-bold text-slate-900 text-sm hover:text-indigo-600 hover:underline flex items-center gap-1"
                    >
                      <span>{authorDisplay}</span>
                      <span className="text-slate-400 text-xs font-normal">↗</span>
                    </a>

                    {/* Round Badge */}
                    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${
                      round === 1
                        ? 'bg-blue-50 text-blue-700 border-blue-200'
                        : round === 2
                        ? 'bg-amber-50 text-amber-700 border-amber-200'
                        : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                    }`}>
                      {round === 1 && '🎯 Round 1: 破冰共情 · 兑现承诺'}
                      {round === 2 && '🧲 Round 2: 场景实测 · Lead Magnet 诱饵'}
                      {round >= 3 && '💰 Round 3: 精准逼单 · 动态 UTM 链接'}
                    </span>

                    {/* Status Badge */}
                    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-md border ${
                      isClosed
                        ? 'bg-slate-100 text-slate-600 border-slate-200'
                        : isReplied
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                        : 'bg-amber-50 text-amber-700 border-amber-200'
                    }`}>
                      {isClosed ? '✓ 已闭环' : isReplied ? '💬 已回复攻坚中' : '⏳ 待回复'}
                    </span>
                  </div>

                  <span className="text-[11px] text-slate-400">
                    更新于 {timeAgo(conv.updated_at || conv.created_at)}
                  </span>
                </div>

                {/* Subject if any */}
                {conv.subject && (
                  <div className="text-xs text-slate-500 font-medium flex items-center gap-1.5">
                    <span>📌 主题:</span>
                    <span className="text-slate-800">{conv.subject}</span>
                  </div>
                )}

                {/* Inbound & Outbound Dialog Box */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                  {/* Inbound */}
                  <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3 space-y-1.5">
                    <div className="flex items-center justify-between text-slate-500 font-bold text-[11px]">
                      <span className="flex items-center gap-1 text-slate-700">
                        <span>📥 对方来信:</span>
                      </span>
                      <button
                        onClick={() => copyText(`in_${conv.id}`, conv.last_inbound_msg)}
                        className="hover:text-indigo-600 cursor-pointer"
                      >
                        {copiedId === `in_${conv.id}` ? '✓ 已复制' : '复制'}
                      </button>
                    </div>
                    <div className="text-slate-800 leading-relaxed font-sans whitespace-pre-wrap">
                      {conv.last_inbound_msg || '(暂无来信文本记录)'}
                    </div>
                  </div>

                  {/* Outbound AI Draft */}
                  <div className="bg-indigo-50/40 border border-indigo-100 rounded-xl p-3 space-y-1.5">
                    <div className="flex items-center justify-between text-indigo-700 font-bold text-[11px]">
                      <span className="flex items-center gap-1">
                        <span>📤 AI 攻坚回复草稿:</span>
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => copyText(`out_${conv.id}`, conv.last_outbound_msg)}
                          className="hover:text-indigo-900 cursor-pointer"
                        >
                          {copiedId === `out_${conv.id}` ? '✓ 已复制' : '复制'}
                        </button>
                      </div>
                    </div>
                    <div className="text-slate-800 leading-relaxed font-sans whitespace-pre-wrap">
                      {conv.last_outbound_msg || '(等待生成回复话术)'}
                    </div>
                  </div>
                </div>

                {/* Action Toolbar */}
                <div className="flex items-center justify-between pt-2 border-t border-slate-100 flex-wrap gap-2 text-xs">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        setActiveModalConv(conv);
                        setCustomReplyText(conv.last_outbound_msg || '');
                      }}
                      className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold rounded-lg transition cursor-pointer flex items-center gap-1"
                    >
                      <span>✏️ 微调回复</span>
                    </button>

                    <button
                      onClick={() => handleSendReply(conv.id)}
                      disabled={replyingId === conv.id}
                      className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-lg transition shadow-2xs cursor-pointer flex items-center gap-1 disabled:opacity-50"
                    >
                      {replyingId === conv.id ? '正在处理...' : '⚡ 确认发送并推 Bark'}
                    </button>

                    <a
                      href={getComposeUrl(conv)}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={() => copyText(`out_${conv.id}`, conv.last_outbound_msg)}
                      className="px-3 py-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200 font-semibold rounded-lg transition cursor-pointer flex items-center gap-1"
                      title="打开官方私信窗口预填话术，完全通过用户浏览器手动发送，0 风控"
                    >
                      <span>🚀 官方发信窗口直达 ↗</span>
                    </a>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleUpdateStatus(conv.id, isClosed ? 'active' : 'closed')}
                      className="text-[11px] text-slate-500 hover:text-slate-800 hover:underline cursor-pointer"
                    >
                      {isClosed ? '↺ 重新激活' : '✓ 标记已闭环'}
                    </button>
                    <span className="text-slate-300">|</span>
                    <button
                      onClick={() => handleDelete(conv.id)}
                      className="text-[11px] text-red-500 hover:text-red-700 hover:underline cursor-pointer"
                    >
                      移除
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* ── Modal for Custom Editing & Dispatch ─────────────────────── */}
      {activeModalConv && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-xl w-full p-6 space-y-4 border border-slate-200 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <span className="p-1.5 bg-indigo-100 text-indigo-700 rounded-lg text-base">✉️</span>
                <h3 className="text-sm font-bold text-slate-900">
                  编辑并发送回复: {activeModalConv.partner_handle} ({activeModalConv.platform.toUpperCase()})
                </h3>
              </div>
              <button
                onClick={() => setActiveModalConv(null)}
                className="w-7 h-7 rounded-lg hover:bg-slate-100 flex items-center justify-center text-slate-400 hover:text-slate-600 text-sm cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block mb-1">
                  对方来信:
                </label>
                <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-slate-700 font-sans">
                  {activeModalConv.last_inbound_msg}
                </div>
              </div>

              <div>
                <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block mb-1">
                  当前攻坚轮次与拟发送话术 (含 UTM 归因与 Lead Magnet):
                </label>
                <textarea
                  rows={6}
                  value={customReplyText}
                  onChange={(e) => setCustomReplyText(e.target.value)}
                  className="w-full text-xs bg-slate-50 border border-slate-200 rounded-lg p-3 text-slate-800 leading-relaxed font-sans focus:bg-white focus:outline-indigo-500"
                />
              </div>

              <div className="bg-amber-50 border border-amber-200 rounded-xl p-2.5 text-[11px] text-amber-800 leading-relaxed">
                💡 <strong>发信建议</strong>: 点击「官方发信窗口直达」将自动复制文案并在新标签页打开 Reddit/𝕏 官方页面预填，既能完成精准获客，又享有 100% 官方环境防封保障。
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
              <button
                onClick={() => setActiveModalConv(null)}
                className="px-3.5 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-lg font-semibold cursor-pointer"
              >
                取消
              </button>
              <a
                href={getComposeUrl(activeModalConv, customReplyText)}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => {
                  copyText('modal_msg', customReplyText);
                  handleSendReply(activeModalConv.id, customReplyText);
                }}
                className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-lg text-xs transition cursor-pointer flex items-center gap-1 shadow-xs"
              >
                🚀 官方发信窗口直达 ↗
              </a>
              <button
                onClick={() => handleSendReply(activeModalConv.id, customReplyText)}
                disabled={replyingId === activeModalConv.id}
                className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-lg text-xs transition cursor-pointer shadow-xs disabled:opacity-50"
              >
                {replyingId === activeModalConv.id ? '正在处理...' : '确认发送'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
