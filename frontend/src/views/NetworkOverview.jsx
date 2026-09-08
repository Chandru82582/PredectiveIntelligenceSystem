import { useEffect, useState, useCallback } from 'react';
import { Activity, Signal, Flame, Crosshair, Grid as GridIcon, Map as MapIcon } from 'lucide-react';
import * as api from '../services/api';
import GeographicHeatmap from '../components/GeographicHeatmap';
import GridMatrix100 from '../components/GridMatrix100';
// import PeakHourDial from '../components/PeakHourDial';
import HotspotsLeaderboard from '../components/HotspotsLeaderboard';
import AnomalyFeed from '../components/AnomalyFeed';

function KpiTile({ icon: Icon, label, value, accent }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3">
      <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md border ${accent}`}>
        <Icon size={16} />
      </span>
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
        <div className="truncate font-mono text-lg text-slate-100">{value}</div>
      </div>
    </div>
  );
}

export default function NetworkOverview({ selectedGridId, onSelectGrid, onNavigate, isVisible }) {
  const [summary, setSummary] = useState(null);
  const [gridList, setGridList] = useState([]);
  const [geoByGrid, setGeoByGrid] = useState({});
  const [dialTimeseries, setDialTimeseries] = useState([]);
  const [weekly, setWeekly] = useState(null);
  const [hotspots, setHotspots] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [mapView, setMapView] = useState('matrix'); // 'matrix' | 'geographic'

  // A single Promise.all pass, and every request below now hits the
  // client-side cache (api.js) on repeat visits instead of re-querying the
  // backend — this is what used to make every tab switch feel like a cold
  // load.
  const load = useCallback(async () => {
    setLoading(true);
    const [summaryRes, gridsRes, hotspotsRes, alertsRes] = await Promise.all([
      api.getNetworkSummary(),
      api.listGrids({ limit: 600 }),
      api.getHotspots({ limit: 8, severity: 'HIGH' }),
      api.getAlerts({ limit: 12 }),
    ]);
    setSummary(summaryRes);
    const rawGrids = gridsRes.grids || [];
    const uniqueGridsMap = new Map();
    rawGrids.forEach((g) => {
      if (g && g.grid_id != null && !uniqueGridsMap.has(g.grid_id)) {
        uniqueGridsMap.set(g.grid_id, g);
      }
    });
    setGridList(Array.from(uniqueGridsMap.values()));
    setHotspots(hotspotsRes.hotspots || []);
    setAlerts(alertsRes.alerts || []);

    const idsForGeo = [
      ...new Set([...(hotspotsRes.hotspots || []).map((h) => h.grid_id), ...(gridsRes.grids || []).map((g) => g.grid_id)]),
    ];
    const geoRes = await api.getGridsGeography(idsForGeo);
    const map = {};
    (geoRes.grids || []).forEach((g) => (map[g.grid_id] = g));
    setGeoByGrid(map);

    const [tsRes, weeklyRes] = await Promise.all([
      api.getGridTimeseries(summaryRes.top_grid || 100),
      api.getWeeklyPeak(summaryRes.top_grid || 100),
    ]);
    setDialTimeseries(tsRes.timeseries || []);
    setWeekly(weeklyRes);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const cells = gridList.map((g) => ({
    grid_id: g.grid_id,
    total_activity: g.total_activity,
    ...(geoByGrid[g.grid_id] || {}),
  }));

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiTile icon={Activity} label="Total Activity" value={summary ? summary.total_activity.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—'} accent="border-cyan-500/30 text-cyan-300" />
        <KpiTile icon={Signal} label="Active Grids" value={summary ? summary.active_grids.toLocaleString() : '—'} accent="border-emerald-500/30 text-emerald-300" />
        <KpiTile icon={Flame} label="Network Peak Hour" value={summary ? `${String(summary.peak_hour).padStart(2, '0')}:00` : '—'} accent="border-amber-500/30 text-amber-300" />
        <KpiTile icon={Crosshair} label="Top Grid" value={summary ? `#${summary.top_grid}` : '—'} accent="border-rose-500/30 text-rose-300" />
      </div>

      {/* Spatial context & 100x100 Predictive Lattice */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-100">
              {mapView === 'matrix' ? 'Grid Matrix (10,000 Cells)' : 'Geographic Load Map (Leaflet)'}
            </h2>
            <span className="text-[11px] font-mono text-cyan-400 bg-cyan-950/60 border border-cyan-800/40 px-2 py-0.5 rounded">
              Milan Lattice
            </span>
          </div>

          <div className="flex items-center rounded-lg border border-slate-800 bg-slate-950 p-0.5">
            <button
              type="button"
              onClick={() => setMapView('matrix')}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-all ${
                mapView === 'matrix'
                  ? 'bg-cyan-500/20 text-cyan-300 shadow-sm border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <GridIcon size={12} />
              <span>Grid Matrix</span>
            </button>
            <button
              type="button"
              onClick={() => setMapView('geographic')}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-all ${
                mapView === 'geographic'
                  ? 'bg-cyan-500/20 text-cyan-300 shadow-sm border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <MapIcon size={12} />
              <span>Geographic Map</span>
            </button>
          </div>
        </div>

        {mapView === 'matrix' ? (
          <GridMatrix100
            selectedGridId={selectedGridId}
            onSelectGrid={onSelectGrid}
            onNavigate={onNavigate}
          />
        ) : (
          <GeographicHeatmap
            cells={cells}
            selectedGridId={selectedGridId}
            onSelectGrid={onSelectGrid}
            isVisible={isVisible && mapView === 'geographic'}
          />
        )}
      </div>
      {/* Most actionable first: what needs attention right now, and where. */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          <h2 className="mb-3 text-sm font-medium text-slate-200">Algorithmic Anomaly Feed</h2>
          <AnomalyFeed alerts={alerts} onSelectGrid={onSelectGrid} />
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          <h2 className="mb-3 text-sm font-medium text-slate-200">Hotspots Leaderboard</h2>
          <HotspotsLeaderboard hotspots={hotspots} geoByGrid={geoByGrid} selectedGridId={selectedGridId} onSelectGrid={onSelectGrid} />
        </div>
      </div>
    </div>
  );
}
