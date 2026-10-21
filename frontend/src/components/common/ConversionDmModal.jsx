import React, { useState, useEffect } from 'react';

export default function ConversionDmModal({ isOpen, onClose, loading, data }) {
  const [activeTab, setActiveTab] = useState('quick'); // 'quick' | 'playbook'
  const [currentSubject, setCurrentSubject] = useState('');
  const [currentMessage, setCurrentMessage] = useState('');
  const [copiedKey, setCopiedKey] = useState(null);

  useEffect(() => {
    if (data) {
      setCurrentSubject(data.subject || '');
      setCurrentMessage(data.message || '');
      setActiveTab('quick');
    }
  }, [data]);

  if (!isOpen) return null;

  const author = data?.author || 'friend';
  const platform = data?.platform || 'reddit';
  const isX = platform === 'x' || platform === 'twitter';
  const authorDisplay = isX ? `@${author}` : `u/${author}`;

  async function copyText(text, key) {
    await navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 1800);
  }

  function applyRoundToMessage(draft) {
    setCurrentMessage(draft);
    setActiveTab('quick');
  }

  const composeUrlWithCurrent = () => {
    if (!data) return '';
    if (isX) {
      const clean = author.replace('@', '').trim();
      return clean && clean !== 'unknown' ? `https://x.com/${clean}` : 'https://x.com/messages/compose';
    }
    const clean = author.replace('u/', '').trim();
    const sub = encodeURIComponent(currentSubject || data.subject || 'Re: question');
    const msg = encodeURIComponent(currentMessage || data.message || '');
    return clean && clean !== 'unknown'
      ? `https://www.reddit.com/message/compose?to=${clean}&subject=${sub}&message=${msg}`
      : 'https://www.reddit.com/message/compose';
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full p-6 space-y-4 border border-slate-200 animate-in fade-in zoom-in-95 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-100 flex-shrink-0">
          <div className="flex items-center gap-2">
            <span className="p-1.5 bg-indigo-100 text-indigo-700 rounded-lg text-base">✉️</span>
            <div>
              <h3 className="text-sm font-bold text-slate-900">1v1 聊单转化与极速私信驾驶舱</h3>
              <p className="text-xs text-slate-500">向 {authorDisplay} 发送专属定制破冰话术与转化心智流</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-lg hover:bg-slate-100 flex items-center justify-center text-slate-400 hover:text-slate-600 text-sm cursor-pointer"
          >
            ✕
          </button>
        </div>

        {/* Loading State */}
        {loading ? (
          <div className="py-16 text-center text-slate-500 text-xs flex items-center justify-center gap-2">
            <span className="spin">⟳</span> 正在通过 AI 匹配痛点并生成 3 轮聊单策略与专属短链…
          </div>
        ) : data ? (
          <div className="space-y-3.5 overflow-y-auto flex-1 pr-1">
            {/* Dynamic Routed Tool Banner */}
            {data.routed_tool && (
              <div className="flex items-center justify-between bg-indigo-50/80 border border-indigo-100 rounded-xl px-3.5 py-2 text-xs text-indigo-900 flex-wrap gap-2">
                <span className="flex items-center gap-1.5 font-medium">
                  <span>🎯 智能匹配落地工具:</span>
                  <span className="font-bold text-indigo-700">{data.routed_tool.tool_name}</span>
                </span>
                {data.short_url && (
                  <span className="text-[11px] font-mono text-indigo-700 bg-white px-2 py-0.5 rounded-md border border-indigo-200">
                    🔗 {data.short_url}
                  </span>
                )}
              </div>
            )}

            {/* Mode Switch Tabs */}
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setActiveTab('quick')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                    activeTab === 'quick' ? 'bg-indigo-600 text-white shadow-xs' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  ⚡ 极速直发模式
                </button>
                <button
                  onClick={() => setActiveTab('playbook')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-1 ${
                    activeTab === 'playbook' ? 'bg-indigo-600 text-white shadow-xs' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  <span>📋 三轮递进聊单心智流</span>
                  {data.playbook && <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>}
                </button>
              </div>
              <span className="text-[11px] text-slate-400">
                {activeTab === 'quick' ? '快速微调发件' : '多轮递进，逼单收割'}
              </span>
            </div>

            {/* Tab 1: Quick Send */}
            {activeTab === 'quick' && (
              <div className="space-y-3">
                {currentSubject !== undefined && (
                  <div>
                    <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block mb-1">
                      私信主题 (Subject):
                    </label>
                    <input
                      type="text"
                      value={currentSubject}
                      onChange={(e) => setCurrentSubject(e.target.value)}
                      className="w-full text-xs bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-800 font-medium focus:bg-white focus:outline-indigo-500"
                    />
                  </div>
                )}

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                      私信正文 (可直接编辑 / 点下方发送预填):
                    </label>
                    <span className="text-[11px] text-slate-400">{currentMessage.length} 字符</span>
                  </div>
                  <textarea
                    rows={5}
                    value={currentMessage}
                    onChange={(e) => setCurrentMessage(e.target.value)}
                    className="w-full text-xs bg-slate-50 border border-slate-200 rounded-lg p-3 text-slate-800 leading-relaxed font-sans focus:bg-white focus:outline-indigo-500"
                    placeholder="输入或从三轮聊单中选择话术填入…"
                  />
                </div>

                <div className="bg-amber-50 border border-amber-200 rounded-xl p-2.5 text-[11px] text-amber-800 leading-relaxed">
                  🛡️ <strong>防封安全建议</strong>: 1v1 私信转化率极高（约 30%~45%）。建议每日同一账号私信控制在 10 条以内，首选真诚同行探讨，勿做推销狂轰滥炸。
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                  <button
                    onClick={() => copyText(currentMessage, 'msg_quick')}
                    className="px-3.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold rounded-lg text-xs transition-colors cursor-pointer"
                  >
                    {copiedKey === 'msg_quick' ? '✓ 已复制' : '📋 复制文案'}
                  </button>
                  <a
                    href={composeUrlWithCurrent()}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => copyText(currentMessage, 'msg_quick')}
                    className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold rounded-lg text-xs transition-colors flex items-center gap-1.5 shadow-xs cursor-pointer"
                  >
                    🚀 直达官方私信窗口 ↗
                  </a>
                </div>
              </div>
            )}

            {/* Tab 2: 3-Stage Conversational Playbook */}
            {activeTab === 'playbook' && data.playbook && (
              <div className="space-y-3.5">
                {/* Profile info */}
                {data.playbook.target_profile && (
                  <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-700">意向定级:</span>
                      <span className="px-2 py-0.5 bg-emerald-100 text-emerald-800 rounded font-bold text-[11px]">
                        {data.playbook.target_profile.intent_level || 'Tier 1'}
                      </span>
                    </div>
                    <div className="text-slate-600">
                      <span className="font-semibold text-slate-700">攻坚心智:</span> {data.playbook.target_profile.recommended_angle}
                    </div>
                  </div>
                )}

                {/* 3 Rounds */}
                <div className="space-y-2.5">
                  {(data.playbook.rounds || []).map((r, idx) => (
                    <div key={idx} className="p-3 bg-white border border-slate-200 rounded-xl hover:border-indigo-300 transition-all space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="w-5 h-5 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-[11px]">
                            {r.round}
                          </span>
                          <span className="text-xs font-bold text-slate-800">{r.title}</span>
                          <span className="text-[10px] text-slate-400">({r.goal})</span>
                          {r.round === 2 && (
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">
                              🧲 Lead Magnet 诱饵
                            </span>
                          )}
                          {r.round === 3 && (
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                              🎯 动态 UTM 归因
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => copyText(r.draft, `round_${idx}`)}
                            className="px-2 py-1 text-[11px] bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-md font-medium cursor-pointer"
                          >
                            {copiedKey === `round_${idx}` ? '✓ 已复制' : '复制'}
                          </button>
                          <button
                            onClick={() => applyRoundToMessage(r.draft)}
                            className="px-2.5 py-1 text-[11px] bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 rounded-md font-bold cursor-pointer"
                          >
                            ⚡ 填入发信框
                          </button>
                        </div>
                      </div>
                      <div className="text-xs text-slate-700 bg-slate-50 p-2.5 rounded-lg border border-slate-100 leading-relaxed font-sans">
                        "{r.draft}"
                      </div>
                    </div>
                  ))}
                </div>

                {/* Objections */}
                {data.playbook.objections && data.playbook.objections.length > 0 && (
                  <div className="space-y-2 pt-2 border-t border-slate-100">
                    <h4 className="text-xs font-bold text-slate-700">💡 常见异议应对速查</h4>
                    <div className="grid grid-cols-1 gap-2">
                      {data.playbook.objections.map((obj, i) => (
                        <div key={i} className="p-2.5 bg-amber-50/50 border border-amber-200/70 rounded-lg text-xs space-y-1">
                          <div className="font-semibold text-amber-900 flex items-center justify-between">
                            <span>❓ {obj.objection}</span>
                            <button
                              onClick={() => copyText(obj.response, `obj_${i}`)}
                              className="text-[10px] text-amber-700 hover:underline cursor-pointer"
                            >
                              {copiedKey === `obj_${i}` ? '✓ 已复制' : '复制回答'}
                            </button>
                          </div>
                          <div className="text-slate-600 text-[11px] italic">"{obj.response}"</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
