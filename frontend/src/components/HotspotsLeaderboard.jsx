const SEVERITY_STYLE = {
  HIGH: 'text-rose-300 bg-rose-500/15 border-rose-500/30',
  MEDIUM: 'text-amber-300 bg-amber-500/15 border-amber-500/30',
  LOW: 'text-cyan-300 bg-cyan-500/15 border-cyan-500/30',
};

export default function HotspotsLeaderboard({ hotspots, geoByGrid, selectedGridId, onSelectGrid }) {
  if (!hotspots || hotspots.length === 0) {
    return <div className="py-6 text-center text-[12px] text-slate-500">No hotspots reported for this window.</div>;
  }
  const max = Math.max(...hotspots.map((h) => h.total_activity), 1);

  return (
    <div className="flex flex-col gap-1.5">
      {hotspots.map((h, i) => {
        const geo = geoByGrid?.[h.grid_id];
        const isSelected = h.grid_id === selectedGridId;
        return (
          <button
            key={`hotspot-${h.grid_id}-${i}`}
            onClick={() => onSelectGrid?.(h.grid_id)}
            className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors ${
              isSelected ? 'border-cyan-500/50 bg-cyan-500/10' : 'border-slate-800 bg-slate-900/50 hover:border-slate-700 hover:bg-slate-900'
            }`}
          >
            <span className="w-6 shrink-0 font-mono text-[11px] text-slate-500">#{i + 1}</span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate font-mono text-[12px] text-slate-100">GRID #{h.grid_id}</span>
                <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-medium ${SEVERITY_STYLE[h.severity] || SEVERITY_STYLE.LOW}`}>
                  {h.severity}
                </span>
              </div>
              <div className="mt-0.5 truncate text-[10px] text-slate-500">
                {geo ? `${geo.latitude.toFixed(3)}°N, ${geo.longitude.toFixed(3)}°E · ${geo.sector_label}` : 'Resolving coordinates…'}
              </div>
              {h.timestamp && (
                <div className="mt-0.5 font-mono text-[10px] text-slate-600">
                  {new Date(h.timestamp).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
                </div>
              )}
              <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-slate-800">
                <div className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-amber-400" style={{ width: `${(h.total_activity / max) * 100}%` }} />
              </div>
            </div>
            <span className="shrink-0 font-mono text-[12px] text-amber-300">{h.total_activity.toFixed(0)}</span>
          </button>
        );
      })}
    </div>
  );
}
