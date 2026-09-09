import { useMemo } from 'react';
import { ComposedChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { useTheme } from '../context/ThemeContext';

export default function TrafficDynamics({ timeseries }) {
  const { isDark, chartTheme } = useTheme();

  const rows = useMemo(
    () =>
      (timeseries || []).map((p) => ({
        label: new Date(p.timestamp).toLocaleTimeString([], { hour: '2-digit' }),
        dataMb: p.internet_activity,
        voiceErlangs: p.call_activity,
        momentum: p.total_activity,
      })),
    [timeseries]
  );

  const dataColor = isDark ? '#38bdf8' : '#0284c7';
  const voiceColor = isDark ? '#a855f7' : '#9333ea';

  return (
    <div className="flex flex-col gap-6">
      <div>
        <div className="mb-2 text-[11px] text-slate-500 dark:text-slate-400">Voice vs Data — 24h synchronized trend</div>
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={rows} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.gridStroke} vertical={false} />
            <XAxis dataKey="label" tick={{ fill: chartTheme.axisTick, fontSize: 10 }} axisLine={{ stroke: chartTheme.axisLine }} tickLine={false} minTickGap={30} />
            <YAxis yAxisId="left" tick={{ fill: dataColor, fontSize: 10 }} axisLine={{ stroke: chartTheme.axisLine }} tickLine={false} label={{ value: 'MB/hr', angle: -90, position: 'insideLeft', fill: dataColor, fontSize: 10 }} />
            <YAxis yAxisId="right" orientation="right" tick={{ fill: voiceColor, fontSize: 10 }} axisLine={{ stroke: chartTheme.axisLine }} tickLine={false} label={{ value: 'Erlangs', angle: 90, position: 'insideRight', fill: voiceColor, fontSize: 10 }} />
            <Tooltip contentStyle={chartTheme.tooltipContentStyle} labelStyle={chartTheme.tooltipLabelStyle} />
            <Line yAxisId="left" type="monotone" dataKey="dataMb" stroke={dataColor} strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line yAxisId="right" type="monotone" dataKey="voiceErlangs" stroke={voiceColor} strokeWidth={2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
        <div className="mt-1 flex gap-4 text-[10px] text-slate-500 dark:text-slate-400">
          <span className="flex items-center gap-1.5"><span className="h-0.5 w-3 bg-sky-500" /> Data (MB/hr)</span>
          <span className="flex items-center gap-1.5"><span className="h-0.5 w-3 bg-purple-500" /> Voice (Erlangs)</span>
        </div>
      </div>

      <div>
        <div className="mb-2 text-[11px] text-slate-500 dark:text-slate-400">Bandwidth momentum</div>
        <ResponsiveContainer width="100%" height={140}>
          <AreaChart data={rows} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
            <defs>
              <linearGradient id="momentumFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#f43f5e" stopOpacity={isDark ? 0.55 : 0.45} />
                <stop offset="100%" stopColor="#f43f5e" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis dataKey="label" hide />
            <YAxis hide />
            <Tooltip contentStyle={chartTheme.tooltipContentStyle} labelStyle={chartTheme.tooltipLabelStyle} />
            <Area type="natural" dataKey="momentum" stroke="#fb7185" strokeWidth={2} fill="url(#momentumFill)" isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
