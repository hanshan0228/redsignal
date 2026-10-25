import { useApp } from '../../context.jsx';

export default function ListenerCard({ listener, onEdit, onDelete, onToggleActive, onStartStop, onToggleEnabled }) {
  const { cfg, listenerStatus } = useApp();
  const toggleHandler = onToggleActive || onStartStop || onToggleEnabled;
  const credentials = cfg.credentials || [];

  const isX = listener.platform === 'x' || listener.platform === 'twitter';
  const isForum = listener.platform === 'forum' || listener.platform === 'vbulletin' || listener.platform === 'phpbb' || listener.platform === 'xenforo';
  const isReddit = !isX && !isForum;
  const rCred = credentials.find(c => c.id === listener.reddit_credential_id && c.type === 'reddit');
  const xCred = credentials.find(c => c.id === listener.x_credential_id && (c.type === 'x' || c.type === 'twitter'));
  const aiCred = credentials.find(c => c.id === listener.ai_credential_id && ['anthropic', 'openai', 'ollama'].includes(c.type));
  const running = !!listenerStatus[listener.id];
  const kwCnt = (listener.keywords || []).length;
  const flCnt = (listener.filters || []).filter(f => f.enabled).length;

  return (
    <div className="card px-4 py-3.5 flex items-center gap-3.5">
      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${running ? 'bg-emerald-400 pulse-dot' : 'bg-slate-300'}`} />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm text-slate-800 truncate">{listener.name}</span>
          {isForum ? (
            <span className="text-[11px] bg-emerald-50 text-emerald-700 border border-emerald-300 px-1.5 py-0.2 rounded font-semibold flex items-center gap-1">
              🌐 论坛
            </span>
          ) : isX ? (
            <span className="text-[11px] bg-black text-white px-1.5 py-0.2 rounded font-semibold flex items-center gap-1">
              𝕏
            </span>
          ) : (
            <span className="text-[11px] bg-orange-50 text-orange-600 border border-orange-200 px-1.5 py-0.2 rounded font-semibold">
              Reddit
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-1 flex-wrap">
          {isForum ? (
            <span className="text-xs text-emerald-700 font-medium font-mono truncate max-w-xs" title={listener.forum_rss_url || ''}>
              {listener.forum_rss_url ? listener.forum_rss_url.replace(/^https?:\/\//, '') : '论坛 RSS 监控流'}
            </span>
          ) : isX ? (
            <span className="text-xs text-slate-700 font-medium">𝕏 关键词监控流</span>
          ) : (
            <span className="text-xs text-orange-500 font-medium">r/{listener.subreddits || 'all'}</span>
          )}
          {isForum ? (
            <span className="text-xs text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-100 font-medium">
              免 API (论坛开放流)
            </span>
          ) : isX ? (
            xCred ? (
              <span className="text-xs text-slate-500 font-medium">{xCred.name}</span>
            ) : (
              <span className="text-xs text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-100 font-medium">
                免 API (公开流)
              </span>
            )
          ) : (
            rCred ? (
              <span className="text-xs text-slate-400">{rCred.name}</span>
            ) : (
              <span className="text-xs text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-100 font-medium">
                免 API (RSS 引擎)
              </span>
            )
          )}
          {aiCred && <span className="text-xs text-violet-500">{aiCred.name}</span>}
          {isForum ? (
            <span className={`text-[11px] px-1.5 py-0.5 rounded font-medium ${
              listener.stealth_mode === 'profile_only'
                ? 'bg-emerald-50 text-emerald-800 border border-emerald-300'
                : listener.stealth_mode === 'two_step'
                ? 'bg-violet-50 text-violet-700 border border-violet-200'
                : 'bg-amber-50 text-amber-700 border border-amber-200'
            }`}>
              {listener.stealth_mode === 'profile_only' ? '🥷 个人主页无痕' : listener.stealth_mode === 'two_step' ? '🎣 二段钓鱼' : '⚡ BBCode直链'}
            </span>
          ) : (
            <span className={`text-[11px] px-1.5 py-0.5 rounded font-medium ${
              listener.stealth_mode === 'bio_routing' || listener.stealth_mode === 'profile_only'
                ? 'bg-emerald-50 text-emerald-800 border border-emerald-300'
                : listener.stealth_mode === 'inbound_dm' || listener.anti_ban_mode === 'inbound_dm'
                ? 'bg-purple-50 text-purple-800 border border-purple-300'
                : listener.anti_ban_mode === 'direct_link'
                ? 'bg-amber-50 text-amber-800 border border-amber-200'
                : listener.anti_ban_mode === 'adaptive'
                ? 'bg-violet-50 text-violet-800 border border-violet-200'
                : 'bg-blue-50 text-blue-800 border border-blue-200'
            }`}>
              {listener.stealth_mode === 'bio_routing' || listener.stealth_mode === 'profile_only'
                ? '🥷 Bio主页'
                : listener.stealth_mode === 'inbound_dm' || listener.anti_ban_mode === 'inbound_dm'
                ? '📩 逆向私信'
                : listener.anti_ban_mode === 'direct_link'
                ? '⚡ 直链'
                : listener.anti_ban_mode === 'adaptive'
                ? '🧠 智能'
                : '🛡️ 品牌搜索'
              }
            </span>
          )}
          {listener.dark_fleet_enabled !== false && (
            <span className="text-[11px] px-1.5 py-0.5 rounded font-medium bg-purple-50 text-purple-700 border border-purple-200">
              🛸 Dark Fleet
            </span>
          )}
          <span className="text-xs text-slate-400">{kwCnt} kw</span>
          {flCnt > 0 && <span className="text-xs text-violet-400">{flCnt} filter{flCnt !== 1 ? 's' : ''}</span>}
        </div>
      </div>

      <div className="flex items-center gap-2 flex-shrink-0">
        <button
          type="button"
          role="switch"
          aria-checked={running}
          onClick={() => toggleHandler && toggleHandler(listener.id, running)}
          title={running ? '监控运行中（点击停止）' : '监控已停止（点击启动）'}
          className={`flex items-center gap-2 px-2.5 py-1.5 rounded-full text-xs font-medium transition-all border ${
            running
              ? 'bg-emerald-50 border-emerald-300/80 text-emerald-700 hover:bg-emerald-100/70 shadow-2xs'
              : 'bg-slate-50 border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
          }`}
        >
          <span
            className={`relative inline-flex h-4 w-7 flex-shrink-0 rounded-full transition-colors duration-200 ease-in-out ${
              running ? 'bg-emerald-500' : 'bg-slate-300'
            }`}
          >
            <span
              className={`inline-block h-3 w-3 transform rounded-full bg-white shadow transition-transform duration-200 ease-in-out mt-0.5 ml-0.5 ${
                running ? 'translate-x-3' : 'translate-x-0'
              }`}
            />
          </span>
          <span className="font-semibold tracking-tight select-none">
            {running ? 'Running' : 'Stopped'}
          </span>
        </button>

        <button onClick={() => onEdit(listener.id)} className="text-xs px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 font-medium transition-colors">
          Edit
        </button>

        <button onClick={() => onDelete(listener.id)} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-red-50 text-slate-300 hover:text-red-400 transition-colors text-xl leading-none">
          ×
        </button>
      </div>
    </div>
  );
}
