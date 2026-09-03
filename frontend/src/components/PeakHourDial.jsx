import { useMemo, useState } from 'react';
import { Moon, TrendingUp, TrendingDown } from 'lucide-react';

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function polar(cx, cy, r, hour) {
  const theta = (hour / 24) * 2 * Math.PI - Math.PI / 2;
  return { x: cx + r * Math.cos(theta), y: cy + r * Math.sin(theta) };
}

function DayDial({ timeseries }) {
  const { peakHour, peakValue, hourly } = useMemo(() => {
    const buckets = Array.from({ length: 24 }, () => 0);
    const counts = Array.from({ length: 24 }, () => 0);
    (timeseries || []).forEach((p) => {
      const h = new Date(p.timestamp).getHours();
      buckets[h] += p.total_activity;
      counts[h] += 1;
    });
    const hourly = buckets.map((v, h) => (counts[h] ? v / counts[h] : 0));
    let peakHour = 0;
    hourly.forEach((v, h) => {
      if (v > hourly[peakHour]) peakHour = h;
    });
    return { peakHour, peakValue: hourly[peakHour] || 0, hourly };
  }, [timeseries]);

  const max = Math.max(...hourly, 1);
  const size = 260;
  const cx = size / 2, cy = size / 2;
  const outerR = 108, innerR = 60;

  const bucketRanges = [
    { label: 'Morning Rush', range: [7, 9], color: 'text-amber-300' },
    { label: 'Afternoon Core', range: [10, 16], color: 'text-cyan-300' },
    { label: 'Evening Leisure', range: [17, 22], color: 'text-rose-300' },
    { label: 'Night Trough', range: [23, 5], color: 'text-slate-400' },
  ];
  const avgFor = (range) => {
    const [a, b] = range;
    const hrs = a <= b ? Array.from({ length: b - a + 1 }, (_, i) => a + i) : [...Array.from({ length: 24 - a }, (_, i) => a + i), ...Array.from({ length: b + 1 }, (_, i) => i)];
    const vals = hrs.map((h) => hourly[h] || 0);
    return vals.reduce((s, v) => s + v, 0) / vals.length;
  };

  return (
    <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-start sm:gap-8">
      <svg width={size} height={size} className="shrink-0">
        <circle cx={cx} cy={cy} r={outerR} fill="none" stroke="#1e293b" strokeWidth={1} />
        <circle cx={cx} cy={cy} r={innerR} fill="none" stroke="#1e293b" strokeWidth={1} />

        {/* nocturnal maintenance window 02:00-05:00 */}
        {(() => {
          const a = polar(cx, cy, outerR, 2);
          const b = polar(cx, cy, outerR, 5);
          const largeArc = 0;
          return (
            <path
              d={`M ${cx} ${cy} L ${a.x} ${a.y} A ${outerR} ${outerR} 0 ${largeArc} 1 ${b.x} ${b.y} Z`}
              fill="rgba(6,182,212,0.08)"
              stroke="rgba(6,182,212,0.25)"
              strokeWidth={1}
            />
          );
        })()}

        {Array.from({ length: 24 }).map((_, h) => {
          const r = innerR + ((outerR - innerR) * (hourly[h] || 0)) / max;
          const p = polar(cx, cy, r, h);
          const tick = polar(cx, cy, outerR + 14, h);
          const isPeak = h === peakHour;
          const isNight = h >= 2 && h <= 5;
          return (
            <g key={h}>
              <line x1={cx + innerR * Math.cos((h / 24) * 2 * Math.PI - Math.PI / 2)} y1={cy + innerR * Math.sin((h / 24) * 2 * Math.PI - Math.PI / 2)} x2={p.x} y2={p.y} stroke={isPeak ? '#f59e0b' : isNight ? '#0891b2' : '#334155'} strokeWidth={isPeak ? 2.5 : 1.5} />
              {h % 3 === 0 && (
                <text x={tick.x} y={tick.y} textAnchor="middle" dominantBaseline="middle" className="fill-slate-500 font-mono" fontSize={9}>
                  {String(h).padStart(2, '0')}
                </text>
              )}
              {isPeak && <circle cx={p.x} cy={p.y} r={5} fill="#f59e0b" className="animate-pulse" />}
            </g>
          );
        })}

        <circle cx={cx} cy={cy} r={innerR - 4} fill="#0f172a" stroke="#1e293b" />
        <text x={cx} y={cy - 10} textAnchor="middle" className="fill-slate-500" fontSize={9} letterSpacing={1}>
          PEAK HOUR
        </text>
        <text x={cx} y={cy + 12} textAnchor="middle" className="fill-amber-300 font-mono font-semibold" fontSize={22}>
          {String(peakHour).padStart(2, '0')}:00
        </text>
        <text x={cx} y={cy + 30} textAnchor="middle" className="fill-cyan-300 font-mono" fontSize={11}>
          {peakValue.toFixed(0)} ops/hr
        </text>
      </svg>

      <div className="grid w-full grid-cols-2 gap-3 sm:w-52">
        {bucketRanges.map((b) => (
          <div key={b.label} className="rounded border border-slate-800 bg-slate-900/60 px-2.5 py-2">
            <div className="flex items-center gap-1 text-[10px] text-slate-500">
              {b.label === 'Night Trough' && <Moon size={10} />}
              {b.label}
            </div>
            <div className={`font-mono text-sm ${b.color}`}>{avgFor(b.range).toFixed(0)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function WeekRibbon({ weekly }) {
  if (!weekly || !weekly.days?.length) return null;
  const days = weekly.days;
  const maxActivity = Math.max(...days.map((d) => d.peak_activity), 1);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between text-[11px] text-slate-400">
        <span>Trailing 7-day peak-hour drift</span>
        <span className="font-mono text-cyan-300">avg {weekly.trailing_avg_peak_hour.toFixed(1)}h</span>
      </div>
      <div className="grid grid-cols-7 gap-2">
        {days.map((d) => {
          const isLate = d.delta_hours > 0.15;
          const isEarly = d.delta_hours < -0.15;
          return (
            <div key={d.date} className="flex flex-col items-center gap-2 rounded border border-slate-800 bg-slate-900/60 p-2">
              <div className="text-[10px] font-medium text-slate-500">{DAY_LABELS[d.day_of_week]}</div>
              <div
                className="w-full rounded-sm bg-gradient-to-t from-cyan-500/30 to-amber-400/70"
                style={{ height: `${18 + (d.peak_activity / maxActivity) * 46}px` }}
              />
              <div className="font-mono text-xs text-slate-200">{String(d.peak_hour).padStart(2, '0')}:00</div>
              <div
                className={`flex items-center gap-0.5 rounded px-1 py-0.5 text-[9px] font-medium ${
                  isLate ? 'bg-rose-500/15 text-rose-300' : isEarly ? 'bg-cyan-500/15 text-cyan-300' : 'bg-slate-800 text-slate-500'
                }`}
              >
                {isLate && <TrendingUp size={9} />}
                {isEarly && <TrendingDown size={9} />}
                {d.delta_hours > 0 ? '+' : ''}
                {d.delta_hours.toFixed(1)}h
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function PeakHourDial({ timeseries, weekly }) {
  const [view, setView] = useState('day');

  return (
    <div className="flex flex-col gap-4">
      <div className="inline-flex w-fit rounded-full border border-slate-800 bg-slate-900/70 p-0.5">
        {[
          { id: 'day', label: 'Day View' },
          { id: 'week', label: 'Week View' },
        ].map((opt) => (
          <button
            key={opt.id}
            onClick={() => setView(opt.id)}
            className={`rounded-full px-3.5 py-1 text-[11px] font-medium transition-colors ${
              view === opt.id ? 'bg-cyan-500/20 text-cyan-300' : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {view === 'day' ? <DayDial timeseries={timeseries} /> : <WeekRibbon weekly={weekly} />}
    </div>
  );
}
