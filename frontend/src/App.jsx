import { useEffect, useState } from 'react';
import { RadioTower, Search, CircleDot, LayoutDashboard, ScanSearch, Table2, Bot, GitBranch } from 'lucide-react';
import * as api from './services/api';
import NetworkOverview from './views/NetworkOverview';
import GridInvestigator from './views/GridInvestigator';
import DataExplorer from './views/DataExplorer';
import ClaudeAssistant from './views/ClaudeAssistant';
import PipelineTracker from './views/PipelineTracker';
import ThemeToggle from './components/ThemeToggle';
import ModelSelector from './components/ModelSelector';

export default function App() {
  const [tab, setTab] = useState('overview');
  const [selectedGridId, setSelectedGridId] = useState(api.QUICK_SWITCH_GRIDS[0]);
  const [gridSelectKey, setGridSelectKey] = useState(0);
  const [searchInput, setSearchInput] = useState('');
  const [asOf, setAsOf] = useState(null);
  const [syncOk, setSyncOk] = useState(true);
  const [availableModels, setAvailableModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState('');

  useEffect(() => {
    let mounted = true;
    api.getNetworkSummary().then((res) => {
      if (!mounted) return;
      setAsOf(res.as_of);
      setSyncOk(!res.meta?.fallback);
    });

    api.getAvailableModels().then((res) => {
      if (!mounted) return;
      const list = res.models || [];
      setAvailableModels(list);
      setSelectedModel(res.default || list[0] || 'lgbm_high_activity_v2.joblib');
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

  function handleNavigate(gridId, targetTab) {
    if (gridId != null) {
      setSelectedGridId(gridId);
      setGridSelectKey((k) => k + 1);
    }
    if (targetTab) {
      setTab(targetTab);
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
    <div className={`min-h-screen bg-slate-50 text-slate-900 transition-colors duration-150 dark:bg-slate-950 dark:text-slate-200 ${tab === 'assistant' ? 'h-screen flex flex-col overflow-hidden' : ''}`}>
      <header className="sticky top-0 z-20 shrink-0 border-b border-slate-200 bg-white/95 text-slate-800 backdrop-blur transition-colors duration-150 dark:border-slate-800 dark:bg-slate-950/95 dark:text-slate-100">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-4 px-5 py-3">
          <div className="flex items-center gap-2">
            <RadioTower size={18} className="text-cyan-600 dark:text-cyan-400" />
            <span className="text-sm font-semibold tracking-wide text-slate-900 dark:text-slate-100">Telecom Activity Intelligence</span>
          </div>

          <nav className="flex rounded-full border border-slate-200 bg-slate-100/80 p-0.5 dark:border-slate-800 dark:bg-slate-900/70">
            {[
              { id: 'overview',     label: 'Network Overview & Map', icon: LayoutDashboard },
              { id: 'investigator', label: 'Grid Investigator',       icon: ScanSearch },
              { id: 'data',         label: 'Data',                    icon: Table2 },
              { id: 'assistant',    label: 'NOC Assistant',           icon: Bot },
              { id: 'pipeline',     label: 'Pipeline',                icon: GitBranch },
            ].map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12px] font-medium transition-colors ${
                  tab === t.id
                    ? 'bg-white text-cyan-700 shadow-sm border border-slate-200/80 dark:border-transparent dark:bg-cyan-500/20 dark:text-cyan-300'
                    : 'text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200'
                }`}
              >
                <t.icon size={12} className={tab === t.id ? 'text-cyan-600 dark:text-cyan-400' : 'opacity-60'} />
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
                    ? 'border-amber-500/50 bg-amber-500/20 font-semibold text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-300'
                    : 'border-slate-200 bg-slate-100/70 text-slate-600 hover:bg-slate-200/70 hover:text-slate-900 dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-400 dark:hover:text-slate-200'
                }`}
              >
                #{id}
              </button>
            ))}
          </div>

          <form onSubmit={handleSearchSubmit} className="ml-auto flex items-center gap-2">
            <div className="flex items-center gap-1.5 rounded border border-slate-200 bg-slate-50 px-2 py-1 dark:border-slate-800 dark:bg-slate-900/60">
              <Search size={12} className="text-slate-400 dark:text-slate-500" />
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Jump to grid_id"
                className="w-28 bg-transparent font-mono text-[11px] text-slate-800 placeholder:text-slate-400 focus:outline-none dark:text-slate-200 dark:placeholder:text-slate-600"
              />
            </div>
          </form>

          {availableModels.length > 0 && (
            <ModelSelector
              models={availableModels}
              selectedModel={selectedModel}
              onSelectModel={setSelectedModel}
              compact={true}
            />
          )}

          <div className="flex items-center gap-3 text-[10px] text-slate-500 dark:text-slate-400">
            <span className="flex items-center gap-1.5">
              <CircleDot size={9} className={syncOk ? 'text-emerald-500 dark:text-emerald-400' : 'text-amber-500 dark:text-amber-400'} />
              {syncOk ? 'Pipeline synced' : 'Synthetic fallback'}
            </span>
            {asOf && <span className="font-mono">AS_OF {new Date(asOf).toLocaleString()}</span>}
          </div>

          <ThemeToggle />
        </div>
      </header>

      <main className={`mx-auto w-full max-w-[1400px] ${tab === 'assistant' ? 'flex-1 min-h-0 flex flex-col p-3 sm:p-4 overflow-hidden' : ''}`}>
        <div className={tab === 'overview' ? 'px-5 py-6' : 'hidden'}>
          <NetworkOverview
            selectedGridId={selectedGridId}
            onSelectGrid={(id) => { setSelectedGridId(id); setGridSelectKey((k) => k + 1); }}
            onNavigate={handleNavigate}
            isVisible={tab === 'overview'}
          />
        </div>
        <div className={tab === 'investigator' ? 'px-5 py-6' : 'hidden'}>
          <GridInvestigator
            gridId={selectedGridId}
            selectedModel={selectedModel}
            onSelectModel={setSelectedModel}
            availableModels={availableModels}
          />
        </div>
        <div className={tab === 'data' ? 'px-5 py-6' : 'hidden'}>
          <DataExplorer
            onSelectGrid={handleGridSelect}
            selectedGridId={selectedGridId}
            gridSelectKey={gridSelectKey}
          />
        </div>
        <div className={tab === 'assistant' ? 'flex-1 min-h-0 h-full w-full' : 'hidden'}>
          <ClaudeAssistant
            gridId={selectedGridId}
            selectedModel={selectedModel}
          />
        </div>
        <div className={tab === 'pipeline' ? 'px-5 py-6' : 'hidden'}>
          <PipelineTracker />
        </div>
      </main>
    </div>
  );
} 