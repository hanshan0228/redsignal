import { timeAgo, getHitTimeDetails, STATUS_CFG } from '../../utils.js';
import { useState, useRef, useEffect } from 'react';
import { apiFetch } from '../../api.js';

export default function BoardCard({ hit, onStatusChange }) {
  const isPost = hit.kind === 'post';
  const isX = hit.platform === 'x' || hit.platform === 'twitter' || (hit.url && (hit.url.includes('x.com') || hit.url.includes('twitter.com')));
  const timeDetails = getHitTimeDetails(hit);
  const age = timeDetails.relative || timeAgo((hit.ts || 0) * 1000);
  const s = hit.status || 'new';
  const sc = STATUS_CFG[s] || STATUS_CFG.new;
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, []);

  async function setStatus(status) {
    setOpen(false);
    await apiFetch(`/api/hits/${hit.id}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, listener_id: hit.listener_id || null }),
    });
    if (onStatusChange) onStatusChange(hit, status);
  }

  const typeDot = isX
    ? <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-black text-white">𝕏</span>
    : isPost
    ? <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-blue-50 text-blue-500 border border-blue-100">POST</span>
    : <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-violet-50 text-violet-500 border border-violet-100">CMT</span>;

  return (
    <div
      className="bg-white rounded-xl border border-slate-200 p-3 space-y-2 hover:border-slate-300 transition-all"
      style={{ boxShadow: '0 1px 3px rgba(15,23,42,.04)' }}
    >
      <div className="flex items-center gap-1.5 flex-wrap">
        {typeDot}
        {isX ? (
          <span className="text-xs font-semibold text-slate-800">@{hit.author || 'tweet'}</span>
        ) : (
          <span className="text-xs font-semibold text-orange-500">r/{hit.subreddit || ''}</span>
        )}
        <span
          className="ml-auto inline-flex items-center gap-1 text-[11px] text-slate-600 bg-slate-50 border border-slate-200/80 px-1.5 py-0.5 rounded cursor-help flex-shrink-0"
          title={`【发帖具体时间】\n本地时间: ${timeDetails.full || timeDetails.exact}\n相对时效: ${timeDetails.relative}\n入库时间: ${hit.created_at || '实时'}`}
        >
          <svg className="w-3 h-3 text-slate-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="font-medium text-slate-700">{timeDetails.exact || timeDetails.relative}</span>
        </span>
      </div>
      {hit.title
        ? <div className="text-xs font-semibold text-slate-800 leading-snug line-clamp-2">{hit.title}</div>
        : <div className="text-xs text-slate-500 leading-relaxed line-clamp-2">{hit.excerpt || ''}</div>
      }
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-mono bg-amber-50 text-amber-600 border border-amber-100 px-1.5 py-0.5 rounded truncate max-w-[100px]">
          {hit.match || ''}
        </span>
        <div className="relative inline-block" ref={ref}>
          <button
            onClick={() => setOpen(o => !o)}
            className={`text-[10px] px-1.5 py-0.5 rounded font-medium cursor-pointer ${sc.cls}`}
          >
            {sc.label}
          </button>
          {open && (
            <div className="st-menu">
              {Object.entries(STATUS_CFG).map(([k, v]) => (
                <button
                  key={k}
                  onClick={() => setStatus(k)}
                  className={k === s ? 'font-semibold text-slate-900' : 'text-slate-600'}
                >
                  {v.label}
                </button>
              ))}
            </div>
          )}
        </div>
        <a
          href={hit.url || ''}
          target="_blank"
          rel="noopener"
          className="text-[10px] px-2 py-1 rounded-lg bg-slate-900 text-white hover:bg-slate-700 font-medium transition-colors flex-shrink-0"
        >
          ↗
        </a>
      </div>
    </div>
  );
}
