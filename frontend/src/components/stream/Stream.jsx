import { useState, useCallback } from 'react';
import { useApp } from '../../context.jsx';
import { apiFetch } from '../../api.js';
import LiveFeed from './LiveFeed.jsx';
import HistoryFeed from './HistoryFeed.jsx';
import BoardFeed from './BoardFeed.jsx';
import ReplyPanel from './ReplyPanel.jsx';
import ThreadPanel from './ThreadPanel.jsx';

export default function Stream({ newHit, wsHitCount }) {
  const { cfg, setHits, hitIds, listenerStatus, addToast } = useApp();
  const [viewMode, setViewMode] = useState('live');
  const [platformFilter, setPlatformFilter] = useState(null);
  const [streamFilter, setStreamFilter] = useState(null);
  const [kindFilter, setKindFilter] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [batchDrafting, setBatchDrafting] = useState(false);
  const [autopilotEnabled, setAutopilotEnabled] = useState(false);
  const [togglingAutopilot, setTogglingAutopilot] = useState(false);
  const [runningAutopilotAll, setRunningAutopilotAll] = useState(false);
  const [showAiDashboard, setShowAiDashboard] = useState(false);
  const [aiHealth, setAiHealth] = useState(null);
  const [loadingHealth, setLoadingHealth] = useState(false);

  const fetchAiHealth = useCallback(async () => {
    setLoadingHealth(true);
    try {
      const res = await apiFetch('/api/analytics/ai_health');
      if (res && res.ok) setAiHealth(res);
    } catch {}
    finally { setLoadingHealth(false); }
  }, []);

  function handleToggleAiDashboard() {
    const next = !showAiDashboard;
    setShowAiDashboard(next);
    if (next) fetchAiHealth();
  }

  // Check initial autopilot status
  useState(() => {
    apiFetch('/api/config/autopilot').then(res => {
      if (res && res.enabled !== undefined) setAutopilotEnabled(res.enabled);
    }).catch(() => {});
  });

  async function handleToggleAutopilot() {
    setTogglingAutopilot(true);
    try {
      const next = !autopilotEnabled;
      const res = await apiFetch('/api/config/autopilot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: next }),
      });
      if (res.ok) {
        setAutopilotEnabled(next);
        addToast(next ? '⚡ 已开启 AI 全自动托管模式！新线索将全自动初筛、写草稿、预审并排期发射。' : '⚪ 已切换为半自动模式，草稿需人工排期或发射。', next ? 'green' : 'blue');
      } else {
        addToast(`切换失败: ${res.error}`, 'red');
      }
    } catch (e) {
      addToast(`网络异常: ${e}`, 'red');
    } finally {
      setTogglingAutopilot(false);
    }
  }

  async function handleOneClickAutopilotAll() {
    setRunningAutopilotAll(true);
    try {
      const res = await apiFetch('/api/hits/one_click_autopilot', { method: 'POST' });
      if (res.ok) {
        addToast(`🚀 一键智投完成！已为 ${res.processed_count} 条线索生成草稿，${res.enqueued_count} 条通过预审安全排入队列！`, 'green');
        const d = await apiFetch('/api/hits?limit=25');
        if (d.hits) setHits(d.hits);
      } else {
        addToast(`一键智投失败: ${res.error}`, 'red');
      }
    } catch (e) {
      addToast(`请求异常: ${e}`, 'red');
    } finally {
      setRunningAutopilotAll(false);
    }
  }

  async function handleBatchDraft() {
    setBatchDrafting(true);
    try {
      const res = await apiFetch('/api/hits/batch_auto_draft', { method: 'POST' });
      if (res.ok) {
        addToast(`✅ 成功为 ${res.generated_count} 条线索生成 AI 融合草稿！`, 'green');
        const d = await apiFetch('/api/hits?limit=25');
        if (d.hits) setHits(d.hits);
      } else {
        addToast(`批量生成失败: ${res.error}`, 'red');
      }
    } catch (e) {
      addToast(`请求异常: ${e}`, 'red');
    } finally {
      setBatchDrafting(false);
    }
  }
  const [autoFilter, setAutoFilter] = useState(() => {
    try { return localStorage.getItem('rs-auto-ai') === 'true'; } catch { return true; }
  });
  const [hideRejected, setHideRejected] = useState(() => {
    try { return localStorage.getItem('rs-hide-rejected') === 'true'; } catch { return false; }
  });
  const [hitCount, setHitCount] = useState(0);

  const toggleAutoFilter = (val) => {
    setAutoFilter(val);
    try { localStorage.setItem('rs-auto-ai', val ? 'true' : 'false'); } catch {}
  };

  const toggleHideRejected = (val) => {
    setHideRejected(val);
    try { localStorage.setItem('rs-hide-rejected', val ? 'true' : 'false'); } catch {}
  };

  // Panels
  const [replyHit, setReplyHit] = useState(null);
  const [threadState, setThreadState] = useState(null);

  const listeners = cfg.listeners || [];

  function clearHits() {
    if (!confirm('Clear live feed? (Saved history in DB is not affected)')) return;
    setHits([]);
    hitIds.current.clear();
    setHitCount(0);
  }

  function exportCSV() {
    // We need hits from context
    // This is handled in LiveFeed via the hits from context
    import('../../context.jsx').then(({ useApp: _ }) => {});
  }

  function handleExportCSV() {
    // Access hits via a ref or re-implement here
    // Using a simple approach: we'll use the global approach below
    const { hits } = window.__rsApp || {};
    if (!hits) return;
    const rows = [['ts', 'listener', 'kind', 'subreddit', 'author', 'match', 'title', 'url', 'excerpt', 'filter_passed']];
    for (const h of hits) {
      rows.push([
        new Date((h.ts || 0) * 1000).toISOString(),
        h.listener_name || '',
        h.kind || '',
        h.subreddit || '',
        h.author || '',
        h.match || '',
        h.title || '',
        h.url || '',
        h.excerpt || '',
        h.filter_result ? (h.filter_result.passed ? 'yes' : 'no') : '',
      ]);
    }
    const csv = rows.map(r => r.map(c => `"${String(c ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
    Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(new Blob([csv], { type: 'text/csv' })),
      download: `redsignal_live_${Date.now()}.csv`,
    }).click();
  }

  return (
    <div id="p-stream" className="h-full flex flex-col">
      {/* One-Click AI Autopilot Control Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white px-5 py-3 flex items-center justify-between flex-wrap gap-3 border-b border-indigo-900/50 shadow-xs flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-indigo-500/20 border border-indigo-400/30 flex items-center justify-center text-xl shadow-inner">
            ⚡
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold tracking-tight text-white flex items-center gap-2">
                AI 全托管智投系统 (Autopilot)
                <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full border transition-all ${
                  autopilotEnabled
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-xs'
                    : 'bg-slate-800 text-slate-400 border-slate-700'
                }`}>
                  {autopilotEnabled ? '🟢 24H 全自动托管中' : '⚪ 半自动待命中'}
                </span>
              </span>
            </div>
            <p className="text-xs text-slate-300 mt-0.5">
              一键接管：后台自动捕获新帖 → AI 意向初筛 → 机会打分 → 撰写融合草稿 → 预审员防封门禁 → 自动排期发射，完全无人值守。
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={handleToggleAutopilot}
            disabled={togglingAutopilot}
            className={`text-xs px-3.5 py-1.5 rounded-xl font-bold transition-all flex items-center gap-1.5 cursor-pointer shadow-xs ${
              autopilotEnabled
                ? 'bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/40'
                : 'bg-emerald-500 hover:bg-emerald-600 text-white'
            }`}
          >
            {togglingAutopilot ? <span className="spin">⟳</span> : (autopilotEnabled ? '⏸ 暂停自动托管' : '⚡ 开启全托管模式')}
          </button>

          <button
            onClick={handleToggleAiDashboard}
            className={`text-xs px-3 py-1.5 rounded-xl font-bold transition-all flex items-center gap-1.5 cursor-pointer border ${
              showAiDashboard
                ? 'bg-indigo-600 text-white border-indigo-400 shadow-xs'
                : 'bg-indigo-950/70 hover:bg-indigo-900/80 text-indigo-200 border-indigo-700/60'
            }`}
            title="查看 AI 目标时区调度、自适应专家人设分布与自愈防封规约"
          >
            🧠 {showAiDashboard ? '收起智脑看板' : 'AI 自愈中枢'}
          </button>

          <button
            onClick={handleOneClickAutopilotAll}
            disabled={runningAutopilotAll}
            className="text-xs px-4 py-1.5 bg-gradient-to-r from-amber-500 via-orange-500 to-amber-600 hover:from-amber-600 hover:to-orange-700 text-white font-bold rounded-xl transition-all shadow-sm flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            title="一键将当前待处理线索批量生成草稿、通过防封预审并直接推入排期队列"
          >
            {runningAutopilotAll ? <span className="spin">⟳</span> : '🚀'}
            {runningAutopilotAll ? '正在全速智投…' : '一键智投当前线索'}
          </button>
        </div>
      </div>

      {/* AI Health & Self-Healing Hub Panel */}
      {showAiDashboard && (
        <div className="bg-slate-900 border-b border-indigo-900/60 p-5 text-slate-200 flex-shrink-0 animate-fadeIn">
          <div className="max-w-7xl mx-auto space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-white flex items-center gap-2">
                  🧠 AI 决策与自愈防封知识中枢 (AI Self-Healing Hub)
                </span>
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                  动态人设 · 智能错峰 · 闭环自愈
                </span>
              </div>
              <button
                onClick={fetchAiHealth}
                disabled={loadingHealth}
                className="text-xs text-indigo-300 hover:text-white flex items-center gap-1 transition-colors cursor-pointer"
              >
                {loadingHealth ? <span className="spin">⟳</span> : '⟳'} 刷新指标
              </button>
            </div>

            {/* Metrics Grid */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
              {/* Chrono Peak */}
              <div className="bg-slate-800/80 border border-slate-700/80 rounded-xl p-3.5 space-y-1.5 shadow-sm">
                <div className="text-slate-400 font-medium flex items-center justify-between">
                  <span>{aiHealth?.chrono?.tz_abbr ? `${aiHealth.chrono.tz_abbr} 营销时区` : '目标营销时区'}</span>
                  <span className={`px-1.5 py-0.2 rounded-full font-bold text-[10px] ${
                    aiHealth?.chrono?.is_peak ? 'bg-emerald-500/20 text-emerald-300' : 'bg-indigo-500/20 text-indigo-300'
                  }`}>
                    {aiHealth?.chrono?.is_peak ? '🔥 活跃期' : '🌙 静音期'}
                  </span>
                </div>
                <div className="text-lg font-bold text-white font-mono">{aiHealth?.chrono?.current_est_time || '--:--'}</div>
                <div className="text-[11px] text-slate-300 leading-snug">{aiHealth?.chrono?.policy || '计算中…'}</div>
              </div>

              {/* Safety Audit Pass Rate */}
              <div className="bg-slate-800/80 border border-slate-700/80 rounded-xl p-3.5 space-y-1.5 shadow-sm">
                <div className="text-slate-400 font-medium flex items-center justify-between">
                  <span>AI 预审员防封门禁</span>
                  <span className="text-emerald-400 font-bold">🛡️ LLM-as-Judge</span>
                </div>
                <div className="text-lg font-bold text-emerald-400 font-mono">
                  {aiHealth?.safety_audit?.pass_rate !== undefined ? `${aiHealth.safety_audit.pass_rate}%` : '100%'}
                </div>
                <div className="text-[11px] text-slate-400">
                  通过 {aiHealth?.safety_audit?.passed_count || 0} / 共初审 {aiHealth?.safety_audit?.total_audited || 0} 条
                </div>
              </div>

              {/* AutoMod Visibility Penetration */}
              <div className="bg-slate-800/80 border border-slate-700/80 rounded-xl p-3.5 space-y-1.5 shadow-sm">
                <div className="text-slate-400 font-medium flex items-center justify-between">
                  <span>AutoMod 穿透可见率</span>
                  <span className="text-teal-400 font-bold">👁️ 游客视角</span>
                </div>
                <div className="text-lg font-bold text-teal-400 font-mono">
                  {aiHealth?.automod_penetration?.penetration_rate !== undefined ? `${aiHealth.automod_penetration.penetration_rate}%` : '100%'}
                </div>
                <div className="text-[11px] text-slate-400">
                  存活 {aiHealth?.automod_penetration?.visible_count || 0} / 已发 {aiHealth?.automod_penetration?.total_submitted || 0} 条
                </div>
              </div>

              {/* Self-Healing Knowledge Rules Count */}
              <div className="bg-slate-800/80 border border-slate-700/80 rounded-xl p-3.5 space-y-1.5 shadow-sm">
                <div className="text-slate-400 font-medium flex items-center justify-between">
                  <span>自愈规则库沉淀</span>
                  <span className="text-amber-400 font-bold">📚 记忆避坑</span>
                </div>
                <div className="text-lg font-bold text-amber-400 font-mono">
                  {aiHealth?.self_healing_rules_count || 3} 条已沉淀规则
                </div>
                <div className="text-[11px] text-slate-400">
                  针对外链拦截自动采用 Brand Search 规避
                </div>
              </div>
            </div>

            {/* Personas & Self-healing Rules details */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
              {/* Dynamic Personas */}
              <div className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-3 space-y-2">
                <div className="text-xs font-bold text-white flex items-center gap-1.5">
                  <span>🎭 自适应专家人设分布</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {(() => {
                    const activeLst = streamFilter ? (cfg?.listeners || []).find(l => l.id === streamFilter) : (cfg?.listeners || [])[0];
                    const listenerPersonas = (activeLst?.personas && activeLst.personas.length > 0)
                      ? activeLst.personas
                      : [
                          { label: '🎯 领域专家', desc: '客观技术诊断、核心参数分析', key: 'expert' },
                          { label: '⚡ 极客先锋', desc: '深度极客调校、性能指标', key: 'modder' },
                          { label: '🤝 社区老友', desc: '日常经验分享、痛点答疑', key: 'community' },
                          { label: '📜 合规专家', desc: '标准法规、权威数据出处', key: 'compliance' }
                        ];
                    return listenerPersonas.map(p => {
                      const label = p.label || p.key || p.name;
                      const count = aiHealth?.personas?.[label] || aiHealth?.personas?.[p.key] || 0;
                      return (
                        <div key={p.key || label} className="bg-slate-900/80 border border-slate-800 rounded-lg p-2 flex flex-col justify-between">
                          <div className="font-semibold text-slate-200 flex items-center justify-between">
                            <span>{label}</span>
                            <span className="text-indigo-400 font-bold font-mono">
                              {count}
                            </span>
                          </div>
                          <div className="text-[10px] text-slate-400 mt-1 line-clamp-1">{p.desc || p.tone || '自适应专家策略'}</div>
                        </div>
                      );
                    });
                  })()}
                </div>
              </div>

              {/* Active Self-Healing Rules */}
              <div className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-3 space-y-2">
                <div className="text-xs font-bold text-white flex items-center justify-between">
                  <span>🛡️ 最新自愈防封学习规约 (Auto-Learned Rules)</span>
                  <span className="text-[10px] text-emerald-400">已自动注入 Prompt 负面约束</span>
                </div>
                <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
                  {(aiHealth?.self_healing_rules || []).map(rule => (
                    <div key={rule.id} className="bg-slate-900/80 border border-slate-800 rounded-lg p-2 text-xs">
                      <div className="flex items-center justify-between gap-1">
                        <span className="font-semibold text-amber-300">
                          {rule.subreddit ? `r/${rule.subreddit}` : rule.platform} · {rule.title}
                        </span>
                        <span className="text-[10px] text-slate-500">{rule.created_at?.slice(5, 10)}</span>
                      </div>
                      <div className="text-[11px] text-slate-300 mt-0.5">{rule.action_taken}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Toolbar row 1 */}
      <div className="bg-white border-b border-slate-100 px-5 py-2.5 flex items-center gap-3 flex-wrap flex-shrink-0">
        {/* Platform filter buttons */}
        <div className="flex items-center bg-slate-100 rounded-lg p-0.5 flex-shrink-0">
          {[
            { key: null, label: '全部平台', id: 'all_plat' },
            { key: 'reddit', label: 'Reddit', id: 'reddit_plat' },
            { key: 'x', label: '𝕏', id: 'x_plat' },
            { key: 'forum', label: '🌐 技术论坛', id: 'forum_plat' },
          ].map(({ key, label, id }) => (
            <button
              key={id}
              onClick={() => setPlatformFilter(key)}
              className={`view-btn text-xs px-2.5 py-1 ${platformFilter === key ? 'active' : ''}`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Listener pills */}
        <div className="flex gap-2 flex-wrap items-center">
          <button
            className={`pill ${streamFilter === null ? 'active' : ''}`}
            onClick={() => setStreamFilter(null)}
          >
            All
          </button>
          {listeners.map(l => (
            <button
              key={l.id}
              className={`pill flex items-center ${streamFilter === l.id ? 'active' : ''}`}
              onClick={() => setStreamFilter(streamFilter === l.id ? null : l.id)}
            >
              {l.name}
              <span
                className={`${listenerStatus[l.id] ? 'bg-emerald-400' : 'bg-slate-300'} w-1.5 h-1.5 rounded-full ml-1.5 flex-shrink-0`}
              />
            </button>
          ))}
        </div>

        {/* Kind filter */}
        <div className="flex items-center bg-slate-100 rounded-lg p-0.5 flex-shrink-0">
          {[
            { key: null, label: 'All', id: 'all' },
            { key: 'post', label: 'Posts', id: 'post' },
            { key: 'comment', label: 'Comments', id: 'comment' },
            { key: 'follow_up', label: '💬 追评/追问', id: 'follow_up' },
          ].map(({ key, label, id }) => (
            <button
              key={id}
              onClick={() => setKindFilter(key)}
              className={`view-btn text-xs px-2.5 py-1 ${kindFilter === key ? 'active' : ''}`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Status filter */}
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="text-xs border border-slate-200 bg-white rounded-lg px-2 py-1.5 text-slate-600 outline-none cursor-pointer flex-shrink-0"
        >
          <option value="">Any status</option>
          <option value="new">New</option>
          <option value="reviewing">Reviewing</option>
          <option value="replied">Replied</option>
          <option value="converted">Converted</option>
          <option value="skipped">Skipped</option>
        </select>

        <div className="ml-auto flex items-center gap-4 flex-shrink-0">
          {/* View mode toggle */}
          <div className="flex items-center bg-slate-100 rounded-xl p-0.5">
            {[
              { mode: 'live', label: '● Live' },
              { mode: 'history', label: 'History' },
              { mode: 'board', label: 'Board' },
            ].map(({ mode, label }) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={`view-btn ${viewMode === mode ? 'active' : ''}`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Live controls */}
          {viewMode === 'live' && (
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={autoFilter}
                    onChange={e => toggleAutoFilter(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-9 h-5 bg-slate-200 rounded-full peer peer-checked:bg-violet-500 transition-colors"></div>
                  <div className="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform peer-checked:translate-x-4"></div>
                </div>
                <span className="text-sm text-slate-600 font-medium flex items-center gap-1.5">
                  Auto AI
                  {autopilotEnabled && (
                    <span className="text-[10px] font-normal text-emerald-600 bg-emerald-50 px-1.5 py-0.2 rounded border border-emerald-200" title="顶部全自动托管已在服务器端自动执行意向分级、价值打分、写草稿与合规排期">
                      后台已接管
                    </span>
                  )}
                </span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={hideRejected}
                    onChange={e => toggleHideRejected(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-9 h-5 bg-slate-200 rounded-full peer peer-checked:bg-red-400 transition-colors"></div>
                  <div className="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform peer-checked:translate-x-4"></div>
                </div>
                <span className="text-sm text-slate-600 font-medium">Hide rejected</span>
              </label>
              <button
                onClick={handleBatchDraft}
                disabled={batchDrafting}
                className="text-xs px-2.5 py-1.5 bg-violet-50 hover:bg-violet-100 text-violet-700 font-medium rounded-lg border border-violet-200 transition-colors flex items-center gap-1 cursor-pointer disabled:opacity-50"
                title="为所有尚未生成回复草稿的线索批量生成 AI 独立站植入回复"
              >
                {batchDrafting ? <span className="spin">⟳</span> : '✨'}
                {batchDrafting ? '批量生成中…' : '批量生成草稿'}
              </button>
              <button onClick={clearHits} className="text-sm text-slate-400 hover:text-slate-700 transition-colors">Clear</button>
              <ExportCSVButton />
            </div>
          )}
        </div>
      </div>

      {/* Feeds */}
      {viewMode === 'live' && (
        <LiveFeed
          streamFilter={streamFilter}
          platformFilter={platformFilter}
          kindFilter={kindFilter}
          statusFilter={statusFilter}
          hideRejected={hideRejected}
          autoFilter={autoFilter}
          onOpenReply={setReplyHit}
          onOpenThread={(postId, listenerId, commentId) => setThreadState({ postId, listenerId, commentId })}
          newHit={newHit}
          onHitCountUpdate={setHitCount}
        />
      )}
      {viewMode === 'history' && (
        <HistoryFeed
          onOpenReply={setReplyHit}
          onOpenThread={(postId, listenerId, commentId) => setThreadState({ postId, listenerId, commentId })}
        />
      )}
      {viewMode === 'board' && (
        <div className="flex-1 overflow-x-auto overflow-y-hidden">
          <BoardFeed newHit={newHit} />
        </div>
      )}

      {/* Reply Panel */}
      {replyHit && (
        <ReplyPanel
          hit={replyHit}
          onClose={() => setReplyHit(null)}
          onSaved={() => setReplyHit(null)}
        />
      )}

      {/* Thread Panel */}
      {threadState && (
        <ThreadPanel
          postId={threadState.postId}
          listenerId={threadState.listenerId}
          commentId={threadState.commentId}
          onClose={() => setThreadState(null)}
        />
      )}
    </div>
  );
}

function ExportCSVButton() {
  const { hits } = useApp();
  function exportCSV() {
    const rows = [['ts', 'listener', 'kind', 'subreddit', 'author', 'match', 'title', 'url', 'excerpt', 'filter_passed']];
    for (const h of hits) {
      rows.push([
        new Date((h.ts || 0) * 1000).toISOString(),
        h.listener_name || '',
        h.kind || '',
        h.subreddit || '',
        h.author || '',
        h.match || '',
        h.title || '',
        h.url || '',
        h.excerpt || '',
        h.filter_result ? (h.filter_result.passed ? 'yes' : 'no') : '',
      ]);
    }
    const csv = rows.map(r => r.map(c => `"${String(c ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
    Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(new Blob([csv], { type: 'text/csv' })),
      download: `redsignal_live_${Date.now()}.csv`,
    }).click();
  }
  return (
    <button onClick={exportCSV} className="text-sm text-slate-400 hover:text-slate-700 transition-colors">
      ↓ CSV
    </button>
  );
}
