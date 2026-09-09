import { useCallback, useEffect, useMemo, useState } from 'react';
import { Database, RefreshCw, ChevronLeft, ChevronRight, X } from 'lucide-react';
import * as api from '../services/api';
import DataTable from '../components/DataTable';

function fmtNum(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function fmtDateTime(v) {
  if (!v) return '—';
  return new Date(v).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' });
}

function fmtSeconds(v) {
  if (v === null || v === undefined) return '—';
  return `${Number(v).toFixed(1)}s`;
}

function truncated(v, max = 100) {
  if (!v) return '—';
  const text = String(v);
  return (
    <span title={text}>
      {text.length > max ? `${text.slice(0, max)}…` : text}
    </span>
  );
}

const TABLES = {
  hourly: {
    label: 'Hourly Grid Summary',
    table: 'hourly_grid_summary',
    note: 'Finest granularity available — one row per (date, hour, grid_id).',
    fetch: api.getHourlyData,
    defaultSort: 'date',
    hasHour: true,
    hasGeometryFilter: false,
    columns: [
      { key: 'id', label: 'ID', align: 'right' },
      { key: 'date', label: 'Date' },
      { key: 'hour', label: 'Hour', format: (v) => `${String(v).padStart(2, '0')}:00` },
      { key: 'grid_id', label: 'Grid' },
      { key: 'sms_in', label: 'SMS In', align: 'right', format: fmtNum },
      { key: 'sms_out', label: 'SMS Out', align: 'right', format: fmtNum },
      { key: 'call_in', label: 'Call In', align: 'right', format: fmtNum },
      { key: 'call_out', label: 'Call Out', align: 'right', format: fmtNum },
      { key: 'internet_activity', label: 'Internet', align: 'right', format: fmtNum },
      { key: 'total_activity', label: 'Total Activity', align: 'right', format: fmtNum },
      { key: 'record_count', label: 'Records', align: 'right', format: fmtNum },
      { key: 'loaded_at', label: 'Loaded At', format: fmtDateTime, sortable: false },
    ],
  },
  grid_summary: {
    label: 'Grid Daily Rollup',
    table: 'grid_summary',
    note: 'Per-day, per-grid rollup — faster trailing-week aggregates than scanning hourly rows.',
    fetch: api.getGridSummaryData,
    defaultSort: 'date',
    hasHour: false,
    hasGeometryFilter: false,
    columns: [
      { key: 'id', label: 'ID', align: 'right' },
      { key: 'date', label: 'Date' },
      { key: 'grid_id', label: 'Grid' },
      { key: 'total_sms', label: 'Total SMS', align: 'right', format: fmtNum },
      { key: 'total_calls', label: 'Total Calls', align: 'right', format: fmtNum },
      { key: 'internet_usage', label: 'Internet Usage', align: 'right', format: fmtNum },
      { key: 'total_activity', label: 'Total Activity', align: 'right', format: fmtNum },
      { key: 'active_hours', label: 'Active Hours', align: 'right', format: fmtNum },
      { key: 'loaded_at', label: 'Loaded At', format: fmtDateTime, sortable: false },
    ],
  },
  daily_summary: {
    label: 'Network Daily Summary',
    table: 'daily_summary',
    note: 'Network-wide per-day rollup — no grid_id, one row per day.',
    fetch: api.getDailySummaryData,
    defaultSort: 'date',
    hasHour: false,
    hasGridFilter: false,
    hasGeometryFilter: false,
    columns: [
      { key: 'id', label: 'ID', align: 'right' },
      { key: 'date', label: 'Date' },
      { key: 'total_sms', label: 'Total SMS', align: 'right', format: fmtNum },
      { key: 'total_calls', label: 'Total Calls', align: 'right', format: fmtNum },
      { key: 'internet_usage', label: 'Internet Usage', align: 'right', format: fmtNum },
      { key: 'total_activity', label: 'Total Activity', align: 'right', format: fmtNum },
      { key: 'active_grids', label: 'Active Grids', align: 'right', format: fmtNum },
      { key: 'total_records', label: 'Total Records', align: 'right', format: fmtNum },
      { key: 'loaded_at', label: 'Loaded At', format: fmtDateTime, sortable: false },
    ],
  },
  quality: {
    label: 'Quality Check',
    table: 'audit_log (flow/logs/audit_log.json)',
    note: 'Pipeline file-ingestion audit trail — one row per processing attempt, with the rejection reason on failure.',
    fetch: api.getAuditLogData,
    defaultSort: 'processed_at',
    hasGridFilter: false,
    hasHour: false,
    hasActivityFilter: false,
    hasGeometryFilter: false,
    hasStatusFilter: true,
    hasFilenameFilter: true,
    columns: [
      { key: 'id', label: 'ID', align: 'right' },
      { key: 'filename', label: 'Filename' },
      {
        key: 'status',
        label: 'Status',
        format: (v) => (
          <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${v === 'ACCEPTED' ? 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300' : 'border-rose-500/30 bg-rose-500/15 text-rose-300'}`}>
            {v}
          </span>
        ),
      },
      { key: 'row_count', label: 'Rows', align: 'right', format: fmtNum },
      { key: 'duration_seconds', label: 'Duration', align: 'right', format: fmtSeconds },
      { key: 'processed_at', label: 'Processed At', format: fmtDateTime },
      { key: 'reason', label: 'Reason', format: (v) => truncated(v, 120), sortable: false },
    ],
  },
};

function defaultFilters(def) {
  return {
    grid_id: '',
    date_from: '',
    date_to: '',
    hour_min: '',
    hour_max: '',
    min_activity: '',
    max_activity: '',
    has_geometry: '',
    status: '',
    filename: '',
    sort_by: def.defaultSort || 'date',
    sort_dir: 'desc',
    page: 1,
    page_size: 25,
  };
}

export default function DataExplorer({ onSelectGrid, selectedGridId, gridSelectKey }) {
  const [activeKey, setActiveKey] = useState('hourly');
  const [filtersByTable, setFiltersByTable] = useState(() =>
    Object.fromEntries(Object.entries(TABLES).map(([key, t]) => [key, defaultFilters(t)]))
  );
  const [result, setResult] = useState({ total: 0, records: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [usingFallback, setUsingFallback] = useState(false);

  useEffect(() => {
    if (gridSelectKey > 0 && selectedGridId) {
      setFiltersByTable((prev) => {
        const next = { ...prev };
        Object.keys(TABLES).forEach((key) => {
          if (TABLES[key].hasGridFilter !== false) {
            next[key] = { ...next[key], grid_id: String(selectedGridId), page: 1 };
          }
        });
        return next;
      });
    }
  }, [gridSelectKey, selectedGridId]);

  const def = TABLES[activeKey];
  const filters = filtersByTable[activeKey];

  const setFilters = useCallback(
    (patch) => {
      setFiltersByTable((prev) => ({
        ...prev,
        [activeKey]: { ...prev[activeKey], ...patch, ...(('page' in patch) ? {} : { page: 1 }) },
      }));
    },
    [activeKey]
  );

  const requestParams = useMemo(() => {
    const p = {
      date_from: filters.date_from || undefined,
      date_to: filters.date_to || undefined,
      sort_by: filters.sort_by,
      sort_dir: filters.sort_dir,
      page: filters.page,
      page_size: filters.page_size,
    };
    if (def.hasGridFilter !== false) {
      p.grid_id = filters.grid_id || undefined;
    }
    if (def.hasActivityFilter !== false) {
      p.min_activity = filters.min_activity || undefined;
      p.max_activity = filters.max_activity || undefined;
    }
    if (def.hasHour) {
      p.hour_min = filters.hour_min || undefined;
      p.hour_max = filters.hour_max || undefined;
    }
    if (def.hasGeometryFilter && filters.has_geometry !== '') {
      p.has_geometry = filters.has_geometry;
    }
    if (def.hasStatusFilter) {
      p.status = filters.status || undefined;
    }
    if (def.hasFilenameFilter) {
      p.filename = filters.filename || undefined;
    }
    return p;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeKey, filters]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await def.fetch(requestParams);
      setResult(data);
      setUsingFallback(!!data.meta?.fallback);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeKey, requestParams]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil((result.total || 0) / filters.page_size));

  function handleSort(colKey) {
    if (filters.sort_by === colKey) {
      setFilters({ sort_dir: filters.sort_dir === 'asc' ? 'desc' : 'asc' });
    } else {
      setFilters({ sort_by: colKey, sort_dir: 'desc' });
    }
  }

  function clearFilters() {
    setFiltersByTable((prev) => ({ ...prev, [activeKey]: defaultFilters(def) }));
  }

  const columns = useMemo(() => {
    if (!onSelectGrid) return def.columns;
    return def.columns.map((col) =>
      col.key === 'grid_id'
        ? {
            ...col,
            format: (v) => (
              <button onClick={() => onSelectGrid(v)} className="font-mono text-cyan-300 hover:underline">
                #{v}
              </button>
            ),
          }
        : col
    );
  }, [def, onSelectGrid]);

  const hasActiveFilters =
    filters.grid_id ||
    filters.date_from ||
    filters.date_to ||
    filters.hour_min ||
    filters.hour_max ||
    filters.min_activity ||
    filters.max_activity ||
    filters.has_geometry !== '' ||
    filters.status ||
    filters.filename;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white/80 px-4 py-3 shadow-sm backdrop-blur transition-colors duration-150 dark:border-slate-800 dark:bg-slate-900/40">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-md border border-cyan-500/30 bg-cyan-500/10 text-cyan-600 dark:text-cyan-300">
            <Database size={16} />
          </span>
          <div>
            <div className="text-sm font-medium text-slate-900 dark:text-slate-100">Data Explorer</div>
            <div className="text-[11px] text-slate-500 dark:text-slate-400">{def.note}</div>
          </div>
        </div>

        <div className="flex items-center gap-2 text-[10px] text-slate-500 dark:text-slate-400">
          {usingFallback && <span className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-amber-700 dark:text-amber-300">synthetic fallback data</span>}
          <button onClick={load} className="flex items-center gap-1 rounded border border-slate-200 bg-slate-100 px-2 py-1 text-slate-700 hover:text-cyan-700 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-300 dark:hover:text-cyan-300">
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      <div className="flex flex-wrap rounded-full border border-slate-200 bg-slate-100/80 p-0.5 w-fit dark:border-slate-800 dark:bg-slate-900/70">
        {Object.entries(TABLES).map(([key, t]) => (
          <button
            key={key}
            onClick={() => setActiveKey(key)}
            className={`rounded-full px-3.5 py-1.5 text-[12px] font-medium transition-colors ${
              activeKey === key
                ? 'bg-white text-cyan-700 shadow-sm border border-slate-200/80 dark:border-transparent dark:bg-cyan-500/20 dark:text-cyan-300'
                : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white/80 p-4 shadow-sm backdrop-blur transition-colors duration-150 dark:border-slate-800 dark:bg-slate-900/40">
        <div className="mb-3 flex flex-wrap items-end gap-3">
          {def.hasGridFilter !== false && (
            <label className="flex flex-col gap-1">
              <span className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Grid ID</span>
              <input
                type="number"
                value={filters.grid_id}
                onChange={(e) => setFilters({ grid_id: e.target.value })}
                placeholder="any"
                className="w-24 rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-800 focus:outline-none focus:border-cyan-500/50 dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-200"
              />
            </label>
          )}

          {def.hasFilenameFilter && (
            <label className="flex flex-col gap-1">
              <span className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Filename</span>
              <input
                type="text"
                value={filters.filename}
                onChange={(e) => setFilters({ filename: e.target.value })}
                placeholder="contains…"
                className="w-40 rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-800 focus:outline-none focus:border-cyan-500/50 dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-200"
              />
            </label>
          )}

          {def.hasStatusFilter && (
            <label className="flex flex-col gap-1">
              <span className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Status</span>
              <select
                value={filters.status}
                onChange={(e) => setFilters({ status: e.target.value })}
                className="rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-800 focus:outline-none dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-200"
              >
                <option value="">any</option>
                <option value="ACCEPTED">accepted</option>
                <option value="REJECTED">rejected</option>
              </select>
            </label>
          )}

          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Date From</span>
            <input
              type="date"
              value={filters.date_from}
              onChange={(e) => setFilters({ date_from: e.target.value })}
              className="rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-800 focus:outline-none dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-200"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Date To</span>
            <input
              type="date"
              value={filters.date_to}
              onChange={(e) => setFilters({ date_to: e.target.value })}
              className="rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-800 focus:outline-none dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-200"
            />
          </label>

          {def.hasHour && (
            <>
              <label className="flex flex-col gap-1">
                <span className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Hour ≥</span>
                <input
                  type="number"
                  min={0}
                  max={23}
                  value={filters.hour_min}
                  onChange={(e) => setFilters({ hour_min: e.target.value })}
                  placeholder="0"
                  className="w-16 rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-800 focus:outline-none focus:border-cyan-500/50 dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-200"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Hour ≤</span>
                <input
                  type="number"
                  min={0}
                  max={23}
                  value={filters.hour_max}
                  onChange={(e) => setFilters({ hour_max: e.target.value })}
                  placeholder="23"
                  className="w-16 rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-800 focus:outline-none focus:border-cyan-500/50 dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-200"
                />
              </label>
            </>
          )}

          {def.hasActivityFilter !== false && (
            <>
              <label className="flex flex-col gap-1">
                <span className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Activity ≥</span>
                <input
                  type="number"
                  value={filters.min_activity}
                  onChange={(e) => setFilters({ min_activity: e.target.value })}
                  placeholder="any"
                  className="w-24 rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-800 focus:outline-none focus:border-cyan-500/50 dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-200"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Activity ≤</span>
                <input
                  type="number"
                  value={filters.max_activity}
                  onChange={(e) => setFilters({ max_activity: e.target.value })}
                  placeholder="any"
                  className="w-24 rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-800 focus:outline-none focus:border-cyan-500/50 dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-200"
                />
              </label>
            </>
          )}

          {def.hasGeometryFilter && (
            <label className="flex flex-col gap-1">
              <span className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Geometry</span>
              <select
                value={filters.has_geometry}
                onChange={(e) => setFilters({ has_geometry: e.target.value })}
                className="rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-800 focus:outline-none dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-200"
              >
                <option value="">any</option>
                <option value="true">real</option>
                <option value="false">computed</option>
              </select>
            </label>
          )}

          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Page size</span>
            <select
              value={filters.page_size}
              onChange={(e) => setFilters({ page_size: Number(e.target.value), page: 1 })}
              className="rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-800 focus:outline-none dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-200"
            >
              {[25, 50, 100, 250, 500].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>

          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="flex items-center gap-1 rounded border border-slate-200 bg-slate-100 px-2 py-1.5 text-[11px] text-slate-700 hover:text-rose-600 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-300 dark:hover:text-rose-300"
            >
              <X size={11} /> Clear filters
            </button>
          )}
        </div>

        {error && <div className="mb-3 rounded border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-300">{error}</div>}

        <DataTable
          columns={columns}
          rows={result.records || []}
          sortBy={filters.sort_by}
          sortDir={filters.sort_dir}
          onSort={handleSort}
          loading={loading}
        />

        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500 dark:text-slate-400">
          <span>
            {(result.total || 0).toLocaleString()} row{result.total === 1 ? '' : 's'} · page {filters.page} of {totalPages}
          </span>
          <div className="flex items-center gap-1.5">
            <button
              disabled={filters.page <= 1}
              onClick={() => setFilters({ page: filters.page - 1 })}
              className="flex items-center gap-1 rounded border border-slate-200 bg-slate-100 px-2 py-1 text-slate-700 hover:text-cyan-700 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-300 dark:hover:text-cyan-300"
            >
              <ChevronLeft size={12} /> Prev
            </button>
            <button
              disabled={filters.page >= totalPages}
              onClick={() => setFilters({ page: filters.page + 1 })}
              className="flex items-center gap-1 rounded border border-slate-200 bg-slate-100 px-2 py-1 text-slate-700 hover:text-cyan-700 disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-800 dark:bg-slate-800/60 dark:text-slate-300 dark:hover:text-cyan-300"
            >
              Next <ChevronRight size={12} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
