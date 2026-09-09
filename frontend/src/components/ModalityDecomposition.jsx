import { useMemo, useState } from 'react';
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts';
import { useTheme } from '../context/ThemeContext';

export default function ModalityDecomposition({ timeseries, modality }) {
  const { isDark, chartTheme } = useTheme();
  const [channel, setChannel] = useState('sms');

  const stacked = useMemo(
    () =>
      (timeseries || []).map((p) => ({
        label: new Date(p.timestamp).toLocaleTimeString([], { hour: '2-digit' }),
        internet_activity: p.internet_activity,
        call_activity: p.call_activity,
        sms_activity: p.sms_activity,
      })),
    [timeseries]
  );

  const diverging = useMemo(
    () =>
      (modality || []).map((p) => ({
        label: new Date(p.timestamp).toLocaleTimeString([], { hour: '2-digit' }),
        outbound: channel === 'sms' ? p.sms_out : p.call_out,
        inbound: -(channel === 'sms' ? p.sms_in : p.call_in),
      })),
    [modality, channel]
  );

  return (
    <div className="flex flex-col gap-6">
      <div>
        <div className="mb-2 text-[11px] text-slate-500 dark:text-slate-400">Modality mix — SMS vs Voice vs Data</div>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={stacked} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.gridStroke} vertical={false} />
            <XAxis dataKey="label" tick={{ fill: chartTheme.axisTick, fontSize: 10 }} axisLine={{ stroke: chartTheme.axisLine }} tickLine={false} minTickGap={30} />
            <YAxis tick={{ fill: chartTheme.axisTick, fontSize: 10 }} axisLine={{ stroke: chartTheme.axisLine }} tickLine={false} />
            <Tooltip contentStyle={chartTheme.tooltipContentStyle} labelStyle={chartTheme.tooltipLabelStyle} />
            <Area type="monotone" dataKey="internet_activity" stackId="1" stroke="#0284c7" fill="#38bdf8" fillOpacity={isDark ? 0.35 : 0.45} isAnimationActive={false} />
            <Area type="monotone" dataKey="call_activity" stackId="1" stroke="#9333ea" fill="#a855f7" fillOpacity={isDark ? 0.35 : 0.45} isAnimationActive={false} />
            <Area type="monotone" dataKey="sms_activity" stackId="1" stroke="#059669" fill="#34d399" fillOpacity={isDark ? 0.35 : 0.45} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
        <div className="mt-1 flex gap-4 text-[10px] text-slate-500 dark:text-slate-400">
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-sky-500" /> Internet</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-purple-500" /> Voice</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-emerald-500" /> SMS</span>
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[11px] text-slate-500 dark:text-slate-400">Directional asymmetry — inbound vs outbound</span>
          <div className="inline-flex rounded-full border border-slate-200 bg-slate-100/80 p-0.5 dark:border-slate-800 dark:bg-slate-900/70">
            {['sms', 'voice'].map((c) => (
              <button
                key={c}
                onClick={() => setChannel(c)}
                className={`rounded-full px-3 py-0.5 text-[10px] font-medium capitalize transition-colors ${
                  channel === c
                    ? 'bg-white text-amber-700 shadow-sm border border-slate-200/80 dark:border-transparent dark:bg-amber-500/20 dark:text-amber-300'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-500 dark:hover:text-slate-300'
                }`}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={diverging} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={chartTheme.gridStroke} vertical={false} />
            <XAxis dataKey="label" tick={{ fill: chartTheme.axisTick, fontSize: 10 }} axisLine={{ stroke: chartTheme.axisLine }} tickLine={false} minTickGap={30} />
            <YAxis tick={{ fill: chartTheme.axisTick, fontSize: 10 }} axisLine={{ stroke: chartTheme.axisLine }} tickLine={false} />
            <Tooltip
              contentStyle={chartTheme.tooltipContentStyle}
              labelStyle={chartTheme.tooltipLabelStyle}
              formatter={(v) => Math.abs(v).toFixed(1)}
            />
            <ReferenceLine y={0} stroke={isDark ? '#475569' : '#94a3b8'} />
            <Bar dataKey="outbound" fill="#f59e0b" radius={[2, 2, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="inbound" fill="#06b6d4" radius={[0, 0, 2, 2]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
        <div className="mt-1 flex gap-4 text-[10px] text-slate-500 dark:text-slate-400">
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-amber-500" /> Outbound (+)</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-cyan-600 dark:bg-cyan-500" /> Inbound (−)</span>
        </div>
      </div>
    </div>
  );
}
