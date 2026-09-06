import { AlertTriangle, ShieldCheck, Gauge } from 'lucide-react';

const FEATURE_LABELS = {
  activity_growth: { label: '6h/24h growth', format: (v) => `${v >= 1 ? '+' : ''}${((v - 1) * 100).toFixed(1)}%` },
  current_to_baseline_ratio: { label: 'Current vs baseline', format: (v) => `${v.toFixed(2)}x` },
  peak_ratio: { label: 'Peak burst ratio', format: (v) => `${v.toFixed(2)}x` },
  variability: { label: 'Variability', format: (v) => v.toFixed(2) },
  internet_share: { label: 'Data traffic share', format: (v) => `${(v * 100).toFixed(0)}%` },
  velocity_1h: { label: '1h velocity', format: (v) => v.toFixed(1) },
  activity_vs_same_hour_yesterday: { label: 'Vs same hour yesterday', format: (v) => `${v.toFixed(2)}x` },
};

export default function ActivityPrediction({ prediction, loading }) {
  if (loading && !prediction) {
    return <div className="py-8 text-center text-[11px] text-slate-500">Scoring trailing history…</div>;
  }

  if (!prediction) {
    return (
      <div className="py-8 text-center text-[11px] text-slate-500">
        Not enough trailing history for this grid to compute a prediction (needs at least 24h of prior hourly data).
      </div>
    );
  }

  const isHigh = prediction.risk_label === 'HIGH_ACTIVITY_RISK';
  const pct = Math.round(prediction.probability * 100);
  const thresholdPct = Math.round(prediction.threshold * 100);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-4">
        <span
          className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-full border-2 ${
            isHigh ? 'border-rose-500/50 bg-rose-500/10 text-rose-300' : 'border-emerald-500/50 bg-emerald-500/10 text-emerald-300'
          }`}
        >
          {isHigh ? <AlertTriangle size={22} /> : <ShieldCheck size={22} />}
        </span>

        <div className="min-w-0">
          <div className={`text-sm font-semibold ${isHigh ? 'text-rose-300' : 'text-emerald-300'}`}>
            {isHigh ? 'High-Activity Risk — Next Hour' : 'Normal — Next Hour'}
          </div>
          <div className="text-[11px] text-slate-500">
            LightGBM classifier · trained on {'>'}1.5x within-day baseline events · forecasting from{' '}
            {new Date(prediction.feature_timestamp).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
          </div>
        </div>

        <div className="ml-auto text-right">
          <div className="font-mono text-2xl text-slate-100">{pct}%</div>
          <div className="text-[10px] uppercase tracking-wide text-slate-500">predicted probability</div>
        </div>
      </div>

      <div>
        <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-slate-800">
          <div
            className={`h-full rounded-full transition-all ${isHigh ? 'bg-rose-500' : 'bg-cyan-500'}`}
            style={{ width: `${pct}%` }}
          />
          <div className="absolute inset-y-0 w-px bg-slate-400/70" style={{ left: `${thresholdPct}%` }} title={`Decision threshold: ${thresholdPct}%`} />
        </div>
        <div className="mt-1 flex items-center justify-between text-[10px] text-slate-500">
          <span className="flex items-center gap-1">
            <Gauge size={10} /> Decision threshold {thresholdPct}%
          </span>
          <span>{prediction.data_points_used}h trailing history used</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
        {Object.entries(FEATURE_LABELS).map(([key, { label, format }]) => {
          const value = prediction.features?.[key];
          if (value === undefined) return null;
          return (
            <div key={key} className="rounded border border-slate-800 bg-slate-900/60 p-2.5">
              <div className="text-[10px] text-slate-500">{label}</div>
              <div className="font-mono text-sm text-slate-200">{format(value)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
