export function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function parseHitTimestamp(ts, createdAt) {
  if (typeof ts === 'number' && ts > 0) {
    // If ts is in seconds (standard Unix timestamp < 1e11), convert to ms
    return ts < 1e11 ? Math.floor(ts * 1000) : Math.floor(ts);
  }
  if (typeof ts === 'string' && ts.trim()) {
    const num = Number(ts);
    if (!isNaN(num) && num > 0) {
      return num < 1e11 ? Math.floor(num * 1000) : Math.floor(num);
    }
    const parsed = Date.parse(ts);
    if (!isNaN(parsed) && parsed > 0) return parsed;
  }
  if (createdAt) {
    const parsed = Date.parse(createdAt);
    if (!isNaN(parsed) && parsed > 0) return parsed;
  }
  return null;
}

export function formatExactDateTime(ts, createdAt) {
  const ms = parseHitTimestamp(ts, createdAt);
  if (!ms) return '';
  const d = new Date(ms);
  if (isNaN(d.getTime())) return '';

  const pad = n => String(n).padStart(2, '0');
  const y = d.getFullYear();
  const m = pad(d.getMonth() + 1);
  const day = pad(d.getDate());
  const h = pad(d.getHours());
  const min = pad(d.getMinutes());

  const now = new Date();
  return y === now.getFullYear() ? `${m}-${day} ${h}:${min}` : `${y}-${m}-${day} ${h}:${min}`;
}

export function formatFullDateTime(ts, createdAt) {
  const ms = parseHitTimestamp(ts, createdAt);
  if (!ms) return '';
  const d = new Date(ms);
  if (isNaN(d.getTime())) return '';

  const pad = n => String(n).padStart(2, '0');
  const y = d.getFullYear();
  const m = pad(d.getMonth() + 1);
  const day = pad(d.getDate());
  const h = pad(d.getHours());
  const min = pad(d.getMinutes());
  const s = pad(d.getSeconds());

  const offsetMinutes = -d.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? '+' : '-';
  const offsetHours = pad(Math.floor(Math.abs(offsetMinutes) / 60));
  const offsetMins = pad(Math.abs(offsetMinutes) % 60);
  const tzStr = `UTC${sign}${offsetHours}:${offsetMins}`;

  return `${y}-${m}-${day} ${h}:${min}:${s} (${tzStr})`;
}

export function formatTimeAgo(ms) {
  if (!ms) return '';
  const diffSec = Math.floor((Date.now() - ms) / 1000);
  if (diffSec < 5) return '刚刚';
  if (diffSec < 60) return `${diffSec}秒前`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}分钟前`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}小时前`;
  if (diffSec < 86400 * 30) return `${Math.floor(diffSec / 86400)}天前`;
  if (diffSec < 86400 * 365) return `${Math.floor(diffSec / (86400 * 30))}个月前`;
  return `${Math.floor(diffSec / (86400 * 365))}年前`;
}

export function getHitTimeDetails(hit) {
  if (!hit) {
    return { ms: null, exact: '', relative: '', full: '', label: '未知时间' };
  }
  const ms = parseHitTimestamp(hit.ts, hit.created_at);
  if (!ms) {
    return { ms: null, exact: '', relative: '', full: '', label: '刚刚' };
  }
  const exact = formatExactDateTime(hit.ts, hit.created_at);
  const relative = formatTimeAgo(ms);
  const full = formatFullDateTime(hit.ts, hit.created_at);
  return {
    ms,
    exact,
    relative,
    full,
    label: exact ? `${exact} (${relative})` : relative,
  };
}

export function getQueueTimeInfo(item) {
  if (!item) {
    return {
      primaryType: 'unknown',
      prefix: '操作时间',
      exact: '',
      relative: '',
      full: '',
      label: '未知时间',
      createdExact: '',
      createdRel: '',
      createdFull: '',
      postExact: '',
      postRel: '',
      postFull: '',
      scheduledExact: '',
      scheduledRel: '',
      scheduledFull: '',
    };
  }

  const nowMs = Date.now();
  const createdMs = parseHitTimestamp(null, item.created_at);
  const scheduledMs = item.scheduled_at ? parseHitTimestamp(item.scheduled_at) : null;
  const submittedMs = item.submitted_at ? parseHitTimestamp(item.submitted_at) : null;
  const failedMs = item.failed_at ? parseHitTimestamp(item.failed_at) : null;
  const updatedMs = item.updated_at ? parseHitTimestamp(item.updated_at) : null;
  const postMs = parseHitTimestamp(item.post_ts, item.post_created_at);

  let primaryType = 'created';
  let primaryMs = createdMs;
  let prefix = '入队于';

  if (item.status === 'submitted') {
    primaryType = 'submitted';
    primaryMs = submittedMs || updatedMs || createdMs;
    prefix = '提交于';
  } else if (item.status === 'failed') {
    primaryType = 'failed';
    primaryMs = failedMs || updatedMs || scheduledMs || createdMs;
    prefix = '失败于';
  } else if (item.status === 'scheduled') {
    primaryType = 'scheduled';
    primaryMs = scheduledMs || createdMs;
    prefix = '预计执行';
  } else if (item.status === 'needs_review') {
    primaryType = 'needs_review';
    primaryMs = updatedMs || createdMs;
    prefix = '拦截于';
  } else if (item.status === 'cancelled') {
    primaryType = 'cancelled';
    primaryMs = updatedMs || createdMs;
    prefix = '取消于';
  }

  const exact = primaryMs ? formatExactDateTime(primaryMs) : '';
  let relative = '';
  if (primaryMs) {
    if (primaryType === 'scheduled') {
      const diffSec = Math.floor((primaryMs - nowMs) / 1000);
      if (diffSec <= 10) {
        relative = '即将执行';
      } else if (diffSec < 60) {
        relative = `${diffSec}秒后`;
      } else if (diffSec < 3600) {
        relative = `约${Math.max(1, Math.round(diffSec / 60))}分钟后`;
      } else {
        relative = `约${Math.round(diffSec / 3600)}小时后`;
      }
    } else {
      relative = formatTimeAgo(primaryMs);
    }
  }
  const full = primaryMs ? formatFullDateTime(primaryMs) : '';

  // Enqueued / Created time
  const createdExact = createdMs ? formatExactDateTime(createdMs) : '';
  const createdRel = createdMs ? formatTimeAgo(createdMs) : '';
  const createdFull = createdMs ? formatFullDateTime(createdMs) : '';

  // Scheduled time
  const scheduledExact = scheduledMs ? formatExactDateTime(scheduledMs) : '';
  const scheduledRel = scheduledMs ? (
    scheduledMs > nowMs
      ? `约${Math.max(1, Math.round((scheduledMs - nowMs) / 60000))}分钟后`
      : formatTimeAgo(scheduledMs)
  ) : '';
  const scheduledFull = scheduledMs ? formatFullDateTime(scheduledMs) : '';

  // Original post time
  const postExact = postMs ? formatExactDateTime(postMs) : '';
  const postRel = postMs ? formatTimeAgo(postMs) : '';
  const postFull = postMs ? formatFullDateTime(postMs) : '';

  return {
    primaryType,
    primaryMs,
    prefix,
    exact,
    relative,
    full,
    label: exact ? `${prefix} ${exact}${relative ? ` (${relative})` : ''}` : '',
    createdMs,
    createdExact,
    createdRel,
    createdFull,
    scheduledMs,
    scheduledExact,
    scheduledRel,
    scheduledFull,
    postMs,
    postExact,
    postRel,
    postFull,
  };
}

export function timeAgo(ts) {
  if (!ts) return '';
  const num = typeof ts === 'number' ? ts : Number(ts);
  if (!num || isNaN(num)) return '';
  const ms = num < 1e11 ? num * 1000 : num;
  const s = Math.floor((Date.now() - ms) / 1000);
  if (s < 5) return '刚刚';
  if (s < 60) return `${s}s前`;
  if (s < 3600) return `${Math.floor(s / 60)}m前`;
  if (s < 86400) return `${Math.floor(s / 3600)}h前`;
  return `${Math.floor(s / 86400)}d前`;
}

export const STATUS_CFG = {
  new:       { label: '新线索',        cls: 'st-new'       },
  reviewing: { label: '审核中',        cls: 'st-reviewing'  },
  replied:   { label: '已回复',        cls: 'st-replied'    },
  converted: { label: '已转化 ✓',      cls: 'st-converted'  },
  skipped:   { label: '已忽略',        cls: 'st-skipped'    },
};

export const BOARD_COLS = [
  { status: 'new',       label: '新线索', color: 'bg-blue-50 text-blue-600 border-blue-100'     },
  { status: 'reviewing', label: '审核中', color: 'bg-amber-50 text-amber-600 border-amber-100'   },
  { status: 'replied',   label: '已回复', color: 'bg-violet-50 text-violet-600 border-violet-100' },
  { status: 'converted', label: '已转化', color: 'bg-emerald-50 text-emerald-600 border-emerald-100' },
  { status: 'skipped',   label: '已忽略', color: 'bg-slate-100 text-slate-400 border-slate-200'  },
];

export const C = {
  blue:        '#3b82f6',
  violet:      '#8b5cf6',
  orange:      '#f97316',
  emerald:     '#10b981',
  red:         '#ef4444',
  amber:       '#f59e0b',
  slate:       '#94a3b8',
  sky:         '#0ea5e9',
  blueFill:    'rgba(59,130,246,.12)',
  violetFill:  'rgba(139,92,246,.12)',
  emeraldFill: 'rgba(16,185,129,.10)',
};

export const PALETTE = [
  C.blue, C.violet, C.orange, C.emerald, C.amber, C.red, C.sky,
  '#ec4899', '#14b8a6', '#a855f7', '#f43f5e', '#84cc16', '#6366f1', '#fb923c', '#22d3ee'
];
