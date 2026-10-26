import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../../api.js';

export default function AccountHealthMatrix() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [doctorLoading, setDoctorLoading] = useState(false);
  const [doctorReport, setDoctorReport] = useState(null);
  const [showDoctorModal, setShowDoctorModal] = useState(false);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch('/api/accounts/health');
      if (res && res.ok) {
        setData(res);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  const runDoctor = async () => {
    setDoctorLoading(true);
    setShowDoctorModal(true);
    try {
      const res = await apiFetch('/api/doctor');
      if (res && res.ok) {
        setDoctorReport(res.diagnostics || []);
      } else {
        setDoctorReport([]);
        alert(`体检异常: ${res?.error || '未知错误'}`);
      }
    } catch (e) {
      alert(`体检请求异常: ${e}`);
    } finally {
      setDoctorLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, [fetchHealth]);

  if (!data) return null;

  const accounts = data.accounts || [];
  const readyCount = accounts.filter(a => a.status === 'ready').length;
  const coolingCount = accounts.filter(a => a.status === 'cooling').length;
  const totalUsed = accounts.reduce((sum, a) => sum + (a.today_used || 0), 0);
  const totalLimit = accounts.reduce((sum, a) => sum + (a.daily_limit || 0), 0);

  return (
    <div className="bg-gradient-to-br from-slate-900 via-slate-900 to-indigo-950 border border-slate-800 rounded-2xl p-5 text-white shadow-lg mb-8">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3 pb-4 border-b border-slate-800/80">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center text-xl shadow-inner">
            🛡️
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-base tracking-tight text-white">多账号风控配额与冷却监控矩阵</h3>
              <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                Anti-Ban Engine
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              实时掌控 Reddit / 𝕏 账号的单日安全发帖配额使用进度与防封错峰冷却倒计时
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={runDoctor}
            disabled={doctorLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 text-white rounded-xl text-xs font-semibold shadow-sm transition-all cursor-pointer disabled:opacity-50"
            title="全面测试 Reddit/X 会话有效性、AI API 与 Bark 推送健康度"
          >
            <span className={doctorLoading ? 'spin' : ''}>🩺</span>
            {doctorLoading ? '正在体检…' : '凭证体检 (Doctor)'}
          </button>

          <button
            onClick={fetchHealth}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 active:bg-slate-600 text-slate-300 hover:text-white rounded-xl text-xs font-medium border border-slate-700/80 transition-all cursor-pointer disabled:opacity-50"
            title="刷新各账号健康与冷却倒计时"
          >
            <span className={loading ? 'spin' : ''}>⟳</span>
            {loading ? '检测中…' : '刷新矩阵'}
          </button>
        </div>
      </div>

      {/* Overview Stat Counters */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 my-4">
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-3">
          <div className="text-[11px] font-medium text-slate-400">活跃社交账号</div>
          <div className="text-xl font-bold text-white mt-1 flex items-baseline gap-1.5">
            {accounts.length}
            <span className="text-xs font-normal text-slate-400">个</span>
          </div>
        </div>
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-3">
          <div className="text-[11px] font-medium text-emerald-400">安全就绪可发射</div>
          <div className="text-xl font-bold text-emerald-400 mt-1 flex items-baseline gap-1.5">
            {readyCount}
            <span className="text-xs font-normal text-slate-400">个</span>
          </div>
        </div>
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-3">
          <div className="text-[11px] font-medium text-amber-400">风控错峰冷却中</div>
          <div className="text-xl font-bold text-amber-400 mt-1 flex items-baseline gap-1.5">
            {coolingCount}
            <span className="text-xs font-normal text-slate-400">个</span>
          </div>
        </div>
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-3">
          <div className="text-[11px] font-medium text-indigo-400">今日总配额消耗</div>
          <div className="text-xl font-bold text-indigo-300 mt-1 flex items-baseline gap-1.5">
            {totalUsed} <span className="text-xs font-normal text-slate-400">/ {totalLimit} 帖</span>
          </div>
        </div>
      </div>

      {/* Account Cards Grid */}
      {accounts.length === 0 ? (
        <div className="text-center py-6 text-xs text-slate-400 bg-slate-800/20 rounded-xl border border-dashed border-slate-800">
          尚未配置 Reddit 或 𝕏 账号凭据，请在下方添加社交账号以启用防封矩阵监控
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5 mt-2">
          {accounts.map(acc => {
            const isReddit = acc.type === 'reddit';
            const pct = acc.usage_pct || 0;
            const barColor = pct >= 85 ? 'bg-rose-500' : pct >= 50 ? 'bg-amber-400' : 'bg-emerald-400';

            let statusBadge = null;
            if (acc.status === 'ready') {
              statusBadge = (
                <span className="text-[11px] font-bold px-2 py-0.5 rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-1">
                  ● 安全就绪
                </span>
              );
            } else if (acc.status === 'cooling') {
              const minLeft = Math.ceil((acc.cooldown_remaining_seconds || 0) / 60);
              statusBadge = (
                <span className="text-[11px] font-bold px-2 py-0.5 rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center gap-1 animate-pulse">
                  ⏳ 冷却中 ({minLeft}m)
                </span>
              );
            } else if (acc.status === 'limit_reached') {
              statusBadge = (
                <span className="text-[11px] font-bold px-2 py-0.5 rounded-lg bg-rose-500/20 text-rose-300 border border-rose-500/30 flex items-center gap-1">
                  🛑 达今日上限
                </span>
              );
            } else {
              statusBadge = (
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-lg bg-slate-700 text-slate-400 border border-slate-600 flex items-center gap-1">
                  ⚠️ 未配置
                </span>
              );
            }

            return (
              <div
                key={acc.id}
                className="bg-slate-800/80 hover:bg-slate-800 border border-slate-700/80 rounded-xl p-3.5 transition-all flex flex-col justify-between gap-3 shadow-2xs"
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2 min-w-0">
                      {isReddit ? (
                        <span className="w-6 h-6 rounded-lg bg-orange-500/20 text-orange-400 border border-orange-500/30 flex items-center justify-center font-bold text-xs flex-shrink-0">
                          r/
                        </span>
                      ) : (
                        <span className="w-6 h-6 rounded-lg bg-black text-white border border-slate-700 flex items-center justify-center font-bold text-xs flex-shrink-0">
                          𝕏
                        </span>
                      )}
                      <div className="font-semibold text-xs text-white truncate" title={acc.name}>
                        {acc.name}
                      </div>
                    </div>
                    {statusBadge}
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
                    <span>单日安全配额</span>
                    <span className="font-semibold text-slate-200">
                      {acc.today_used} / {acc.daily_limit} 贴 ({pct}%)
                    </span>
                  </div>

                  {/* Progress bar */}
                  <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>

                <div className="flex items-center justify-between text-[10px] text-slate-400 pt-2 border-t border-slate-700/60">
                  <span>模式: <span className="text-slate-300 font-mono">{acc.auth_mode}</span></span>
                  <span>上次发帖: <span className="text-slate-300">{acc.last_reply_time}</span></span>
                  <span>冷却: <span className="text-slate-300">{isReddit ? '45m' : '15m'}</span></span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Doctor Diagnostic Report Modal ──────────────────────── */}
      {showDoctorModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl max-w-lg w-full p-6 text-white space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2.5">
                <span className="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 flex items-center justify-center text-lg">
                  🩺
                </span>
                <div>
                  <h3 className="text-sm font-bold text-white">凭证与会话深度体检 (Doctor)</h3>
                  <p className="text-[11px] text-slate-400">检测社媒 Cookie 有效性、AI 意向分类与 Bark 通知链路</p>
                </div>
              </div>
              <button
                onClick={() => setShowDoctorModal(false)}
                className="w-7 h-7 rounded-lg hover:bg-slate-800 flex items-center justify-center text-slate-400 hover:text-white text-xs cursor-pointer"
              >
                ✕
              </button>
            </div>

            {doctorLoading ? (
              <div className="py-12 text-center text-slate-400 text-xs flex flex-col items-center gap-3">
                <span className="spin text-2xl text-indigo-400">⟳</span>
                <span>正在向 Reddit / 𝕏 / Bark / AI 发起会话存活探测...</span>
              </div>
            ) : doctorReport && doctorReport.length > 0 ? (
              <div className="space-y-2.5 max-h-[60vh] overflow-y-auto pr-1">
                {doctorReport.map((diag, idx) => {
                  const isHealthy = diag.status === 'healthy';
                  const isExpired = diag.status === 'expired';
                  const isMissing = diag.status === 'missing';

                  return (
                    <div
                      key={idx}
                      className="p-3 rounded-xl bg-slate-800/80 border border-slate-700/80 flex items-start justify-between gap-3 text-xs"
                    >
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-white">{diag.name}</span>
                          {diag.account && (
                            <span className="text-[11px] font-mono text-indigo-300 bg-slate-900/60 px-1.5 py-0.5 rounded border border-slate-700">
                              {diag.account}
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-slate-400 truncate">
                          {diag.details || '无附加信息'}
                        </div>
                      </div>

                      <span
                        className={`text-[11px] font-bold px-2 py-0.5 rounded-md border flex-shrink-0 flex items-center gap-1 ${
                          isHealthy
                            ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                            : isExpired
                            ? 'bg-rose-500/20 text-rose-300 border-rose-500/40 animate-pulse'
                            : isMissing
                            ? 'bg-slate-700 text-slate-400 border-slate-600'
                            : 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                        }`}
                      >
                        {isHealthy ? '● 会话正常' : isExpired ? '🛑 Cookie失效' : isMissing ? '○ 未配置' : '⚠️ 连接超时'}
                      </span>
                    </div>
                  );
                })}

                <div className="bg-slate-800/50 rounded-xl p-3 border border-slate-700/60 text-[11px] text-slate-300 space-y-1">
                  <div className="font-semibold text-slate-200">💡 体检建议:</div>
                  <p>• 若 Reddit/𝕏 显示「Cookie失效」，只需用浏览器打开对应社交网站重新复制 Cookie 并更新 Vault 即可。</p>
                  <p>• 若为「未配置」，可根据需要在下方 Vault 录入相应账号或通知渠道。</p>
                </div>
              </div>
            ) : (
              <div className="py-8 text-center text-slate-400 text-xs">
                暂未获取到体检数据，请点击下方「重新体检」。
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
              <button
                onClick={runDoctor}
                disabled={doctorLoading}
                className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 text-white rounded-xl text-xs font-semibold transition cursor-pointer disabled:opacity-50"
              >
                {doctorLoading ? '检测中…' : '↺ 重新体检'}
              </button>
              <button
                onClick={() => setShowDoctorModal(false)}
                className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-semibold transition cursor-pointer"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
