import { useState, useEffect } from 'react';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, BarElement, LineElement,
  PointElement, ArcElement, Title, Tooltip, Legend, Filler,
} from 'chart.js';
import { Line, Bar, Doughnut } from 'react-chartjs-2';
import { useApp } from '../../context.jsx';
import { apiFetch } from '../../api.js';
import { C, PALETTE } from '../../utils.js';

ChartJS.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, ArcElement, Title, Tooltip, Legend, Filler);
ChartJS.defaults.font.family = "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif";
ChartJS.defaults.font.size   = 11;
ChartJS.defaults.color       = '#64748b';
ChartJS.defaults.plugins.legend.display = false;
ChartJS.defaults.plugins.tooltip.backgroundColor = 'rgba(15,23,42,.88)';
ChartJS.defaults.plugins.tooltip.padding         = 10;
ChartJS.defaults.plugins.tooltip.cornerRadius    = 8;
ChartJS.defaults.plugins.tooltip.titleFont       = { size: 12, weight: '600' };
ChartJS.defaults.plugins.tooltip.bodyFont        = { size: 11 };
ChartJS.defaults.scale.grid.color                = '#f1f5f9';
ChartJS.defaults.scale.border.display            = false;
ChartJS.defaults.animation.duration              = 400;

const baseOpts = { maintainAspectRatio: false };
const noLegend = { plugins: { legend: { display: false } } };

export default function Analytics() {
  const { activeProject } = useApp();
  const [activeTab, setActiveTab] = useState('roi'); // 'roi' | 'traffic'
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  // Sync Chart.js canvas colors with Dark Mode
  useEffect(() => {
    function applyThemeColors() {
      const isDark = document.documentElement.classList.contains('dark');
      ChartJS.defaults.color = isDark ? '#94a3b8' : '#64748b';
      ChartJS.defaults.scale.grid.color = isDark ? 'rgba(51, 65, 85, 0.45)' : '#f1f5f9';
    }
    applyThemeColors();
    const observer = new MutationObserver(applyThemeColors);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setLoading(true);
    const projParam = activeProject && activeProject !== 'all' ? `&project=${encodeURIComponent(activeProject)}` : '';
    apiFetch(`/api/stats?days=${days}${projParam}`)
      .then(d => {
        setData(d);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, [days, activeProject]);

  const ov = data?.overview;
  const funnel = data?.funnel || {};
  const projectsRoi = data?.projects_roi || [];
  const topLinks = data?.top_links || [];

  const rangeBtns = [7, 30, 90, 0];
  const rangeLabel = { 7: '7d', 30: '30d', 90: '90d', 0: 'All' };

  if (loading && !data) {
    return (
      <div className="h-full flex items-center justify-center text-slate-400 text-sm gap-2">
        <span className="spin">⟳</span> 加载转化与流量全链路数据…
      </div>
    );
  }

  const hasAnyData = (ov && ov.total > 0) || (funnel && (funnel.hits_captured > 0 || funnel.scheduled > 0 || funnel.total_clicks > 0));

  if (!hasAnyData) {
    return (
      <div className="h-full overflow-y-auto p-8">
        <div className="max-w-5xl mx-auto">
          <div className="flex items-center justify-between mb-8">
            <div>
              <h2 className="text-lg font-semibold">商业转化与流量数据</h2>
              <p className="text-sm text-slate-400 mt-0.5">当前工作区: {activeProject === 'all' ? '全部项目 (Global)' : activeProject}</p>
            </div>
            <RangeButtons days={days} setDays={setDays} rangeBtns={rangeBtns} rangeLabel={rangeLabel} />
          </div>
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="1.5"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
            </div>
            <div className="text-slate-700 font-semibold text-lg">暂无监测线索或转化数据</div>
            <div className="text-slate-400 text-sm mt-1">请启动监听器或在当前工作区沉淀线索后查看全链路漏斗分析</div>
          </div>
        </div>
      </div>
    );
  }

  const tl = data.timeline || [];
  const tlLabels = tl.map(r => {
    const d = new Date(r.day + 'T00:00:00');
    return d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
  });

  const byHour = data.by_hour || [];
  const maxH   = Math.max(...byHour.map(r => r.count), 1);
  const byDow  = data.by_dow  || [];
  const maxD   = Math.max(...byDow.map(r => r.count), 1);
  const DOW    = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  const bySubPass = data.sub_pass || [];
  const total = ov ? (ov.posts + ov.comments) : 0;

  return (
    <div className="h-full overflow-y-auto p-6 md:p-8">
      <div className="max-w-6xl mx-auto space-y-7">

        {/* Top Header & Workspace Context */}
        <div className="flex items-center justify-between flex-wrap gap-4 pb-2 border-b border-slate-200">
          <div>
            <div className="flex items-center gap-2.5">
              <h2 className="text-xl font-bold text-slate-900 tracking-tight">商业转化全链路与引流归因看板</h2>
              <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                {activeProject === 'all' ? '🌐 全部工作区' : `🏷️ ${activeProject}`}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              打通「线索捕获 ➔ AI 深度过滤 ➔ 防封排期 ➔ 安全发射 ➔ 社区获赞 ➔ 短链引流 UV」全链路商业 ROI 漏斗
            </p>
          </div>

          <div className="flex items-center gap-3">
            {/* Tab Switcher */}
            <div className="flex items-center bg-slate-200/80 p-1 rounded-xl text-xs font-semibold">
              <button
                onClick={() => setActiveTab('roi')}
                className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
                  activeTab === 'roi'
                    ? 'bg-white text-indigo-700 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                📊 转化漏斗与引流 ROI
              </button>
              <button
                onClick={() => setActiveTab('traffic')}
                className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer ${
                  activeTab === 'traffic'
                    ? 'bg-white text-indigo-700 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                📈 流量分布与社区热力
              </button>
            </div>
            <RangeButtons days={days} setDays={setDays} rangeBtns={rangeBtns} rangeLabel={rangeLabel} />
          </div>
        </div>

        {activeTab === 'roi' ? (
          /* ── TAB 1: 全链路商业转化与引流 ROI 看板 ──────────────────────── */
          <div className="space-y-7">
            {/* Funnel KPI Ribbon */}
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
              <div className="card px-3.5 py-3 border-l-4 border-l-blue-500 shadow-2xs">
                <div className="text-[11px] text-slate-400 font-medium">1. 捕获线索</div>
                <div className="text-xl font-bold text-slate-800 mt-0.5">{(funnel.hits_captured || 0).toLocaleString()}</div>
                <div className="text-[10px] text-slate-400 mt-0.5">原始意向帖子</div>
              </div>
              <div className="card px-3.5 py-3 border-l-4 border-l-emerald-500 shadow-2xs">
                <div className="text-[11px] text-emerald-600 font-medium">2. AI 放行/复活</div>
                <div className="text-xl font-bold text-emerald-600 mt-0.5">{(funnel.ai_passed || 0).toLocaleString()}</div>
                <div className="text-[10px] text-emerald-700 font-medium mt-0.5">放行率 {funnel.pass_rate || 0}%</div>
              </div>
              <div className="card px-3.5 py-3 border-l-4 border-l-amber-500 shadow-2xs">
                <div className="text-[11px] text-amber-600 font-medium">3. 防封排期入队</div>
                <div className="text-xl font-bold text-amber-600 mt-0.5">{(funnel.scheduled || 0).toLocaleString()}</div>
                <div className="text-[10px] text-amber-700 font-medium mt-0.5">入队率 {funnel.schedule_rate || 0}%</div>
              </div>
              <div className="card px-3.5 py-3 border-l-4 border-l-indigo-500 shadow-2xs">
                <div className="text-[11px] text-indigo-600 font-medium">4. 社交安全投放</div>
                <div className="text-xl font-bold text-indigo-700 mt-0.5">{(funnel.published || 0).toLocaleString()}</div>
                <div className="text-[10px] text-indigo-700 font-medium mt-0.5">发射率 {funnel.publish_rate || 0}%</div>
              </div>
              <div className="card px-3.5 py-3 border-l-4 border-l-teal-500 shadow-2xs">
                <div className="text-[11px] text-teal-600 font-medium">5. 社区获赞跟评</div>
                <div className="text-xl font-bold text-teal-700 mt-0.5">+{funnel.total_upvotes || 0}</div>
                <div className="text-[10px] text-teal-700 font-medium mt-0.5">获赞率 {funnel.engagement_rate || 0}%</div>
              </div>
              <div className="card px-3.5 py-3 border-l-4 border-l-violet-500 shadow-2xs">
                <div className="text-[11px] text-violet-600 font-medium">6. 短链点击 PV</div>
                <div className="text-xl font-bold text-violet-700 mt-0.5">{(funnel.total_clicks || 0).toLocaleString()}</div>
                <div className="text-[10px] text-violet-700 font-medium mt-0.5">引流 CTR {funnel.ctr || 0}%</div>
              </div>
              <div className="card px-3.5 py-3 border-l-4 border-l-rose-500 shadow-2xs">
                <div className="text-[11px] text-rose-600 font-medium">7. 独立访客 UV</div>
                <div className="text-xl font-bold text-rose-700 mt-0.5">{(funnel.total_uv || 0).toLocaleString()}</div>
                <div className="text-[10px] text-rose-700 font-medium mt-0.5">纯净率 {funnel.uv_rate || 0}%</div>
              </div>
              <div className="card px-3.5 py-3 border-l-4 border-l-yellow-500 shadow-2xs">
                <div className="text-[11px] text-amber-700 font-medium">8. 黄金范式沉淀</div>
                <div className="text-xl font-bold text-amber-900 mt-0.5">{(funnel.winners || 0).toLocaleString()}</div>
                <div className="text-[10px] text-amber-700 font-medium mt-0.5">获赞 ≥3 模版</div>
              </div>
            </div>

            {/* Visual Conversion Funnel Flow */}
            <div className="card p-6 bg-gradient-to-br from-white to-slate-50 border border-slate-200">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="font-bold text-slate-800 text-base">商业转化全链路全景漏斗 (Full Funnel Flow)</h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    从公域线索捕获到私域独立站进站 UV 的逐层过滤与转化留存分析
                  </p>
                </div>
                <span className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-indigo-50 text-indigo-700 border border-indigo-200">
                  全链路穿透率: {funnel.hits_captured > 0 ? (funnel.total_uv / funnel.hits_captured * 100).toFixed(1) : 0}% UV/Hit
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-6 gap-3 pt-2">
                {/* Step 1 */}
                <div className="bg-white border border-slate-200 rounded-xl p-3.5 flex flex-col justify-between shadow-2xs">
                  <div>
                    <div className="flex items-center justify-between text-xs text-slate-400 font-semibold mb-1">
                      <span>阶段 01</span>
                      <span>100%</span>
                    </div>
                    <div className="font-bold text-sm text-slate-800">原始线索流</div>
                    <div className="text-2xl font-black text-blue-600 my-2">{funnel.hits_captured || 0}</div>
                    <p className="text-[11px] text-slate-400">社群关键词触发命中</p>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-1.5 mt-3 overflow-hidden">
                    <div className="bg-blue-500 h-full rounded-full" style={{ width: '100%' }} />
                  </div>
                </div>

                {/* Step 2 */}
                <div className="bg-white border border-slate-200 rounded-xl p-3.5 flex flex-col justify-between shadow-2xs">
                  <div>
                    <div className="flex items-center justify-between text-xs text-emerald-600 font-semibold mb-1">
                      <span>阶段 02</span>
                      <span>{funnel.pass_rate || 0}%</span>
                    </div>
                    <div className="font-bold text-sm text-slate-800">AI 过滤与复活</div>
                    <div className="text-2xl font-black text-emerald-600 my-2">{funnel.ai_passed || 0}</div>
                    <p className="text-[11px] text-slate-400">高意向与逆向纠偏线索</p>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-1.5 mt-3 overflow-hidden">
                    <div className="bg-emerald-500 h-full rounded-full" style={{ width: `${Math.min(100, funnel.pass_rate || 0)}%` }} />
                  </div>
                </div>

                {/* Step 3 */}
                <div className="bg-white border border-slate-200 rounded-xl p-3.5 flex flex-col justify-between shadow-2xs">
                  <div>
                    <div className="flex items-center justify-between text-xs text-amber-600 font-semibold mb-1">
                      <span>阶段 03</span>
                      <span>{funnel.schedule_rate || 0}%</span>
                    </div>
                    <div className="font-bold text-sm text-slate-800">防封节流入队</div>
                    <div className="text-2xl font-black text-amber-600 my-2">{funnel.scheduled || 0}</div>
                    <p className="text-[11px] text-slate-400">错峰注入冷却保护</p>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-1.5 mt-3 overflow-hidden">
                    <div className="bg-amber-500 h-full rounded-full" style={{ width: `${Math.min(100, funnel.schedule_rate || 0)}%` }} />
                  </div>
                </div>

                {/* Step 4 */}
                <div className="bg-white border border-slate-200 rounded-xl p-3.5 flex flex-col justify-between shadow-2xs">
                  <div>
                    <div className="flex items-center justify-between text-xs text-indigo-600 font-semibold mb-1">
                      <span>阶段 04</span>
                      <span>{funnel.publish_rate || 0}%</span>
                    </div>
                    <div className="font-bold text-sm text-slate-800">安全成功投放</div>
                    <div className="text-2xl font-black text-indigo-700 my-2">{funnel.published || 0}</div>
                    <p className="text-[11px] text-slate-400">Reddit / 𝕏 成功上链</p>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-1.5 mt-3 overflow-hidden">
                    <div className="bg-indigo-600 h-full rounded-full" style={{ width: `${Math.min(100, funnel.publish_rate || 0)}%` }} />
                  </div>
                </div>

                {/* Step 5 */}
                <div className="bg-white border border-slate-200 rounded-xl p-3.5 flex flex-col justify-between shadow-2xs">
                  <div>
                    <div className="flex items-center justify-between text-xs text-teal-600 font-semibold mb-1">
                      <span>阶段 05</span>
                      <span>{funnel.engagement_rate || 0}%</span>
                    </div>
                    <div className="font-bold text-sm text-slate-800">社区获赞反馈</div>
                    <div className="text-2xl font-black text-teal-700 my-2">+{funnel.total_upvotes || 0}</div>
                    <p className="text-[11px] text-slate-400">真实点赞回扫与跟评</p>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-1.5 mt-3 overflow-hidden">
                    <div className="bg-teal-600 h-full rounded-full" style={{ width: `${Math.min(100, funnel.engagement_rate || 0)}%` }} />
                  </div>
                </div>

                {/* Step 6 */}
                <div className="bg-white border border-slate-200 rounded-xl p-3.5 flex flex-col justify-between shadow-2xs">
                  <div>
                    <div className="flex items-center justify-between text-xs text-rose-600 font-semibold mb-1">
                      <span>阶段 06</span>
                      <span>{funnel.ctr || 0}% CTR</span>
                    </div>
                    <div className="font-bold text-sm text-slate-800">独立站进站引流</div>
                    <div className="text-2xl font-black text-rose-700 my-2">{funnel.total_uv || 0} <span className="text-xs font-normal text-slate-500">UV</span></div>
                    <p className="text-[11px] text-slate-400">{funnel.total_clicks || 0} 次智能 UTM 点击</p>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-1.5 mt-3 overflow-hidden">
                    <div className="bg-rose-500 h-full rounded-full" style={{ width: `${Math.min(100, (funnel.total_uv / (funnel.published || 1)) * 100)}%` }} />
                  </div>
                </div>
              </div>
            </div>

            {/* Multi-Project ROI Comparison Table */}
            <div className="card p-6">
              <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                <div>
                  <h3 className="font-bold text-slate-800 text-base">多品牌独立站 ROI 引流对比矩阵</h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    多项目隔离监测环境下的线索获取量、发射量、社区互动与独立站引流转化综合对比
                  </p>
                </div>
                <span className="text-xs font-medium text-slate-400">
                  共计 {projectsRoi.length} 个独立站工作区
                </span>
              </div>

              {projectsRoi.length === 0 ? (
                <div className="text-slate-400 text-sm text-center py-8">暂无独立站项目数据</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs text-slate-400 border-b border-slate-100">
                        <th className="text-left pb-2 font-medium">品牌独立站 / 项目</th>
                        <th className="text-left pb-2 font-medium">覆盖渠道</th>
                        <th className="text-right pb-2 font-medium">监测线索</th>
                        <th className="text-right pb-2 font-medium">AI 放行</th>
                        <th className="text-right pb-2 font-medium">安全发射</th>
                        <th className="text-right pb-2 font-medium">真实获赞</th>
                        <th className="text-right pb-2 font-medium">短链点击 PV</th>
                        <th className="text-right pb-2 font-medium">独立访客 UV</th>
                        <th className="text-right pb-2 font-medium">引流转化率 (CTR)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {projectsRoi.map(p => (
                        <tr key={p.name} className="hover:bg-slate-50/80 transition-colors">
                          <td className="py-3 font-semibold text-slate-800">
                            <div className="flex items-center gap-1.5">
                              <span>🏷️ {p.name}</span>
                              {p.site_url && (
                                <a
                                  href={p.site_url}
                                  target="_blank"
                                  rel="noopener"
                                  className="text-xs text-blue-500 hover:text-blue-700 hover:underline font-normal"
                                >
                                  ↗
                                </a>
                              )}
                            </div>
                          </td>
                          <td className="py-3 text-slate-500 text-xs">
                            <div className="flex items-center gap-1">
                              {(p.platforms || []).map(plat => (
                                <span
                                  key={plat}
                                  className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                    plat === 'reddit' ? 'bg-orange-100 text-orange-800' : 'bg-black text-white'
                                  }`}
                                >
                                  {plat === 'reddit' ? 'r/' : '𝕏'}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td className="py-3 text-right font-medium text-slate-700">{p.hits.toLocaleString()}</td>
                          <td className="py-3 text-right text-emerald-600 font-semibold">{p.passed.toLocaleString()}</td>
                          <td className="py-3 text-right text-indigo-700 font-semibold">{p.published.toLocaleString()}</td>
                          <td className="py-3 text-right text-amber-700 font-bold">
                            +{p.upvotes || 0}
                            {p.winners > 0 && (
                              <span className="text-[10px] ml-1 bg-amber-100 text-amber-800 px-1 py-0.2 rounded font-bold">
                                🏆 {p.winners}
                              </span>
                            )}
                          </td>
                          <td className="py-3 text-right text-violet-700 font-semibold">{p.clicks.toLocaleString()}</td>
                          <td className="py-3 text-right text-rose-700 font-bold">{p.uv.toLocaleString()}</td>
                          <td className="py-3 text-right">
                            <span className="inline-flex items-center gap-1.5 font-bold text-slate-700">
                              <span>{p.ctr}%</span>
                              <span className="w-12 h-1.5 bg-slate-100 rounded-full overflow-hidden inline-block">
                                <span className="h-full bg-indigo-500 rounded-full block" style={{ width: `${Math.min(100, p.ctr)}%` }} />
                              </span>
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Top Attributed Links & Conversion Pathways */}
            <div className="card p-6">
              <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                <div>
                  <h3 className="font-bold text-slate-800 text-base">高价值归因短链与穿透分析 (Top Attributed Short Links)</h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    带有智能渠道 UTM 标记的短链访问量、独立 IP 去重统计与原帖点赞联动穿透
                  </p>
                </div>
                <span className="text-xs font-semibold text-slate-500">
                  TOP 10 转化路径
                </span>
              </div>

              {topLinks.length === 0 ? (
                <div className="text-slate-400 text-sm text-center py-8">
                  暂无短链点击数据（在队列中生成带链接的回复并发布后，此处将自动统计真实进站引流效果）
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs text-slate-400 border-b border-slate-100">
                        <th className="text-left pb-2 font-medium">短链代码</th>
                        <th className="text-left pb-2 font-medium">渠道 / 社区</th>
                        <th className="text-left pb-2 font-medium">目标落地页 (Landing Page)</th>
                        <th className="text-right pb-2 font-medium">点击量 (PV)</th>
                        <th className="text-right pb-2 font-medium">独立访客 (UV)</th>
                        <th className="text-right pb-2 font-medium">关联贴获赞</th>
                        <th className="text-right pb-2 font-medium">范式评级</th>
                        <th className="text-right pb-2 font-medium">操作</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {topLinks.map(l => (
                        <tr key={l.code} className="hover:bg-slate-50 transition-colors">
                          <td className="py-2.5 font-mono font-bold text-indigo-600">
                            /r/{l.code}
                          </td>
                          <td className="py-2.5 text-xs text-slate-600">
                            {l.subreddit ? `r/${l.subreddit}` : (l.platform === 'x' ? '𝕏 Tweet' : 'Reddit')}
                          </td>
                          <td className="py-2.5 max-w-[280px] truncate text-slate-500 text-xs" title={l.target_url}>
                            {l.target_url}
                          </td>
                          <td className="py-2.5 text-right font-bold text-slate-800">{l.clicks}</td>
                          <td className="py-2.5 text-right font-bold text-rose-600">{l.uv}</td>
                          <td className="py-2.5 text-right font-semibold text-amber-700">+{l.upvotes || 0}</td>
                          <td className="py-2.5 text-right">
                            {l.is_winner ? (
                              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-200">
                                🏆 黄金范式
                              </span>
                            ) : (
                              <span className="text-[10px] text-slate-400">标准投放</span>
                            )}
                          </td>
                          <td className="py-2.5 text-right">
                            <a
                              href={`/r/${l.code}`}
                              target="_blank"
                              rel="noopener"
                              className="text-xs text-blue-600 hover:text-blue-800 hover:underline font-medium"
                              title="在新标签页测试短链跳转与 UTM 注入"
                            >
                              测试跳转 ↗
                            </a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        ) : (
          /* ── TAB 2: 历史流量与社区热力看板 ──────────────────────────── */
          <div className="space-y-7">
            {/* Timeline */}
            <div className="card p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className="font-semibold text-slate-800">线索增长趋势 (Hits over time)</div>
                  <div className="text-xs text-slate-400 mt-0.5">每日捕获总量与 AI 放行曲线</div>
                </div>
                <div className="flex items-center gap-3 text-xs text-slate-500">
                  <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-blue-500 inline-block" />总线索</span>
                  <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-violet-400 inline-block" />帖子 Posts</span>
                  <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-emerald-400 inline-block" />AI 放行</span>
                </div>
              </div>
              <div style={{ height: 220 }}>
                <Line
                  data={{
                    labels: tlLabels,
                    datasets: [
                      { label: 'Total',  data: tl.map(r => r.total),  borderColor: C.blue,    backgroundColor: C.blueFill,    borderWidth: 2,   pointRadius: 2, tension: .35, fill: true },
                      { label: 'Posts',  data: tl.map(r => r.posts),  borderColor: C.violet,  backgroundColor: C.violetFill,  borderWidth: 1.5, pointRadius: 0, tension: .35, fill: true },
                      { label: 'Passed', data: tl.map(r => r.passed), borderColor: C.emerald, backgroundColor: C.emeraldFill, borderWidth: 1.5, pointRadius: 0, tension: .35, fill: true },
                    ],
                  }}
                  options={{ ...baseOpts, interaction: { mode: 'index', intersect: false }, scales: { x: { ticks: { maxTicksLimit: 10, maxRotation: 0 } }, y: { beginAtZero: true, ticks: { precision: 0 } } }, plugins: { legend: { display: false } } }}
                />
              </div>
            </div>

            {/* Type donut + subreddits */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="card p-6">
                <div className="font-semibold text-slate-800 mb-1">内容形态分布</div>
                <div className="text-xs text-slate-400 mb-4">主贴 (Posts) vs 回帖 (Comments)</div>
                <div style={{ height: 160 }}>
                  {total > 0 && (
                    <Doughnut
                      data={{ labels: ['Posts', 'Comments'], datasets: [{ data: [ov.posts, ov.comments], backgroundColor: [C.blue, C.violet], borderWidth: 0, hoverOffset: 4 }] }}
                      options={{ ...baseOpts, cutout: '72%', plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.raw.toLocaleString()} (${Math.round(ctx.raw / total * 100)}%)` } } } }}
                    />
                  )}
                </div>
                <div className="flex justify-center gap-4 mt-3 text-xs text-slate-500">
                  <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-blue-500 inline-block" />Posts {total ? Math.round(ov.posts / total * 100) : 0}%</span>
                  <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-violet-500 inline-block" />Comments {total ? Math.round(ov.comments / total * 100) : 0}%</span>
                </div>
              </div>
              <div className="lg:col-span-2 card p-6">
                <div className="font-semibold text-slate-800 mb-1">活跃社群板块分布</div>
                <div className="text-xs text-slate-400 mb-4">按线索捕获总量与 AI 放行深度排序</div>
                <div style={{ height: 220 }}>
                  <Bar
                    data={{
                      labels: (data.by_subreddit || []).map(r => 'r/' + r.name),
                      datasets: [
                        { label: '捕获总量', data: (data.by_subreddit || []).map(r => r.count),  backgroundColor: C.blue,    borderRadius: 4 },
                        { label: '放行优质', data: (data.by_subreddit || []).map(r => r.passed), backgroundColor: C.emerald, borderRadius: 4 },
                      ],
                    }}
                    options={{ ...baseOpts, indexAxis: 'y', interaction: { mode: 'index', intersect: false }, scales: { x: { beginAtZero: true, ticks: { precision: 0 } }, y: { ticks: { font: { size: 11 } } } }, plugins: { legend: { display: true, position: 'top', labels: { boxWidth: 10, padding: 12, font: { size: 11 } } } } }}
                  />
                </div>
              </div>
            </div>

            {/* Keywords + By hour */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="card p-6">
                <div className="font-semibold text-slate-800 mb-1">高频触发词排行</div>
                <div className="text-xs text-slate-400 mb-4">命中频次最高的核心意图关键词</div>
                <div style={{ height: 240 }}>
                  <Bar
                    data={{
                      labels: (data.by_keyword || []).map(r => r.keyword),
                      datasets: [{ data: (data.by_keyword || []).map(r => r.count), backgroundColor: (data.by_keyword || []).map((_, i) => PALETTE[i % PALETTE.length]), borderRadius: 4 }],
                    }}
                    options={{ ...baseOpts, ...noLegend, indexAxis: 'y', scales: { x: { beginAtZero: true, ticks: { precision: 0 } }, y: { ticks: { font: { size: 11, family: 'monospace' } } } } }}
                  />
                </div>
              </div>
              <div className="card p-6">
                <div className="font-semibold text-slate-800 mb-1">时段热力分布 (UTC)</div>
                <div className="text-xs text-slate-400 mb-4">社区活跃高峰与最佳投放时段</div>
                <div style={{ height: 240 }}>
                  <Bar
                    data={{
                      labels: byHour.map(r => r.hour === 0 ? '12am' : r.hour < 12 ? `${r.hour}am` : r.hour === 12 ? '12pm' : `${r.hour - 12}pm`),
                      datasets: [{ data: byHour.map(r => r.count), backgroundColor: byHour.map(r => `rgba(59,130,246,${0.2 + r.count / maxH * 0.8})`), borderRadius: 3 }],
                    }}
                    options={{ ...baseOpts, ...noLegend, scales: { x: { ticks: { maxRotation: 0, font: { size: 10 } } }, y: { beginAtZero: true, ticks: { precision: 0 } } } }}
                  />
                </div>
              </div>
            </div>

            {/* Sub pass rate + Top authors */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="card p-6">
                <div className="font-semibold text-slate-800 mb-1">社群质量透视 <span className="text-xs text-slate-400 font-normal">(AI 放行率, ≥3次筛选)</span></div>
                <div className="text-xs text-slate-400 mb-4">商业转化匹配度最高的 Subreddit</div>
                <div style={{ height: 220 }}>
                  <Bar
                    data={{
                      labels: bySubPass.map(r => `r/${r.name}`),
                      datasets: [{ data: bySubPass.map(r => r.rate), backgroundColor: bySubPass.map(r => { const h = r.rate / 100; return `rgba(${Math.round(16 + h * 224 - h * 200)},${Math.round(185 - h * 30)},${Math.round(129 - h * 90)},0.85)`; }), borderRadius: 4 }],
                    }}
                    options={{ ...baseOpts, ...noLegend, indexAxis: 'y', scales: { x: { beginAtZero: true, max: 100, ticks: { callback: v => v + '%' } }, y: { ticks: { font: { size: 11 } } } }, plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => `${ctx.raw}% 放行率 (${bySubPass[ctx.dataIndex]?.count} 次筛选)` } } } }}
                  />
                </div>
              </div>
              <div className="card p-6 flex flex-col">
                <div className="font-semibold text-slate-800 mb-1">高频提及活跃用户</div>
                <div className="text-xs text-slate-400 mb-3">最常探讨您目标痛点与关键词的用户</div>
                <div className="flex-1 overflow-auto">
                  {!(data.top_authors || []).length ? (
                    <div className="text-slate-400 text-sm text-center py-6">暂无用户数据</div>
                  ) : (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-xs text-slate-400 border-b border-slate-100">
                          <th className="text-left pb-2 font-medium">用户</th>
                          <th className="text-right pb-2 font-medium">线索数</th>
                          <th className="text-right pb-2 font-medium">帖子</th>
                          <th className="text-right pb-2 font-medium">评论</th>
                          <th className="text-right pb-2 font-medium">放行</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-50">
                        {(data.top_authors || []).map((r, i) => (
                          <tr key={r.author} className="hover:bg-slate-50 transition-colors">
                            <td className="py-2 pr-3">
                              <div className="flex items-center gap-2">
                                <span className="text-xs text-slate-300 w-4 text-right">{i + 1}</span>
                                <a href={`https://reddit.com/u/${r.author}`} target="_blank" rel="noopener" className="font-medium text-slate-700 hover:text-blue-600 transition-colors">u/{r.author}</a>
                              </div>
                            </td>
                            <td className="py-2 text-right font-semibold text-slate-700">{r.count}</td>
                            <td className="py-2 text-right text-blue-600">{r.posts}</td>
                            <td className="py-2 text-right text-violet-600">{r.comments}</td>
                            <td className="py-2 text-right text-emerald-600">{r.passed || 0}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

function RangeButtons({ days, setDays, rangeBtns, rangeLabel }) {
  return (
    <div className="flex items-center bg-slate-100 rounded-xl p-1 gap-0.5">
      {rangeBtns.map(d => (
        <button
          key={d}
          onClick={() => setDays(d)}
          className={`view-btn text-xs px-3 py-1.5${days === d ? ' active' : ''}`}
        >
          {rangeLabel[d]}
        </button>
      ))}
    </div>
  );
}
