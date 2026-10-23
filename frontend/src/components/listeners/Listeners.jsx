import { useState, useRef, useEffect } from 'react';
import { useApp } from '../../context.jsx';
import { apiFetch, saveConfig } from '../../api.js';
import ListenerCard from './ListenerCard.jsx';
import ListenerDrawer from './ListenerDrawer.jsx';

const PRESETS = [
  {
    id: 'white_hat',
    title: '🎯 白帽精细截流 (White-Hat)',
    desc: '高质无痕回复，零外链，品牌关键词自然搜索引导，人工审核后发布',
    config: {
      anti_ban_mode: 'brand_search',
      stealth_mode: 'profile_only',
      reply_cooldown_minutes: 20,
      daily_reply_limit: 10,
      auto_reply_enabled: false,
      dark_fleet_enabled: false,
    }
  },
  {
    id: 'dark_fleet',
    title: '🛸 暗黑全自动舰队 (Dark Fleet)',
    desc: '自适应防封，高置信度全自动错峰排期与多账号轮替发射',
    config: {
      anti_ban_mode: 'adaptive',
      stealth_mode: 'direct_link',
      reply_cooldown_minutes: 15,
      daily_reply_limit: 25,
      auto_reply_enabled: true,
      auto_submit_enabled: true,
      dark_fleet_enabled: true,
    }
  },
  {
    id: 'barnacle_seo',
    title: '🪨 藤壶 SEO 长效占坑 (Barnacle)',
    desc: '针对 Google 首页高权重讨论帖，长篇深度干货，直链技术参考',
    config: {
      anti_ban_mode: 'direct_link',
      stealth_mode: 'direct_link',
      reply_cooldown_minutes: 45,
      daily_reply_limit: 5,
      auto_reply_enabled: false,
      dark_fleet_enabled: false,
    }
  }
];

export default function Listeners() {
  const { cfg, setCfg, setListenerStatus, addToast, activeProject } = useApp();
  const [editingId, setEditingId] = useState(null);
  const [projectFilter, setProjectFilter] = useState('all');
  const [presetOpen, setPresetOpen] = useState(false);
  const dropdownRef = useRef(null);

  const listeners = cfg.listeners || [];

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setPresetOpen(false);
      }
    }
    if (presetOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [presetOpen]);

  const isMatchProject = (l) => {
    if (!activeProject || activeProject === 'all') return true;
    return (
      (l.site_name && l.site_name.toLowerCase() === activeProject.toLowerCase()) ||
      (l.name && l.name.toLowerCase().includes(activeProject.toLowerCase())) ||
      (l.project && l.project.toLowerCase() === activeProject.toLowerCase())
    );
  };

  const matchedListeners = listeners.filter(isMatchProject);
  const displayedListeners = (activeProject && activeProject !== 'all' && projectFilter === 'current')
    ? matchedListeners
    : listeners;

  const createListenerFromPreset = async (preset) => {
    const id = crypto.randomUUID();
    const defaultSite = (activeProject && activeProject !== 'all') ? activeProject : 'Product';
    const lst = {
      id,
      name: `${defaultSite} ${preset ? preset.title.split(' ')[1] : 'Listener'}`,
      site_name: defaultSite,
      enabled: true,
      subreddits: 'all',
      webhook: '',
      keywords: [],
      filters: [],
      negative_keywords: [],
      reddit_credential_id: '',
      ai_credential_id: '',
      ...(preset ? preset.config : {})
    };
    const next = { ...cfg, listeners: [...listeners, lst] };
    setCfg(next);
    await saveConfig(next);
    setEditingId(id);
    setPresetOpen(false);
  };

  const deleteListener = async (id) => {
    if (!confirm('Delete this listener?')) return;
    const next = { ...cfg, listeners: listeners.filter(l => l.id !== id) };
    setCfg(next);
    await saveConfig(next);
    if (editingId === id) setEditingId(null);
  };

  const toggleActive = async (id, running) => {
    const nextRunning = !running;
    setListenerStatus(prev => ({ ...prev, [id]: nextRunning }));
    const nextCfg = {
      ...cfg,
      listeners: listeners.map(l => l.id === id ? { ...l, enabled: nextRunning } : l)
    };
    setCfg(nextCfg);

    try {
      if (running) {
        await apiFetch(`/api/listeners/${id}/stop`, { method: 'POST' });
      } else {
        const r = await apiFetch(`/api/listeners/${id}/start`, { method: 'POST' });
        if (!r.ok) {
          addToast(r.message || 'Failed to start listener', 'red');
          setListenerStatus(prev => ({ ...prev, [id]: false }));
          setCfg(prev => ({
            ...prev,
            listeners: (prev.listeners || []).map(l => l.id === id ? { ...l, enabled: false } : l)
          }));
        }
      }
    } catch (err) {
      addToast(String(err), 'red');
      setListenerStatus(prev => ({ ...prev, [id]: running }));
    }

    setTimeout(async () => {
      const status = await apiFetch('/api/listeners/status').catch(() => null);
      if (status) setListenerStatus(status);
    }, 800);
  };

  const editingListener = listeners.find(l => l.id === editingId);

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6 flex-wrap gap-4">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <span>Listeners 监听器</span>
              {activeProject && activeProject !== 'all' && (
                <span className="text-xs font-semibold px-2 py-0.5 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200">
                  ⛳ {activeProject}
                </span>
              )}
            </h2>
            <p className="text-sm text-slate-400 mt-0.5">多平台商机监听与自动化截流巡航中枢</p>
          </div>

          <div className="flex items-center gap-2.5">
            {/* Project Filter Pills if in specific workspace */}
            {activeProject && activeProject !== 'all' && (
              <div className="flex items-center bg-slate-100 p-0.5 rounded-xl text-xs font-medium">
                <button
                  type="button"
                  onClick={() => setProjectFilter('current')}
                  className={`px-2.5 py-1.5 rounded-lg transition-colors cursor-pointer ${
                    projectFilter === 'current'
                      ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  当前项目 ({matchedListeners.length})
                </button>
                <button
                  type="button"
                  onClick={() => setProjectFilter('all')}
                  className={`px-2.5 py-1.5 rounded-lg transition-colors cursor-pointer ${
                    projectFilter === 'all'
                      ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  全部 ({listeners.length})
                </button>
              </div>
            )}

            {/* New Listener Button with Presets Dropdown */}
            <div className="relative" ref={dropdownRef}>
              <button
                type="button"
                onClick={() => setPresetOpen(prev => !prev)}
                className="flex items-center gap-2 px-3.5 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-sm font-medium transition-colors cursor-pointer shadow-xs"
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12h14"/></svg>
                <span>新建监听器</span>
                <svg width="9" height="5" viewBox="0 0 10 6" fill="currentColor" className={`transition-transform duration-150 ${presetOpen ? 'rotate-180' : ''}`}><path d="M0 0l5 5 5-5z"/></svg>
              </button>

              {presetOpen && (
                <div
                  className="absolute right-0 mt-2 w-72 bg-white rounded-2xl shadow-xl border border-slate-200/90 p-2 z-50 space-y-1"
                >
                  <div className="px-2 py-1 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    选择截流战法预设
                  </div>
                  {PRESETS.map(p => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => createListenerFromPreset(p)}
                      className="w-full text-left p-2.5 rounded-xl hover:bg-slate-50 transition-colors cursor-pointer group"
                    >
                      <div className="text-xs font-bold text-slate-800 group-hover:text-emerald-600 transition-colors">
                        {p.title}
                      </div>
                      <div className="text-[11px] text-slate-400 mt-0.5 leading-snug">
                        {p.desc}
                      </div>
                    </button>
                  ))}
                  <div className="border-t border-slate-100 my-1" />
                  <button
                    type="button"
                    onClick={() => createListenerFromPreset(null)}
                    className="w-full text-left px-2.5 py-2 rounded-xl hover:bg-slate-50 text-xs font-semibold text-slate-600 hover:text-slate-900 transition-colors flex items-center justify-between cursor-pointer"
                  >
                    <span>⚡ 空白自定义</span>
                    <span className="text-[10px] text-slate-400">手动配齐参数</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {displayedListeners.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="1.5"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83m9.9 9.9 2.83 2.83M1 12h4m14 0h4M4.22 19.78l2.83-2.83m9.9-9.9 2.83-2.83"/></svg>
            </div>
            <div className="text-slate-700 font-semibold text-lg">
              {projectFilter === 'current' ? `当前工作区 [${activeProject}] 暂无监听器` : '暂无监听器'}
            </div>
            <div className="text-slate-400 text-sm mt-1">
              点击右上角「新建监听器」选择战法模版一键初始化
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {displayedListeners.map(l => (
              <ListenerCard
                key={l.id}
                listener={l}
                onEdit={setEditingId}
                onDelete={deleteListener}
                onToggleActive={toggleActive}
              />
            ))}
          </div>
        )}
      </div>

      {editingListener && (
        <ListenerDrawer
          listener={editingListener}
          onClose={() => setEditingId(null)}
        />
      )}
    </div>
  );
}
