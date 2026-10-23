import { useState, useEffect, useRef } from 'react';
import { useApp } from '../../context.jsx';
import { apiFetch } from '../../api.js';
import { getHitTimeDetails } from '../../utils.js';

const TONES = ['helpful', 'casual', 'professional', 'direct'];

export default function ReplyPanel({ hit, onClose, onSaved }) {
  const { cfg, setCfg, addToast, setActiveTab } = useApp();
  const [tone, setTone] = useState('helpful');
  const [funnelTier, setFunnelTier] = useState(hit?.funnel_tier || 3);
  const [reply, setReply] = useState(hit?.reply_draft || '');
  const [submitting, setSubmitting] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [opportunityScore, setOpportunityScore] = useState(hit?.opportunity_score || 50);
  const [safetyResult, setSafetyResult] = useState(
    hit?.safety_verdict ? { verdict: hit.safety_verdict, safety_score: hit.safety_score || 8, reason: '' } : null
  );
  const [evaluatingSafety, setEvaluatingSafety] = useState(false);

  const isX = hit?.platform === 'x' || hit?.platform === 'twitter' || (hit?.url && (hit.url.includes('x.com') || hit.url.includes('twitter.com')));
  const isForum = hit?.platform === 'forum' || hit?.platform === 'vbulletin' || hit?.platform === 'phpbb' || hit?.platform === 'xenforo' || (!isX && hit?.url && (hit.url.includes('buggiesgonewild.com') || hit.url.includes('/forum') || hit.url.includes('thread') || hit.url.includes('showpost')));
  const platformName = isForum ? '垂直技术论坛' : (isX ? '𝕏 (Twitter)' : 'Reddit');

  async function checkSafety(currentText) {
    const textToCheck = currentText || reply;
    if (!textToCheck.trim()) return;
    setEvaluatingSafety(true);
    try {
      const res = await apiFetch('/api/reply/evaluate_safety', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: textToCheck,
          title: hit?.title || '',
          excerpt: hit?.excerpt || '',
          platform: isForum ? 'forum' : (isX ? 'x' : 'reddit'),
          listener_id: hit?.listener_id,
        })
      });
      setSafetyResult(res);
      addToast(res.verdict === 'PASSED' ? `🛡️ AI 预审员通过 (${res.safety_score}/10)` : `⚠️ AI 预审拦截: ${res.reason}`, res.verdict === 'PASSED' ? 'green' : 'amber');
    } catch (e) {
      console.error('Safety check failed:', e);
    } finally {
      setEvaluatingSafety(false);
    }
  }

  async function postNow() {
    if (!hit || !reply.trim()) return;
    setSubmitting(true);
    const res = await apiFetch('/api/queue/enqueue', {
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
        reply_text: reply,
        funnel_tier: funnelTier,
        opportunity_score: opportunityScore,
        safety_verdict: safetyResult?.verdict || hit?.safety_verdict || 'PASSED',
        immediate: true,
      }),
    });
    setSubmitting(false);
    if (res.ok) {
      addToast(`🚀 已成功发布至 ${platformName}！`, 'green');
      if (onSaved) onSaved(hit.id, reply);
      const openUrl = res.tweet_url || res.comment_url || hit.url;
      if (openUrl) {
        window.open(openUrl, '_blank');
      }
    } else {
      addToast(`发布失败: ${res.error || (isForum ? '请检查论坛源或讨论帖状态' : (isX ? '请检查 Vault 中的 𝕏 账号密钥或 Cookie' : '请检查 Vault 中的 Reddit 账号密码'))}`, 'red');
    }
  }

  async function addToQueue() {
    if (!hit || !reply.trim()) return;
    const res = await apiFetch('/api/queue/enqueue', {
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
        reply_text: reply,
        funnel_tier: funnelTier,
        opportunity_score: opportunityScore,
        safety_verdict: safetyResult?.verdict || hit?.safety_verdict || 'PASSED',
        delay_seconds: isForum ? 600 : (isX ? 180 : 300),
        immediate: false,
      }),
    });
    if (res.ok) {
      addToast(`⏰ 已推入 ${platformName} 防封安全队列，将按风控频率自动排期执行`, 'blue');
      if (onSaved) onSaved(hit.id, reply);
    } else {
      addToast('加入队列失败', 'red');
    }
  }
  const [showResult, setShowResult] = useState(!!(hit?.reply_draft));
  const productSaveRef = useRef(null);

  // Multi-channel & Visual Asset states
  const [activeChannel, setActiveChannel] = useState(isForum ? 'bbcode' : (isX ? 'x' : 'reddit'));
  const [channels, setChannels] = useState({ reddit: '', bbcode: '', op_comment: '', x: '' });
  const [matchedAsset, setMatchedAsset] = useState(null);
  const [availableAssets, setAvailableAssets] = useState([]);
  const [selectedAssetId, setSelectedAssetId] = useState('auto');

  async function ensureChannelsFormatted(text, overrideAssetId, channelToSet) {
    if (!text || !hit) return;
    const targetChan = channelToSet || activeChannel;
    const assetIdToUse = overrideAssetId !== undefined
      ? (overrideAssetId === 'auto' ? null : overrideAssetId)
      : (selectedAssetId === 'auto' ? null : selectedAssetId);

    try {
      const res = await apiFetch('/api/reply/format_channels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text,
          title: hit.title || '',
          excerpt: hit.excerpt || '',
          listener_id: hit.listener_id,
          asset_id: assetIdToUse,
        }),
      });
      if (res && res.channels) {
        setChannels(res.channels);
        setMatchedAsset(res.matched_asset || null);
        if (res.available_assets) {
          setAvailableAssets(res.available_assets);
        }
        if (res.channels[targetChan]) {
          setReply(res.channels[targetChan]);
        }
      }
    } catch (e) {
      console.error('Failed to format channels:', e);
    }
  }

  async function handleAssetChange(val) {
    setSelectedAssetId(val);
    await ensureChannelsFormatted(reply, val);
  }

  useEffect(() => {
    if (hit?.reply_draft) {
      setReply(hit.reply_draft);
      setShowResult(true);
      ensureChannelsFormatted(hit.reply_draft);
    }
    if (hit?.funnel_tier) {
      setFunnelTier(hit.funnel_tier);
    }
  }, [hit]);

  function debounceSaveProduct(val) {
    setCfg(prev => ({ ...prev, product_context: val }));
    clearTimeout(productSaveRef.current);
    productSaveRef.current = setTimeout(() => {
      apiFetch('/api/settings/product_context', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: val }),
      });
    }, 800);
  }

  function selectChannel(chan) {
    setActiveChannel(chan);
    if (channels[chan]) {
      setReply(channels[chan]);
    } else if (reply.trim()) {
      ensureChannelsFormatted(reply, undefined, chan);
    }
  }

  async function generateReply() {
    if (!hit) return;
    const lst = (cfg.listeners || []).find(l => l.id === hit.listener_id);
    const credId = lst?.ai_credential_id || null;
    const assetIdToUse = selectedAssetId === 'auto' ? null : selectedAssetId;

    setGenerating(true);
    const result = await apiFetch('/api/reply/draft', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: hit.title || '',
        excerpt: hit.excerpt || '',
        subreddit: hit.subreddit || '',
        product_context: cfg.product_context || '',
        tone,
        funnel_tier: funnelTier,
        credential_id: credId,
        listener_id: hit.listener_id,
        platform: isForum ? 'forum' : (isX ? 'x' : 'reddit'),
        preferred_channel: activeChannel,
        asset_id: assetIdToUse,
      }),
    });
    setGenerating(false);
    if (result.error) { addToast(result.error, 'red'); return; }
    setReply(result.reply);
    setShowResult(true);
    if (result.opportunity_score) {
      setOpportunityScore(result.opportunity_score);
    }
    if (result.safety_details) {
      setSafetyResult(result.safety_details);
    } else if (result.safety_verdict) {
      setSafetyResult({ verdict: result.safety_verdict, safety_score: result.safety_score, reason: '' });
    }
    if (result.channels) {
      setChannels(result.channels);
    }
    if (result.matched_asset !== undefined) {
      setMatchedAsset(result.matched_asset);
    }
    if (result.available_assets) {
      setAvailableAssets(result.available_assets);
    }
  }

  async function copyReply() {
    await navigator.clipboard.writeText(reply).catch(() => {});
    addToast('Copied to clipboard', 'green');
    await saveReplyDraft();
  }

  async function copyAndDirectOpenForum() {
    if (!hit || !reply.trim()) return;
    try {
      await navigator.clipboard.writeText(reply);
    } catch (e) {
      console.error('Clipboard copy failed:', e);
    }
    await saveReplyDraft();
    addToast('📋 已复制 BBCode 草稿并标记为已回复！原帖已在新标签页打开，按 Ctrl+V 粘贴即可提交！', 'green');
    if (hit.url) {
      window.open(hit.url, '_blank');
    }
    if (onClose) onClose();
  }

  async function saveReplyDraft() {
    if (!hit) return;
    await apiFetch(`/api/hits/${hit.id}/reply`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reply, listener_id: hit.listener_id }),
    });
    if (onSaved) onSaved(hit.id, reply);
    addToast('Draft saved · status → Replied', 'blue');
  }

  if (!hit) return null;

  return (
    <>
      <div className="panel-backdrop" onClick={onClose}></div>
      <div className="side-panel">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
          <div>
            <h2 className="font-semibold text-slate-900">Draft Reply</h2>
            <p className="text-xs text-slate-400 mt-0.5">Claude writes a context-aware, non-spammy reply</p>
          </div>
          <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-400 text-xl">×</button>
        </div>
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Post context */}
          {(() => {
            const timeDetails = getHitTimeDetails(hit);
            return (
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-2">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  {isForum ? (
                    <div className="text-xs font-semibold text-emerald-800 flex items-center gap-1.5">
                      <span className="bg-emerald-600 text-white text-[10px] px-1.5 py-0.2 rounded font-bold">🌐 论坛</span>
                      <span>{hit.subreddit ? `[${hit.subreddit}]` : 'Technical Forum'}</span>
                      {hit.author && <span className="text-slate-500 font-normal">by @{hit.author}</span>}
                    </div>
                  ) : isX ? (
                    <div className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
                      <span className="bg-black text-white text-[10px] px-1.5 py-0.2 rounded font-bold">𝕏</span>
                      <span>@{hit.author || 'tweet'}</span>
                    </div>
                  ) : (
                    <div className="text-xs font-semibold text-orange-500">r/{hit.subreddit}</div>
                  )}
                  <span
                    className="inline-flex items-center gap-1 text-[11px] text-slate-600 bg-white border border-slate-200 px-2 py-0.5 rounded cursor-help shadow-2xs"
                    title={`【发帖具体时间】\n本地时间: ${timeDetails.full || timeDetails.exact}\n相对时效: ${timeDetails.relative}\n抓取入库: ${hit.created_at || '实时'}`}
                  >
                    <svg className="w-3 h-3 text-slate-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span className="font-medium text-slate-700">{timeDetails.exact || '刚刚'}</span>
                    {timeDetails.relative && <span className="text-slate-400">({timeDetails.relative})</span>}
                  </span>
                </div>
                <div className="text-sm font-medium text-slate-800 leading-snug">{hit.title || ''}</div>
                <div className="text-xs text-slate-500 line-clamp-3">{hit.excerpt || ''}</div>
              </div>
            );
          })()}

          {/* Product context */}
          <div>
            <label className="text-sm font-medium text-slate-700 block mb-1.5">
              Your product / context{' '}
              <span className="text-xs font-normal text-slate-400 ml-1">saved automatically</span>
            </label>
            <textarea
              rows="3"
              className="inp text-sm"
              placeholder="What are you selling? What problem does it solve? Who is it for? (used in all replies)"
              value={cfg.product_context || ''}
              onChange={e => debounceSaveProduct(e.target.value)}
            />
          </div>

          {/* Promotion Warrior Funnel Tier */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-sm font-medium text-slate-700">Promotion Warrior 流量漏斗层级</span>
              <span className="text-xs text-slate-400">自动侦测与精准打击</span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {[
                { tier: 1, label: '🎯 Tier 1 显性转化', desc: 'Direct Close · 直接解答并作为最佳选择' },
                { tier: 2, label: '⚡ Tier 2 侧翼切入', desc: 'Side Attack · 共情痛点 -> 引申客观工具' },
                { tier: 3, label: '💡 Tier 3 干货养号', desc: 'Value First · 100%干货解答 -> 隐晦/不提' },
              ].map(t => (
                <button
                  key={t.tier}
                  type="button"
                  onClick={() => setFunnelTier(t.tier)}
                  className={`text-left p-2.5 rounded-xl border transition-all ${
                    funnelTier === t.tier
                      ? 'bg-slate-900 text-white border-slate-900 shadow-sm'
                      : 'bg-white text-slate-700 border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <div className="text-xs font-semibold">{t.label}</div>
                  <div className={`text-[10px] mt-1 line-clamp-2 ${funnelTier === t.tier ? 'text-slate-300' : 'text-slate-500'}`}>{t.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Tone */}
          <div>
            <div className="text-sm font-medium text-slate-700 mb-2">Tone</div>
            <div className="flex gap-2 flex-wrap">
              {TONES.map(t => (
                <button
                  key={t}
                  onClick={() => setTone(t)}
                  className={`text-xs px-3 py-1.5 rounded-lg border font-medium transition-all capitalize ${
                    tone === t
                      ? 'bg-slate-900 text-white border-slate-900'
                      : 'bg-white text-slate-600 border-slate-200 hover:border-slate-400'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/* Generate */}
          <button
            onClick={generateReply}
            disabled={generating}
            className="w-full px-4 py-2.5 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-sm font-medium transition-colors flex items-center justify-center gap-2 disabled:opacity-60"
          >
            {generating ? (
              <><span className="spin">⟳</span> Generating…</>
            ) : (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="m13 2-2 2.5h3L12 15" /><path d="M9.42 7.89 3.5 14h4l-2 8 9.08-10.11H11l2-8z" />
                </svg>
                Generate Reply
              </>
            )}
          </button>

          {/* Generated reply */}
          {showResult && (
            <div className="space-y-3.5">
              {/* AI 预审员防封门禁 & 机会评分栏 */}
              <div className="flex items-center justify-between p-2.5 rounded-xl border bg-slate-50 border-slate-200">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`text-xs font-semibold px-2.5 py-1 rounded-lg flex items-center gap-1 border ${
                    opportunityScore >= 80 ? 'bg-amber-100 text-amber-900 border-amber-300' :
                    opportunityScore >= 65 ? 'bg-emerald-50 text-emerald-800 border-emerald-200' :
                    'bg-slate-100 text-slate-700 border-slate-200'
                  }`} title={`商业抢楼机会分: ${opportunityScore}/100`}>
                    {opportunityScore >= 80 ? '🔥' : opportunityScore >= 65 ? '✨' : '🎯'} 机会分: {opportunityScore}/100 ({opportunityScore >= 80 ? '黄金高潜' : opportunityScore >= 65 ? '高价值' : '常规'})
                  </span>

                  <span className={`text-xs font-semibold px-2.5 py-1 rounded-lg flex items-center gap-1 border ${
                    (safetyResult?.verdict || hit?.safety_verdict || 'PASSED') === 'PASSED'
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : 'bg-rose-50 text-rose-700 border-rose-200 animate-pulse'
                  }`} title={safetyResult?.reason || 'AI 预审员三维防封门禁'}>
                    {(safetyResult?.verdict || hit?.safety_verdict || 'PASSED') === 'PASSED'
                      ? `🛡️ 预审门禁通过 (${safetyResult?.safety_score || hit?.safety_score || 8}/10)`
                      : `⚠️ 疑似营销敏感 (${safetyResult?.safety_score || hit?.safety_score || 4}/10)`}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => checkSafety(reply)}
                  disabled={evaluatingSafety}
                  className="text-xs px-2.5 py-1 rounded-lg bg-white border border-slate-200 hover:bg-slate-100 text-slate-700 font-medium transition-colors flex items-center gap-1 cursor-pointer shadow-xs disabled:opacity-60"
                >
                  {evaluatingSafety ? <><span className="spin">⟳</span> 审查中</> : '🔍 重新预审'}
                </button>
              </div>

              {safetyResult?.reason && (
                <div className="text-[11px] text-slate-600 bg-amber-50/60 p-2.5 rounded-lg border border-amber-200/80 leading-relaxed">
                  <span className="font-bold text-slate-800">🛡️ AI 预审员评注：</span>{safetyResult.reason}
                </div>
              )}

              {/* Visual Asset Selector & Preview Banner */}
              <div className="bg-gradient-to-r from-blue-50/80 via-indigo-50/50 to-slate-50 border border-blue-200/80 rounded-xl p-3 space-y-2 shadow-xs">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="w-10 h-10 rounded-lg border border-blue-200 bg-white overflow-hidden flex-shrink-0 flex items-center justify-center">
                      {matchedAsset && matchedAsset.image_url ? (
                        <img
                          src={matchedAsset.image_url}
                          alt={matchedAsset.name}
                          className="w-full h-full object-cover"
                          onError={(e) => { e.target.style.display = 'none'; if (e.target.nextSibling) e.target.nextSibling.style.display = 'flex'; }}
                        />
                      ) : null}
                      <span className={`w-full h-full ${matchedAsset?.image_url ? 'hidden' : 'flex'} items-center justify-center text-sm bg-blue-50 text-blue-500`}>
                        {matchedAsset ? '📊' : '📝'}
                      </span>
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-slate-800 flex items-center gap-1.5 truncate">
                        <span className="text-blue-600 font-bold">🖼️ 图表资产:</span>
                        <span className="truncate">{matchedAsset ? matchedAsset.name : '纯文字模式 (未附加图表)'}</span>
                      </div>
                      <div className="text-[10px] text-slate-500 truncate mt-0.5">
                        {matchedAsset ? (matchedAsset.citation_source || '权威学术数据源') : '点击下方下拉菜单可指定插入工程图表'}
                      </div>
                    </div>
                  </div>
                  <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full flex-shrink-0 border ${
                    selectedAssetId === 'auto'
                      ? (matchedAsset ? 'text-blue-700 bg-blue-100/90 border-blue-200' : 'text-slate-600 bg-slate-100 border-slate-200')
                      : (selectedAssetId === 'none' ? 'text-amber-700 bg-amber-100 border-amber-200' : 'text-purple-700 bg-purple-100 border-purple-200')
                  }`}>
                    {selectedAssetId === 'auto' ? (matchedAsset ? '🎯 意图命中' : '无匹配') : (selectedAssetId === 'none' ? '纯文字' : '✏️ 手动指定')}
                  </span>
                </div>

                {/* Quick Asset Switch Dropdown */}
                {availableAssets.length > 0 && (
                  <div className="flex items-center gap-2 pt-1.5 border-t border-blue-200/50">
                    <span className="text-[11px] text-slate-500 flex-shrink-0 font-medium">切换图表:</span>
                    <select
                      value={selectedAssetId}
                      onChange={(e) => handleAssetChange(e.target.value)}
                      className="w-full text-xs bg-white border border-blue-200 rounded-lg px-2 py-1 text-slate-700 font-medium focus:ring-1 focus:ring-blue-500 focus:outline-none cursor-pointer"
                    >
                      <option value="auto">🎯 智能意图自动匹配 {matchedAsset ? `(当前: ${matchedAsset.name})` : ''}</option>
                      <option value="none">🚫 纯文字回复 (不插入图表/外链)</option>
                      {availableAssets.map(a => (
                        <option key={a.id} value={a.id}>
                          📊 {a.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {/* Multi-Channel Switching Tabs */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
                    多渠道转化输出 (Multi-Channel Formatter)
                  </span>
                  {activeChannel === 'x' && (
                    <span className={`text-xs font-mono ${reply.length > 280 ? 'text-rose-600 font-bold' : 'text-slate-400'}`}>
                      {reply.length}/280 字符 (建议 ≤220)
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-4 gap-1.5 p-1 bg-slate-100 rounded-xl border border-slate-200">
                  <button
                    type="button"
                    onClick={() => selectChannel('reddit')}
                    className={`py-1.5 px-2 rounded-lg text-xs font-medium transition-all text-center truncate ${
                      activeChannel === 'reddit'
                        ? 'bg-white text-orange-600 shadow-xs font-semibold'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    📝 Reddit Markdown
                  </button>
                  <button
                    type="button"
                    onClick={() => selectChannel('bbcode')}
                    className={`py-1.5 px-2 rounded-lg text-xs font-medium transition-all text-center truncate ${
                      activeChannel === 'bbcode'
                        ? 'bg-white text-indigo-600 shadow-xs font-semibold'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    🏛️ 论坛 BBCode
                  </button>
                  <button
                    type="button"
                    onClick={() => selectChannel('op_comment')}
                    className={`py-1.5 px-2 rounded-lg text-xs font-medium transition-all text-center truncate ${
                      activeChannel === 'op_comment'
                        ? 'bg-white text-emerald-700 shadow-xs font-semibold'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    💬 OP 首评连击
                  </button>
                  <button
                    type="button"
                    onClick={() => selectChannel('x')}
                    className={`py-1.5 px-2 rounded-lg text-xs font-medium transition-all text-center truncate ${
                      activeChannel === 'x'
                        ? 'bg-white text-black shadow-xs font-semibold'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    𝕏 极简短推
                  </button>
                </div>

                {/* Channel Guide Tips */}
                {activeChannel === 'bbcode' && (
                  <div className="text-[11px] text-indigo-700 bg-indigo-50/70 border border-indigo-200/80 rounded-lg p-2 leading-relaxed">
                    💡 <strong>老牌垂直论坛专享 (vBulletin / phpBB / BuggiesGoneWild):</strong> 已自动生成 <code>[URL=...][IMG]...[/IMG][/URL]</code> 图片包裹外链与学术引用。车友点击大图直接跳转独立站落地页，完全规避硬文本删帖。
                  </div>
                )}
                {activeChannel === 'op_comment' && (
                  <div className="text-[11px] text-emerald-800 bg-emerald-50/70 border border-emerald-200/80 rounded-lg p-2 leading-relaxed">
                    💡 <strong>Reddit OP 首评连击法:</strong> 建议先以 Image Post 纯图形式发帖（获取移动端全屏曝光），发帖后 30 秒内以 OP 身份粘贴此长文跟帖，带出数据源独立站链接收割置顶与精准流量。
                  </div>
                )}
              </div>

              {isForum && (
                <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-900 space-y-2 shadow-2xs">
                  <div className="flex items-start gap-2 leading-relaxed">
                    <span className="text-base flex-shrink-0">💡</span>
                    <div>
                      <span className="font-bold">浏览器已登录论坛模式：</span>AI 已为您生成垂直论坛专属的 <strong>BBCode 格式</strong>。直接点击下方<strong>「📋 复制 BBCode 并直达论坛回帖」</strong>，将在新标签页打开原帖回帖区，按 <kbd className="px-1.5 py-0.5 bg-white border border-emerald-300 rounded font-mono text-[10px]">Ctrl+V / Cmd+V</kbd> 粘贴即可秒发（免人机验证零风控）！
                    </div>
                  </div>
                  <div className="pt-2 border-t border-emerald-200/60 flex items-center justify-between">
                    <span className="text-[11px] text-emerald-700">如需后台 100% 全自动无人值守代发：</span>
                    <button
                      type="button"
                      onClick={() => {
                        if (onClose) onClose();
                        setActiveTab('vault');
                      }}
                      className="text-xs px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-medium transition-colors flex items-center gap-1 shadow-xs cursor-pointer"
                    >
                      🔑 去 Vault 录入论坛 Cookie
                    </button>
                  </div>
                </div>
              )}

              <textarea
                rows="6"
                className="inp text-sm font-mono text-slate-800 bg-white"
                value={reply}
                onChange={e => setReply(e.target.value)}
              />

              <div className="flex gap-2">
                <button
                  onClick={copyReply}
                  className="flex-1 px-3 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-sm font-medium transition-colors flex items-center justify-center gap-1.5"
                >
                  <span>📋</span> 复制当前渠道内容
                </button>
                <button
                  onClick={saveReplyDraft}
                  className="px-3 py-2 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 rounded-xl text-sm font-medium transition-colors"
                >
                  Save draft
                </button>
                <a
                  href={hit.url || '#'}
                  target="_blank"
                  rel="noopener"
                  className="px-3 py-2 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 rounded-xl text-sm font-medium transition-colors"
                >
                  ↗ {isForum ? 'Open thread' : (isX ? 'Open tweet' : 'Open post')}
                </a>
              </div>

              {/* One-click post & queue */}
              <div className="pt-2 border-t border-slate-100">
                {isForum ? (
                  <div className="space-y-2">
                    <button
                      type="button"
                      onClick={copyAndDirectOpenForum}
                      className="w-full px-4 py-3 bg-gradient-to-r from-emerald-600 via-teal-600 to-cyan-600 hover:from-emerald-700 hover:to-teal-700 text-white rounded-xl text-sm font-bold transition-all shadow-md flex items-center justify-center gap-2 cursor-pointer"
                    >
                      <span>📋</span> 复制 BBCode 并直达论坛回帖 (浏览器已登录 · 推荐)
                    </button>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={postNow}
                        disabled={submitting}
                        className="flex-1 px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-medium transition-colors flex items-center justify-center gap-1.5 disabled:opacity-60 cursor-pointer"
                        title="需在 Vault 中配置论坛 Web Session Cookie"
                      >
                        {submitting ? <span className="spin">⟳</span> : '🤖'} 后台自动提交 (需 Cookie)
                      </button>
                      <button
                        type="button"
                        onClick={addToQueue}
                        className="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-medium transition-colors flex items-center justify-center gap-1 cursor-pointer"
                      >
                        ⏰ 加入排期队列
                      </button>
                    </div>
                  </div>
                ) : isX ? (
                  <div className="flex gap-2">
                    <button
                      onClick={postNow}
                      disabled={submitting}
                      className="flex-1 px-3 py-2.5 bg-black hover:bg-slate-800 text-white rounded-xl text-sm font-semibold transition-all shadow-sm flex items-center justify-center gap-1.5 disabled:opacity-60 cursor-pointer"
                    >
                      {submitting ? <span className="spin">⟳</span> : '🚀'} 立即发布至 𝕏
                    </button>
                    <button
                      onClick={addToQueue}
                      className="px-3 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-sm font-medium transition-colors flex items-center justify-center gap-1 cursor-pointer"
                    >
                      ⏰ 加入排期队列
                    </button>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <button
                      onClick={postNow}
                      disabled={submitting}
                      className="flex-1 px-3 py-2.5 bg-gradient-to-r from-orange-500 to-amber-600 hover:from-orange-600 hover:to-amber-700 text-white rounded-xl text-sm font-medium transition-all shadow-sm flex items-center justify-center gap-1.5 disabled:opacity-60 cursor-pointer"
                    >
                      {submitting ? <span className="spin">⟳</span> : '🚀'} 立即发布至 Reddit
                    </button>
                    <button
                      onClick={addToQueue}
                      className="px-3 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-sm font-medium transition-colors flex items-center justify-center gap-1 cursor-pointer"
                    >
                      ⏰ 加入排期队列
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
