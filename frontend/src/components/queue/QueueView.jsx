import { useState, useEffect } from 'react';
import { useApp } from '../../context.jsx';
import { apiFetch } from '../../api.js';
import { timeAgo, getQueueTimeInfo } from '../../utils.js';
import ConversionDmModal from '../common/ConversionDmModal.jsx';

export default function QueueView() {
  const { activeProject } = useApp();
  const [items, setItems] = useState([]);
  const [dailyUsed, setDailyUsed] = useState(0);
  const [pendingCount, setPendingCount] = useState(0);
  const [totalUpvotes, setTotalUpvotes] = useState(0);
  const [totalClicks, setTotalClicks] = useState(0);
  const [totalWinners, setTotalWinners] = useState(0);
  const [statusCounts, setStatusCounts] = useState({ all: 0, scheduled: 0, submitted: 0, failed: 0, cancelled: 0, needs_review: 0 });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [aiHealth, setAiHealth] = useState(null);
  const [showLinksModal, setShowLinksModal] = useState(false);
  const [linksData, setLinksData] = useState(null);
  const [loadingLinks, setLoadingLinks] = useState(false);
  const [copiedCode, setCopiedCode] = useState(null);
  const [switchingQueueId, setSwitchingQueueId] = useState(null);
  const [showQueueDmModal, setShowQueueDmModal] = useState(false);
  const [queueDmData, setQueueDmData] = useState(null);
  const [loadingQueueDm, setLoadingQueueDm] = useState(false);
  const [dmTargetItem, setDmTargetItem] = useState(null);

  async function openQueueDm(item) {
    setDmTargetItem(item);
    setShowQueueDmModal(true);
    setLoadingQueueDm(true);
    try {
      const res = await apiFetch(`/api/queue/${item.id}/dm_pitch`, { method: 'POST' });
      if (res.ok) {
        setQueueDmData(res);
      } else {
        alert(`生成私信话术失败: ${res.error || '未知错误'}`);
      }
    } catch (e) {
      alert(`请求异常: ${e}`);
    } finally {
      setLoadingQueueDm(false);
    }
  }

  async function switchQueueStyle(id, style) {
    setSwitchingQueueId(id);
    try {
      const res = await apiFetch(`/api/queue/${id}/switch_style?style=${style}`, { method: 'POST' });
      if (res.ok) {
        loadQueue();
      } else {
        alert(`切换风格失败: ${res.error || '生成错误'}`);
      }
    } catch (e) {
      alert(`请求异常: ${e}`);
    } finally {
      setSwitchingQueueId(null);
    }
  }

  async function loadQueue() {
    setLoading(true);
    const data = await apiFetch(`/api/queue?status=${filter}&project=${activeProject}`)
      .catch(() => ({ items: [], daily_used: 0, pending_count: 0 }));
    setItems(data.items || []);
    setDailyUsed(data.daily_used || 0);
    setPendingCount(data.pending_count || 0);
    setTotalUpvotes(data.total_upvotes || 0);
    setTotalClicks(data.total_clicks || 0);
    setTotalWinners(data.total_winners || 0);
    if (data.status_counts) {
      setStatusCounts(data.status_counts);
    }
    setLoading(false);

    apiFetch('/api/analytics/ai_health')
      .then(res => { if (res && res.ok) setAiHealth(res); })
      .catch(() => {});
  }

  async function openLinksAnalytics() {
    setShowLinksModal(true);
    setLoadingLinks(true);
    try {
      const res = await apiFetch(`/api/analytics/links`);
      setLinksData(res);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingLinks(false);
    }
  }

  useEffect(() => {
    loadQueue();
    const interval = setInterval(loadQueue, 15000);
    return () => clearInterval(interval);
  }, [filter, activeProject]);

  async function submitNow(id, platform = 'reddit') {
    const pName = (platform === 'x' || platform === 'twitter') ? '𝕏 (Twitter)' : 'Reddit';
    if (!confirm(`确认立即提交这条回复至 ${pName}？`)) return;
    const res = await apiFetch(`/api/queue/${id}/submit_now`, { method: 'POST' });
    if (res.ok) {
      alert(`🚀 提交成功！已发送至 ${pName}。`);
      loadQueue();
    } else {
      alert(`提交失败: ${res.error}`);
      loadQueue();
    }
  }

  async function cancelItem(id) {
    if (!confirm('确认取消此回复任务？')) return;
    await apiFetch(`/api/queue/${id}/cancel`, { method: 'POST' });
    loadQueue();
  }

  async function retryItem(id) {
    await apiFetch(`/api/queue/${id}/retry`, { method: 'POST' });
    loadQueue();
  }

  const [enqueuing, setEnqueuing] = useState(false);

  async function enqueueAllPassed() {
    if (!confirm('确认将所有已通过 AI 筛选的高意向线索排入防封安全队列？系统将自动注入冷却间隔有序发帖。')) return;
    setEnqueuing(true);
    try {
      const res = await apiFetch('/api/queue/enqueue_all_passed', { method: 'POST' });
      if (res.ok) {
        alert(res.enqueued_count > 0 ? `✅ 已成功加入 ${res.enqueued_count} 条回复任务到防封队列！` : (res.message || '没有发现可排期的线索。'));
        loadQueue();
      } else {
        alert(`排期失败: ${res.error}`);
      }
    } catch (e) {
      alert(`请求错误: ${e}`);
    } finally {
      setEnqueuing(false);
    }
  }

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-50 overflow-hidden">
      {/* Top Banner & Stats */}
      <div className="bg-white border-b border-slate-200 px-6 py-4 flex-shrink-0">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-slate-900">自动回复与安全风控队列</h1>
              <span className="text-xs bg-amber-100 text-amber-800 font-semibold px-2 py-0.5 rounded-full border border-amber-200">
                Promotion Warrior 防封节流引擎
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              全自动调度 Reddit 回帖投放，严格遵守账号单日上限与时间冷却间隔，内置 AutoMod 穿透与可见性侦测。
            </p>
          </div>

          {/* Quota Indicators */}
          <div className="flex items-center gap-3">
            {aiHealth?.chrono && (
              <div className="bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-1.5 text-center" title={`${aiHealth.chrono.window_desc}\n策略: ${aiHealth.chrono.policy}`}>
                <div className="text-[10px] uppercase font-semibold text-slate-400">
                  {aiHealth.chrono.tz_abbr ? `${aiHealth.chrono.tz_abbr} 受众时区` : '目标营销时区'}
                </div>
                <div className="text-xs font-bold text-slate-800 flex items-center gap-1 justify-center mt-0.5">
                  <span>{aiHealth.chrono.current_est_time}</span>
                  <span className={`text-[10px] font-bold px-1.5 py-0.2 rounded-full ${
                    aiHealth.chrono.is_peak ? 'bg-emerald-100 text-emerald-800' : 'bg-indigo-100 text-indigo-800'
                  }`}>
                    {aiHealth.chrono.is_peak ? '🔥 活跃期' : '🌙 静音期'}
                  </span>
                </div>
              </div>
            )}
            <div className="bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 text-center">
              <div className="text-[10px] uppercase font-semibold text-slate-400">今日已发评论</div>
              <div className="text-base font-bold text-slate-800">{dailyUsed} <span className="text-xs font-normal text-slate-400">/ 8 条</span></div>
            </div>
            <div className="bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 text-center">
              <div className="text-[10px] uppercase font-semibold text-slate-400">排期中待执行</div>
              <div className="text-base font-bold text-amber-600">{pendingCount} 条</div>
            </div>
            <div className="bg-amber-50/60 border border-amber-200/80 rounded-xl px-3.5 py-1.5 text-center" title="通过实时回扫获取的已发布评论累计真实点赞，获赞 ≥3 自动沉淀为 AI 黄金语料">
              <div className="text-[10px] uppercase font-semibold text-amber-700">👍 真实点赞回扫</div>
              <div className="text-base font-bold text-amber-900 flex items-center justify-center gap-1">
                <span>+{totalUpvotes} 赞</span>
                {totalWinners > 0 && (
                  <span className="text-[10px] bg-amber-200 text-amber-800 font-bold px-1.5 py-0.2 rounded-full">
                    🏆 {totalWinners} 范式
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={openLinksAnalytics}
              className="bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 rounded-xl px-3.5 py-1.5 text-center transition-colors cursor-pointer"
              title="查看所有带有智能 UTM 标记的短链访问 PV、独立访客 UV 及来源渠道"
            >
              <div className="text-[10px] uppercase font-semibold text-indigo-700">🔗 转化短链点击</div>
              <div className="text-base font-bold text-indigo-900 flex items-center justify-center gap-1">
                <span>{totalClicks} 次</span>
                <span className="text-[10px] font-medium text-indigo-600">透视 ↗</span>
              </div>
            </button>
            <button
              onClick={loadQueue}
              className="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-medium transition-colors flex items-center gap-1 cursor-pointer"
            >
              ⟳ 刷新
            </button>
            <button
              onClick={enqueueAllPassed}
              disabled={enqueuing}
              className="px-3.5 py-2 bg-gradient-to-r from-orange-500 to-amber-600 hover:from-orange-600 hover:to-amber-700 text-white rounded-xl text-xs font-semibold transition-all shadow-xs flex items-center gap-1.5 disabled:opacity-60 cursor-pointer"
            >
              {enqueuing ? <span className="spin">⟳</span> : '⚡'}
              {enqueuing ? '正在安全排期…' : '一键排期已通过线索'}
            </button>
          </div>
        </div>

        {/* Filter bar */}
        <div className="flex items-center gap-2 mt-4 pt-3 border-t border-slate-100 flex-wrap">
          <span className="text-xs font-semibold text-slate-500 mr-1">状态筛选:</span>
          {[
            { key: '', label: '全部', countKey: 'all' },
            { key: 'scheduled', label: '排期中', countKey: 'scheduled' },
            { key: 'submitted', label: '已提交', countKey: 'submitted' },
            { key: 'failed', label: '失败', countKey: 'failed' },
            { key: 'needs_review', label: '待人工复核', countKey: 'needs_review' },
            { key: 'cancelled', label: '已取消', countKey: 'cancelled' },
          ].map(tab => {
            const count = statusCounts[tab.countKey] ?? 0;
            const isActive = filter === tab.key;
            return (
              <button
                key={tab.key}
                onClick={() => setFilter(tab.key)}
                className={`text-xs px-2.5 py-1 rounded-lg border font-medium transition-all flex items-center gap-1.5 cursor-pointer ${
                  isActive
                    ? 'bg-slate-900 text-white border-slate-900 shadow-2xs'
                    : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                }`}
              >
                <span>{tab.label}</span>
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold leading-tight ${
                    isActive
                      ? 'bg-slate-700 text-slate-100'
                      : tab.countKey === 'failed' && count > 0
                      ? 'bg-rose-100 text-rose-700 border border-rose-200'
                      : tab.countKey === 'needs_review' && count > 0
                      ? 'bg-amber-100 text-amber-700 border border-amber-200'
                      : 'bg-slate-100 text-slate-500'
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Queue List */}
      <div className="flex-1 overflow-y-auto p-6 space-y-3">
        {loading && items.length === 0 ? (
          <div className="text-center py-16 text-slate-400 text-sm">正在加载回复任务队列…</div>
        ) : items.length === 0 ? (
          <div className="card p-12 text-center text-slate-400 space-y-2">
            <div className="text-3xl">📭</div>
            <div className="text-sm font-medium text-slate-600">当前没有队列任务</div>
            <div className="text-xs text-slate-400 max-w-sm mx-auto">
              在线流信息中发现高意向线索后，点击「加入排期队列」或在监听器中启用「全自动回复」，系统将在此有序执行安全投放。
            </div>
          </div>
        ) : (
          items.map(item => {
            const isX = item.platform === 'x' || item.platform === 'twitter';
            const isForum = item.platform === 'forum' || item.platform === 'vbulletin' || item.platform === 'phpbb' || item.platform === 'xenforo';
            const isFollowUp = (item.target_id && item.target_id.startsWith('t1_')) || (item.persona_label && item.persona_label.includes('二轮')) || item.kind === 'follow_up';
            const isScheduled = item.status === 'scheduled';
            const isSubmitted = item.status === 'submitted';
            const isFailed = item.status === 'failed';
            const isCancelled = item.status === 'cancelled';
            const isNeedsReview = item.status === 'needs_review';

            const isArchived = Boolean(item.is_archived) || Boolean(item.error_message && (item.error_message.includes('TOO_OLD') || item.error_message.includes('已归档') || item.error_message.includes('已锁定') || item.error_message.includes('THREAD_LOCKED')));

            const timeInfo = getQueueTimeInfo(item);

            let statusBadge = null;
            if (isScheduled) {
              statusBadge = (
                <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-amber-50 text-amber-700 border border-amber-200 flex items-center gap-1" title={timeInfo.scheduledFull || timeInfo.full}>
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-ping"></span>
                  {timeInfo.label || '排期中'}
                </span>
              );
            } else if (isNeedsReview) {
              statusBadge = (
                <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-rose-50 text-rose-700 border border-rose-200 flex items-center gap-1" title={timeInfo.full}>
                  ⚠️ 门禁拦截 ({timeInfo.exact || '待人工复核'})
                </span>
              );
            } else if (isSubmitted) {
              statusBadge = (
                <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1" title={`提交时间: ${timeInfo.full || timeInfo.exact}\n初次入队: ${timeInfo.createdFull || timeInfo.createdExact}`}>
                  ✓ {timeInfo.label || '已发布'}
                </span>
              );
            } else if (isFailed) {
              if (isArchived) {
                statusBadge = (
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-200 text-slate-700 border border-slate-300 flex items-center gap-1" title={item.error_message || '原帖发布过久已关闭回复区'}>
                    🗄️ 原帖已归档 (无法回复)
                  </span>
                );
              } else {
                statusBadge = (
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-rose-50 text-rose-700 border border-rose-200 flex items-center gap-1" title={`失败时间: ${timeInfo.full || timeInfo.exact}\n初次入队: ${timeInfo.createdFull || timeInfo.createdExact}`}>
                    ✗ {timeInfo.label || '发布失败'}
                  </span>
                );
              }
            } else {
              statusBadge = (
                <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-100 text-slate-500 border border-slate-200 flex items-center gap-1" title={timeInfo.full}>
                  {timeInfo.label || '已取消'}
                </span>
              );
            }

            // Visibility badge
            let visBadge = null;
            if (isSubmitted) {
              const vs = (item.visibility_status || '').toLowerCase();
              if (vs === 'visible' || vs === 'live') {
                visBadge = (
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-teal-50 text-teal-700 border border-teal-200 flex items-center gap-1" title="通过无 Cookie 游客视角核查，内容公开可见">
                    🛡️ 公开可见 (Live)
                  </span>
                );
              } else if (vs === 'shadowbanned_or_removed' || vs === 'removed') {
                visBadge = (
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-red-100 text-red-800 border border-red-300 flex items-center gap-1" title="警告: 游客视角未检测到该内容，可能已被系统过滤或账号被限流">
                    ⚠️ 疑似被屏蔽 / 拦截 (Removed)
                  </span>
                );
              } else if (vs === 'locked') {
                visBadge = (
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-300 flex items-center gap-1" title="原帖已被版主锁定禁止回复">
                    🔒 原帖锁定 (Locked)
                  </span>
                );
              } else {
                visBadge = (
                  <span className="text-xs font-medium px-2 py-0.5 rounded-md bg-slate-100 text-slate-500 border border-slate-200">
                    🔍 正在进行可见性验证...
                  </span>
                );
              }
            }

            return (
              <div key={item.id} className="card p-4 space-y-3 hover:border-slate-300 transition-all">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    {isForum ? (
                      <>
                        <span className="text-xs font-bold bg-emerald-600 text-white px-1.5 py-0.2 rounded flex items-center gap-1">🌐 论坛</span>
                        <span className="text-xs text-slate-700 font-mono truncate max-w-[200px]" title={item.target_url || item.target_id}>
                          {item.subreddit && item.subreddit !== 'forum' ? item.subreddit : 'Thread'}
                        </span>
                        {item.author && <span className="text-xs text-slate-400">Target: @{item.author}</span>}
                      </>
                    ) : isX ? (
                      <>
                        <span className="text-xs font-bold bg-black text-white px-1.5 py-0.2 rounded flex items-center gap-1">𝕏</span>
                        <span className="text-xs text-slate-700 font-mono">Tweet: {item.target_id || item.post_id}</span>
                        <span className="text-xs text-slate-400">Target User: @{item.author || 'unknown'}</span>
                      </>
                    ) : (
                      <>
                        <span className="text-xs font-bold text-orange-600">r/{item.subreddit}</span>
                        <span className="text-xs text-slate-400">Post ID: {item.post_id}</span>
                        <span className="text-xs text-slate-400">Target User: u/{item.author || 'unknown'}</span>
                      </>
                    )}
                    <span className="text-xs text-slate-300">·</span>
                    <span className="text-xs font-medium text-slate-500">{item.listener_name || item.listener_id}</span>
                    <span className={`text-[11px] font-bold px-2 py-0.5 rounded-md flex items-center gap-1 border ${
                      (item.opportunity_score || 50) >= 80 ? 'bg-amber-100 text-amber-900 border-amber-300' :
                      (item.opportunity_score || 50) >= 65 ? 'bg-emerald-50 text-emerald-800 border-emerald-200' :
                      'bg-slate-100 text-slate-700 border-slate-200'
                    }`} title={`抢楼与时效机会分: ${item.opportunity_score || 50}/100`}>
                      {(item.opportunity_score || 50) >= 80 ? '🔥' : (item.opportunity_score || 50) >= 65 ? '✨' : '🎯'} {item.opportunity_score || 50}分
                    </span>
                    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-md flex items-center gap-1 border ${
                      item.safety_verdict === 'PASSED' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
                      item.safety_verdict === 'FLAGGED' ? 'bg-rose-50 text-rose-700 border-rose-200' :
                      'bg-slate-100 text-slate-600 border-slate-200'
                    }`}>
                      {item.safety_verdict === 'PASSED' ? '🛡️ 门禁通过' : item.safety_verdict === 'FLAGGED' ? '⚠️ 人工待审' : '🛡️ 已审核'}
                    </span>
                    {item.persona_label && (
                      <span className="text-[11px] font-bold px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200 flex items-center gap-1 shadow-2xs" title="AI 专家人设">
                        {item.persona_label}
                      </span>
                    )}
                    {isFollowUp && (
                      <span className="text-[11px] font-bold px-2 py-0.5 rounded-md bg-purple-100 text-purple-800 border border-purple-300 flex items-center gap-1 shadow-2xs" title="Step 2 转化闭环：针对社区用户的二次追问或主动跟评">
                        💬 二轮闭环追评
                      </span>
                    )}
                    {statusBadge}
                    {visBadge}
                    {isSubmitted && (
                      <>
                        <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-200 flex items-center gap-1" title="实时回扫真实点赞与跟评数据">
                          👍 {item.upvotes || 0} 赞 · 💬 {item.replies_count || 0} 评
                        </span>
                        {Boolean(item.is_winner) && (
                          <span className="text-xs font-bold px-2 py-0.5 rounded-md bg-gradient-to-r from-amber-400 to-yellow-500 text-amber-950 shadow-2xs border border-amber-300 flex items-center gap-1" title="高赞优质回帖！已自动收录为 AI 黄金范例">
                            🏆 黄金范式
                          </span>
                        )}
                        {item.short_url && (
                          <a
                            href={item.short_url.startsWith('http') ? item.short_url : `https://s.hanzhe.dpdns.org${item.short_url}`}
                            target="_blank"
                            rel="noopener"
                            className="text-xs font-mono px-2 py-0.5 rounded-md bg-sky-50 text-sky-700 hover:bg-sky-100 border border-sky-200 flex items-center gap-1"
                            title="智能归因短链 (点击测试跳转与PV/UV统计)"
                          >
                            🔗 {item.short_url.startsWith('http') ? item.short_url : `https://s.hanzhe.dpdns.org${item.short_url}`}
                          </a>
                        )}
                      </>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5 flex-wrap">
                    <button
                      onClick={async () => {
                        await navigator.clipboard.writeText(item.reply_text);
                        if (item.target_url) window.open(item.target_url, '_blank');
                        alert(isForum
                          ? '📋 BBCode 草稿已复制到剪贴板，原帖已在新标签页打开！在论坛编辑器中粘贴 (Cmd+V / Ctrl+V) 即可提交。'
                          : '✅ AI 营销草稿已复制到剪贴板，原帖已在新标签页打开！直接在评论框粘贴 (Cmd+V / Ctrl+V) 即可瞬间发布。');
                      }}
                      className="text-xs px-2.5 py-1 bg-violet-600 hover:bg-violet-700 text-white rounded-lg font-medium transition-colors flex items-center gap-1 cursor-pointer shadow-xs"
                      title={isForum ? "复制 BBCode 并直达论坛原帖（浏览器已登录推荐）" : "免 API 凭据：一键复制文案并在新标签页打开原帖"}
                    >
                      {isForum ? '📋 复制 BBCode 并直达' : '📋 复制文案并直达'}
                    </button>
                    {isNeedsReview && (
                      <>
                        <button
                          onClick={async () => {
                            if (!confirm('确认人工核准此回复并排期入队？')) return;
                            await apiFetch(`/api/queue/${item.id}/retry`, { method: 'POST' });
                            loadQueue();
                          }}
                          className="text-xs px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-medium transition-colors"
                        >
                          ✓ 人工核准排期
                        </button>
                        <button
                          onClick={() => submitNow(item.id, item.platform)}
                          className="text-xs px-2.5 py-1 bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-medium transition-colors"
                        >
                          🚀 立即提交
                        </button>
                        <button
                          onClick={() => cancelItem(item.id)}
                          className="text-xs px-2.5 py-1 bg-white hover:bg-slate-100 border border-slate-200 text-slate-600 rounded-lg font-medium transition-colors"
                        >
                          取消
                        </button>
                      </>
                    )}
                    {isScheduled && (
                      <>
                        <button
                          onClick={() => submitNow(item.id, item.platform)}
                          className="text-xs px-2.5 py-1 bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-medium transition-colors"
                        >
                          🚀 立即提交
                        </button>
                        <button
                          onClick={() => cancelItem(item.id)}
                          className="text-xs px-2.5 py-1 bg-white hover:bg-slate-100 border border-slate-200 text-slate-600 rounded-lg font-medium transition-colors"
                        >
                          取消
                        </button>
                      </>
                    )}
                    {isFailed && (
                      isArchived ? (
                        <button
                          onClick={() => cancelItem(item.id)}
                          className="text-xs px-2.5 py-1 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg font-medium transition-colors cursor-pointer"
                          title="原帖已被 Reddit 归档关闭，无法回复。点击清理移除该任务。"
                        >
                          🗑️ 清理移除
                        </button>
                      ) : (
                        <button
                          onClick={() => retryItem(item.id)}
                          className="text-xs px-2.5 py-1 bg-slate-900 hover:bg-slate-800 text-white rounded-lg font-medium transition-colors cursor-pointer"
                        >
                          重试
                        </button>
                      )
                    )}
                    {item.comment_url && (
                      <a
                        href={item.comment_url}
                        target="_blank"
                        rel="noopener"
                        className="text-xs px-2.5 py-1 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-lg font-medium transition-colors"
                      >
                        ↗ {isX ? '查看推文' : '查看评论'}
                      </a>
                    )}
                    {item.target_url && (
                      <a
                        href={item.target_url}
                        target="_blank"
                        rel="noopener"
                        className="text-xs px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg font-medium transition-colors"
                      >
                        原帖
                      </a>
                    )}
                    {isSubmitted && (
                      <button
                        onClick={async () => {
                          if (!confirm('确认针对此已发布的评论发起 Step 2 闭环追评？系统将自动融入产品规格及专属短链，并排入安全队列。')) return;
                          try {
                            const res = await apiFetch(`/api/queue/${item.id}/follow_up`, { method: 'POST' });
                            if (res.ok) {
                              alert(`✅ Step 2 闭环追评已生成并排入安全队列！任务ID: #${res.follow_up_id}`);
                              loadQueue();
                            } else {
                              alert(`发起追评失败: ${res.error}`);
                            }
                          } catch (e) {
                            alert(`请求异常: ${e}`);
                          }
                        }}
                        className="text-xs px-2.5 py-1 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors flex items-center gap-1 cursor-pointer shadow-xs"
                        title="在已发布评论下发起二轮追评（带专属短链促转化）"
                      >
                        💬 主动发追评
                      </button>
                    )}
                    <button
                      onClick={() => openQueueDm(item)}
                      className="text-xs px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 rounded-lg font-semibold transition-colors flex items-center gap-1 cursor-pointer"
                      title="1v1 私信联系该用户"
                    >
                      ✉️ 私信
                    </button>
                  </div>
                </div>

                {/* Original Post Context & Attribution Strip */}
                {(item.post_title || item.target_url || item.hit_url) && (
                  <div className="flex items-center justify-between text-xs bg-slate-100/80 border border-slate-200/90 px-3 py-1.5 rounded-lg gap-2 text-slate-600 flex-wrap sm:flex-nowrap">
                    <div className="flex items-center gap-1.5 min-w-0 flex-1">
                      <span className="font-bold text-slate-500 flex-shrink-0 flex items-center gap-0.5">
                        📌 原帖:
                      </span>
                      <a
                        href={item.target_url || item.hit_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-medium text-slate-800 hover:text-indigo-600 truncate hover:underline"
                        title={item.post_title || '查看原帖详情'}
                      >
                        {item.post_title || (item.post_excerpt ? item.post_excerpt.slice(0, 80) + '…' : (item.target_url || item.hit_url))}
                      </a>
                    </div>
                    {timeInfo.postExact && (
                      <span
                        className="text-[11px] text-slate-500 font-normal flex-shrink-0 flex items-center gap-1 bg-white px-2 py-0.5 rounded border border-slate-200/70"
                        title={`原帖作者发布时间: ${timeInfo.postFull || timeInfo.postExact}`}
                      >
                        🕒 发帖于 {timeInfo.postExact} {timeInfo.postRel ? `(${timeInfo.postRel})` : ''}
                      </span>
                    )}
                  </div>
                )}

                {/* Smart Chrono Dispatch Reason */}
                {item.chrono_reason && (
                  <div className="flex items-center gap-2 text-xs bg-amber-50/80 border border-amber-200/70 text-slate-700 px-3 py-1.5 rounded-xl">
                    <span className="text-amber-700 font-bold flex items-center gap-1 flex-shrink-0">
                      ⏱️ 智能错峰调度:
                    </span>
                    <span className="text-slate-600 font-medium">{item.chrono_reason}</span>
                  </div>
                )}

                {/* Adaptive Tone A/B Switcher for Queued Item */}
                {!isSubmitted && !isCancelled && (
                  <div className="flex items-center justify-between bg-slate-100/90 rounded-lg px-2.5 py-1.5 flex-wrap gap-2 border border-slate-200/60">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">A/B 风格:</span>
                      <button
                        onClick={() => switchQueueStyle(item.id, 'guru')}
                        disabled={switchingQueueId === item.id}
                        className={`text-[11px] px-2 py-0.5 rounded-md font-semibold transition-all cursor-pointer ${
                          item.persona === 'guru'
                            ? 'bg-indigo-600 text-white shadow-xs'
                            : 'bg-white hover:bg-slate-50 text-slate-700 border border-slate-200'
                        }`}
                        title="极客技术干货向：资深诊断专家口吻，拆解电路/机械/固件根因，严谨无废话"
                      >
                        {switchingQueueId === item.id ? '⟳ 生成中…' : '⚡ 极客干货向'}
                      </button>
                      <button
                        onClick={() => switchQueueStyle(item.id, 'authentic')}
                        disabled={switchingQueueId === item.id}
                        className={`text-[11px] px-2 py-0.5 rounded-md font-semibold transition-all cursor-pointer ${
                          item.persona === 'authentic'
                            ? 'bg-indigo-600 text-white shadow-xs'
                            : 'bg-white hover:bg-slate-50 text-slate-700 border border-slate-200'
                        }`}
                        title="真实折腾测评向：车主/用户第一视角，分享折腾踩坑经历与实测体感，亲切高共鸣"
                      >
                        {switchingQueueId === item.id ? '⟳ 生成中…' : '🛠️ 真实测评向'}
                      </button>
                    </div>
                    {item.persona_label && (
                      <span className="text-[10px] text-slate-500 font-medium">
                        当前人设: <span className="font-bold text-indigo-700">{item.persona_label}</span>
                      </span>
                    )}
                  </div>
                )}

                {/* Reply Content Preview */}
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-700 font-sans whitespace-pre-wrap leading-relaxed">
                  {item.reply_text}
                </div>

                {/* Error message & failure operation time if failed */}
                {item.error_message && (
                  <div className={`text-xs px-3.5 py-2.5 rounded-xl border flex items-start justify-between gap-3 ${
                    isArchived
                      ? 'text-slate-700 bg-slate-100/90 border-slate-300'
                      : 'text-rose-700 bg-rose-50/90 border-rose-200'
                  }`}>
                    <div className="space-y-1 min-w-0 flex-1">
                      <div className={`font-bold flex items-center gap-1.5 ${isArchived ? 'text-slate-800' : 'text-rose-800'}`}>
                        <span>{isArchived ? '🗄️ 归档拦截原因' : '⚠ 失败原因'}</span>
                        {timeInfo.exact && (
                          <span className={`text-[11px] font-normal ${isArchived ? 'text-slate-500' : 'text-rose-600'}`}>
                            ({isArchived ? '拦截于' : '失败于'} {timeInfo.exact} · {timeInfo.relative})
                          </span>
                        )}
                      </div>
                      <div className={`${isArchived ? 'text-slate-600' : 'text-rose-600'} font-sans text-xs leading-relaxed break-words`}>
                        {item.error_message}
                      </div>
                    </div>
                    {isFailed && !isArchived && (
                      <button
                        onClick={() => retryItem(item.id)}
                        className="px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-semibold transition-colors flex-shrink-0 cursor-pointer shadow-xs"
                      >
                        ↺ 重新排期
                      </button>
                    )}
                    {isFailed && isArchived && (
                      <button
                        onClick={() => cancelItem(item.id)}
                        className="px-3 py-1.5 bg-slate-700 hover:bg-slate-800 text-white rounded-lg text-xs font-semibold transition-colors flex-shrink-0 cursor-pointer shadow-xs"
                        title="原帖已归档关闭，无法重发。点击从队列移除。"
                      >
                        🗑️ 移除此任务
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Attribution & UTM Short Links Modal */}
      {showLinksModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-4xl w-full max-h-[85vh] flex flex-col overflow-hidden border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/70">
              <div className="flex items-center gap-2.5">
                <span className="p-2 bg-indigo-100 text-indigo-700 rounded-xl text-lg font-bold">
                  🔗
                </span>
                <div>
                  <h2 className="text-base font-bold text-slate-900">
                    智能转化短链与 UTM 归因透视看板
                  </h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    基于动态 302 重定向与 SHA-256 IP 去重技术，全闭环追踪社交评论引流的真实 PV 与独立访客 UV
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowLinksModal(false)}
                className="w-8 h-8 rounded-lg hover:bg-slate-200/80 flex items-center justify-center text-slate-400 hover:text-slate-600 transition-colors text-sm"
              >
                ✕
              </button>
            </div>

            {/* Metrics Overview Row */}
            <div className="px-6 py-3.5 bg-indigo-50/40 border-b border-indigo-100/60 grid grid-cols-4 gap-3">
              <div className="bg-white p-3 rounded-xl border border-indigo-100 shadow-2xs">
                <div className="text-[11px] text-slate-500 font-medium">累计归因短链</div>
                <div className="text-lg font-bold text-slate-800 mt-0.5">
                  {linksData?.total_links || 0} <span className="text-xs font-normal text-slate-400">条</span>
                </div>
              </div>
              <div className="bg-white p-3 rounded-xl border border-indigo-100 shadow-2xs">
                <div className="text-[11px] text-slate-500 font-medium">总浏览点击 (PV)</div>
                <div className="text-lg font-bold text-indigo-700 mt-0.5">
                  {linksData?.total_clicks || 0} <span className="text-xs font-normal text-slate-400">次</span>
                </div>
              </div>
              <div className="bg-white p-3 rounded-xl border border-indigo-100 shadow-2xs">
                <div className="text-[11px] text-slate-500 font-medium">真实独立访客 (UV)</div>
                <div className="text-lg font-bold text-emerald-700 mt-0.5">
                  {linksData?.total_uv || 0} <span className="text-xs font-normal text-slate-400">人</span>
                </div>
              </div>
              <div className="bg-white p-3 rounded-xl border border-indigo-100 shadow-2xs">
                <div className="text-[11px] text-slate-500 font-medium">访客纯度 (UV / PV)</div>
                <div className="text-lg font-bold text-amber-700 mt-0.5">
                  {linksData?.total_clicks ? `${Math.round(((linksData.total_uv || 0) / linksData.total_clicks) * 100)}%` : '0%'}
                </div>
              </div>
            </div>

            {/* Modal Body / Table */}
            <div className="p-6 overflow-y-auto flex-1 space-y-3">
              {loadingLinks ? (
                <div className="py-16 text-center text-slate-400 text-sm flex items-center justify-center gap-2">
                  <span className="spin">⟳</span> 正在加载短链归因报表…
                </div>
              ) : !linksData?.links || linksData.links.length === 0 ? (
                <div className="py-16 text-center text-slate-400 text-sm">
                  暂无短链记录。系统在排期生成带营销链接的回复时，将自动注入短链与 UTM 参数。
                </div>
              ) : (
                <div className="space-y-3">
                  {linksData.links.map(link => {
                    const shortUrl = `${window.location.origin}/r/${link.code}`;
                    const isCopied = copiedCode === link.code;

                    return (
                      <div
                        key={link.id}
                        className="p-3.5 bg-slate-50 hover:bg-slate-100/80 border border-slate-200 rounded-xl transition-all flex flex-col gap-2"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-mono text-xs font-bold text-indigo-700 bg-indigo-100/70 border border-indigo-200 px-2 py-0.5 rounded-md">
                              /r/{link.code}
                            </span>
                            <span className="text-xs px-2 py-0.5 rounded-md bg-slate-200/70 text-slate-700 font-medium">
                              {link.platform === 'x' ? '𝕏' : `r/${link.subreddit || 'reddit'}`}
                            </span>
                            {link.persona && (
                              <span className="text-xs px-2 py-0.5 rounded-md bg-purple-100 text-purple-700 font-medium">
                                {link.persona}
                              </span>
                            )}
                            {Boolean(link.is_winner) && (
                              <span className="text-xs px-2 py-0.5 rounded-md bg-amber-200 text-amber-900 font-bold">
                                🏆 黄金范式
                              </span>
                            )}
                          </div>

                          {/* Stats Counters & Actions */}
                          <div className="flex items-center gap-3">
                            <span className="text-xs font-semibold text-slate-700">
                              PV: <b className="text-indigo-700">{link.clicks || 0}</b> · UV: <b className="text-emerald-700">{link.uv || 0}</b>
                            </span>
                            {link.upvotes !== null && link.upvotes !== undefined && (
                              <span className="text-xs px-2 py-0.5 rounded-md bg-amber-100 text-amber-800 font-medium">
                                👍 +{link.upvotes} 赞
                              </span>
                            )}
                            <button
                              onClick={() => {
                                navigator.clipboard.writeText(shortUrl);
                                setCopiedCode(link.code);
                                setTimeout(() => setCopiedCode(null), 2000);
                              }}
                              className="text-xs px-2.5 py-1 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 rounded-lg font-medium transition-colors shadow-2xs cursor-pointer"
                            >
                              {isCopied ? '✓ 已复制' : '复制短链'}
                            </button>
                            <a
                              href={shortUrl}
                              target="_blank"
                              rel="noopener"
                              className="text-xs px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium transition-colors"
                            >
                              测试跳转 ↗
                            </a>
                          </div>
                        </div>

                        {/* Target & UTM details */}
                        <div className="text-[11px] font-mono text-slate-500 bg-white p-2 rounded-lg border border-slate-200/60 break-all leading-normal">
                          <span className="text-slate-400 font-sans mr-1">最终跳转:</span>
                          <span className="text-slate-700">{link.final_url || link.target_url}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3 border-t border-slate-100 bg-slate-50/70 flex items-center justify-between">
              <span className="text-xs text-slate-400">
                短链支持自主生成与多渠道归因映射
              </span>
              <button
                onClick={() => setShowLinksModal(false)}
                className="px-4 py-1.5 bg-slate-800 hover:bg-slate-900 text-white rounded-xl text-xs font-semibold transition-colors"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 1v1 Queue Item Direct Message (DM) Outreach & Playbook Modal */}
      <ConversionDmModal
        isOpen={showQueueDmModal}
        onClose={() => setShowQueueDmModal(false)}
        loading={loadingQueueDm}
        data={queueDmData}
      />
    </div>
  );
}
