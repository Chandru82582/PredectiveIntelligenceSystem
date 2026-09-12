import React, { useState } from 'react';
import {
  Database,
  Radio,
  Sparkles,
  Server,
  Bot,
  Zap,
  CheckCircle2,
  AlertTriangle,
  Info,
  ChevronDown,
  ChevronUp,
  ShieldAlert,
  Layers,
  ArrowRight
} from 'lucide-react';

const SPECIALISTS_INFO = {
  data_pipeline: {
    name: 'Data Pipeline Agent',
    shortName: 'Data Pipeline',
    role: 'Data Reliability & Ingestion Specialist',
    responsibility: 'Audits raw-to-analytical ETL freshness, monitors rejected batches in audit logs, and validates the non-negotiable hourly grid grain invariant.',
    allowedTools: ['get_pipeline_status', 'check_grain_duplicates', 'read_skill_runbook'],
    accent: 'sky',
    colorClasses: {
      border: 'border-sky-500/40',
      activeBorder: 'border-sky-400',
      bg: 'bg-sky-500/10 dark:bg-sky-950/40',
      text: 'text-sky-400',
      badge: 'bg-sky-500/20 text-sky-300 border-sky-500/30',
      glow: 'rgba(56, 189, 248, 0.8)',
    },
    icon: Database,
  },
  network_analysis: {
    name: 'Network Analysis Agent',
    shortName: 'Network Analysis',
    role: 'Cell Telemetry & Spatial Traffic Specialist',
    responsibility: 'Investigates physical grid telemetry, 24-hour baseline deviations, traffic surges, spatial sector coordinates, and fleet-wide hotspots.',
    allowedTools: ['get_network_summary', 'get_grid_activity', 'get_hotspots', 'get_grid_location'],
    accent: 'cyan',
    colorClasses: {
      border: 'border-cyan-500/40',
      activeBorder: 'border-cyan-400',
      bg: 'bg-cyan-500/10 dark:bg-cyan-950/40',
      text: 'text-cyan-400',
      badge: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
      glow: 'rgba(6, 182, 212, 0.8)',
    },
    icon: Radio,
  },
  ml_analysis: {
    name: 'ML Analysis Agent',
    shortName: 'ML Analysis',
    role: 'Predictive Inference & Anomaly Specialist',
    responsibility: 'Evaluates LightGBM predictive risk scoring, rolling lag feature dynamics, and arbitrates consensus between static rule heuristics and ML velocity.',
    allowedTools: ['get_anomaly_score', 'get_grid_features', 'review_grid_anomaly'],
    accent: 'amber',
    colorClasses: {
      border: 'border-amber-500/40',
      activeBorder: 'border-amber-400',
      bg: 'bg-amber-500/10 dark:bg-amber-950/40',
      text: 'text-amber-400',
      badge: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
      glow: 'rgba(245, 158, 11, 0.8)',
    },
    icon: Sparkles,
  },
  api_agent: {
    name: 'API Agent',
    shortName: 'API Agent',
    role: 'REST API Contract & Latency Specialist',
    responsibility: 'Executes the backend REST API test suite, verifies HTTP contract schemas, benchmarks endpoint response latencies, and isolates API regressions.',
    allowedTools: ['run_api_test_suite', 'read_skill_runbook'],
    accent: 'emerald',
    colorClasses: {
      border: 'border-emerald-500/40',
      activeBorder: 'border-emerald-400',
      bg: 'bg-emerald-500/10 dark:bg-emerald-950/40',
      text: 'text-emerald-400',
      badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
      glow: 'rgba(16, 185, 129, 0.8)',
    },
    icon: Server,
  },
};

export default function SubagentTopology({
  subagentsCalled = [],
  currentlyRunningAgent = null,
  isQuerying = false,
  specialistReports = {},
  activeGridId = 4365,
}) {
  const [selectedAgentKey, setSelectedAgentKey] = useState(null);

  // Determine active/communicating specialists
  const isSupervisorActive = isQuerying || currentlyRunningAgent === 'supervisor';
  const activeSubagents = isQuerying
    ? subagentsCalled.length > 0
      ? subagentsCalled
      : ['data_pipeline', 'network_analysis', 'ml_analysis']
    : subagentsCalled;

  // Handler to toggle inspection card
  const handleNodeClick = (key) => {
    setSelectedAgentKey((prev) => (prev === key ? null : key));
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white/95 p-3.5 shadow-sm dark:border-slate-800 dark:bg-slate-900/90 transition-all">
      {/* Topology Header */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-2.5 mb-3 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <div className="relative flex h-2 w-2">
            {isQuerying && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
            )}
            <span
              className={`relative inline-flex rounded-full h-2 w-2 ${
                isQuerying ? 'bg-cyan-500' : 'bg-emerald-500'
              }`}
            ></span>
          </div>
          <span className="font-mono text-[11px] font-bold tracking-wider uppercase text-slate-800 dark:text-slate-200">
            Specialist Multi-Agent Swarm
          </span>
        </div>
        <span
          className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
            isQuerying
              ? 'bg-cyan-500/10 text-cyan-600 border-cyan-500/30 dark:text-cyan-400'
              : 'bg-slate-100 text-slate-600 border-slate-300 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700'
          }`}
        >
          {isQuerying ? 'INVESTIGATING...' : 'READY / STANDBY'}
        </span>
      </div>

      {/* Real-time Query Activity Banner */}
      {isQuerying && (
        <div className="mb-3 rounded-lg border border-cyan-500/40 bg-cyan-500/10 p-2 text-xs font-mono text-cyan-800 dark:text-cyan-200 animate-pulse">
          <div className="flex items-center gap-1.5 font-bold mb-0.5">
            <Zap size={13} className="text-cyan-600 dark:text-cyan-400 animate-bounce" />
            <span>Currently Running: Supervisor Agent</span>
          </div>
          <div className="text-[11px] text-cyan-700 dark:text-cyan-300 flex items-center gap-1">
            <span>Delegating to:</span>
            <span className="font-bold underline">
              {activeSubagents.map((k) => SPECIALISTS_INFO[k]?.shortName || k).join(', ')}
            </span>
          </div>
        </div>
      )}

      {/* TOPOLOGY VISUAL DIAGRAM */}
      <div className="relative flex flex-col items-center">
        {/* SVG CONNECTING EDGES OVERLAY */}
        <svg
          className="absolute inset-0 h-full w-full pointer-events-none z-0"
          viewBox="0 0 320 220"
          preserveAspectRatio="none"
        >
          <defs>
            <linearGradient id="edgeGradActiveCyan" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#6366f1" />
              <stop offset="100%" stopColor="#06b6d4" />
            </linearGradient>
            <linearGradient id="edgeGradActiveAmber" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#6366f1" />
              <stop offset="100%" stopColor="#f59e0b" />
            </linearGradient>
            <linearGradient id="edgeGradActiveSky" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#6366f1" />
              <stop offset="100%" stopColor="#38bdf8" />
            </linearGradient>
            <linearGradient id="edgeGradActiveEmerald" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#6366f1" />
              <stop offset="100%" stopColor="#10b981" />
            </linearGradient>
            <filter id="svgGlow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="0" stdDeviation="2" floodColor="#06b6d4" />
            </filter>
          </defs>

          {/* Edge 1: Supervisor (160, 48) -> Data Pipeline (75, 105) */}
          <path
            id="edge-pipeline"
            d="M 160 48 C 160 75, 75 75, 75 98"
            fill="none"
            stroke={
              activeSubagents.includes('data_pipeline') && isQuerying
                ? 'url(#edgeGradActiveSky)'
                : activeSubagents.includes('data_pipeline')
                ? '#38bdf8'
                : 'currentColor'
            }
            strokeWidth={activeSubagents.includes('data_pipeline') ? 2.5 : 1.2}
            className={
              activeSubagents.includes('data_pipeline') && isQuerying
                ? 'text-sky-400 animate-edge-flow drop-shadow-[0_0_5px_rgba(56,189,248,0.7)]'
                : 'text-slate-300 dark:text-slate-700/80'
            }
            strokeDasharray={
              activeSubagents.includes('data_pipeline') && isQuerying ? '6, 4' : 'none'
            }
          />

          {/* Edge 2: Supervisor (160, 48) -> API Agent (245, 105) */}
          <path
            id="edge-api"
            d="M 160 48 C 160 75, 245 75, 245 98"
            fill="none"
            stroke={
              activeSubagents.includes('api_agent') && isQuerying
                ? 'url(#edgeGradActiveEmerald)'
                : activeSubagents.includes('api_agent')
                ? '#10b981'
                : 'currentColor'
            }
            strokeWidth={activeSubagents.includes('api_agent') ? 2.5 : 1.2}
            className={
              activeSubagents.includes('api_agent') && isQuerying
                ? 'text-emerald-400 animate-edge-flow drop-shadow-[0_0_5px_rgba(16,185,129,0.7)]'
                : 'text-slate-300 dark:text-slate-700/80'
            }
            strokeDasharray={
              activeSubagents.includes('api_agent') && isQuerying ? '6, 4' : 'none'
            }
          />

          {/* Edge 3: Supervisor (160, 48) -> Network Analysis (75, 168) */}
          <path
            id="edge-network"
            d="M 160 48 C 160 110, 75 125, 75 162"
            fill="none"
            stroke={
              activeSubagents.includes('network_analysis') && isQuerying
                ? 'url(#edgeGradActiveCyan)'
                : activeSubagents.includes('network_analysis')
                ? '#06b6d4'
                : 'currentColor'
            }
            strokeWidth={activeSubagents.includes('network_analysis') ? 2.5 : 1.2}
            className={
              activeSubagents.includes('network_analysis') && isQuerying
                ? 'text-cyan-400 animate-edge-flow drop-shadow-[0_0_5px_rgba(6,182,212,0.7)]'
                : 'text-slate-300 dark:text-slate-700/80'
            }
            strokeDasharray={
              activeSubagents.includes('network_analysis') && isQuerying ? '6, 4' : 'none'
            }
          />

          {/* Edge 4: Supervisor (160, 48) -> ML Analysis (245, 168) */}
          <path
            id="edge-ml"
            d="M 160 48 C 160 110, 245 125, 245 162"
            fill="none"
            stroke={
              activeSubagents.includes('ml_analysis') && isQuerying
                ? 'url(#edgeGradActiveAmber)'
                : activeSubagents.includes('ml_analysis')
                ? '#f59e0b'
                : 'currentColor'
            }
            strokeWidth={activeSubagents.includes('ml_analysis') ? 2.5 : 1.2}
            className={
              activeSubagents.includes('ml_analysis') && isQuerying
                ? 'text-amber-400 animate-edge-flow drop-shadow-[0_0_5px_rgba(245,158,11,0.7)]'
                : 'text-slate-300 dark:text-slate-700/80'
            }
            strokeDasharray={
              activeSubagents.includes('ml_analysis') && isQuerying ? '6, 4' : 'none'
            }
          />

          {/* ANIMATED PACKET PARTICLES DURING COMMUNICATION */}
          {isQuerying && activeSubagents.includes('data_pipeline') && (
            <circle r="3" fill="#38bdf8" filter="url(#svgGlow)">
              <animateMotion dur="0.9s" repeatCount="indefinite" path="M 160 48 C 160 75, 75 75, 75 98" />
            </circle>
          )}
          {isQuerying && activeSubagents.includes('api_agent') && (
            <circle r="3" fill="#10b981" filter="url(#svgGlow)">
              <animateMotion dur="0.9s" repeatCount="indefinite" path="M 160 48 C 160 75, 245 75, 245 98" />
            </circle>
          )}
          {isQuerying && activeSubagents.includes('network_analysis') && (
            <circle r="3" fill="#06b6d4" filter="url(#svgGlow)">
              <animateMotion dur="1.1s" repeatCount="indefinite" path="M 160 48 C 160 110, 75 125, 75 162" />
            </circle>
          )}
          {isQuerying && activeSubagents.includes('ml_analysis') && (
            <circle r="3" fill="#f59e0b" filter="url(#svgGlow)">
              <animateMotion dur="1.1s" repeatCount="indefinite" path="M 160 48 C 160 110, 245 125, 245 162" />
            </circle>
          )}
        </svg>

        {/* 1. SUPERVISOR PARENT NODE */}
        <div
          onClick={() => handleNodeClick('supervisor')}
          className={`relative z-10 w-full max-w-[210px] cursor-pointer rounded-lg border px-3 py-2 text-center transition-all ${
            isSupervisorActive
              ? 'border-indigo-500 bg-indigo-500/15 shadow-[0_0_12px_rgba(99,102,241,0.4)] dark:border-indigo-400 dark:bg-indigo-950/60'
              : 'border-slate-300 bg-slate-50 hover:border-indigo-400 dark:border-slate-700 dark:bg-slate-800/80'
          }`}
        >
          <div className="flex items-center justify-center gap-1.5">
            <div className="flex h-5 w-5 items-center justify-center rounded-md bg-indigo-500/20 text-indigo-600 dark:text-indigo-400">
              <Bot size={13} />
            </div>
            <span className="font-mono text-xs font-bold text-indigo-900 dark:text-indigo-200">
              Supervisor Agent
            </span>
          </div>
          <div className="mt-0.5 flex items-center justify-center gap-1 text-[10px] font-mono text-slate-500 dark:text-slate-400">
            <span>Lead NOC Commander</span>
            {isQuerying && (
              <span className="px-1 rounded bg-indigo-500/20 text-indigo-700 dark:text-indigo-300 text-[9px]">
                RUNNING
              </span>
            )}
          </div>
        </div>

        {/* 2. SPECIALIST NODES (2x2 GRID) */}
        <div className="relative z-10 mt-6 grid w-full grid-cols-2 gap-2.5">
          {/* Node 1: Data Pipeline Agent */}
          <SpecialistNodeCard
            agentKey="data_pipeline"
            info={SPECIALISTS_INFO.data_pipeline}
            isActive={activeSubagents.includes('data_pipeline')}
            isQuerying={isQuerying}
            report={specialistReports.data_pipeline}
            onClick={() => handleNodeClick('data_pipeline')}
            isSelected={selectedAgentKey === 'data_pipeline'}
          />

          {/* Node 2: API Agent */}
          <SpecialistNodeCard
            agentKey="api_agent"
            info={SPECIALISTS_INFO.api_agent}
            isActive={activeSubagents.includes('api_agent')}
            isQuerying={isQuerying}
            report={specialistReports.api_agent}
            onClick={() => handleNodeClick('api_agent')}
            isSelected={selectedAgentKey === 'api_agent'}
          />

          {/* Node 3: Network Analysis Agent */}
          <SpecialistNodeCard
            agentKey="network_analysis"
            info={SPECIALISTS_INFO.network_analysis}
            isActive={activeSubagents.includes('network_analysis')}
            isQuerying={isQuerying}
            report={specialistReports.network_analysis}
            onClick={() => handleNodeClick('network_analysis')}
            isSelected={selectedAgentKey === 'network_analysis'}
          />

          {/* Node 4: ML Analysis Agent */}
          <SpecialistNodeCard
            agentKey="ml_analysis"
            info={SPECIALISTS_INFO.ml_analysis}
            isActive={activeSubagents.includes('ml_analysis')}
            isQuerying={isQuerying}
            report={specialistReports.ml_analysis}
            onClick={() => handleNodeClick('ml_analysis')}
            isSelected={selectedAgentKey === 'ml_analysis'}
          />
        </div>
      </div>

      {/* INSPECTION DRAWER / DETAILS POPOVER */}
      {selectedAgentKey && (
        <div className="mt-3.5 rounded-lg border border-slate-300 bg-slate-50 p-2.5 text-xs dark:border-slate-700 dark:bg-slate-950/80 animate-in fade-in duration-200">
          {selectedAgentKey === 'supervisor' ? (
            <div className="space-y-1.5 font-mono">
              <div className="flex items-center justify-between text-indigo-700 dark:text-indigo-400 font-bold">
                <span className="flex items-center gap-1">
                  <Bot size={13} /> Supervisor Agent
                </span>
                <button
                  onClick={() => setSelectedAgentKey(null)}
                  className="text-slate-400 hover:text-slate-200 text-[10px]"
                >
                  ✕
                </button>
              </div>
              <p className="text-[11px] text-slate-600 dark:text-slate-300 font-sans">
                Parent orchestrator for telecom investigations. Coordinates the 4 specialist subagents, distributes restricted tasks, and synthesizes findings into one cohesive NOC report.
              </p>
              <div className="text-[10px] text-slate-500 pt-1 border-t border-slate-200 dark:border-slate-800">
                Shared Key: <span className="text-emerald-600 dark:text-emerald-400">ANTHROPIC_API_KEY</span> (Shared across all 4 specialists)
              </div>
            </div>
          ) : (
            <SpecialistDetailDrawer
              info={SPECIALISTS_INFO[selectedAgentKey]}
              report={specialistReports[selectedAgentKey]}
              onClose={() => setSelectedAgentKey(null)}
            />
          )}
        </div>
      )}
    </div>
  );
}

function SpecialistNodeCard({
  agentKey,
  info,
  isActive,
  isQuerying,
  report,
  onClick,
  isSelected,
}) {
  const Icon = info.icon;
  const isRunning = isActive && isQuerying;

  return (
    <div
      onClick={onClick}
      className={`relative cursor-pointer rounded-lg border p-2 transition-all duration-150 ${
        isRunning
          ? `${info.colorClasses.activeBorder} ${info.colorClasses.bg} shadow-[0_0_10px_rgba(6,182,212,0.3)] animate-agent-radar`
          : isActive
          ? `${info.colorClasses.border} ${info.colorClasses.bg}`
          : 'border-slate-200 bg-white/60 opacity-85 hover:opacity-100 dark:border-slate-800 dark:bg-slate-900/60'
      } ${isSelected ? 'ring-2 ring-cyan-500/50' : ''}`}
    >
      <div className="flex items-center justify-between gap-1 mb-1">
        <div className="flex items-center gap-1.5">
          <div
            className={`flex h-4 w-4 items-center justify-center rounded ${
              isActive ? info.colorClasses.text : 'text-slate-400'
            }`}
          >
            <Icon size={13} />
          </div>
          <span className="font-mono text-[11px] font-semibold text-slate-800 dark:text-slate-200 truncate">
            {info.shortName}
          </span>
        </div>

        {/* State Indicator */}
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            isRunning
              ? 'bg-amber-400 animate-ping'
              : isActive
              ? 'bg-emerald-400'
              : 'bg-slate-400 dark:bg-slate-600'
          }`}
        />
      </div>

      <div className="text-[10px] text-slate-500 dark:text-slate-400 font-mono truncate">
        {isRunning ? (
          <span className="text-amber-600 dark:text-amber-400 font-bold flex items-center gap-1">
            <Zap size={10} className="animate-spin" /> Calling...
          </span>
        ) : report?.status ? (
          <span
            className={`font-semibold ${
              report.status === 'HEALTHY' || report.status === 'PASS'
                ? 'text-emerald-600 dark:text-emerald-400'
                : 'text-amber-600 dark:text-amber-400'
            }`}
          >
            {report.status}
          </span>
        ) : (
          <span className="text-slate-400 dark:text-slate-500">
            {info.allowedTools.length} restricted tools
          </span>
        )}
      </div>
    </div>
  );
}

function SpecialistDetailDrawer({ info, report, onClose }) {
  const Icon = info.icon;

  return (
    <div className="space-y-2 font-mono">
      <div className="flex items-center justify-between">
        <span className={`font-bold text-xs flex items-center gap-1.5 ${info.colorClasses.text}`}>
          <Icon size={14} /> {info.name}
        </span>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-200 text-[10px]">
          ✕
        </button>
      </div>

      <div className="text-[11px] text-slate-600 dark:text-slate-300 font-sans leading-relaxed">
        <strong>Narrow Responsibility:</strong> {info.responsibility}
      </div>

      <div className="space-y-1 pt-1 border-t border-slate-200 dark:border-slate-800 text-[10px]">
        <span className="text-slate-400 block uppercase tracking-wider">Restricted Tool Set:</span>
        <div className="flex flex-wrap gap-1">
          {info.allowedTools.map((tool) => (
            <span
              key={tool}
              className="rounded bg-slate-200 px-1.5 py-0.5 text-slate-800 dark:bg-slate-800 dark:text-slate-300 border border-slate-300 dark:border-slate-700 font-mono"
            >
              {tool}
            </span>
          ))}
        </div>
      </div>

      {report && (
        <div className="pt-1.5 border-t border-slate-200 dark:border-slate-800 text-[10px] space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-slate-400">Latest Status:</span>
            <span className="font-bold text-emerald-600 dark:text-emerald-400">{report.status}</span>
          </div>
          <div className="text-slate-600 dark:text-slate-300 font-sans text-[11px]">
            {report.summary}
          </div>
        </div>
      )}
    </div>
  );
}
