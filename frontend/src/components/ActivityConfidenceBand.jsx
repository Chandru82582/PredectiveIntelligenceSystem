import { useMemo, useState } from 'react';
import { Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ComposedChart } from 'recharts';
import { useTheme } from '../context/ThemeContext';

function leaveOneOutMedian(values) {
  const n = values.length;
  if (n < 2) return values.map(() => NaN);
  return values.map((_, i) => {
    const rest = values.filter((_, j) => j !== i).sort((a, b) => a - b);
    const m = rest.length;
    return m % 2 === 1 ? rest[(m - 1) / 2] : (rest[m / 2 - 1] + rest[m / 2]) / 2;
  });
}

export default function ActivityConfidenceBand({ timeseries }) {
  const { isDark, chartTheme } = useTheme();
  const [range, setRange] = useState([0, 23]);

  const rows = useMemo(() => {
    if (!timeseries || timeseries.length === 0) return [];
    const values = timeseries.map((p) => p.total_activity);
    const baselines = leaveOneOutMedian(values);
    return timeseries.map((p, i) => {
      const ts = new Date(p.timestamp);
      const baseline = baselines[i];
      return {
        hour: ts.getHours(),
        label: ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        actual: p.total_activity,
        baseline,
        upper: baseline * 1.35,
      };
    });
  }, [timeseries]);

  const filtered = rows.filter((r) => r.hour >= range[0] && r.hour <= range[1]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <span className="w-8 shrink-0 font-mono text-[11px] text-slate-500 dark:text-slate-400">{String(range[0]).padStart(2, '0')}h</span>
        <div className="relative flex-1">
          <input
            type="range"
            min={0}
            max={22}
            value={range[0]}
            onChange={(e) => setRange(([, end]) => [Math.min(+e.target.value, end - 1), end])}
            className="absolute w-full accent-cyan-500"
          />
          <input
            type="range"
            min={1}
            max={23}
            value={range[1]}
            onChange={(e) => setRange(([start]) => [start, Math.max(+e.target.value, start + 1)])}
            className="absolute w-full accent-amber-500"
          />
          <div className="h-1" />
        </div>
        <span className="w-8 shrink-0 text-right font-mono text-[11px] text-slate-500 dark:text-slate-400">{String(range[1]).padStart(2, '0')}h</span>
      </div>

      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={filtered} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
          <defs>
            <linearGradient id="confidenceFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#06b6d4" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#06b6d4" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.gridStroke} vertical={false} />
          <XAxis dataKey="label" tick={{ fill: chartTheme.axisTick, fontSize: 10 }} axisLine={{ stroke: chartTheme.axisLine }} tickLine={false} minTickGap={30} />
          <YAxis tick={{ fill: chartTheme.axisTick, fontSize: 10 }} axisLine={{ stroke: chartTheme.axisLine }} tickLine={false} />
          <Tooltip
            contentStyle={chartTheme.tooltipContentStyle}
            labelStyle={chartTheme.tooltipLabelStyle}
          />
          <Area type="monotone" dataKey="upper" stroke="none" fill="url(#confidenceFill)" isAnimationActive={false} />
          <Line type="monotone" dataKey="baseline" stroke={chartTheme.baselineStroke} strokeDasharray="4 3" strokeWidth={1.5} dot={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="actual" stroke="#f59e0b" strokeWidth={2.5} dot={{ r: 2.5, fill: '#f59e0b' }} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>

      <div className="flex items-center gap-4 text-[11px] text-slate-500 dark:text-slate-400">
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-amber-500 dark:bg-amber-400" /> Actual load</span>
        <span className="flex items-center gap-1.5"><span className="h-0.5 w-3 bg-slate-500 dark:bg-slate-400" /> LOO median baseline</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-cyan-500/50" /> Tolerance band (1.35x)</span>
      </div>
    </div>
  );
}
