import { useState, useEffect } from 'react';
import { apiFetch } from '../../api.js';
import { timeAgo } from '../../utils.js';

export default function BarnacleView() {
  const [targets, setTargets] = useState([]);
  const [stats, setStats] = useState({ total: 0, active: 0, archived: 0, drafted: 0, submitted: 0 });
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [scanKeyword, setScanKeyword] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [addUrl, setAddUrl] = useState('');
  const [addKeyword, setAddKeyword] = useState('');
  const [addNotes, setAddNotes] = useState('');
  const [addingTarget, setAddingTarget] = useState(false);
  const [filter, setFilter] = useState('all'); // all, active, drafted, submitted, archived
  const [draftingId, setDraftingId] = useState(null);
  const [copiedId, setCopiedId] = useState(null);
  const [editingDraftId, setEditingDraftId] = useState(null);
  const [editingText, setEditingText] = useState('');
  const [auditing, setAuditing] = useState(false);
  const [auditSummary, setAuditSummary] = useState(null);

  useEffect(() => {
    loadTargets();
  }, []);

  async function handleAudit(fast = false) {
    setAuditing(true);
    try {
      const res = await apiFetch('/api/barnacle/audit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'all', limit: 25, fast })
      });
      if (res && res.ok) {
        setAuditSummary(res);
        await loadTargets();
        const liveCnt = (res.targets || []).filter(t => t.status_label === 'LIVE').length;
        alert(`✅ 巡检完成！已审计 ${(res.replies || []).length} 条回帖与 ${(res.targets || []).length} 个目标帖。\n存活良好: ${liveCnt} 个。`);
      } else {
        alert(`巡检失败: ${res?.error || '未知错误'}`);
      }
    } catch (e) {
      alert(`请求异常: ${e}`);
    } finally {
      setAuditing(false);
    }
  }

  async function loadTargets() {
    setLoading(true);
    try {
      const res = await apiFetch('/api/barnacle/targets');
      if (res && res.ok) {
        setTargets(res.targets || []);
        setStats(res.stats || { total: 0, active: 0, archived: 0, drafted: 0, submitted: 0 });
      }
    } catch (e) {
      console.error('Failed to load barnacle targets', e);
    } finally {
      setLoading(false);
    }
  }

  async function handleScan(e) {
    if (e) e.preventDefault();
    if (!scanKeyword.trim()) return;
    setScanning(true);
    try {
      const res = await apiFetch('/api/barnacle/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyword: scanKeyword.trim(), max_results: 12 })
      });
      if (res && res.ok) {
        await loadTargets();
        alert(`🎉 扫描完成！探明并入库 ${res.count || 0} 个搜索首页讨论帖。`);
      } else {
        alert(`扫描失败: ${res?.error || '未知错误'}`);
      }
    } catch (e) {
      alert(`请求异常: ${e}`);
    } finally {
      setScanning(false);
    }
  }

  async function handleAddManual(e) {
    if (e) e.preventDefault();
    if (!addUrl.trim() || !addKeyword.trim()) {
      alert('请填写帖子 URL 和关联搜索关键词');
      return;
    }
    setAddingTarget(true);
    try {
      const res = await apiFetch('/api/barnacle/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: addUrl.trim(), keyword: addKeyword.trim(), notes: addNotes.trim() })
      });
      if (res && res.ok) {
        setShowAddModal(false);
        setAddUrl('');
        setAddKeyword('');
        setAddNotes('');
        await loadTargets();
      } else {
        alert(`添加失败: ${res?.error || '未知错误'}`);
      }
    } catch (e) {
      alert(`请求失败: ${e}`);
    } finally {
      setAddingTarget(false);
    }
  }

  async function handleGenerateDraft(targetId, customInstruction = '') {
    setDraftingId(targetId);
    try {
      const res = await apiFetch(`/api/barnacle/targets/${targetId}/draft`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ custom_instruction: customInstruction })
      });
      if (res && res.ok) {
        setTargets(prev => prev.map(t => t.id === targetId ? { ...t, evergreen_draft: res.draft, status: 'drafted' } : t));
        setStats(prev => ({ ...prev, drafted: prev.drafted + 1 }));
      } else {
        alert(`生成失败: ${res?.error || '请检查 Vault 中的 AI 凭据'}`);
      }
    } catch (e) {
      alert(`请求失败: ${e}`);
    } finally {
      setDraftingId(null);
    }
  }

  async function handleUpdateStatus(targetId, newStatus) {
    try {
      const res = await apiFetch(`/api/barnacle/targets/${targetId}/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      });
      if (res && res.ok) {
        setTargets(prev => prev.map(t => t.id === targetId ? { ...t, status: newStatus } : t));
        loadTargets();
      }
    } catch (e) {
      alert(`更新状态失败: ${e}`);
    }
  }

  async function handleSaveDraft(targetId) {
    try {
      const res = await apiFetch(`/api/barnacle/targets/${targetId}/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ evergreen_draft: editingText })
      });
      if (res && res.ok) {
        setTargets(prev => prev.map(t => t.id === targetId ? { ...t, evergreen_draft: editingText } : t));
        setEditingDraftId(null);
      }
    } catch (e) {
      alert(`保存草稿失败: ${e}`);
    }
  }

  async function handleDelete(targetId) {
    if (!confirm('确定要移除此藤壶目标吗？')) return;
    try {
      const res = await apiFetch(`/api/barnacle/targets/${targetId}`, { method: 'DELETE' });
      if (res && res.ok) {
        setTargets(prev => prev.filter(t => t.id !== targetId));
        loadTargets();
      }
    } catch (e) {
      alert(`删除失败: ${e}`);
    }
  }

  function copyToClipboard(id, text) {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2500);
  }

  const filteredTargets = targets.filter(t => {
    if (filter === 'active') return !t.is_archived;
    if (filter === 'archived') return t.is_archived;
    if (filter === 'drafted') return t.status === 'drafted';
    if (filter === 'submitted') return t.status === 'submitted';
    return true;
  });

  return (
    <div className="flex flex-col h-full bg-slate-50/60 overflow-hidden">
      {/* ── Top Header & Mission Statement ─────────────────────────────────────── */}
      <div className="bg-white border-b border-slate-200/80 px-6 py-4 flex-shrink-0 shadow-2xs">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-amber-600 to-indigo-600 flex items-center justify-center text-white text-xl shadow-sm">
              🪨
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-lg font-bold text-slate-900 tracking-tight">藤壶 SEO 长效截流 (Barnacle SEO)</h1>
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200/70">
                  Google Page 1 不动产资产
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                锁定常年稳居 Google 首页前列的高流量 Reddit/论坛讨论帖，留下权威常青树答案与转化钩子，持续收割被动搜索流量。
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => handleAudit(false)}
              disabled={auditing}
              className="px-3.5 py-2 text-xs font-semibold text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg hover:bg-emerald-100 transition shadow-2xs flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              title="巡检已发回帖与目标帖的公开存活度、AutoMod 折叠与锁定状态"
            >
              {auditing ? (
                <>
                  <span className="spin">⟳</span>
                  <span>正在巡检中...</span>
                </>
              ) : (
                <>
                  <span>🔍</span>
                  <span>存活与折叠巡检 (Audit)</span>
                </>
              )}
            </button>
            <button
              onClick={() => setShowAddModal(true)}
              className="px-3.5 py-2 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition shadow-2xs flex items-center gap-1.5 cursor-pointer"
            >
              <span>➕ 手动录入目标帖</span>
            </button>
            <button
              onClick={loadTargets}
              className="p-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition cursor-pointer"
              title="刷新数据"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
              </svg>
            </button>
          </div>
        </div>

        {/* ── KPI Metrics Cards ─────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mt-4 pt-3 border-t border-slate-100">
          <div className="bg-slate-50 rounded-xl p-3 border border-slate-150">
            <div className="text-[11px] text-slate-500 font-medium">🎯 探明总目标帖</div>
            <div className="text-xl font-bold text-slate-900 mt-1">{stats.total}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">已收录搜索讨论楼</div>
          </div>
          <div className="bg-emerald-50/60 rounded-xl p-3 border border-emerald-200/60">
            <div className="text-[11px] text-emerald-700 font-medium">💎 活跃可回复金矿</div>
            <div className="text-xl font-bold text-emerald-800 mt-1">{stats.active}</div>
            <div className="text-[10px] text-emerald-600 mt-0.5">未归档，立即可抢占</div>
          </div>
          <div className="bg-amber-50/60 rounded-xl p-3 border border-amber-200/60">
            <div className="text-[11px] text-amber-700 font-medium">📝 常青树草稿就绪</div>
            <div className="text-xl font-bold text-amber-800 mt-1">{stats.drafted}</div>
            <div className="text-[10px] text-amber-600 mt-0.5">深度权威答案待发射</div>
          </div>
          <div className="bg-indigo-50/60 rounded-xl p-3 border border-indigo-200/60">
            <div className="text-[11px] text-indigo-700 font-medium">🚀 已成功截流占位</div>
            <div className="text-xl font-bold text-indigo-800 mt-1">{stats.submitted}</div>
            <div className="text-[10px] text-indigo-600 mt-0.5">常青树评论持续吸粉</div>
          </div>
          <div className="bg-slate-50 rounded-xl p-3 border border-slate-150">
            <div className="text-[11px] text-slate-500 font-medium">🗄️ 超期锁定归档</div>
            <div className="text-xl font-bold text-slate-600 mt-1">{stats.archived}</div>
            <div className="text-[10px] text-slate-400 mt-0.5">已锁定禁回（仅做参考）</div>
          </div>
        </div>

        {/* ── Keyword Scout Console ────────────────────────────────────────────── */}
        <form onSubmit={handleScan} className="mt-4 flex gap-2">
          <div className="relative flex-1">
            <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-sm">🔎</span>
            <input
              type="text"
              value={scanKeyword}
              onChange={(e) => setScanKeyword(e.target.value)}
              placeholder="输入核心出海搜索词（如：best golf cart enclosures reddit、evolution d5 problems、stable vpn for china）..."
              className="w-full pl-9 pr-4 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg outline-none focus:border-indigo-500 focus:bg-white transition"
            />
          </div>
          <button
            type="submit"
            disabled={scanning || !scanKeyword.trim()}
            className="px-5 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 rounded-lg transition flex items-center gap-1.5 shadow-sm"
          >
            {scanning ? (
              <>
                <svg className="animate-spin h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                </svg>
                <span>正在深度探测 SERP...</span>
              </>
            ) : (
              <>
                <span>🚀 探测 Google 首页讨论贴</span>
              </>
            )}
          </button>
        </form>
      </div>

      {/* ── Sub Navigation Tabs ────────────────────────────────────────────────── */}
      <div className="px-6 py-2.5 bg-slate-100/80 border-b border-slate-200 flex items-center justify-between flex-shrink-0">
        <div className="flex gap-1">
          {[
            { key: 'all', label: `全部 (${targets.length})` },
            { key: 'active', label: `💎 活跃金矿 (${stats.active})` },
            { key: 'drafted', label: `📝 草稿就绪 (${stats.drafted})` },
            { key: 'submitted', label: `🚀 已占位 (${stats.submitted})` },
            { key: 'archived', label: `🗄️ 已归档 (${stats.archived})` }
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setFilter(tab.key)}
              className={`px-3 py-1 text-xs font-medium rounded-lg transition ${
                filter === tab.key
                  ? 'bg-white text-indigo-700 shadow-2xs font-semibold border border-slate-200/80'
                  : 'text-slate-600 hover:bg-slate-200/60'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="text-[11px] text-slate-500">
          Showing {filteredTargets.length} targets
        </div>
      </div>

      {/* ── Target Cards Deck ─────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {loading ? (
          <div className="text-center py-20 text-slate-400 text-xs">加载藤壶 SEO 目标矩阵中...</div>
        ) : filteredTargets.length === 0 ? (
          <div className="text-center py-20 bg-white rounded-2xl border border-dashed border-slate-300 p-8">
            <div className="text-3xl mb-2">🪨</div>
            <div className="text-sm font-semibold text-slate-800">暂无符合条件的藤壶目标</div>
            <div className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
              在上方控制台输入你在 Google 最想排名的出海产品词，点击「探测 Google 首页讨论贴」，系统将自动帮你找出在 Google 首页排名的活跃讨论帖！
            </div>
          </div>
        ) : (
          filteredTargets.map(t => {
            const isArchived = Boolean(t.is_archived);
            const isDrafted = t.status === 'drafted';
            const isSubmitted = t.status === 'submitted';
            const hasDraft = Boolean(t.evergreen_draft);
            const isEditing = editingDraftId === t.id;

            return (
              <div
                key={t.id}
                className={`bg-white rounded-xl border transition shadow-2xs hover:shadow-xs p-5 ${
                  isSubmitted ? 'border-indigo-200 bg-indigo-50/10' : (isArchived ? 'border-slate-200 opacity-80' : 'border-slate-200/90')
                }`}
              >
                {/* Header row */}
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1.5">
                      {t.google_rank > 0 ? (
                        <span className="text-[11px] font-bold px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-200/80 flex items-center gap-1">
                          🏆 SERP Rank #{t.google_rank}
                        </span>
                      ) : (
                        <span className="text-[11px] font-medium px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 border border-slate-200 flex items-center gap-1">
                          💬 站内高优 (非SERP)
                        </span>
                      )}
                      <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 uppercase">
                        {t.platform || 'reddit'}
                      </span>
                      <span className="text-[11px] font-medium px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700">
                        🔍 搜索词: {t.keyword}
                      </span>

                      {t.status_label ? (
                        <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-md border ${
                          t.status_label === 'LIVE'
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : t.status_label === 'LOCKED'
                            ? 'bg-amber-50 text-amber-700 border-amber-200'
                            : t.status_label === 'REMOVED'
                            ? 'bg-red-50 text-red-700 border-red-200'
                            : 'bg-slate-100 text-slate-500 border-slate-200'
                        }`}>
                          {t.status_label === 'LIVE' && '🟢 存活良好 (Live)'}
                          {t.status_label === 'LOCKED' && '🔒 版主锁定 (Locked)'}
                          {t.status_label === 'REMOVED' && '⚠️ 疑似折叠/已删 (Removed)'}
                          {t.status_label === 'ARCHIVED' && '📦 超期归档 (Archived)'}
                        </span>
                      ) : isArchived ? (
                        <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-slate-100 text-slate-500 border border-slate-200">
                          🗄️ 已归档锁定 (禁止新回复)
                        </span>
                      ) : (
                        <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200">
                          💎 开放回复中 (高价值金矿)
                        </span>
                      )}

                      {isSubmitted && (
                        <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-purple-50 text-purple-700 border border-purple-200">
                          🚀 已占位截流
                        </span>
                      )}
                    </div>

                    <h2 className="text-sm font-bold text-slate-900 hover:text-indigo-600 transition">
                      <a href={t.target_url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5">
                        <span>{t.post_title || t.target_url}</span>
                        <span className="text-slate-400 text-xs font-normal">↗</span>
                      </a>
                    </h2>

                    {t.search_snippet && (
                      <p className="text-xs text-slate-500 mt-1 line-clamp-2 italic">
                        "{t.search_snippet}"
                      </p>
                    )}

                    <div className="flex items-center gap-3 text-[11px] text-slate-400 mt-2">
                      {t.author && <span>作者: u/{t.author}</span>}
                      {t.post_created_at > 0 && <span>发帖时间: {timeAgo(t.post_created_at)}</span>}
                      <span>意向潜力分: <strong className="text-slate-700">{t.opportunity_score}</strong>/100</span>
                      {t.notes && <span className="text-indigo-600">备注: {t.notes}</span>}
                    </div>
                  </div>

                  {/* Actions right */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={() => handleGenerateDraft(t.id)}
                      disabled={draftingId === t.id}
                      className="px-3 py-1.5 text-xs font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 rounded-lg transition disabled:opacity-50 flex items-center gap-1"
                    >
                      {draftingId === t.id ? (
                        <span>✨ AI 雕琢中...</span>
                      ) : (
                        <span>{hasDraft ? '↺ 重写常青树草稿' : '✨ AI 雕琢常青树草稿'}</span>
                      )}
                    </button>
                    <button
                      onClick={() => handleDelete(t.id)}
                      className="p-1.5 text-slate-400 hover:text-red-600 rounded-lg hover:bg-red-50 transition"
                      title="移除此目标"
                    >
                      🗑️
                    </button>
                  </div>
                </div>

                {/* ── Evergreen Reply Section ────────────────────────────────────────── */}
                {hasDraft && (
                  <div className="mt-3.5 pt-3.5 border-t border-slate-150">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2 text-xs font-bold text-slate-700">
                        <span>📄 常青树权威方案 (针对 Google 搜索客流)</span>
                        <span className="text-[10px] font-normal px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
                          已植入未完待续转化钩子
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {isEditing ? (
                          <>
                            <button
                              onClick={() => handleSaveDraft(t.id)}
                              className="px-2.5 py-1 text-xs font-medium bg-emerald-600 text-white rounded hover:bg-emerald-700 transition"
                            >
                              保存
                            </button>
                            <button
                              onClick={() => setEditingDraftId(null)}
                              className="px-2.5 py-1 text-xs text-slate-500 hover:bg-slate-100 rounded transition"
                            >
                              取消
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() => {
                              setEditingDraftId(t.id);
                              setEditingText(t.evergreen_draft);
                            }}
                            className="text-xs text-slate-500 hover:text-indigo-600 flex items-center gap-1"
                          >
                            <span>✏️ 编辑</span>
                          </button>
                        )}
                        <button
                          onClick={() => copyToClipboard(t.id, t.evergreen_draft)}
                          className="px-2.5 py-1 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded transition flex items-center gap-1"
                        >
                          {copiedId === t.id ? <span className="text-emerald-600 font-bold">✓ 已复制到剪贴板</span> : <span>📋 复制草稿</span>}
                        </button>
                        <a
                          href={t.target_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-2.5 py-1 text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded transition flex items-center gap-1"
                        >
                          <span>🚀 直达原帖抢占楼层 ↗</span>
                        </a>
                        {!isSubmitted && (
                          <button
                            onClick={() => handleUpdateStatus(t.id, 'submitted')}
                            className="px-2.5 py-1 text-xs font-medium text-purple-700 bg-purple-50 hover:bg-purple-100 border border-purple-200 rounded transition"
                          >
                            ✓ 标记已发布
                          </button>
                        )}
                      </div>
                    </div>

                    {isEditing ? (
                      <textarea
                        value={editingText}
                        onChange={(e) => setEditingText(e.target.value)}
                        rows={6}
                        className="w-full text-xs font-mono p-3 bg-slate-50 border border-slate-300 rounded-lg outline-none focus:border-indigo-500 focus:bg-white"
                      />
                    ) : (
                      <div className="bg-slate-50 rounded-lg p-3 text-xs text-slate-800 leading-relaxed font-mono whitespace-pre-wrap border border-slate-200/80 max-h-48 overflow-y-auto">
                        {t.evergreen_draft}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* ── Manual Add Modal ─────────────────────────────────────────────────── */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-md p-6">
            <h3 className="text-base font-bold text-slate-900 mb-1">➕ 手动录入藤壶 SEO 目标帖</h3>
            <p className="text-xs text-slate-500 mb-4">
              如果你在 Google 搜索发现某个 Reddit 或专业论坛帖子排在第 1 页，直接将链接录入，系统将自动检测其活跃度并生成常青树草稿。
            </p>

            <form onSubmit={handleAddManual} className="space-y-3">
              <div>
                <label className="text-[11px] font-bold text-slate-700 block mb-1">帖子完整 URL *</label>
                <input
                  type="url"
                  required
                  value={addUrl}
                  onChange={(e) => setAddUrl(e.target.value)}
                  placeholder="https://www.reddit.com/r/golfcarts/comments/..."
                  className="w-full text-xs px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg outline-none focus:border-indigo-500 focus:bg-white"
                />
              </div>

              <div>
                <label className="text-[11px] font-bold text-slate-700 block mb-1">关联 Google 搜索关键词 *</label>
                <input
                  type="text"
                  required
                  value={addKeyword}
                  onChange={(e) => setAddKeyword(e.target.value)}
                  placeholder="例如：golf cart roof enclosure"
                  className="w-full text-xs px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg outline-none focus:border-indigo-500 focus:bg-white"
                />
              </div>

              <div>
                <label className="text-[11px] font-bold text-slate-700 block mb-1">备忘与转化说明 (可选)</label>
                <input
                  type="text"
                  value={addNotes}
                  onChange={(e) => setAddNotes(e.target.value)}
                  placeholder="例如：Google 排名第 2，大量用户在问顶棚尺寸"
                  className="w-full text-xs px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg outline-none focus:border-indigo-500 focus:bg-white"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={addingTarget}
                  className="px-4 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 rounded-lg transition shadow-sm"
                >
                  {addingTarget ? '正在健康体检...' : '确认录入并体检'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
