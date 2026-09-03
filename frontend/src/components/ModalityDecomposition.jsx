import { useMemo, useState } from 'react';
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts';

export default function ModalityDecomposition({ timeseries, modality }) {
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
        <div className="mb-2 text-[11px] text-slate-500">Modality mix — SMS vs Voice vs Data</div>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={stacked} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis dataKey="label" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={{ stroke: '#1e293b' }} tickLine={false} minTickGap={30} />
            <YAxis tick={{ fill: '#64748b', fontSize: 10 }} axisLine={{ stroke: '#1e293b' }} tickLine={false} />
            <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, fontSize: 11 }} />
            <Area type="monotone" dataKey="internet_activity" stackId="1" stroke="#38bdf8" fill="#38bdf8" fillOpacity={0.35} isAnimationActive={false} />
            <Area type="monotone" dataKey="call_activity" stackId="1" stroke="#a855f7" fill="#a855f7" fillOpacity={0.35} isAnimationActive={false} />
            <Area type="monotone" dataKey="sms_activity" stackId="1" stroke="#34d399" fill="#34d399" fillOpacity={0.35} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
        <div className="mt-1 flex gap-4 text-[10px] text-slate-500">
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-sky-400" /> Internet</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-purple-400" /> Voice</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-emerald-400" /> SMS</span>
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[11px] text-slate-500">Directional asymmetry — inbound vs outbound</span>
          <div className="inline-flex rounded-full border border-slate-800 bg-slate-900/70 p-0.5">
            {['sms', 'voice'].map((c) => (
              <button
                key={c}
                onClick={() => setChannel(c)}
                className={`rounded-full px-3 py-0.5 text-[10px] font-medium capitalize transition-colors ${
                  channel === c ? 'bg-amber-500/20 text-amber-300' : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={diverging} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis dataKey="label" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={{ stroke: '#1e293b' }} tickLine={false} minTickGap={30} />
            <YAxis tick={{ fill: '#64748b', fontSize: 10 }} axisLine={{ stroke: '#1e293b' }} tickLine={false} />
            <Tooltip
              contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, fontSize: 11 }}
              formatter={(v) => Math.abs(v).toFixed(1)}
            />
            <ReferenceLine y={0} stroke="#475569" />
            <Bar dataKey="outbound" fill="#f59e0b" radius={[2, 2, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="inbound" fill="#06b6d4" radius={[0, 0, 2, 2]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
        <div className="mt-1 flex gap-4 text-[10px] text-slate-500">
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-amber-400" /> Outbound (+)</span>
          <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-cyan-500" /> Inbound (−)</span>
        </div>
      </div>
    </div>
  );
}
