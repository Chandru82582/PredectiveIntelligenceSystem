import { useState, useRef, useEffect, useCallback } from 'react';
import {
  UploadCloud, CheckCircle2, XCircle, AlertCircle, Clock,
  Database, Cpu, Eye, EyeOff, History, X, ChevronDown,
  ChevronRight, FileText, Loader2, Zap, Activity, RefreshCw,
  HardDrive, GitBranch,
} from 'lucide-react';
import {
  uploadPipelineFiles,
  getDagStatus,
  getDagLogs,
  getPipelineHistory,
} from '../services/api';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const FILE_PATTERN = /^sms-call-internet-mi-\d{4}-\d{2}-\d{2}\.csv$/;
const PATTERN_HINT = 'sms-call-internet-mi-YYYY-MM-DD.csv';

const DAG_STAGES = [
  { key: 'idle',             label: 'Waiting',       icon: Clock,        pct: 0  },
  { key: 'ingesting',        label: 'Ingest',        icon: UploadCloud,  pct: 20 },
  { key: 'validating',       label: 'Validate',      icon: CheckCircle2, pct: 40 },
  { key: 'spark_processing', label: 'Spark Process', icon: Cpu,          pct: 65 },
  { key: 'mysql_ingesting',  label: 'MySQL Ingest',  icon: Database,     pct: 85 },
];

const STAGE_ORDER = DAG_STAGES.map((s) => s.key);

// Log line colouring — checked in order, first match wins
const LOG_TOKENS = [
  ['ERROR',           'text-red-600 dark:text-red-400'],
  ['WARN',            'text-amber-600 dark:text-amber-400'],
  ['WARNING',         'text-amber-600 dark:text-amber-400'],
  ['[ingest]',        'text-violet-700 dark:text-violet-300'],
  ['[validate]',      'text-blue-700 dark:text-blue-300'],
  ['[spark_process]', 'text-amber-700 dark:text-amber-300'],
  ['[mysql_ingest]',  'text-emerald-700 dark:text-emerald-300'],
  ['[sensor]',        'text-slate-500 dark:text-slate-400'],
  ['INFO',            'text-cyan-700 dark:text-cyan-400'],
];

function colorLine(line) {
  for (const [token, cls] of LOG_TOKENS) {
    if (line.includes(token)) return cls;
  }
  return 'text-slate-700 dark:text-slate-300';
}

function fmtBytes(b) {
  if (b >= 1_048_576) return `${(b / 1_048_576).toFixed(1)} MB`;
  if (b >= 1024)      return `${(b / 1024).toFixed(0)} KB`;
  return `${b} B`;
}

function fmtDuration(secs) {
  if (!secs && secs !== 0) return '—';
  const s = Number(secs);
  if (s >= 60) return `${Math.floor(s / 60)}m ${(s % 60).toFixed(0)}s`;
  return `${s.toFixed(1)}s`;
}

function fmtDate(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

// ---------------------------------------------------------------------------
// Subcomponents
// ---------------------------------------------------------------------------

function StatusBadge({ status }) {
  const map = {
    ACCEPTED:  { cls: 'bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-400 dark:border-emerald-500/30', label: 'ACCEPTED' },
    REJECTED:  { cls: 'bg-red-100 text-red-700 border-red-300 dark:bg-red-500/15 dark:text-red-400 dark:border-red-500/30',                       label: 'REJECTED' },
    accepted:  { cls: 'bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-400 dark:border-emerald-500/30', label: 'QUEUED' },
    rejected:  { cls: 'bg-red-100 text-red-700 border-red-300 dark:bg-red-500/15 dark:text-red-400 dark:border-red-500/30',                       label: 'INVALID' },
    error:     { cls: 'bg-rose-100 text-rose-700 border-rose-300 dark:bg-rose-500/15 dark:text-rose-400 dark:border-rose-500/30',                  label: 'ERROR' },
    uploading: { cls: 'bg-cyan-100 text-cyan-700 border-cyan-300 dark:bg-cyan-500/15 dark:text-cyan-400 dark:border-cyan-500/30',                  label: 'UPLOADING' },
    pending:   { cls: 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-500/15 dark:text-slate-400 dark:border-slate-500/30',            label: 'PENDING' },
  };
  const cfg = map[status] || map.pending;
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wider ${cfg.cls}`}>
      {cfg.label}
    </span>
  );
}

function UploadCard({ file, result }) {
  const valid  = FILE_PATTERN.test(file.name);
  const status = result ? result.status : valid ? 'pending' : 'rejected';

  return (
    <div className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm transition-all
      ${status === 'accepted'  ? 'border-emerald-300 bg-emerald-50 dark:border-emerald-500/30 dark:bg-emerald-500/5'
      : status === 'rejected'  ? 'border-red-300 bg-red-50 dark:border-red-500/30 dark:bg-red-500/5'
      : status === 'error'     ? 'border-rose-300 bg-rose-50 dark:border-rose-500/30 dark:bg-rose-500/5'
      : status === 'uploading' ? 'border-cyan-300 bg-cyan-50 animate-pulse dark:border-cyan-500/30 dark:bg-cyan-500/5'
      : 'border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/40'}`}
    >
      <FileText size={14} className="shrink-0 text-slate-400" />
      <span className="flex-1 truncate font-mono text-[11px] text-slate-700 dark:text-slate-200">{file.name}</span>
      <span className="shrink-0 font-mono text-[10px] text-slate-400">{fmtBytes(file.size)}</span>
      <StatusBadge status={status} />
      {status === 'uploading' && <Loader2 size={12} className="shrink-0 animate-spin text-cyan-500" />}
      {!valid && !result && (
        <span className="max-w-xs truncate text-[10px] text-red-500">Must match {PATTERN_HINT}</span>
      )}
      {result?.reason && (
        <span className="max-w-[200px] truncate text-[10px] text-red-500" title={result.reason}>{result.reason}</span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function PipelineTracker() {
  // Upload
  const [dragOver, setDragOver]       = useState(false);
  const [uploadFiles, setUploadFiles] = useState([]);
  const [uploading, setUploading]     = useState(false);
  const fileInputRef = useRef(null);

  // DAG status
  const [dagStatus, setDagStatus]     = useState(null);
  const [statusErr, setStatusErr]     = useState(null);

  // Logs
  const [logs, setLogs]               = useState([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const logBoxRef = useRef(null);
  const [autoScroll, setAutoScroll]   = useState(true);

  // History panel
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory]         = useState([]);
  const [histLoading, setHistLoading] = useState(false);
  const [expandedRow, setExpandedRow] = useState(null);

  // ── Polling ──────────────────────────────────────────────────────────────

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getDagStatus();
      setDagStatus(data);
      setStatusErr(null);
    } catch (e) {
      setStatusErr(String(e.message || e));
    }
  }, []);

  const fetchLogs = useCallback(async () => {
    setLogsLoading(true);
    try {
      const data = await getDagLogs(200);
      setLogs(data.lines || []);
    } catch { /* silent */ }
    setLogsLoading(false);
  }, []);

  useEffect(() => {
    fetchStatus();
    fetchLogs();
    const t1 = setInterval(fetchStatus, 4000);
    const t2 = setInterval(fetchLogs,   3000);
    return () => { clearInterval(t1); clearInterval(t2); };
  }, [fetchStatus, fetchLogs]);

  // Auto-scroll log box
  useEffect(() => {
    if (autoScroll && logBoxRef.current) {
      logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  function handleLogScroll() {
    if (!logBoxRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = logBoxRef.current;
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 30);
  }

  // ── History panel ─────────────────────────────────────────────────────────

  async function openHistory() {
    setHistoryOpen(true);
    setHistLoading(true);
    try {
      const data = await getPipelineHistory(200);
      setHistory(data.entries || []);
    } catch { setHistory([]); }
    setHistLoading(false);
  }

  // ── File handling ─────────────────────────────────────────────────────────

  function addFiles(newFiles) {
    const incoming = Array.from(newFiles).map((f) => ({ file: f, result: null }));
    setUploadFiles((prev) => {
      const names = new Set(prev.map((x) => x.file.name));
      return [...prev, ...incoming.filter((i) => !names.has(i.file.name))];
    });
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files);
  }

  function handleFileInput(e) {
    if (e.target.files?.length) addFiles(e.target.files);
    e.target.value = '';
  }

  function removeFile(name) {
    setUploadFiles((prev) => prev.filter((x) => x.file.name !== name));
  }

  async function handleUpload() {
    const filesToSend = uploadFiles
      .filter(({ file, result }) =>
        FILE_PATTERN.test(file.name) && (!result || result.status === 'pending')
      )
      .map(({ file }) => file);

    if (!filesToSend.length) return;

    setUploadFiles((prev) =>
      prev.map((x) =>
        filesToSend.some((f) => f.name === x.file.name)
          ? { ...x, result: { status: 'uploading' } }
          : x
      )
    );
    setUploading(true);

    try {
      const data = await uploadPipelineFiles(filesToSend);
      const resultMap = Object.fromEntries((data.files || []).map((r) => [r.filename, r]));
      setUploadFiles((prev) =>
        prev.map((x) => ({ ...x, result: resultMap[x.file.name] ?? x.result }))
      );
    } catch (err) {
      setUploadFiles((prev) =>
        prev.map((x) =>
          x.result?.status === 'uploading'
            ? { ...x, result: { status: 'error', reason: String(err.message || err) } }
            : x
        )
      );
    }
    setUploading(false);
    fetchStatus();
  }

  // ── Derived values ────────────────────────────────────────────────────────

  const currentStageKey  = dagStatus?.stage || 'idle';
  const currentIdx       = STAGE_ORDER.indexOf(currentStageKey);
  const progressPct      = dagStatus?.progress_pct ?? 0;
  const pendingValidFiles = uploadFiles.filter(
    ({ file, result }) => FILE_PATTERN.test(file.name) && (!result || result.status === 'pending')
  ).length;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col gap-5 pb-12">

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-bold text-slate-900 dark:text-slate-100">
            <GitBranch size={20} className="text-violet-600 dark:text-violet-400" />
            DAG Pipeline Tracker
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">
            Drop Milano telecom CSVs to trigger the ingestion DAG and monitor it live.
          </p>
        </div>

        {dagStatus && (
          <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-1.5 text-xs text-slate-700 shadow-sm dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-300">
            <span
              className={`h-2 w-2 rounded-full ${
                currentStageKey === 'idle'
                  ? 'bg-slate-400'
                  : 'animate-pulse bg-emerald-500 shadow-[0_0_6px_#34d399]'
              }`}
            />
            <span className="font-medium">{dagStatus.stage_label}</span>
          </div>
        )}
      </div>

      {/* ── Two-column: drop-zone + stage strip ──────────────────────────── */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">

        {/* ── DROP-ZONE ── */}
        <div className="flex flex-col gap-3">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`relative flex min-h-[200px] cursor-pointer flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed px-6 py-8 text-center transition-all duration-200
              ${dragOver
                ? 'border-violet-500 bg-violet-50 shadow-[0_0_32px_rgba(139,92,246,0.2)] dark:bg-violet-500/10 dark:shadow-[0_0_32px_rgba(139,92,246,0.3)]'
                : 'border-slate-300 bg-slate-50 hover:border-violet-400 hover:bg-violet-50/50 dark:border-slate-700 dark:bg-slate-800/30 dark:hover:border-violet-500/50 dark:hover:bg-slate-800/50'}`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              multiple
              className="hidden"
              onChange={handleFileInput}
            />
            <div className={`flex h-14 w-14 items-center justify-center rounded-2xl border-2 transition-all duration-200
              ${dragOver
                ? 'border-violet-400 bg-violet-100 dark:bg-violet-500/20'
                : 'border-slate-300 bg-white dark:border-slate-600 dark:bg-slate-800'}`}>
              <UploadCloud size={26} className={dragOver ? 'text-violet-600 dark:text-violet-300' : 'text-slate-400'} />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                {dragOver ? 'Release to queue files' : 'Drag & drop CSV files here'}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                or click to browse — multiple files supported
              </p>
            </div>
            <div className="flex flex-col items-center gap-1">
              <p className="text-[10px] font-medium uppercase tracking-widest text-slate-400">Required filename format</p>
              <code className="rounded-lg border border-violet-200 bg-violet-50 px-3 py-1.5 font-mono text-[11px] text-violet-700 dark:border-violet-500/20 dark:bg-slate-900/80 dark:text-violet-300">
                {PATTERN_HINT}
              </code>
            </div>
          </div>

          {/* File cards */}
          {uploadFiles.length > 0 && (
            <div className="flex flex-col gap-1.5">
              {uploadFiles.map(({ file, result }) => (
                <div key={file.name} className="group relative">
                  <UploadCard file={file} result={result} />
                  {!uploading && (
                    <button
                      onClick={(e) => { e.stopPropagation(); removeFile(file.name); }}
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 opacity-0 transition-all hover:bg-slate-200 group-hover:opacity-100 dark:hover:bg-slate-700"
                    >
                      <X size={12} className="text-slate-500" />
                    </button>
                  )}
                </div>
              ))}

              {/* Action row */}
              <div className="mt-1.5 flex items-center gap-2">
                <button
                  onClick={handleUpload}
                  disabled={uploading || pendingValidFiles === 0}
                  className={`flex items-center gap-2 rounded-xl px-5 py-2 text-sm font-semibold transition-all duration-200
                    ${uploading || pendingValidFiles === 0
                      ? 'cursor-not-allowed bg-slate-200 text-slate-400 dark:bg-slate-700 dark:text-slate-500'
                      : 'bg-violet-600 text-white shadow-[0_0_20px_rgba(139,92,246,0.3)] hover:bg-violet-500'}`}
                >
                  {uploading
                    ? <><Loader2 size={14} className="animate-spin" /> Uploading…</>
                    : <><UploadCloud size={14} /> Send to Landing Zone ({pendingValidFiles})</>}
                </button>
                <button
                  onClick={() => setUploadFiles([])}
                  disabled={uploading}
                  className="rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-500 hover:border-slate-300 hover:text-slate-700 transition-colors dark:border-slate-700 dark:text-slate-400 dark:hover:border-slate-600 dark:hover:text-slate-300"
                >
                  Clear all
                </button>
                <span className="ml-auto font-mono text-[10px] text-slate-400">
                  {uploadFiles.filter(({ file }) => FILE_PATTERN.test(file.name)).length} valid /&nbsp;
                  {uploadFiles.length} total
                </span>
              </div>
            </div>
          )}
        </div>

        {/* ── DAG STAGE STRIP ── */}
        <div className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-800/30">
          <div className="flex items-center gap-2">
            <Activity size={13} className="text-emerald-500" />
            <span className="text-[11px] font-bold uppercase tracking-widest text-slate-500">
              Live DAG Progress
            </span>
          </div>

          {statusErr && (
            <div className="flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-400">
              <AlertCircle size={12} /> Backend unreachable: {statusErr}
            </div>
          )}

          {/* Stage pills */}
          <div className="flex flex-col gap-2">
            {DAG_STAGES.map((stage) => {
              const stageIdx = STAGE_ORDER.indexOf(stage.key);
              const isActive = stage.key === currentStageKey;
              const isDone   = stageIdx < currentIdx;
              const Icon = stage.icon;
              return (
                <div
                  key={stage.key}
                  className={`flex items-center gap-3 rounded-xl border px-4 py-2.5 transition-all duration-300
                    ${isActive
                      ? 'border-violet-300 bg-violet-50 shadow-sm dark:border-violet-500/50 dark:bg-violet-500/10 dark:shadow-[0_0_16px_rgba(139,92,246,0.2)]'
                    : isDone
                      ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-500/20 dark:bg-emerald-500/5'
                    : 'border-slate-100 bg-slate-50/50 opacity-50 dark:border-slate-700/50 dark:bg-slate-800/20'}`}
                >
                  <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border transition-all
                    ${isActive ? 'border-violet-400 bg-violet-100 dark:bg-violet-500/20'
                    : isDone   ? 'border-emerald-400 bg-emerald-100 dark:bg-emerald-500/15'
                    : 'border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800'}`}>
                    {isDone
                      ? <CheckCircle2 size={13} className="text-emerald-600 dark:text-emerald-400" />
                      : isActive
                        ? <Loader2 size={13} className="animate-spin text-violet-600 dark:text-violet-300" />
                        : <Icon size={13} className="text-slate-400" />}
                  </div>

                  <span className={`flex-1 text-sm font-medium
                    ${isActive ? 'text-violet-800 dark:text-violet-200'
                    : isDone   ? 'text-emerald-700 dark:text-emerald-300'
                    : 'text-slate-400 dark:text-slate-600'}`}>
                    {stage.label}
                  </span>

                  {isActive && dagStatus?.active_files?.length > 0 && (
                    <span className="rounded-lg border border-violet-300 bg-violet-100 px-2 py-0.5 font-mono text-[10px] text-violet-700 dark:border-violet-500/30 dark:bg-violet-500/10 dark:text-violet-300">
                      {dagStatus.active_files.length} file{dagStatus.active_files.length !== 1 ? 's' : ''}
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          {/* Progress bar */}
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-[11px] text-slate-500">Overall progress</span>
              <span className="font-mono text-[11px] font-semibold text-slate-600 dark:text-slate-400">{progressPct}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700/70">
              <div
                className="h-full rounded-full bg-gradient-to-r from-violet-600 via-cyan-500 to-emerald-500 transition-all duration-700"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>

          {/* Active files */}
          {dagStatus?.active_files?.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900/60">
              <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-slate-400">
                Processing Now
              </p>
              <div className="flex flex-col gap-1">
                {dagStatus.active_files.map((f) => (
                  <div key={f} className="flex items-center gap-2">
                    <Loader2 size={9} className="shrink-0 animate-spin text-violet-500" />
                    <span className="truncate font-mono text-[11px] text-slate-600 dark:text-slate-300">{f}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Counts */}
          <div className="flex gap-3 text-[11px] text-slate-400">
            <span>Landing: <b className="text-slate-700 dark:text-slate-300">{dagStatus?.landing_count ?? '—'}</b></span>
            <span>Processing: <b className="text-slate-700 dark:text-slate-300">{dagStatus?.processing_count ?? '—'}</b></span>
          </div>
        </div>
      </div>

      {/* ── LOG TERMINAL ───────────────────────────────────────────────── */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 shadow-sm dark:border-slate-700 dark:bg-slate-950">

        {/* Terminal titlebar */}
        <div className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4 py-2.5 dark:border-slate-700/80 dark:bg-slate-900">
          <div className="flex items-center gap-3">
            <div className="flex gap-1.5">
              <div className="h-3 w-3 rounded-full bg-red-400/80" />
              <div className="h-3 w-3 rounded-full bg-amber-400/80" />
              <div className="h-3 w-3 rounded-full bg-emerald-400/80" />
            </div>
            <span className="font-mono text-[11px] text-slate-500">
              telecom_pipeline.log
              {logs.length > 0 && ` · ${logs.length} lines`}
            </span>
            {logsLoading && <Loader2 size={10} className="animate-spin text-slate-400" />}
          </div>

          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setAutoScroll((v) => !v)}
              title={autoScroll ? 'Auto-scroll ON (click to pause)' : 'Auto-scroll OFF (click to resume)'}
              className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[10px] font-medium transition-all
                ${autoScroll
                  ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-500/10 dark:text-emerald-400'
                  : 'border-slate-200 text-slate-500 hover:text-slate-700 dark:border-slate-700 dark:text-slate-500 dark:hover:text-slate-400'}`}
            >
              {autoScroll ? <Eye size={10} /> : <EyeOff size={10} />}
              {autoScroll ? 'Live' : 'Paused'}
            </button>

            <button
              onClick={fetchLogs}
              className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1 text-[10px] text-slate-500 transition-colors hover:border-slate-300 hover:text-slate-700 dark:border-slate-700 dark:text-slate-400 dark:hover:border-slate-600 dark:hover:text-slate-300"
            >
              <RefreshCw size={10} /> Refresh
            </button>

            {/* HISTORY button */}
            <button
              onClick={openHistory}
              className="flex items-center gap-1.5 rounded-lg border border-violet-300 bg-violet-50 px-3 py-1 text-[11px] font-semibold text-violet-700 transition-all hover:bg-violet-100 dark:border-violet-500/40 dark:bg-violet-500/10 dark:text-violet-300 dark:shadow-[0_0_10px_rgba(139,92,246,0.2)] dark:hover:bg-violet-500/20 dark:hover:text-violet-200"
            >
              <History size={11} /> History
            </button>
          </div>
        </div>

        {/* Log lines — dark terminal background always (intentional for readability) */}
        <div
          ref={logBoxRef}
          onScroll={handleLogScroll}
          className="h-80 overflow-y-auto bg-slate-900 px-4 py-3 dark:bg-slate-950"
        >
          {logs.length === 0 ? (
            <p className="font-mono text-[11px] italic text-slate-600">
              # No log output yet. Drop a CSV and the DAG will populate this once it runs.
            </p>
          ) : (
            logs.map((line, i) => (
              <div
                key={i}
                className={`whitespace-pre-wrap break-all font-mono text-[11px] leading-relaxed ${colorLine(line)}`}
              >
                {line || '\u00a0'}
              </div>
            ))
          )}
        </div>
      </div>

      {/* ── HISTORY SIDE-PANEL ──────────────────────────────────────────── */}

      {historyOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/40 backdrop-blur-sm"
          onClick={() => setHistoryOpen(false)}
        />
      )}

      <div
        className={`fixed right-0 top-0 z-40 flex h-full w-full max-w-2xl flex-col border-l border-slate-200 bg-white shadow-2xl transition-transform duration-300 ease-in-out dark:border-slate-700 dark:bg-slate-900
          ${historyOpen ? 'translate-x-0' : 'translate-x-full'}`}
      >
        {/* Panel header */}
        <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-700">
          <div className="flex items-center gap-2.5">
            <History size={16} className="text-violet-600 dark:text-violet-400" />
            <span className="font-bold text-slate-900 dark:text-slate-100">Processing History</span>
            {history.length > 0 && (
              <span className="rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400">
                {history.length} records
              </span>
            )}
          </div>
          <button
            onClick={() => setHistoryOpen(false)}
            className="rounded-lg border border-slate-200 p-1.5 text-slate-500 transition-colors hover:border-slate-300 hover:text-slate-800 dark:border-slate-700 dark:text-slate-400 dark:hover:border-slate-600 dark:hover:text-slate-200"
          >
            <X size={14} />
          </button>
        </div>

        {/* Summary strip */}
        {!histLoading && history.length > 0 && (
          <div className="flex shrink-0 gap-4 border-b border-slate-100 bg-slate-50 px-5 py-3 dark:border-slate-700/50 dark:bg-slate-800/40">
            {[
              { label: 'Accepted',     val: history.filter((e) => e.status === 'ACCEPTED').length, cls: 'text-emerald-600 dark:text-emerald-400' },
              { label: 'Rejected',     val: history.filter((e) => e.status === 'REJECTED').length, cls: 'text-red-600 dark:text-red-400' },
              { label: 'Avg Duration',
                val: (() => {
                  const acc = history.filter((e) => e.duration_seconds);
                  if (!acc.length) return '—';
                  const avg = acc.reduce((s, e) => s + Number(e.duration_seconds), 0) / acc.length;
                  return fmtDuration(avg);
                })(),
                cls: 'text-cyan-600 dark:text-cyan-400' },
            ].map((s) => (
              <div key={s.label} className="flex flex-col">
                <span className="text-[10px] text-slate-400">{s.label}</span>
                <span className={`font-mono text-sm font-bold ${s.cls}`}>{s.val}</span>
              </div>
            ))}
          </div>
        )}

        {/* Panel body */}
        <div className="flex-1 overflow-y-auto p-4">
          {histLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 size={22} className="animate-spin text-slate-400" />
            </div>
          ) : history.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-20 text-slate-400">
              <HardDrive size={36} className="opacity-25" />
              <p className="text-sm">No audit entries found.</p>
              <p className="text-xs">Run the pipeline to see history here.</p>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {history.map((entry, idx) => {
                const isExpanded = expandedRow === idx;
                const isAccepted = entry.status === 'ACCEPTED';
                return (
                  <div
                    key={idx}
                    className={`overflow-hidden rounded-xl border transition-all
                      ${isAccepted
                        ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-500/20 dark:bg-emerald-500/5'
                        : 'border-red-200 bg-red-50 dark:border-red-500/20 dark:bg-red-500/5'}`}
                  >
                    <button
                      onClick={() => setExpandedRow(isExpanded ? null : idx)}
                      className="flex w-full items-center gap-3 px-3.5 py-2.5 text-left transition-colors hover:bg-black/5 dark:hover:bg-white/5"
                    >
                      {isExpanded
                        ? <ChevronDown  size={12} className="shrink-0 text-slate-400" />
                        : <ChevronRight size={12} className="shrink-0 text-slate-400" />}

                      {isAccepted
                        ? <CheckCircle2 size={13} className="shrink-0 text-emerald-500 dark:text-emerald-400" />
                        : <XCircle      size={13} className="shrink-0 text-red-500 dark:text-red-400" />}

                      <span className="flex-1 truncate font-mono text-[11px] text-slate-700 dark:text-slate-200">
                        {entry.filename}
                      </span>

                      <span className="shrink-0 font-mono text-[10px] text-slate-400">
                        {fmtDate(entry.processed_at)}
                      </span>

                      <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-bold
                        ${isAccepted
                          ? 'border-emerald-300 bg-emerald-100 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-400'
                          : 'border-red-300 bg-red-100 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400'}`}>
                        {entry.status}
                      </span>
                    </button>

                    {isExpanded && (
                      <div className="border-t border-slate-200 px-4 py-3 dark:border-slate-700/40">
                        <dl className="grid grid-cols-2 gap-x-6 gap-y-2.5 text-[11px]">
                          <div>
                            <dt className="text-slate-400">Row count</dt>
                            <dd className="font-mono font-semibold text-slate-700 dark:text-slate-200">
                              {entry.row_count != null ? Number(entry.row_count).toLocaleString() : '—'}
                            </dd>
                          </div>
                          <div>
                            <dt className="text-slate-400">Duration</dt>
                            <dd className="font-mono font-semibold text-slate-700 dark:text-slate-200">
                              {fmtDuration(entry.duration_seconds)}
                            </dd>
                          </div>
                          {entry.reason && (
                            <div className="col-span-2">
                              <dt className="mb-1 text-slate-400">
                                {isAccepted ? 'Notes' : 'Failure reason'}
                              </dt>
                              <dd className={`whitespace-pre-wrap break-all rounded-lg border p-2 font-mono text-[10px] leading-relaxed
                                ${isAccepted
                                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/20 dark:bg-emerald-500/5 dark:text-emerald-300'
                                  : 'border-red-200 bg-red-50 text-red-700 dark:border-red-500/20 dark:bg-red-500/5 dark:text-red-300'}`}>
                                {entry.reason}
                              </dd>
                            </div>
                          )}
                        </dl>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
