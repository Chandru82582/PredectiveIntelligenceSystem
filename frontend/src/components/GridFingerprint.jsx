import { useMemo } from 'react';
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { Activity, TrendingUp, TrendingDown } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

function classifyPersona(f) {
  if (!f) return 'Unclassified';
  if (f.active_hours >= 22 && f.avg_activity > 300) return 'Core Hub';
  if (f.peak_ratio > 2.2) return 'Commuter Corridor';
  if (f.active_hours < 16) return 'Inactive';
  return 'Residential';
}

function Donut({ value, color, label, sub, emptyTrack }) {
  const data = [{ v: value }, { v: 1 - value }];
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative h-24 w-24">
        <ResponsiveContainer>
          <PieChart>
            <Pie data={data} dataKey="v" innerRadius={32} outerRadius={44} startAngle={90} endAngle={-270} stroke="none" isAnimationActive={false}>
              <Cell fill={color} />
              <Cell fill={emptyTrack || '#1e293b'} />
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono text-sm font-semibold text-slate-900 dark:text-slate-100">{sub}</span>
        </div>
      </div>
      <span className="text-center text-[10px] text-slate-500 dark:text-slate-400">{label}</span>
    </div>
  );
}

export default function GridFingerprint({ timeseries, features }) {
  const { chartTheme } = useTheme();

  const persistence = useMemo(() => {
    const buckets = Array.from({ length: 24 }, () => 0);
    (timeseries || []).forEach((p) => {
      buckets[new Date(p.timestamp).getHours()] = p.total_activity;
    });
    const max = Math.max(...buckets, 1);
    return buckets.map((v) => v / max);
  }, [timeseries]);

  const radarData = useMemo(() => {
    if (!features) return [];
    const clamp = (v) => Math.max(0, Math.min(100, v));
    return [
      { metric: 'Volume', value: clamp((features.avg_activity / 800) * 100) },
      { metric: 'Burst', value: clamp((features.peak_ratio / 3) * 100) },
      { metric: 'Variability', value: clamp((features.variability / 200) * 100) },
      { metric: 'Data Dominance', value: clamp(features.internet_share * 100) },
      { metric: 'Continuity', value: clamp((features.active_hours / 24) * 100) },
      { metric: 'Growth', value: clamp((features.activity_growth + 0.5) * 100) },
    ];
  }, [features]);

  const persona = classifyPersona(features);
  const growthPositive = (features?.activity_growth || 0) >= 0;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <div className="mb-2 flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
          <span>24h transmission persistence</span>
          <span className="rounded border border-cyan-200 bg-cyan-50 px-2 py-0.5 font-mono text-cyan-700 dark:border-transparent dark:bg-slate-800 dark:text-cyan-300">
            {persona}
          </span>
        </div>
        <div className="flex h-8 overflow-hidden rounded border border-slate-200 dark:border-slate-800">
          {persistence.map((v, h) => (
            <div
              key={h}
              className="flex-1"
              style={{
                background: `linear-gradient(180deg, rgba(6,182,212,${0.2 + v * 0.75}), rgba(6,182,212,${0.05 + v * 0.3}))`,
              }}
              title={`${h}:00 — ${(v * 100).toFixed(0)}%`}
            />
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <div>
          <div className="mb-1 text-[11px] text-slate-500 dark:text-slate-400">Behavioral persona diamond</div>
          <ResponsiveContainer width="100%" height={200}>
            <RadarChart data={radarData} outerRadius={75}>
              <PolarGrid stroke={chartTheme.gridStroke} />
              <PolarAngleAxis dataKey="metric" tick={{ fill: chartTheme.axisTick, fontSize: 9 }} />
              <Radar dataKey="value" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.3} isAnimationActive={false} />
            </RadarChart>
          </ResponsiveContainer>
        </div>

        <div className="flex flex-col justify-center gap-4">
          <div className="flex justify-around">
            <Donut
              value={features?.internet_share ?? 0}
              color="#38bdf8"
              label="Packet data share"
              sub={`${((features?.internet_share ?? 0) * 100).toFixed(0)}%`}
              emptyTrack={chartTheme.emptyTrack}
            />
            <Donut
              value={Math.min((features?.peak_ratio ?? 0) / 4, 1)}
              color="#f43f5e"
              label="Peak burst ratio"
              sub={`${(features?.peak_ratio ?? 0).toFixed(2)}x`}
              emptyTrack={chartTheme.emptyTrack}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-slate-200 bg-white/80 p-2.5 shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
              <div className="flex items-center gap-1 text-[10px] text-slate-500 dark:text-slate-400"><Activity size={10} /> Std deviation</div>
              <div className="font-mono text-sm font-semibold text-slate-900 dark:text-slate-200">±{(features?.variability ?? 0).toFixed(1)}</div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white/80 p-2.5 shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
              <div className="flex items-center gap-1 text-[10px] text-slate-500 dark:text-slate-400">
                {growthPositive ? <TrendingUp size={10} className="text-emerald-500 dark:text-emerald-400" /> : <TrendingDown size={10} className="text-rose-500 dark:text-rose-400" />}
                12h growth
              </div>
              <div className={`font-mono text-sm font-semibold ${growthPositive ? 'text-emerald-600 dark:text-emerald-300' : 'text-rose-600 dark:text-rose-300'}`}>
                {growthPositive ? '+' : ''}
                {((features?.activity_growth ?? 0) * 100).toFixed(1)}%
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
