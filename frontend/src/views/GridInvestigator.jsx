import { useEffect, useState, useCallback } from 'react';
import { MapPin, RefreshCw, CalendarDays, Clock, RotateCcw } from 'lucide-react';
import * as api from '../services/api';
import PeakHourDial from '../components/PeakHourDial';
import ActivityConfidenceBand from '../components/ActivityConfidenceBand';
import ModalityDecomposition from '../components/ModalityDecomposition';
import TrafficDynamics from '../components/TrafficDynamics';
import GridFingerprint from '../components/GridFingerprint';
import ActivityPrediction from '../components/ActivityPrediction';
import ModelSelector from '../components/ModelSelector';

export default function GridInvestigator({
  gridId,
  selectedModel = '',
  onSelectModel,
  availableModels = [],
}) {
  const [timeseries, setTimeseries] = useState([]);
  const [modality, setModality] = useState([]);
  const [features, setFeatures] = useState(null);
  const [weekly, setWeekly] = useState(null);
  const [geo, setGeo] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [loading, setLoading] = useState(true);
  const [usingFallback, setUsingFallback] = useState(false);
  const [selectedDate, setSelectedDate] = useState(''); // '' = latest/live window
  const [selectedHour, setSelectedHour] = useState('23'); // only applied when a date is also picked

  const asOfParam = selectedDate ? `${selectedDate}T${selectedHour}:00:00` : undefined;

  function resetToLatest() {
    setSelectedDate('');
    setSelectedHour('23');
  }

  const load = useCallback(async () => {
    setLoading(true);
    const [tsRes, modRes, featRes, weeklyRes, geoRes, predRes] = await Promise.all([
      api.getGridTimeseries(gridId, selectedDate ? { date: selectedDate } : {}),
      api.getGridModality(gridId, selectedDate ? { date: selectedDate } : { hours: 24 }),
      api.getGridFeatures(gridId, asOfParam),
      api.getWeeklyPeak(gridId, asOfParam),
      api.getGridGeography(gridId),
      api.getGridPrediction(gridId, asOfParam, selectedModel),
    ]);
    setTimeseries(tsRes.timeseries || []);
    setModality(modRes.hours || []);
    setFeatures(featRes);
    setWeekly(weeklyRes);
    setGeo(geoRes);
    setPrediction(predRes);
    setUsingFallback([tsRes, modRes, featRes, weeklyRes, geoRes, predRes].some((r) => r.meta?.fallback));
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gridId, selectedDate, selectedHour, selectedModel]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white/80 px-4 py-3 shadow-sm backdrop-blur transition-colors duration-150 dark:border-slate-800 dark:bg-slate-900/40">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-md border border-cyan-500/30 bg-cyan-500/10 text-cyan-600 dark:text-cyan-300">
            <MapPin size={16} />
          </span>
          <div>
            <div className="font-mono text-base text-slate-900 dark:text-slate-100">GRID #{gridId}</div>
            <div className="text-[11px] text-slate-500 dark:text-slate-400">
              {geo ? `${geo.latitude.toFixed(4)}°N, ${geo.longitude.toFixed(4)}°E · ${geo.sector_label}` : 'Resolving coordinates…'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 rounded border border-slate-200 bg-slate-50 px-2 py-1 dark:border-slate-800 dark:bg-slate-900/70">
            <CalendarDays size={12} className="text-slate-400 dark:text-slate-500" />
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="bg-transparent font-mono text-[11px] text-slate-800 focus:outline-none dark:text-slate-200"
            />
          </div>
          <div className={`flex items-center gap-1.5 rounded border border-slate-200 bg-slate-50 px-2 py-1 dark:border-slate-800 dark:bg-slate-900/70 ${!selectedDate ? 'opacity-40' : ''}`}>
            <Clock size={12} className="text-slate-400 dark:text-slate-500" />
            <select
              value={selectedHour}
              disabled={!selectedDate}
              onChange={(e) => setSelectedHour(e.target.value)}
              className="bg-transparent font-mono text-[11px] text-slate-800 focus:outline-none disabled:cursor-not-allowed dark:text-slate-200"
            >
              {Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0')).map((h) => (
                <option key={h} value={h} className="bg-white text-slate-800 dark:bg-slate-900 dark:text-slate-200">
                  {h}:00
                </option>
              ))}
            </select>
          </div>
          {selectedDate && (
            <button onClick={resetToLatest} className="flex items-center gap-1 rounded border border-slate-200 bg-slate-100 px-2 py-1 text-[10px] text-slate-700 hover:text-cyan-700 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-300 dark:hover:text-cyan-300">
              <RotateCcw size={11} /> Latest
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 text-[10px] text-slate-500 dark:text-slate-400">
          {usingFallback && <span className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-amber-700 dark:text-amber-300">synthetic fallback data</span>}
          <button onClick={load} className="flex items-center gap-1 rounded border border-slate-200 bg-slate-100 px-2 py-1 text-slate-700 hover:text-cyan-700 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-300 dark:hover:text-cyan-300">
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {/* Forward-looking first: is this cell about to spike? */}
      <div className="rounded-xl border border-slate-200 bg-white/80 p-4 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/40">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-medium text-slate-900 dark:text-slate-200">Predicted Activity Risk</h2>
          {availableModels && availableModels.length > 0 && (
            <ModelSelector
              models={availableModels}
              selectedModel={selectedModel}
              onSelectModel={onSelectModel}
              compact={true}
            />
          )}
        </div>
        <ActivityPrediction prediction={prediction} loading={loading} />
      </div>

      {/* Diagnostic next: is this cell behaving abnormally right now? */}
      <div className="rounded-xl border border-slate-200 bg-white/80 p-4 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/40">
        <h2 className="mb-3 text-sm font-medium text-slate-900 dark:text-slate-200">Activity vs Baseline Confidence Band</h2>
        <ActivityConfidenceBand timeseries={timeseries} />
      </div>

      {/* Breakdown analysis, once an anomaly (or its absence) is established. */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white/80 p-4 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/40">
          <h2 className="mb-3 text-sm font-medium text-slate-900 dark:text-slate-200">Modality Decomposition & Asymmetry</h2>
          <ModalityDecomposition timeseries={timeseries} modality={modality} />
        </div>
        <div className="rounded-xl border border-slate-200 bg-white/80 p-4 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/40">
          <h2 className="mb-3 text-sm font-medium text-slate-900 dark:text-slate-200">Traffic Dynamics & Momentum</h2>
          <TrafficDynamics timeseries={timeseries} />
        </div>
      </div>

      {/* Contextual classification — useful once the "what's happening" is known. */}
      <div className="rounded-xl border border-slate-200 bg-white/80 p-4 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/40">
        <h2 className="mb-3 text-sm font-medium text-slate-900 dark:text-slate-200">Cell Behavioral Fingerprint</h2>
        <GridFingerprint timeseries={timeseries} features={features} />
      </div>

      {/* Scheduling/planning context — lowest priority during triage. */}
      <div className="rounded-xl border border-slate-200 bg-white/80 p-4 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/40">
        <h2 className="mb-3 text-sm font-medium text-slate-900 dark:text-slate-200">Diurnal Peak Dynamics</h2>
        <PeakHourDial timeseries={timeseries} weekly={weekly} />
      </div>
    </div>
  );
}
