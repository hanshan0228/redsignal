import { useState } from 'react';
import { useApp } from '../../context.jsx';
import { apiFetch } from '../../api.js';

const TYPE_UI = {
  reddit: {
    bg: 'bg-orange-100', color: 'text-orange-500',
    icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-7.004 4.87-3.874 0-7.004-2.176-7.004-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 .14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.701zM9.25 12C8.561 12 8 12.562 8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 0 0-.231.094.33.33 0 0 0 0 .463c.842.842 2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 0 0 .029-.463.33.33 0 0 0-.464 0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.326.326 0 0 0-.232-.095z"/></svg>,
  },
  x: {
    bg: 'bg-black', color: 'text-white',
    icon: <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>,
  },
  twitter: {
    bg: 'bg-black', color: 'text-white',
    icon: <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>,
  },
  forum: {
    bg: 'bg-emerald-100', color: 'text-emerald-700',
    icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>,
  },
  vbulletin: {
    bg: 'bg-emerald-100', color: 'text-emerald-700',
    icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>,
  },
  anthropic: {
    bg: 'bg-violet-100', color: 'text-violet-600',
    icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>,
  },
  openai: {
    bg: 'bg-emerald-100', color: 'text-emerald-600',
    icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83m9.9 9.9 2.83 2.83M1 12h4m14 0h4M4.22 19.78l2.83-2.83m9.9-9.9 2.83-2.83"/></svg>,
  },
  ollama: {
    bg: 'bg-slate-100', color: 'text-slate-500',
    icon: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M8 9h8M8 12h6M8 15h4"/></svg>,
  },
};

export default function CredCard({ cred, isEditing, draft, onEdit, onCancel, onSave, onDelete, onChange, listenerCount }) {
  const ui = TYPE_UI[cred.type] || TYPE_UI.anthropic;
  const { addToast } = useApp();
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const handleTest = async (e) => {
    e?.stopPropagation?.();
    setTesting(true);
    setTestResult(null);
    try {
      const res = await apiFetch(`/api/credentials/${cred.id}/test`, { method: 'POST' });
      setTestResult(res);
      if (res && res.ok) {
        addToast(res.message || '凭据连接测试通过！', 'green');
      } else {
        addToast(res?.message || '测试未通过', 'amber');
      }
    } catch (err) {
      setTestResult({ ok: false, message: '测试请求失败: ' + err.message });
      addToast('测试网络异常', 'red');
    } finally {
      setTesting(false);
    }
  };

  if (!isEditing) {
    let preview = '', badge = null;
    if (cred.type === 'reddit') {
      preview = (cred.cookie || cred.reddit_session)
        ? `Web Cookie: u/${cred.username || 'session'}`
        : cred.client_id ? `OAuth API: ${cred.client_id.slice(0, 8)}…` : 'No auth set';
      badge = <span className="text-xs bg-orange-100 text-orange-600 px-1.5 py-0.5 rounded-md font-medium">Reddit</span>;
    } else if (cred.type === 'x' || cred.type === 'twitter') {
      preview = cred.api_key ? `OAuth API: ${cred.api_key.slice(0, 6)}…` : cred.auth_token ? `Web Cookie: @${cred.username || 'session'}` : 'No auth set';
      badge = <span className="text-xs bg-black text-white px-1.5 py-0.5 rounded-md font-medium">𝕏</span>;
    } else if (cred.type === 'forum' || cred.type === 'vbulletin') {
      preview = cred.cookie ? `Web Cookie: ${cred.username ? `@${cred.username} · ` : ''}${cred.domain || 'Active'}` : '未填 Cookie (仅辅助复制回帖)';
      badge = <span className="text-xs bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded-md font-medium">🌐 技术论坛</span>;
    } else if (cred.type === 'anthropic') {
      preview = cred.api_key ? `sk-ant-…${cred.api_key.slice(-4)}` : 'No key set';
      badge = <span className="text-xs bg-violet-50 text-violet-500 border border-violet-100 px-1.5 py-0.5 rounded-md font-medium">Claude</span>;
    } else if (cred.type === 'openai') {
      preview = cred.api_key ? `sk-…${cred.api_key.slice(-4)}` : 'No key set';
      badge = <span className="text-xs bg-emerald-50 text-emerald-600 border border-emerald-100 px-1.5 py-0.5 rounded-md font-medium">OpenAI</span>;
    } else if (cred.type === 'ollama') {
      preview = cred.base_url || 'http://localhost:11434';
      badge = <span className="text-xs bg-slate-100 text-slate-500 border border-slate-200 px-1.5 py-0.5 rounded-md font-medium">Local</span>;
    }
    const subline = cred.type === 'reddit' && cred.user_agent
      ? `  ·  ${cred.user_agent.slice(0, 30)}`
      : (cred.type === 'x' || cred.type === 'twitter') && cred.username
      ? `  ·  @${cred.username}`
      : (cred.type === 'forum' || cred.type === 'vbulletin') && (cred.username || cred.domain)
      ? `  ·  ${cred.username ? `@${cred.username} · ` : ''}${cred.domain || ''}`
      : cred.model ? `  ·  model: ${cred.model}` : '';

    return (
      <div className="card p-4 space-y-2.5">
        <div className="flex items-center gap-3.5">
          <div className={`w-9 h-9 rounded-xl ${ui.bg} ${ui.color} flex items-center justify-center flex-shrink-0`}>
            {ui.icon}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm text-slate-800">{cred.name}</span>
              {badge}
            </div>
            <div className="text-xs text-slate-400 mt-0.5 font-mono truncate">{preview}{subline}</div>
          </div>
          {listenerCount > 0 && (
            <span className="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full flex-shrink-0">
              {listenerCount} listener{listenerCount !== 1 ? 's' : ''}
            </span>
          )}
          <button
            onClick={handleTest}
            disabled={testing}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-700 font-medium transition-colors flex items-center gap-1 flex-shrink-0 disabled:opacity-50 cursor-pointer"
            title="测试账号凭据有效性与在线鉴权连通性"
          >
            <span>{testing ? '⏳' : '⚡'}</span>
            {testing ? '测试中…' : '测试连通性'}
          </button>
          <button onClick={onEdit} className="text-xs px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 font-medium transition-colors flex-shrink-0 cursor-pointer">Edit</button>
          <button onClick={onDelete} className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-red-50 text-slate-300 hover:text-red-400 transition-colors text-lg leading-none flex-shrink-0 cursor-pointer">×</button>
        </div>

        {testResult && (
          <div className={`p-3 rounded-xl border text-xs leading-relaxed space-y-1 transition-all ${
            testResult.ok
              ? 'bg-emerald-50/90 border-emerald-200 text-emerald-900'
              : 'bg-amber-50/95 border-amber-200 text-amber-950 shadow-2xs'
          }`}>
            <div className="font-semibold flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                {testResult.ok ? '✅' : '⚠️'} {testResult.message}
              </span>
              <button
                onClick={() => setTestResult(null)}
                className="text-slate-400 hover:text-slate-600 text-xs px-1 cursor-pointer"
                title="关闭提示"
              >
                ✕
              </button>
            </div>
            {testResult.details && (
              <p className="text-[11px] text-slate-600 whitespace-pre-line mt-1 leading-normal">
                {testResult.details}
              </p>
            )}
          </div>
        )}
      </div>
    );
  }

  const f = (key) => (e) => onChange(key, e.target.value);
  const Label = ({ children }) => <span className="text-xs font-medium text-slate-500">{children}</span>;

  return (
    <div className="card border-blue-200 p-4 space-y-3.5">
      {cred.type === 'reddit' && <>
        <label className="block"><Label>Account Name</Label><input className="inp mt-1.5" value={draft.name || ''} onChange={f('name')} /></label>

        {/* Dual Mode Switch for Reddit */}
        <div className="pt-1">
          <Label>授权与自动发帖方式</Label>
          <div className="grid grid-cols-2 gap-2 mt-1.5">
            <button
              type="button"
              onClick={() => onChange('auth_mode', 'cookie')}
              className={`py-2 px-3 text-xs font-semibold rounded-xl border transition-all ${
                (draft.auth_mode || (draft.cookie || draft.reddit_session ? 'cookie' : 'cookie')) === 'cookie'
                  ? 'bg-orange-500 text-white border-orange-500 shadow-xs'
                  : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'
              }`}
            >
              🍪 免申请 Web Cookie 模式 (推荐)
            </button>
            <button
              type="button"
              onClick={() => onChange('auth_mode', 'api')}
              className={`py-2 px-3 text-xs font-semibold rounded-xl border transition-all ${
                draft.auth_mode === 'api'
                  ? 'bg-orange-500 text-white border-orange-500 shadow-xs'
                  : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'
              }`}
            >
              🔑 官方 Script App (需开发者权限)
            </button>
          </div>
        </div>

        {(draft.auth_mode !== 'api') ? (
          <div className="space-y-3 pt-1">
            <div className="p-3 bg-amber-50/80 border border-amber-200/80 rounded-xl text-xs text-amber-800 space-y-1">
              <div className="font-semibold flex items-center gap-1.5 text-amber-900">
                💡 无需在 Reddit 申请开发者应用，直接复用浏览器已登录会话
              </div>
              <p className="text-[11px] text-amber-700 leading-relaxed">
                在 Chrome / Edge 中登录 reddit.com，按 F12 打开开发者工具 → 切换到「Application / 应用」→ 左侧「Cookies」→ 找到并复制 <code>reddit_session</code> 的值粘贴到下方即可。
              </p>
            </div>
            <label className="block">
              <Label>Reddit Session Cookie (reddit_session)</Label>
              <textarea
                className="inp mt-1.5 font-mono text-xs h-20 leading-relaxed resize-none"
                placeholder="例如: 123456789%2C2026-09-27T01%3A00%3A00... 或完整 Cookie 字符串"
                value={draft.cookie || draft.reddit_session || ''}
                onChange={(e) => {
                  onChange('cookie', e.target.value);
                  onChange('reddit_session', e.target.value);
                }}
              />
            </label>
            <label className="block">
              <Label>Reddit 用户名 (可选，例如 u/hanshan0228)</Label>
              <input className="inp mt-1.5 font-mono text-sm" placeholder="hanshan0228" value={draft.username || ''} onChange={f('username')} />
            </label>
          </div>
        ) : (
          <div className="space-y-3 pt-1">
            <div className="grid grid-cols-2 gap-3">
              <label className="block"><Label>Client ID (App ID)</Label><input className="inp mt-1.5 font-mono text-sm" value={draft.client_id || ''} onChange={f('client_id')} /></label>
              <label className="block"><Label>Client Secret</Label><input className="inp mt-1.5 font-mono text-sm" type="password" value={draft.client_secret || ''} onChange={f('client_secret')} /></label>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <Label>Reddit 账号用户名 (Username)</Label>
                <input className="inp mt-1.5 font-mono text-sm" placeholder="hanshan0228" value={draft.username || ''} onChange={f('username')} />
              </label>
              <label className="block">
                <Label>Reddit 账号密码 (Password)</Label>
                <input className="inp mt-1.5 font-mono text-sm" type="password" placeholder="••••••••" value={draft.password || ''} onChange={f('password')} />
              </label>
            </div>
            <a href="https://www.reddit.com/prefs/apps" target="_blank" rel="noopener" className="inline-flex items-center gap-1 text-xs text-blue-500 hover:underline">↗ reddit.com/prefs/apps → create app → script</a>
          </div>
        )}
      </>}

      {(cred.type === 'x' || cred.type === 'twitter') && <>
        <label className="block"><Label>Account Name</Label><input className="inp mt-1.5" value={draft.name || ''} onChange={f('name')} /></label>
        <label className="block">
          <Label>𝕏 用户名 (Username, 例如 @your_brand)</Label>
          <input className="inp mt-1.5 font-mono text-sm" placeholder="username" value={draft.username || ''} onChange={f('username')} />
        </label>

        {/* Dual Mode Switch */}
        <div className="pt-1">
          <Label>授权与发推模式</Label>
          <div className="grid grid-cols-2 gap-2 mt-1.5">
            <button
              type="button"
              onClick={() => onChange('auth_mode', 'api')}
              className={`text-xs p-2.5 rounded-xl border text-left transition-all ${
                (draft.auth_mode || 'api') === 'api'
                  ? 'border-slate-900 bg-slate-900 text-white font-medium shadow-sm'
                  : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'
              }`}
            >
              <div className="font-semibold flex items-center gap-1.5">
                <span>🔑 官方 API (OAuth 1.0a)</span>
              </div>
              <div className={`text-[10px] mt-0.5 ${ (draft.auth_mode || 'api') === 'api' ? 'text-slate-300' : 'text-slate-500'}`}>
                推荐开发者使用，稳定合规调用 X API v2
              </div>
            </button>
            <button
              type="button"
              onClick={() => onChange('auth_mode', 'cookie')}
              className={`text-xs p-2.5 rounded-xl border text-left transition-all ${
                draft.auth_mode === 'cookie'
                  ? 'border-slate-900 bg-slate-900 text-white font-medium shadow-sm'
                  : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'
              }`}
            >
              <div className="font-semibold flex items-center gap-1.5">
                <span>🍪 Web Session Cookie</span>
              </div>
              <div className={`text-[10px] mt-0.5 ${draft.auth_mode === 'cookie' ? 'text-slate-300' : 'text-slate-500'}`}>
                无需申请开发者账号，提取浏览器 Cookie 免 API
              </div>
            </button>
          </div>
        </div>

        {(draft.auth_mode || 'api') === 'api' ? (
          <div className="space-y-3 pt-1">
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <Label>API Key (Consumer Key)</Label>
                <input className="inp mt-1.5 font-mono text-xs" value={draft.api_key || ''} onChange={f('api_key')} />
              </label>
              <label className="block">
                <Label>API Key Secret</Label>
                <input className="inp mt-1.5 font-mono text-xs" type="password" value={draft.api_secret || ''} onChange={f('api_secret')} />
              </label>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <Label>Access Token</Label>
                <input className="inp mt-1.5 font-mono text-xs" value={draft.access_token || ''} onChange={f('access_token')} />
              </label>
              <label className="block">
                <Label>Access Token Secret</Label>
                <input className="inp mt-1.5 font-mono text-xs" type="password" value={draft.access_token_secret || ''} onChange={f('access_token_secret')} />
              </label>
            </div>
            <label className="block">
              <Label>Bearer Token <span className="font-normal text-slate-400">(可选，用于高效检索推文)</span></Label>
              <input className="inp mt-1.5 font-mono text-xs" type="password" value={draft.bearer_token || ''} onChange={f('bearer_token')} />
            </label>
            <a href="https://developer.x.com/en/portal/dashboard" target="_blank" rel="noopener" className="inline-flex items-center gap-1 text-xs text-blue-500 hover:underline">
              ↗ developer.x.com → Projects & Apps → Keys and Tokens (需 Read and Write 权限)
            </a>
          </div>
        ) : (
          <div className="space-y-3 pt-1">
            <label className="block">
              <Label>auth_token (Cookie)</Label>
              <input className="inp mt-1.5 font-mono text-xs" type="password" placeholder="e.g. 847d0f9..." value={draft.auth_token || ''} onChange={f('auth_token')} />
            </label>
            <label className="block">
              <Label>ct0 (CSRF Token / Cookie)</Label>
              <input className="inp mt-1.5 font-mono text-xs" type="password" placeholder="e.g. 7192bf8..." value={draft.ct0 || ''} onChange={f('ct0')} />
            </label>
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-[11px] text-slate-600 space-y-1">
              <div className="font-semibold text-slate-800">💡 浏览器提取 Cookie 指引：</div>
              <div>1. 在电脑浏览器登录 x.com，按 <kbd className="bg-white px-1 border rounded">F12</kbd> 打开开发者工具。</div>
              <div>2. 切换至 <strong>Application</strong>（应用程序） 标签页，展开左侧 <strong>Cookies</strong> → <strong>https://x.com</strong>。</div>
              <div>3. 找到 <code>auth_token</code> 和 <code>ct0</code>，复制粘贴到上方即可免开发者账号自动发推。</div>
            </div>
          </div>
        )}
      </>}

      {(cred.type === 'forum' || cred.type === 'vbulletin') && <>
        <label className="block"><Label>论坛账号备注 (Account Name)</Label><input className="inp mt-1.5" placeholder="例如: BuggiesGoneWild - Han" value={draft.name || ''} onChange={f('name')} /></label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <Label>论坛域名 / 网址 (Domain / URL)</Label>
            <input className="inp mt-1.5 font-mono text-sm" placeholder="https://www.buggiesgonewild.com" value={draft.domain || draft.forum_url || ''} onChange={(e) => { onChange('domain', e.target.value); onChange('forum_url', e.target.value); }} />
          </label>
          <label className="block">
            <Label>论坛用户名 (Username，可选)</Label>
            <input className="inp mt-1.5 font-mono text-sm" placeholder="golfcart_pro" value={draft.username || ''} onChange={f('username')} />
          </label>
        </div>
        <div className="p-3 bg-emerald-50/80 border border-emerald-200/80 rounded-xl text-xs text-emerald-900 space-y-1">
          <div className="font-semibold flex items-center gap-1.5 text-emerald-950">
            💡 论坛 Session Cookie 提取方法 (以 Chrome / Edge 为例)
          </div>
          <p className="text-[11px] text-emerald-800 leading-relaxed">
            在已登录目标论坛（如 Buggies Gone Wild）的网页中按 <kbd className="bg-white px-1 border rounded">F12</kbd> → <strong>Application (应用)</strong> → <strong>Cookies</strong> → 目标域名。复制 <code>bbuser</code>、<code>bbsessionhash</code> 或整段 Cookie 粘贴到下方即可让后台实现无头自动发帖；若留空，仍可使用一键「📋 复制 BBCode 并直达原帖」直接在浏览器中免封号回帖。
          </p>
        </div>
        <label className="block">
          <Label>论坛 Session Cookie</Label>
          <textarea
            className="inp mt-1.5 font-mono text-xs h-24 leading-relaxed resize-none"
            placeholder="例如: bbuser=12345; bbsessionhash=abcdef123456... 或完整 Cookie 字符串"
            value={draft.cookie || ''}
            onChange={f('cookie')}
          />
        </label>
      </>}

      {cred.type === 'anthropic' && <>
        <label className="block"><Label>Name</Label><input className="inp mt-1.5" value={draft.name || ''} onChange={f('name')} /></label>
        <label className="block">
          <Label>API Key</Label>
          <input className="inp mt-1.5 font-mono text-sm" type="password" placeholder="sk-ant-…" value={draft.api_key || ''} onChange={f('api_key')} />
          <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener" className="inline-flex items-center gap-1 text-xs text-blue-500 hover:underline mt-1.5">↗ console.anthropic.com</a>
        </label>
        <label className="block">
          <Label>Model <span className="font-normal text-slate-400">(default: claude-haiku-4-5-20251001)</span></Label>
          <input className="inp mt-1.5 text-sm font-mono" placeholder="claude-haiku-4-5-20251001" value={draft.model || ''} onChange={f('model')} />
        </label>
      </>}

      {cred.type === 'openai' && <>
        <label className="block"><Label>Name</Label><input className="inp mt-1.5" value={draft.name || ''} onChange={f('name')} /></label>
        <label className="block">
          <Label>API Key</Label>
          <input className="inp mt-1.5 font-mono text-sm" type="password" placeholder="sk-…" value={draft.api_key || ''} onChange={f('api_key')} />
          <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener" className="inline-flex items-center gap-1 text-xs text-blue-500 hover:underline mt-1.5">↗ platform.openai.com/api-keys</a>
        </label>
        <label className="block">
          <Label>Model <span className="font-normal text-slate-400">(default: gpt-4o-mini)</span></Label>
          <input className="inp mt-1.5 text-sm font-mono" placeholder="gpt-4o-mini" value={draft.model || ''} onChange={f('model')} />
        </label>
      </>}

      {cred.type === 'ollama' && <>
        <label className="block"><Label>Name</Label><input className="inp mt-1.5" value={draft.name || ''} onChange={f('name')} /></label>
        <label className="block">
          <Label>Base URL</Label>
          <input className="inp mt-1.5 text-sm font-mono" placeholder="http://localhost:11434" value={draft.base_url || 'http://localhost:11434'} onChange={f('base_url')} />
          <p className="text-xs text-slate-400 mt-1.5">Start with <code className="bg-slate-100 px-1 rounded">ollama serve</code></p>
        </label>
        <label className="block">
          <Label>Model <span className="font-normal text-slate-400">(default: llama3.2)</span></Label>
          <input className="inp mt-1.5 text-sm font-mono" placeholder="llama3.2" value={draft.model || ''} onChange={f('model')} />
          <p className="text-xs text-slate-400 mt-1.5">Pull models with: <code className="bg-slate-100 px-1 rounded">ollama pull llama3.2</code></p>
        </label>
      </>}

      <div className="flex gap-2 pt-1">
        <button onClick={onSave} className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-sm font-medium transition-colors">Save</button>
        <button onClick={onCancel} className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-xl text-sm font-medium transition-colors">Cancel</button>
      </div>
    </div>
  );
}
