import { useMemo } from 'react';
import { ComposedChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export default function TrafficDynamics({ timeseries }) {
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

  return (
    <div className="flex flex-col gap-6">
      <div>
        <div className="mb-2 text-[11px] text-slate-500">Voice vs Data — 24h synchronized trend</div>
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={rows} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis dataKey="label" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={{ stroke: '#1e293b' }} tickLine={false} minTickGap={30} />
            <YAxis yAxisId="left" tick={{ fill: '#38bdf8', fontSize: 10 }} axisLine={{ stroke: '#1e293b' }} tickLine={false} label={{ value: 'MB/hr', angle: -90, position: 'insideLeft', fill: '#38bdf8', fontSize: 10 }} />
            <YAxis yAxisId="right" orientation="right" tick={{ fill: '#a855f7', fontSize: 10 }} axisLine={{ stroke: '#1e293b' }} tickLine={false} label={{ value: 'Erlangs', angle: 90, position: 'insideRight', fill: '#a855f7', fontSize: 10 }} />
            <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, fontSize: 11 }} />
            <Line yAxisId="left" type="monotone" dataKey="dataMb" stroke="#38bdf8" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line yAxisId="right" type="monotone" dataKey="voiceErlangs" stroke="#a855f7" strokeWidth={2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
        <div className="mt-1 flex gap-4 text-[10px] text-slate-500">
          <span className="flex items-center gap-1.5"><span className="h-0.5 w-3 bg-sky-400" /> Data (MB/hr)</span>
          <span className="flex items-center gap-1.5"><span className="h-0.5 w-3 bg-purple-400" /> Voice (Erlangs)</span>
        </div>
      </div>

      <div>
        <div className="mb-2 text-[11px] text-slate-500">Bandwidth momentum</div>
        <ResponsiveContainer width="100%" height={140}>
          <AreaChart data={rows} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
            <defs>
              <linearGradient id="momentumFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#f43f5e" stopOpacity={0.55} />
                <stop offset="100%" stopColor="#f43f5e" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis dataKey="label" hide />
            <YAxis hide />
            <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, fontSize: 11 }} />
            <Area type="natural" dataKey="momentum" stroke="#fb7185" strokeWidth={2} fill="url(#momentumFill)" isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
