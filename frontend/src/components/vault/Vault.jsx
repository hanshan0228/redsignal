import { useState } from 'react';
import { useApp } from '../../context.jsx';
import { saveConfig } from '../../api.js';
import CredCard from './CredCard.jsx';
import AccountHealthMatrix from './AccountHealthMatrix.jsx';
import AdminSecurityCard from './AdminSecurityCard.jsx';

function newCred(type) {
  const id = crypto.randomUUID();
  if (type === 'reddit')    return { id, type, name: 'New Reddit Account', auth_mode: 'cookie', cookie: '', reddit_session: '', client_id: '', client_secret: '', username: '', password: '', user_agent: 'redsignal/1.0 by u/yourname' };
  if (type === 'x' || type === 'twitter') return { id, type: 'x', name: 'New X (Twitter) Account', auth_mode: 'api', api_key: '', api_secret: '', access_token: '', access_token_secret: '', bearer_token: '', auth_token: '', ct0: '', username: '' };
  if (type === 'forum' || type === 'vbulletin') return { id, type: 'forum', name: 'Buggies Gone Wild (Forum)', domain: 'https://www.buggiesgonewild.com', forum_url: 'https://www.buggiesgonewild.com', cookie: '', username: '' };
  if (type === 'openai')    return { id, type, name: 'New OpenAI Key', api_key: '', model: '' };
  if (type === 'ollama')    return { id, type, name: 'Local Ollama', base_url: 'http://localhost:11434', model: '' };
  return { id, type: 'anthropic', name: 'New Anthropic Key', api_key: '', model: '' };
}

export default function Vault() {
  const { cfg, setCfg } = useApp();
  const [editingId, setEditingId] = useState(null);
  const [draft, setDraft] = useState(null);

  const credentials = cfg.credentials || [];
  const listeners   = cfg.listeners   || [];

  const reddit    = credentials.filter(c => c.type === 'reddit');
  const xAccounts = credentials.filter(c => c.type === 'x' || c.type === 'twitter');
  const forums    = credentials.filter(c => c.type === 'forum' || c.type === 'vbulletin' || c.type === 'phpbb' || c.type === 'xenforo');
  const ai        = credentials.filter(c => ['anthropic', 'openai', 'ollama'].includes(c.type));

  const listenerCount = (credId, type) => {
    const field = type === 'reddit' ? 'reddit_credential_id' : (type === 'x' || type === 'twitter') ? 'x_credential_id' : (type === 'forum' || type === 'vbulletin') ? 'forum_credential_id' : 'ai_credential_id';
    return listeners.filter(l => l[field] === credId).length;
  };

  const startEdit = (cred) => {
    setEditingId(cred.id);
    setDraft({ ...cred });
  };

  const cancelEdit = () => {
    // Remove if empty new credential
    const cred = credentials.find(c => c.id === editingId);
    if (cred && !cred.client_id && !cred.client_secret && !cred.api_key && !cred.base_url) {
      const next = { ...cfg, credentials: credentials.filter(c => c.id !== editingId) };
      setCfg(next);
    }
    setEditingId(null);
    setDraft(null);
  };

  const saveCred = async () => {
    if (!draft) return;
    const next = credentials.map(c => c.id === draft.id ? { ...draft } : c);
    const newCfg = { ...cfg, credentials: next };
    setCfg(newCfg);
    await saveConfig(newCfg);
    setEditingId(null);
    setDraft(null);
  };

  const deleteCred = async (id) => {
    if (!confirm('Delete this credential?')) return;
    const next = { ...cfg, credentials: credentials.filter(c => c.id !== id) };
    setCfg(next);
    await saveConfig(next);
  };

  const addCred = async (type) => {
    const c = newCred(type);
    const next = { ...cfg, credentials: [...credentials, c] };
    setCfg(next);
    startEdit(c);
  };

  const onChange = (key, val) => setDraft(d => ({ ...d, [key]: val }));

  const renderSection = (list, title, subtitle, addButtons) => (
    <section>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold">{title}</h2>
          <p className="text-sm text-slate-400 mt-0.5">{subtitle}</p>
        </div>
        <div className="flex items-center gap-2">{addButtons}</div>
      </div>
      <div className="space-y-3">
        {list.length === 0
          ? (
            <div className="card p-6 text-center text-slate-400 space-y-1.5 border-dashed border border-slate-200 bg-slate-50/50">
              <div className="text-sm font-medium text-slate-600">暂无已配置的 {title}</div>
              <p className="text-xs text-slate-400">点击右上角按钮即可添加新账号凭据或录入 Cookie</p>
            </div>
          )
          : list.map(c => (
            <CredCard
              key={c.id}
              cred={c}
              isEditing={editingId === c.id}
              draft={editingId === c.id ? draft : null}
              onEdit={() => startEdit(c)}
              onCancel={cancelEdit}
              onSave={saveCred}
              onDelete={() => deleteCred(c.id)}
              onChange={onChange}
              listenerCount={listenerCount(c.id, c.type)}
            />
          ))
        }
      </div>
    </section>
  );

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-5xl mx-auto space-y-8">
        <AdminSecurityCard />
        <AccountHealthMatrix />

        {renderSection(
          reddit,
          'Reddit Accounts',
          'One credential per Reddit app (PRAW OAuth 2.0).',
          <button
            onClick={() => addCred('reddit')}
            className="flex items-center gap-2 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white rounded-xl text-sm font-medium transition-colors"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12h14"/></svg>
            Add Reddit Account
          </button>
        )}

        {renderSection(
          xAccounts,
          '𝕏 (Twitter) Accounts',
          'OAuth 1.0a 官方 API 密钥或免开发者认证 Web Cookie (auth_token & ct0).',
          <button
            onClick={() => addCred('x')}
            className="flex items-center gap-2 px-4 py-2 bg-slate-900 hover:bg-black text-white rounded-xl text-sm font-medium transition-colors border border-slate-700 shadow-sm"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
            </svg>
            Add 𝕏 Account
          </button>
        )}

        {renderSection(
          forums,
          'Technical Forums (垂直技术论坛)',
          'vBulletin / XenForo / phpBB 论坛的浏览器已登录 Session Cookie（支持后台无头自动回帖）。',
          <button
            onClick={() => addCred('forum')}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-medium transition-colors shadow-sm"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12h14"/></svg>
            Add Forum Account
          </button>
        )}

        {renderSection(
          ai,
          'AI Keys',
          'Anthropic Claude, OpenAI, or local Ollama for filter pipelines.',
          <>
            <button onClick={() => addCred('anthropic')} className="flex items-center gap-1.5 px-3 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-xl text-sm font-medium transition-colors">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12h14"/></svg> Anthropic
            </button>
            <button onClick={() => addCred('openai')} className="flex items-center gap-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-medium transition-colors">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12h14"/></svg> OpenAI
            </button>
            <button onClick={() => addCred('ollama')} className="flex items-center gap-1.5 px-3 py-2 bg-slate-600 hover:bg-slate-700 text-white rounded-xl text-sm font-medium transition-colors">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12h14"/></svg> Ollama
            </button>
          </>
        )}
      </div>
    </div>
  );
}
