import { AlertTriangle, TrendingUp, TrendingDown } from 'lucide-react';

const TYPE_META = {
  HIGH_ACTIVITY: {
    icon: AlertTriangle,
    color: 'text-rose-600 bg-rose-500/10 border-rose-500/25 dark:text-rose-300 dark:bg-rose-500/15 dark:border-rose-500/30',
    label: 'High Activity',
  },
  ACTIVITY_SPIKE: {
    icon: TrendingUp,
    color: 'text-amber-600 bg-amber-500/10 border-amber-500/25 dark:text-amber-300 dark:bg-amber-500/15 dark:border-amber-500/30',
    label: 'Activity Spike',
  },
  ACTIVITY_DROP: {
    icon: TrendingDown,
    color: 'text-cyan-600 bg-cyan-500/10 border-cyan-500/25 dark:text-cyan-300 dark:bg-cyan-500/15 dark:border-cyan-500/30',
    label: 'Activity Drop',
  },
};

export default function AnomalyFeed({ alerts, onSelectGrid }) {
  if (!alerts || alerts.length === 0) {
    return <div className="py-6 text-center text-[12px] text-slate-500 dark:text-slate-400">No anomalies detected in the current window.</div>;
  }

  return (
    <div className="flex flex-col gap-1.5">
      {alerts.map((a, i) => {
        const meta = TYPE_META[a.alert_type] || TYPE_META.HIGH_ACTIVITY;
        const Icon = meta.icon;
        const ratio = a.baseline_activity > 0 ? a.current_activity / a.baseline_activity : 0;
        return (
          <button
            key={`${a.grid_id}-${a.timestamp}-${i}`}
            onClick={() => onSelectGrid?.(a.grid_id)}
            className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white/80 px-3 py-2.5 text-left shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900/50 dark:shadow-none dark:hover:border-slate-700 dark:hover:bg-slate-900"
          >
            <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded border ${meta.color}`}>
              <Icon size={12} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[12px] text-slate-900 dark:text-slate-100">GRID #{a.grid_id}</span>
                <span className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] ${meta.color}`}>{ratio.toFixed(2)}x</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{meta.label}</span>
                <span className="shrink-0 font-mono text-[10px] text-slate-400 dark:text-slate-500">
                  {new Date(a.timestamp).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
                </span>
              </div>
              <div className="mt-1 text-[11px] leading-snug text-slate-600 dark:text-slate-300">{a.reason}</div>
              <div className="mt-1 flex gap-3 font-mono text-[10px] text-slate-500 dark:text-slate-400">
                <span>current {a.current_activity.toFixed(1)}</span>
                <span>baseline {a.baseline_activity.toFixed(1)}</span>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
