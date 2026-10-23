import { createContext, useContext, useState, useRef, useCallback, useEffect } from 'react';
import { apiFetch } from './api.js';

export const AppContext = createContext(null);

export function AppProvider({ children }) {
  const [activeTab, setActiveTab] = useState('stream');
  const [cfg, setCfg] = useState({});
  const [hits, setHits] = useState([]);
  const hitIds = useRef(new Set());
  const [listenerStatus, setListenerStatus] = useState({});
  const [toasts, setToasts] = useState([]);
  const [activeProject, setActiveProjectState] = useState(() => localStorage.getItem('rs-active-project') || 'all');
  const [projects, setProjects] = useState([]);

  const setActiveProject = useCallback((p) => {
    localStorage.setItem('rs-active-project', p);
    setActiveProjectState(p);
  }, []);

  const refreshProjects = useCallback(async () => {
    try {
      const res = await apiFetch('/api/projects');
      if (res && res.ok) {
        setProjects(res.projects || []);
      }
    } catch {
      // fallback
    }
  }, []);

  useEffect(() => {
    refreshProjects();
  }, [refreshProjects, cfg]);

  const addToast = useCallback((msg, color = 'gray') => {
    const id = Date.now() + Math.random();
    setToasts(prev => [...prev, { id, msg, color }]);
    setTimeout(() => {
      setToasts(prev => prev.map(t => t.id === id ? { ...t, leaving: true } : t));
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id));
      }, 200);
    }, 3200);
  }, []);

  return (
    <AppContext.Provider value={{
      activeTab, setActiveTab,
      cfg, setCfg,
      hits, setHits,
      hitIds,
      listenerStatus, setListenerStatus,
      toasts, addToast,
      activeProject, setActiveProject,
      projects, refreshProjects,
    }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  return useContext(AppContext);
}
