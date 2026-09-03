import { useEffect, useState, useCallback } from 'react';
import { MapPin, RefreshCw } from 'lucide-react';
import * as api from '../services/api';
import PeakHourDial from '../components/PeakHourDial';
import ActivityConfidenceBand from '../components/ActivityConfidenceBand';
import ModalityDecomposition from '../components/ModalityDecomposition';
import TrafficDynamics from '../components/TrafficDynamics';
import GridFingerprint from '../components/GridFingerprint';

export default function GridInvestigator({ gridId }) {
  const [timeseries, setTimeseries] = useState([]);
  const [modality, setModality] = useState([]);
  const [features, setFeatures] = useState(null);
  const [weekly, setWeekly] = useState(null);
  const [geo, setGeo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [usingFallback, setUsingFallback] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const [tsRes, modRes, featRes, weeklyRes, geoRes] = await Promise.all([
      api.getGridTimeseries(gridId),
      api.getGridModality(gridId, { hours: 24 }),
      api.getGridFeatures(gridId),
      api.getWeeklyPeak(gridId),
      api.getGridGeography(gridId),
    ]);
    setTimeseries(tsRes.timeseries || []);
    setModality(modRes.hours || []);
    setFeatures(featRes);
    setWeekly(weeklyRes);
    setGeo(geoRes);
    setUsingFallback([tsRes, modRes, featRes, weeklyRes, geoRes].some((r) => r.meta?.fallback));
    setLoading(false);
  }, [gridId]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-md border border-cyan-500/30 text-cyan-300">
            <MapPin size={16} />
          </span>
          <div>
            <div className="font-mono text-base text-slate-100">GRID #{gridId}</div>
            <div className="text-[11px] text-slate-500">
              {geo ? `${geo.latitude.toFixed(4)}°N, ${geo.longitude.toFixed(4)}°E · ${geo.sector_label}` : 'Resolving coordinates…'}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 text-[10px] text-slate-500">
          {usingFallback && <span className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-amber-300">synthetic fallback data</span>}
          <button onClick={load} className="flex items-center gap-1 rounded border border-slate-800 bg-slate-800/60 px-2 py-1 text-slate-300 hover:text-cyan-300">
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          <h2 className="mb-3 text-sm font-medium text-slate-200">Diurnal Peak Dynamics</h2>
          <PeakHourDial timeseries={timeseries} weekly={weekly} />
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          <h2 className="mb-3 text-sm font-medium text-slate-200">Activity vs Baseline Confidence Band</h2>
          <ActivityConfidenceBand timeseries={timeseries} />
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          <h2 className="mb-3 text-sm font-medium text-slate-200">Modality Decomposition & Asymmetry</h2>
          <ModalityDecomposition timeseries={timeseries} modality={modality} />
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          <h2 className="mb-3 text-sm font-medium text-slate-200">Traffic Dynamics & Momentum</h2>
          <TrafficDynamics timeseries={timeseries} />
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 xl:col-span-2">
          <h2 className="mb-3 text-sm font-medium text-slate-200">Cell Behavioral Fingerprint</h2>
          <GridFingerprint timeseries={timeseries} features={features} />
        </div>
      </div>
    </div>
  );
}
