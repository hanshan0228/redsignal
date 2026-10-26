import { useState, useEffect } from 'react';
import { useApp } from '../../context.jsx';
import { getAuthProfile, updateAuth, getSystemStatus, restartSystem } from '../../api.js';

export default function AdminSecurityCard() {
  const { addToast } = useApp();
  const [profile, setProfile] = useState({ username: 'admin', has_auth: true });
  const [isEditing, setIsEditing] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  // System runtime & restart states
  const [sysStatus, setSysStatus] = useState(null);
  const [confirmRestart, setConfirmRestart] = useState(false);
  const [isRestarting, setIsRestarting] = useState(false);
  const [countdown, setCountdown] = useState(0);

  const fetchSysStatus = () => {
    getSystemStatus()
      .then(res => {
        if (res && res.ok) {
          setSysStatus(res);
        }
      })
      .catch(() => {});
  };

  useEffect(() => {
    getAuthProfile()
      .then(res => {
        if (res && res.ok) {
          setProfile(res);
          setUsername(res.username || 'admin');
        }
      })
      .catch(() => {});

    fetchSysStatus();
    const timer = setInterval(fetchSysStatus, 12000);
    return () => clearInterval(timer);
  }, []);

  const handleRestart = async () => {
    setConfirmRestart(false);
    setIsRestarting(true);
    setCountdown(5);

    try {
      await restartSystem();
    } catch (_) {
      // Process terminating quickly may abort the HTTP fetch, which is expected
    }

    let remaining = 5;
    const interval = setInterval(async () => {
      remaining -= 1;
      setCountdown(remaining > 0 ? remaining : 0);

      // Probe health endpoint after process had time to respawn
      if (remaining <= 2) {
        try {
          const res = await getSystemStatus();
          if (res && res.ok) {
            clearInterval(interval);
            setIsRestarting(false);
            setSysStatus(res);
            addToast('🎉 后台服务已成功平滑重启并恢复连接！', 'green');
            return;
          }
        } catch (_) {}
      }

      if (remaining <= -10) {
        clearInterval(interval);
        setIsRestarting(false);
        fetchSysStatus();
        addToast('重启探测已结束，请检查服务日志或刷新页面', 'amber');
      }
    }, 1000);
  };

  const handleOpenEdit = () => {
    setUsername(profile.username || 'admin');
    setPassword('');
    setConfirmPassword('');
    setErrorMsg('');
    setIsEditing(true);
  };

  const handleCancel = () => {
    setIsEditing(false);
    setErrorMsg('');
    setPassword('');
    setConfirmPassword('');
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setErrorMsg('');

    if (!username.trim()) {
      setErrorMsg('用户名不能为空');
      return;
    }
    if (!password) {
      setErrorMsg('新密码不能为空');
      return;
    }
    if (password.length < 6) {
      setErrorMsg('密码长度不能少于 6 位');
      return;
    }
    if (password !== confirmPassword) {
      setErrorMsg('两次输入的密码不一致');
      return;
    }

    setSubmitting(true);
    try {
      const res = await updateAuth({
        username: username.trim(),
        password: password
      });

      if (res && res.ok) {
        setProfile(prev => ({ ...prev, username: username.trim() }));
        setIsEditing(false);
        setPassword('');
        setConfirmPassword('');
        addToast('管理员账号与密码已成功修改！已立即生效。', 'green');
      } else {
        setErrorMsg(res?.message || '更新失败，请重试');
      }
    } catch (err) {
      setErrorMsg('网络请求异常，请检查控制台连接状态');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm mb-6 transition-all">
      <div className="flex items-center justify-between flex-wrap gap-4 pb-3 border-b border-slate-100">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-xl shadow-xs">
            🛡️
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-base text-slate-800 tracking-tight">管理后台访问安全与管理员账号</h3>
              <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-600 border border-emerald-200">
                HTTP Basic 鉴权已激活
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              拦截公网非授权访问，保护后台 API 密钥、论坛会话与回帖自动化控制面板
            </p>
          </div>
        </div>

        {!isEditing && (
          <button
            onClick={handleOpenEdit}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-slate-900 hover:bg-black text-white text-xs font-semibold transition-colors shadow-2xs cursor-pointer"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
            修改用户名与密码
          </button>
        )}
      </div>

      {!isEditing ? (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-4 text-xs">
          <div className="bg-slate-50 border border-slate-100 rounded-xl p-3">
            <span className="text-slate-400 block font-medium mb-1">当前管理员用户名</span>
            <span className="text-slate-800 font-bold text-sm tracking-wide flex items-center gap-1.5">
              👤 {profile.username || 'admin'}
            </span>
          </div>

          <div className="bg-slate-50 border border-slate-100 rounded-xl p-3">
            <span className="text-slate-400 block font-medium mb-1">安全防护状态</span>
            <span className="text-emerald-600 font-semibold flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              全域敏感接口 401 拦截开启
            </span>
          </div>

          <div className="bg-slate-50 border border-slate-100 rounded-xl p-3">
            <span className="text-slate-400 block font-medium mb-1">绑定公网控制面</span>
            <span className="text-slate-700 font-medium font-mono text-[11px] truncate block" title="https://redsignal.hanzhe.dpdns.org">
              🌐 redsignal.hanzhe.dpdns.org
            </span>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSave} className="pt-4 space-y-4">
          <div className="bg-amber-50/70 border border-amber-200/80 rounded-xl p-3 text-xs text-amber-800 flex items-start gap-2">
            <span className="text-base leading-none">💡</span>
            <div>
              <p className="font-semibold mb-0.5">安全修改须知：</p>
              <p className="text-amber-700 leading-relaxed">
                修改后系统将实时生效并持久化写入系统配置文件。保存后若浏览器后续弹出验证框，请使用新设置的用户名与密码重新登录。
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                管理员用户名 (Username)
              </label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="例如: admin"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:bg-white focus:border-slate-800 outline-none transition-colors"
                required
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-xs font-semibold text-slate-700">
                  新登录密码 (New Password)
                </label>
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="text-[11px] text-slate-500 hover:text-slate-800 cursor-pointer"
                >
                  {showPassword ? '🙈 隐藏' : '👁️ 显示'}
                </button>
              </div>
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="至少 6 位密码"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:bg-white focus:border-slate-800 outline-none transition-colors"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                确认新密码 (Confirm Password)
              </label>
              <input
                type={showPassword ? 'text' : 'password'}
                value={confirmPassword}
                onChange={e => setConfirmPassword(e.target.value)}
                placeholder="再次输入相同密码"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:bg-white focus:border-slate-800 outline-none transition-colors"
                required
              />
            </div>
          </div>

          {errorMsg && (
            <div className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2 flex items-center gap-1.5">
              <span>⚠️</span>
              <span>{errorMsg}</span>
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={handleCancel}
              disabled={submitting}
              className="px-4 py-2 rounded-xl text-xs font-medium text-slate-600 hover:bg-slate-100 transition-colors cursor-pointer"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-semibold transition-colors shadow-2xs cursor-pointer disabled:opacity-50"
            >
              {submitting ? (
                <>
                  <svg className="animate-spin -ml-1 mr-1 h-3 w-3 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  正在保存...
                </>
              ) : (
                '保存新凭据'
              )}
            </button>
          </div>
        </form>
      )}

      {/* ── System Runtime & Service Control Section ── */}
      <div className="mt-5 pt-4 border-t border-slate-100 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-start sm:items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-blue-50 border border-blue-200 flex items-center justify-center text-lg shadow-xs shrink-0">
            ⚡
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-bold text-xs text-slate-800 tracking-tight">后台服务运行时与热重载控制</span>
              {sysStatus?.reload_active ? (
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-600 border border-emerald-200 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                  开发热重载已激活 (代码秒级热更)
                </span>
              ) : (
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                  生产稳定模式
                </span>
              )}
            </div>
            <div className="text-[11px] text-slate-500 mt-0.5 flex items-center gap-3 flex-wrap">
              <span>PID: <strong className="font-mono text-slate-700">{sysStatus?.pid || '...'}</strong></span>
              <span>端口: <strong className="font-mono text-slate-700">{sysStatus?.port || '8770'}</strong></span>
              <span>运行时间: <strong className="font-mono text-slate-700">{sysStatus?.uptime_human || '刚刚启动'}</strong></span>
              <span>Python: <strong className="font-mono text-slate-700">{sysStatus?.python_version || '3.x'}</strong></span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {!confirmRestart && !isRestarting && (
            <button
              type="button"
              onClick={() => setConfirmRestart(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 text-xs font-semibold transition-colors cursor-pointer shadow-2xs"
              title="重启后台 Python / Uvicorn 进程并平滑重连"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
              </svg>
              重启后台服务
            </button>
          )}

          {confirmRestart && !isRestarting && (
            <div className="flex items-center gap-2 bg-rose-50 border border-rose-200 rounded-xl px-3 py-1.5 animate-in fade-in duration-150">
              <span className="text-xs text-rose-800 font-medium">确认重启服务？</span>
              <button
                type="button"
                onClick={handleRestart}
                className="px-2.5 py-1 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-[11px] font-bold shadow-2xs cursor-pointer transition-colors"
              >
                确认重启
              </button>
              <button
                type="button"
                onClick={() => setConfirmRestart(false)}
                className="px-2 py-1 text-slate-600 hover:text-slate-900 text-[11px] font-medium cursor-pointer"
              >
                取消
              </button>
            </div>
          )}

          {isRestarting && (
            <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-xl px-3 py-1.5 text-xs text-amber-800 font-semibold shadow-2xs">
              <svg className="animate-spin h-3.5 w-3.5 text-amber-600" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <span>正在重启服务，自动探测重连中 ({countdown}s)...</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
