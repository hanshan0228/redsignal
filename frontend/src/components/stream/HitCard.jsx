import { useState } from 'react';
import { timeAgo, getHitTimeDetails } from '../../utils.js';
import StatusBadge from './StatusBadge.jsx';
import ConversionDmModal from '../common/ConversionDmModal.jsx';

export default function HitCard({ hit, isHistory, onStatusUpdate, onOpenReply, onOpenThread, onAnalyze, onFilterByListener }) {
  const [generatingDraft, setGeneratingDraft] = useState(false);
  const [oneClickLoading, setOneClickLoading] = useState(false);
  const [resurrecting, setResurrecting] = useState(false);
  const [isResurrected, setIsResurrected] = useState(false);
  const [queuedInfo, setQueuedInfo] = useState(null);
  const [localDraft, setLocalDraft] = useState(hit.reply_draft || null);
  const [localTier, setLocalTier] = useState(hit.funnel_tier || 3);
  const [localOppScore, setLocalOppScore] = useState(hit.opportunity_score || 50);
  const [localSafetyVerdict, setLocalSafetyVerdict] = useState(hit.safety_verdict || null);
  const [localPersonaLabel, setLocalPersonaLabel] = useState(hit.persona_label || null);
  const [switchingStyle, setSwitchingStyle] = useState(false);
  const [currentPersonaKey, setCurrentPersonaKey] = useState(hit.persona || 'expert');
  const [showDmModal, setShowDmModal] = useState(false);
  const [dmData, setDmData] = useState(null);
  const [loadingDm, setLoadingDm] = useState(false);

  async function handleOpenDm(e) {
    e.stopPropagation();
    setShowDmModal(true);
    if (!dmData) {
      setLoadingDm(true);
      try {
        const res = await fetch(`/api/hits/${hit.id}/dm_pitch`, { method: 'POST' }).then(r => r.json());
        if (res.ok) {
          setDmData(res);
        } else {
          alert(`生成私信话术失败: ${res.error || '未知错误'}`);
        }
      } catch (err) {
        alert(`请求异常: ${err}`);
      } finally {
        setLoadingDm(false);
      }
    }
  }

  async function handleSwitchStyle(e, style) {
    e.stopPropagation();
    setSwitchingStyle(true);
    try {
      const res = await fetch(`/api/hits/${hit.id}/switch_style?style=${style}`, { method: 'POST' }).then(r => r.json());
      if (res.ok) {
        setLocalDraft(res.reply_draft);
        setLocalTier(res.funnel_tier || 3);
        setLocalOppScore(res.opportunity_score || 50);
        setLocalSafetyVerdict(res.safety_verdict || 'PASSED');
        if (res.persona_label) setLocalPersonaLabel(res.persona_label);
        setCurrentPersonaKey(res.persona || style);
        hit.reply_draft = res.reply_draft;
        hit.opportunity_score = res.opportunity_score;
        hit.safety_verdict = res.safety_verdict;
        hit.persona = res.persona || style;
        hit.persona_label = res.persona_label;
      } else {
        alert(`切换风格失败: ${res.error || '请检查 Vault 中的 AI Key'}`);
      }
    } catch (err) {
      alert(`请求异常: ${err}`);
    } finally {
      setSwitchingStyle(false);
    }
  }

  async function handleResurrect(e) {
    e.stopPropagation();
    setResurrecting(true);
    try {
      const res = await fetch(`/api/hits/${hit.id}/resurrect`, { method: 'POST' }).then(r => r.json());
      if (res.ok) {
        setIsResurrected(true);
        const engage = res.engage || {};
        if (engage.reply_draft) {
          setLocalDraft(engage.reply_draft);
          setLocalOppScore(engage.opportunity_score || 50);
          setLocalSafetyVerdict(engage.safety_verdict || 'PASSED');
          if (engage.persona_label) setLocalPersonaLabel(engage.persona_label);
          setQueuedInfo({
            status: engage.status,
            delay_minutes: engage.delay_minutes || 5,
            chrono_reason: engage.chrono_reason || '',
            already: engage.already_queued
          });
          hit.reply_draft = engage.reply_draft;
          hit.opportunity_score = engage.opportunity_score;
          hit.safety_verdict = engage.safety_verdict;
          hit.persona_label = engage.persona_label;
        }
        hit.filter_passed = 1;
        if (hit.filter_result) hit.filter_result.passed = true;
        if (onStatusUpdate) onStatusUpdate(hit.id, 'reviewing');
        const chronoNote = engage.chrono_reason ? `\n\n【时区错峰调度】: ${engage.chrono_reason}` : '';
        alert(
          `⚡ 逆向纠偏复活成功！\n\n已成功复活被误杀线索，并将纠偏知识沉淀入自愈引擎（ai_learnings）！\n已自动匹配人设并生成独立站植入回复。${chronoNote}\n已排入防封队列（预计 ~${engage.delay_minutes || 5} 分钟后发射）。`
        );
      } else {
        alert(`复活失败: ${res.error}`);
      }
    } catch (err) {
      alert(`请求异常: ${err}`);
    } finally {
      setResurrecting(false);
    }
  }

  async function handleOneClickEngage(e) {
    e.stopPropagation();
    setOneClickLoading(true);
    try {
      const res = await fetch(`/api/hits/${hit.id}/one_click_engage`, { method: 'POST' }).then(r => r.json());
      if (res.ok) {
        setLocalDraft(res.reply_draft);
        setLocalOppScore(res.opportunity_score || 50);
        setLocalSafetyVerdict(res.safety_verdict || 'PASSED');
        if (res.persona_label) setLocalPersonaLabel(res.persona_label);
        setQueuedInfo({
          status: res.status,
          delay_minutes: res.delay_minutes || 5,
          chrono_reason: res.chrono_reason || '',
          already: res.already_queued
        });
        hit.reply_draft = res.reply_draft;
        hit.opportunity_score = res.opportunity_score;
        hit.safety_verdict = res.safety_verdict;
        hit.persona_label = res.persona_label;
        if (onStatusUpdate) onStatusUpdate(hit.id, 'reviewing');
        const chronoNote = res.chrono_reason ? `\n\n【时区错峰调度】: ${res.chrono_reason}` : '';
        alert(res.status === 'scheduled'
          ? `⚡ AI 一键智投排期成功！\n\n已匹配人设【${res.persona_label || '🎯 领域专家'}】生成技术回复，并通过防封门禁（机会分: ${res.opportunity_score || 50}分）。${chronoNote}\n已加入发帖队列（预计 ~${res.delay_minutes || 5} 分钟后发射）。`
          : `⚠️ 草稿已生成，但触发预审员风控门禁拦截，已安全转入人工复核队列！`
        );
      } else {
        alert(`一键操作失败: ${res.error}`);
      }
    } catch (err) {
      alert(`网络异常: ${err}`);
    } finally {
      setOneClickLoading(false);
    }
  }

  async function handleGenerateDraft(e) {
    e.stopPropagation();
    setGeneratingDraft(true);
    try {
      const res = await fetch(`/api/hits/${hit.id}/auto_draft`, { method: 'POST' }).then(r => r.json());
      if (res.ok) {
        setLocalDraft(res.reply_draft);
        setLocalTier(res.funnel_tier || 3);
        setLocalOppScore(res.opportunity_score || 50);
        setLocalSafetyVerdict(res.safety_verdict || 'PASSED');
        if (res.persona_label) setLocalPersonaLabel(res.persona_label);
        hit.reply_draft = res.reply_draft;
        hit.funnel_tier = res.funnel_tier;
        hit.opportunity_score = res.opportunity_score;
        hit.safety_verdict = res.safety_verdict;
        hit.safety_score = res.safety_score;
        hit.persona_label = res.persona_label;
      } else {
        alert(`生成失败: ${res.error || '请检查 Vault 中的 AI Key'}`);
      }
    } catch (err) {
      alert(`请求错误: ${err}`);
    } finally {
      setGeneratingDraft(false);
    }
  }

  const isPost = hit.kind === 'post';
  const isFollowUp = hit.kind === 'follow_up';
  const isForum = hit.platform === 'forum' || hit.platform === 'vbulletin' || hit.platform === 'phpbb' || hit.platform === 'xenforo' || (hit.url && (hit.url.includes('buggiesgonewild.com') || hit.url.includes('external.php') || hit.url.includes('/forum')));
  const isX = !isForum && (hit.platform === 'x' || hit.platform === 'twitter' || (hit.url && (hit.url.includes('x.com') || hit.url.includes('twitter.com'))));
  const timeDetails = getHitTimeDetails(hit);
  const age = timeDetails.relative || timeAgo((hit.ts || 0) * 1000);
  const activeDraft = localDraft || hit.reply_draft;
  const activeTier = localTier || hit.funnel_tier || 3;
  const activeOppScore = localOppScore || hit.opportunity_score || 50;
  const activeSafety = localSafetyVerdict || hit.safety_verdict || null;
  const activePersona = localPersonaLabel || hit.persona_label || null;

  const typeBadge = isFollowUp
    ? <span className="text-xs font-bold px-2 py-0.5 rounded-md bg-purple-100 text-purple-800 border border-purple-300 flex items-center gap-1 shadow-2xs">💬 二轮追问转化</span>
    : isForum
    ? <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-emerald-600 text-white flex items-center gap-1">🌐 论坛原帖</span>
    : isX
    ? <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-black text-white flex items-center gap-1">𝕏 TWEET</span>
    : isPost
    ? <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-blue-50 text-blue-600 border border-blue-100">POST</span>
    : <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-violet-50 text-violet-600 border border-violet-100">COMMENT</span>;

  let personaBadge = null;
  if (activePersona) {
    personaBadge = (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200 flex items-center gap-1 shadow-2xs" title="AI 意图分类与专家人设">
        {activePersona}
      </span>
    );
  }

  let tierBadge = null;
  if (activeTier === 1) {
    tierBadge = (
      <span className="text-[11px] font-bold px-2 py-0.5 rounded-md bg-rose-50 text-rose-700 border border-rose-200 flex items-center gap-1" title={hit.funnel_reason || 'Tier 1: 显性需求 (Hot / Direct Intent)'}>
        🎯 Tier 1 显性转化
      </span>
    );
  } else if (activeTier === 2) {
    tierBadge = (
      <span className="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-amber-50 text-amber-700 border border-amber-200 flex items-center gap-1" title={hit.funnel_reason || 'Tier 2: 竞品对比/痛点 (Warm / Comparison)'}>
        ⚡ Tier 2 侧翼切入
      </span>
    );
  } else {
    tierBadge = (
      <span className="text-[11px] font-medium px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 border border-slate-200 flex items-center gap-1" title={hit.funnel_reason || 'Tier 3: 问题意识/干货 (Cold / Problem Aware)'}>
        💡 Tier 3 干货养号
      </span>
    );
  }

  let filterBadge = null;
  if (hit.analyzing) {
    filterBadge = (
      <span className="flex items-center gap-1 text-xs text-amber-600 bg-amber-50 px-2 py-0.5 rounded-md border border-amber-100">
        <span className="spin">⟳</span> Analyzing
      </span>
    );
  } else if (hit.filter_result?.error) {
    filterBadge = (
      <span
        className="text-xs text-red-500 bg-red-50 px-2 py-0.5 rounded-md border border-red-100"
        title={hit.filter_result.error}
      >
        ⚠ Error
      </span>
    );
  } else if (isResurrected) {
    filterBadge = (
      <span className="text-xs text-teal-700 bg-teal-50 px-2 py-0.5 rounded-md border border-teal-200 font-medium flex items-center gap-1">
        ✓ 已纠偏复活
      </span>
    );
  } else if (hit.filter_result?.passed === true) {
    filterBadge = (
      <span className="text-xs text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-100 font-medium">
        ✓ Passed
      </span>
    );
  } else if (hit.filter_result?.passed === false || hit.filter_passed === 0) {
    filterBadge = (
      <span className="text-xs text-red-600 bg-red-50 px-2 py-0.5 rounded-md border border-red-100 font-medium">
        ✗ Rejected
      </span>
    );
  }

  const results = hit.filter_result?.results || [];
  const steps = results.length > 0 ? (
    <div className="mt-2.5 pt-2 border-t border-slate-100 flex items-center gap-1 flex-wrap">
      {results.map((r, i) => {
        const isLast = i === results.length - 1;
        let icon, dotCls, labelCls;
        if (r.skipped) {
          icon = <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14"/></svg>;
          dotCls = 'bg-slate-200 text-slate-400';
          labelCls = 'text-slate-400';
        } else if (r.error || r.passed === false) {
          icon = <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M18 6 6 18M6 6l12 12"/></svg>;
          dotCls = 'bg-red-100 text-red-500';
          labelCls = 'text-red-600';
        } else {
          icon = <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>;
          dotCls = 'bg-emerald-100 text-emerald-600';
          labelCls = 'text-emerald-700';
        }
        return (
          <div key={i} className="flex items-center gap-1 flex-shrink-0">
            <div className="flex items-center gap-1">
              <div className={`w-4 h-4 rounded-full flex items-center justify-center ${dotCls}`}>{icon}</div>
              <span className={`text-[11px] font-medium ${labelCls} whitespace-nowrap`}>{r.step}</span>
            </div>
            {!isLast && (
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" strokeWidth="2">
                <path d="M9 18l6-6-6-6"/>
              </svg>
            )}
          </div>
        );
      })}
    </div>
  ) : null;

  const isRejected = (hit.filter_result?.passed === false || hit.filter_passed === 0) && !isResurrected;
  const dimmed = isRejected ? 'opacity-85 border-dashed border-rose-200 bg-rose-50/10' : '';
  const noClick = hit.analyzing ? 'opacity-50 pointer-events-none' : '';

  return (
    <div className={`card p-4 hover:border-slate-200 transition-all ${dimmed}`}>
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center flex-wrap gap-2 mb-2.5">
            {typeBadge}
            {tierBadge}
            {personaBadge}
            {activeOppScore ? (
              <span className={`text-[11px] font-bold px-2 py-0.5 rounded-md flex items-center gap-1 border ${
                activeOppScore >= 80
                  ? 'bg-amber-100 text-amber-900 border-amber-300 shadow-xs'
                  : activeOppScore >= 65
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                  : 'bg-slate-100 text-slate-700 border-slate-200'
              }`} title={`商业抢楼机会分: ${activeOppScore}/100`}>
                {activeOppScore >= 80 ? '🔥' : activeOppScore >= 65 ? '✨' : '🎯'} {activeOppScore}分
              </span>
            ) : null}
            {activeSafety ? (
              <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-md flex items-center gap-1 border ${
                activeSafety === 'PASSED'
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-rose-50 text-rose-700 border-rose-200'
              }`} title={activeSafety === 'PASSED' ? 'AI 预审员门禁: 安全通过' : 'AI 预审员拦截: 疑似营销敏感'}>
                {activeSafety === 'PASSED' ? '🛡️ 预审通过' : '⚠️ 预审拦截'}
              </span>
            ) : null}
            <StatusBadge hit={hit} isHistory={isHistory} onUpdate={(status) => onStatusUpdate && onStatusUpdate(hit.id, status)} />
            {hit.listener_name && (
              <button
                onClick={() => onFilterByListener && onFilterByListener(hit.listener_id)}
                className="text-xs px-2 py-0.5 rounded-md bg-slate-100 text-slate-500 hover:bg-slate-200 border border-slate-200 transition-colors"
              >
                {hit.listener_name}
              </button>
            )}
            {isForum ? (
              <>
                <span className="text-xs font-semibold bg-emerald-600 text-white px-1.5 py-0.5 rounded flex items-center gap-1">🌐 论坛</span>
                <span className="text-sm font-semibold text-emerald-800">{hit.subreddit || 'Buggies Gone Wild'}</span>
                <span className="text-sm text-slate-400">👤 {hit.author || 'Member'}</span>
              </>
            ) : isX ? (
              <>
                <span className="text-xs font-semibold bg-black text-white px-1.5 py-0.5 rounded flex items-center gap-1">𝕏</span>
                <span className="text-sm font-semibold text-slate-800">@{hit.author || 'tweet'}</span>
              </>
            ) : (
              <>
                <span className="text-sm font-semibold text-orange-500">r/{hit.subreddit || ''}</span>
                <span className="text-sm text-slate-400">u/{hit.author || ''}</span>
              </>
            )}
            <span
              className="inline-flex items-center gap-1.5 text-xs text-slate-600 bg-slate-100/90 border border-slate-200/90 px-2.5 py-0.5 rounded-full hover:bg-slate-200/90 hover:text-slate-800 transition-colors cursor-help shadow-2xs flex-shrink-0"
              title={`【发帖具体时间】\n本地时间: ${timeDetails.full || timeDetails.exact}\n相对时效: ${timeDetails.relative}\n抓取入库: ${hit.created_at ? hit.created_at.replace('T', ' ').slice(0, 19) + ' UTC' : '实时抓取'}`}
            >
              <svg className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="font-semibold text-slate-700">{timeDetails.exact || '刚刚'}</span>
              {timeDetails.relative && (
                <span className="text-slate-500 text-[11px] font-normal">({timeDetails.relative})</span>
              )}
            </span>
            {filterBadge}
          </div>
          {hit.title && (
            <div className="text-sm font-semibold text-slate-800 mb-1 leading-snug line-clamp-1">{hit.title}</div>
          )}
          <div className="text-xs text-slate-500 leading-relaxed line-clamp-2 mb-2.5">{hit.excerpt || ''}</div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-mono bg-amber-50 text-amber-700 border border-amber-100 px-2 py-0.5 rounded-md">{hit.match || ''}</span>
            {activeDraft && (
              <span className="text-xs text-violet-600 bg-violet-50 border border-violet-100 px-2 py-0.5 rounded-md font-medium">
                ⚡ AI 自动融合草稿已生成
              </span>
            )}
          </div>
          {activeDraft ? (
            <div className="mt-2.5 p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 space-y-2">
              <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500 uppercase tracking-wider flex-wrap gap-2">
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-violet-500 animate-pulse"></span>
                  <span className="text-violet-700 font-bold">AI 独立站植入回复</span>
                  {queuedInfo && (
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800 border border-emerald-200">
                      ✓ 已自动排期 {queuedInfo.chrono_reason ? `(${queuedInfo.chrono_reason})` : `(~${queuedInfo.delay_minutes || 5}分钟后)`}
                    </span>
                  )}
                </span>
                <div className="flex items-center gap-1.5 flex-wrap">
                  {!queuedInfo && (
                    <button
                      onClick={handleOneClickEngage}
                      disabled={oneClickLoading}
                      className="px-2.5 py-1 bg-amber-500 hover:bg-amber-600 text-white rounded-lg font-bold transition-all shadow-xs flex items-center gap-1 cursor-pointer disabled:opacity-50 text-[11px] normal-case"
                      title="一键将该草稿推入防封安全队列"
                    >
                      {oneClickLoading ? <span className="spin">⟳</span> : '⚡'}
                      {oneClickLoading ? '正在排期…' : '排入防封队列'}
                    </button>
                  )}
                  <button
                    onClick={async (e) => {
                      e.stopPropagation();
                      await navigator.clipboard.writeText(activeDraft);
                      try {
                        await fetch(`/api/hits/${hit.id}/reply`, {
                          method: 'PATCH',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ reply: activeDraft, listener_id: hit.listener_id }),
                        });
                        if (onStatusUpdate) onStatusUpdate(hit.id, 'replied');
                      } catch (err) {}
                      if (hit.url) {
                        window.open(hit.url, '_blank');
                        alert(isForum
                          ? '✅ BBCode 草稿已复制到剪贴板，状态已更新为「已回复」！论坛原帖已在新标签页打开，直接粘贴 (Ctrl+V / Cmd+V) 即可瞬间发布。'
                          : '✅ AI 营销草稿已复制到剪贴板，状态已更新为「已回复」！原帖已在新标签页打开，在评论框粘贴 (Cmd+V) 即可瞬间发布。'
                        );
                      } else {
                        alert('✅ 草稿已复制到剪贴板！（注：该测试/模拟记录暂无外部原帖 URL）');
                      }
                    }}
                    className={
                      isForum
                        ? "text-emerald-800 bg-emerald-50 hover:bg-emerald-100 border border-emerald-300 font-bold px-2.5 py-1 rounded-lg transition-colors flex items-center gap-1 cursor-pointer text-[11px] normal-case shadow-2xs"
                        : "text-violet-700 bg-violet-50 hover:bg-violet-100 border border-violet-200 font-semibold px-2.5 py-1 rounded-lg transition-colors flex items-center gap-1 cursor-pointer text-[11px] normal-case shadow-2xs"
                    }
                    title={isForum ? "一键复制 BBCode 并直达论坛原帖（浏览器已登录推荐）" : "一键复制文案并在新标签页打开原帖"}
                  >
                    {isForum ? '📋 复制 BBCode 并直达原帖' : '📋 复制并直达原帖'}
                  </button>
                  <button
                    onClick={async (e) => {
                      e.stopPropagation();
                      const targetPlatform = isForum ? '论坛对应讨论帖下' : (isX ? '𝕏 对应推文下' : 'Reddit 对应帖子下');
                      const confirmMsg = isForum
                        ? '确认让系统后台自动提交发布到技术论坛讨论帖？\n(提示: 需在 Vault 中配置论坛 Web Session Cookie。如未配置或浏览器已登录，推荐使用旁边的「📋 复制 BBCode 并直达原帖」)'
                        : `确认将此 AI 草稿立即提交发布到 ${targetPlatform}？`;
                      if (!confirm(confirmMsg)) return;
                      try {
                        const res = await fetch('/api/queue/enqueue', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({
                            hit_id: hit.id,
                            platform: isForum ? 'forum' : (isX ? 'x' : 'reddit'),
                            listener_id: hit.listener_id,
                            subreddit: hit.subreddit || '',
                            post_id: hit.post_id || hit.id,
                            target_id: hit.id,
                            target_url: hit.url || '',
                            author: hit.author || '',
                            reply_text: activeDraft,
                            funnel_tier: activeTier,
                            immediate: true,
                          }),
                        }).then(r => r.json());
                        if (res.ok) {
                          alert(`🚀 发布成功！已同步至 ${isForum ? '技术论坛' : (isX ? '𝕏' : 'Reddit')}。`);
                          if (onStatusUpdate) onStatusUpdate(hit.id, 'replied');
                          const targetUrl = res.tweet_url || res.comment_url || hit.url;
                          if (targetUrl) window.open(targetUrl, '_blank');
                        } else {
                          alert(`发布失败: ${res.error || (isForum ? '请检查 Vault 中的论坛凭据与 Session Cookie' : (isX ? '请检查 Vault 中的 𝕏 账号凭据或 Cookie' : '请检查 Vault 中的 Reddit 账号密码'))}`);
                        }
                      } catch (err) {
                        alert(`请求错误: ${err}`);
                      }
                    }}
                    className={
                      isForum
                        ? "text-emerald-800 hover:text-emerald-900 font-semibold flex items-center gap-0.5 normal-case bg-emerald-50 hover:bg-emerald-100 px-2 py-1 rounded-lg border border-emerald-200 cursor-pointer text-[11px]"
                        : isX
                        ? "text-white bg-black hover:bg-slate-800 font-semibold flex items-center gap-0.5 normal-case px-2 py-1 rounded-lg cursor-pointer text-[11px]"
                        : "text-orange-700 hover:text-orange-800 font-semibold flex items-center gap-0.5 normal-case bg-orange-50 hover:bg-orange-100 px-2 py-1 rounded-lg border border-orange-200 cursor-pointer text-[11px]"
                    }
                  >
                    🚀 立即提交
                  </button>
                </div>
              </div>

              {/* Adaptive Tone A/B Switcher */}
              <div className="flex items-center justify-between bg-slate-100/90 rounded-lg px-2.5 py-1.5 flex-wrap gap-2 border border-slate-200/60">
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">A/B 风格:</span>
                  <button
                    onClick={(e) => handleSwitchStyle(e, 'guru')}
                    disabled={switchingStyle}
                    className={`text-[11px] px-2 py-0.5 rounded-md font-semibold transition-all cursor-pointer ${
                      currentPersonaKey === 'guru'
                        ? 'bg-indigo-600 text-white shadow-xs'
                        : 'bg-white hover:bg-slate-50 text-slate-700 border border-slate-200'
                    }`}
                    title="极客技术干货向：资深诊断专家口吻，拆解电路/机械/固件根因，严谨无废话"
                  >
                    {switchingStyle && currentPersonaKey === 'guru' ? '⟳ 生成中…' : '⚡ 极客干货向'}
                  </button>
                  <button
                    onClick={(e) => handleSwitchStyle(e, 'authentic')}
                    disabled={switchingStyle}
                    className={`text-[11px] px-2 py-0.5 rounded-md font-semibold transition-all cursor-pointer ${
                      currentPersonaKey === 'authentic'
                        ? 'bg-indigo-600 text-white shadow-xs'
                        : 'bg-white hover:bg-slate-50 text-slate-700 border border-slate-200'
                    }`}
                    title="真实折腾测评向：车主/用户第一视角，分享折腾踩坑经历与实测体感，亲切高共鸣"
                  >
                    {switchingStyle && currentPersonaKey === 'authentic' ? '⟳ 生成中…' : '🛠️ 真实测评向'}
                  </button>
                </div>
                {activePersona && (
                  <span className="text-[10px] text-slate-500 font-medium">
                    当前人设: <span className="font-bold text-indigo-700">{activePersona}</span>
                  </span>
                )}
              </div>

              <div className="line-clamp-3 italic text-slate-700 font-sans whitespace-pre-wrap leading-relaxed select-text bg-white p-2.5 rounded-lg border border-slate-100">
                {activeDraft}
              </div>
            </div>
          ) : isRejected ? (
            <div className="mt-2.5 flex items-center justify-between p-3 rounded-xl bg-gradient-to-r from-rose-50/90 to-amber-50/80 border border-rose-200 text-xs gap-3 flex-wrap shadow-2xs">
              <div className="flex items-center gap-2 text-rose-900 font-medium">
                <span className="text-base">🛡️</span>
                <div>
                  <div className="font-semibold text-rose-800">该线索被前置判定拦截淘汰</div>
                  <div className="text-[11px] text-rose-600 font-normal">若属于高价值意向，可一键纠偏复活，系统将沉淀纠偏特征并自动排期</div>
                </div>
              </div>
              <button
                onClick={handleResurrect}
                disabled={resurrecting}
                className="text-xs px-3.5 py-1.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white font-bold rounded-lg transition-all shadow-xs flex items-center gap-1.5 disabled:opacity-60 cursor-pointer"
                title="人工纠偏：复活此线索，自动生成草稿排期，并将纠偏模式反哺 AI 知识库防误杀"
              >
                {resurrecting ? <span className="spin">⟳</span> : '⚡'}
                {resurrecting ? '正在纠偏复活…' : '纠偏复活并排期'}
              </button>
            </div>
          ) : (
            <div className="mt-2.5 flex items-center justify-between p-3 rounded-xl bg-gradient-to-r from-violet-50/80 to-indigo-50/50 border border-violet-100/80 text-xs gap-3 flex-wrap">
              <span className="text-slate-600 flex items-center gap-2 text-xs font-medium">
                <span className="text-base">⚡</span> 尚未生成融合独立站的专业回复草稿
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleOneClickEngage}
                  disabled={oneClickLoading}
                  className="text-xs px-3.5 py-1.5 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-700 hover:to-indigo-700 text-white font-bold rounded-lg transition-all shadow-xs flex items-center gap-1.5 disabled:opacity-60 cursor-pointer"
                  title="一键自动生成草稿、预审门禁并排期发射"
                >
                  {oneClickLoading ? <span className="spin">⟳</span> : '⚡'}
                  {oneClickLoading ? '正在智创与排期…' : '一键 AI 智投排期'}
                </button>
                <button
                  onClick={handleGenerateDraft}
                  disabled={generatingDraft}
                  className="text-xs px-2.5 py-1.5 bg-white hover:bg-slate-100 text-slate-600 font-medium rounded-lg border border-slate-200 transition-colors flex items-center gap-1 disabled:opacity-60 cursor-pointer"
                  title="仅生成草稿查看，不自动排期"
                >
                  {generatingDraft ? <span className="spin">⟳</span> : '✨'}
                  {generatingDraft ? '生成中…' : '仅看草稿'}
                </button>
              </div>
            </div>
          )}
          {steps}
        </div>
        <div className="flex flex-col gap-2 flex-shrink-0 ml-2 pt-1">
          <button
            onClick={() => onOpenReply && onOpenReply(hit)}
            className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold transition-colors flex items-center justify-center gap-1 shadow-xs cursor-pointer"
            title="打开高级回复工作台，微调语气与参数"
          >
            ✍ 细化
          </button>
          <button
            onClick={handleOpenDm}
            className="text-xs px-3 py-1.5 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 font-semibold transition-colors flex items-center justify-center gap-1 cursor-pointer"
            title="1v1 私信截流：AI 自动生成高转化私聊话术并直达官方私信窗口"
          >
            ✉️ 私信
          </button>
          {hit.url ? (
            <a
              href={hit.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-medium transition-colors cursor-pointer"
              title="新标签页打开原始帖子"
            >
              ↗ 原帖
            </a>
          ) : (
            <span
              className="flex items-center justify-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-slate-100 text-slate-400 font-medium opacity-50 cursor-not-allowed select-none"
              title="该条记录暂无外部原帖 URL（测试或模拟数据）"
            >
              ↗ 无原帖
            </span>
          )}
          <button
            onClick={() => onOpenThread && onOpenThread(hit.post_id || hit.id, hit.listener_id || '', hit.id)}
            className="text-[11px] px-2 py-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
          >
            上下文
          </button>
        </div>
      </div>

      {/* 1v1 Direct Message (DM) Outreach & Playbook Modal */}
      <ConversionDmModal
        isOpen={showDmModal}
        onClose={() => setShowDmModal(false)}
        loading={loadingDm}
        data={dmData}
      />
    </div>
  );
}
