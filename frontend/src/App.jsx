import { useEffect, useState } from 'react';
import { RadioTower, Search, CircleDot } from 'lucide-react';
import * as api from './services/api';
import NetworkOverview from './views/NetworkOverview';
import GridInvestigator from './views/GridInvestigator';
import DataExplorer from './views/DataExplorer';
import ClaudeAssistant from './views/ClaudeAssistant';

export default function App() {
  const [tab, setTab] = useState('overview');
  const [selectedGridId, setSelectedGridId] = useState(api.QUICK_SWITCH_GRIDS[0]);
  const [gridSelectKey, setGridSelectKey] = useState(0);
  const [searchInput, setSearchInput] = useState('');
  const [asOf, setAsOf] = useState(null);
  const [syncOk, setSyncOk] = useState(true);

  useEffect(() => {
    let mounted = true;
    api.getNetworkSummary().then((res) => {
      if (!mounted) return;
      setAsOf(res.as_of);
      setSyncOk(!res.meta?.fallback);
    });

    // Background prefetch cache for remaining quick-switch grids and secondary tables
    const prefetchTimer = setTimeout(() => {
      if (!mounted) return;
      api.QUICK_SWITCH_GRIDS.forEach((id) => {
        if (id !== selectedGridId) {
          api.getGridTimeseries(id).catch(() => {});
          api.getGridModality(id).catch(() => {});
          api.getGridFeatures(id).catch(() => {});
          api.getWeeklyPeak(id).catch(() => {});
          api.getGridGeography(id).catch(() => {});
          api.getGridPrediction(id).catch(() => {});
        }
      });
      api.getSpatialData({ page: 1, page_size: 25 }).catch(() => {});
      api.getGridSummaryData({ page: 1, page_size: 25 }).catch(() => {});
    }, 600);

    return () => {
      mounted = false;
      clearTimeout(prefetchTimer);
    };
  }, []);

  // Reset scroll position on tab change to prevent header cutoff/overlap
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [tab]);

  function handleGridSelect(gridId) {
    setSelectedGridId(gridId);
    setGridSelectKey((k) => k + 1);
    if (tab === 'overview') {
      setTab('investigator');
    }
  }

  function handleSearchSubmit(e) {
    e.preventDefault();
    const clean = searchInput.replace(/^[#\s]+/, '').trim();
    const id = parseInt(clean, 10);
    if (Number.isFinite(id) && id >= 1 && id <= 10000) {
      handleGridSelect(id);
      setSearchInput('');
    }
  }

  return (
    <div className={`min-h-screen bg-slate-950 text-slate-200 ${tab === 'assistant' ? 'h-screen flex flex-col overflow-hidden' : ''}`}>
      <header className="sticky top-0 z-20 shrink-0 border-b border-slate-800 bg-slate-950/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-4 px-5 py-3">
          <div className="flex items-center gap-2">
            <RadioTower size={18} className="text-cyan-400" />
            <span className="text-sm font-semibold tracking-wide text-slate-100">Telecom Activity Intelligence</span>
          </div>

          <nav className="flex rounded-full border border-slate-800 bg-slate-900/70 p-0.5">
            {[
              { id: 'overview', label: 'Network Overview & Map' },
              { id: 'investigator', label: 'Grid Investigator' },
              { id: 'data', label: 'Data' },
              { id: 'assistant', label: 'NOC Assistant' },
            ].map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`rounded-full px-3.5 py-1.5 text-[12px] font-medium transition-colors ${
                  tab === t.id ? 'bg-cyan-500/20 text-cyan-300' : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>

          <div className="flex items-center gap-1.5">
            {api.QUICK_SWITCH_GRIDS.map((id) => (
              <button
                key={id}
                onClick={() => handleGridSelect(id)}
                className={`rounded border px-2 py-1 font-mono text-[11px] transition-colors ${
                  selectedGridId === id && tab !== 'overview'
                    ? 'border-amber-500/40 bg-amber-500/15 text-amber-300'
                    : 'border-slate-800 bg-slate-900/60 text-slate-400 hover:text-slate-200'
                }`}
              >
                #{id}
              </button>
            ))}
          </div>

          <form onSubmit={handleSearchSubmit} className="ml-auto flex items-center gap-2">
            <div className="flex items-center gap-1.5 rounded border border-slate-800 bg-slate-900/60 px-2 py-1">
              <Search size={12} className="text-slate-500" />
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Jump to grid_id"
                className="w-28 bg-transparent font-mono text-[11px] text-slate-200 placeholder:text-slate-600 focus:outline-none"
              />
            </div>
          </form>

          <div className="flex items-center gap-3 text-[10px] text-slate-500">
            <span className="flex items-center gap-1.5">
              <CircleDot size={9} className={syncOk ? 'text-emerald-400' : 'text-amber-400'} />
              {syncOk ? 'Pipeline synced' : 'Synthetic fallback'}
            </span>
            {asOf && <span className="font-mono">AS_OF {new Date(asOf).toLocaleString()}</span>}
          </div>
        </div>
      </header>

      <main className={`mx-auto w-full max-w-[1400px] ${tab === 'assistant' ? 'flex-1 min-h-0 flex flex-col p-3 sm:p-4 overflow-hidden' : ''}`}>
        <div className={tab === 'overview' ? 'px-5 py-6' : 'hidden'}>
          <NetworkOverview selectedGridId={selectedGridId} onSelectGrid={handleGridSelect} isVisible={tab === 'overview'} />
        </div>
        <div className={tab === 'investigator' ? 'px-5 py-6' : 'hidden'}>
          <GridInvestigator gridId={selectedGridId} />
        </div>
        <div className={tab === 'data' ? 'px-5 py-6' : 'hidden'}>
          <DataExplorer
            onSelectGrid={handleGridSelect}
            selectedGridId={selectedGridId}
            gridSelectKey={gridSelectKey}
          />
        </div>
        <div className={tab === 'assistant' ? 'flex-1 min-h-0 h-full w-full' : 'hidden'}>
          <ClaudeAssistant gridId={selectedGridId} />
        </div>
      </main>
    </div>
  );
} 