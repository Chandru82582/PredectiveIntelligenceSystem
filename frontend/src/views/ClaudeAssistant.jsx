import React, { useState, useRef, useEffect } from 'react';
import { Send, Activity, AlertTriangle, ShieldCheck, Map, Cpu, Server, Loader2, RotateCcw, Clock, Terminal, Zap, Sparkles } from 'lucide-react';
import * as api from '../services/api';
import SubagentTopology from '../components/SubagentTopology';

const SLASH_COMMANDS = [
  {
    command: '/check-pipeline',
    syntax: '/check-pipeline',
    description: 'Call GET /pipeline/status and summarize health, naming any rejected rows or staleness',
    category: 'HEALTH',
    badgeClass: 'text-cyan-400 border-cyan-500/30 bg-cyan-500/10'
  },
  {
    command: '/explain-grid',
    syntax: '/explain-grid [grid_id]',
    description: 'Gather activity, features, anomaly score & location -> SEVERITY / EVIDENCE / INTERPRETATION / NEXT CHECKS',
    category: 'REPORT',
    requiresGrid: true,
    badgeClass: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
  },
  {
    command: '/review-anomaly',
    syntax: '/review-anomaly [grid_id]',
    description: 'Compare rule alert, classifier output and anomaly score for a grid and explain any disagreement',
    category: 'DIAGNOSTIC',
    requiresGrid: true,
    badgeClass: 'text-amber-400 border-amber-500/30 bg-amber-500/10'
  },
  {
    command: '/test-api',
    syntax: '/test-api',
    description: 'Run the API test suite and summarize failures',
    category: 'TEST SUITE',
    badgeClass: 'text-violet-400 border-violet-500/30 bg-violet-500/10'
  },
  {
    command: '/network-health',
    syntax: '/network-health',
    description: 'Run grain duplicate check on hourly_grid_summary and report pass or fail',
    category: 'AUDIT',
    badgeClass: 'text-rose-400 border-rose-500/30 bg-rose-500/10'
  }
];

const CHAT_STORAGE_KEY = 'noc_chat_histories_by_grid';


function loadStoredHistories() {
  try {
    const raw = localStorage.getItem(CHAT_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveStoredHistories(histories) {
  try {
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(histories));
  } catch (e) {
    console.warn('Failed to save chat histories to localStorage:', e);
  }
}

function formatTimestamp(ts) {
  if (!ts) return null;
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return null;
    return {
      time: d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      full: d.toLocaleString()
    };
  } catch {
    return null;
  }
}

function getInitialMessageForGrid(id) {
  return [
    {
      role: 'assistant',
      timestamp: new Date().toISOString(),
      content: `<div class="noc-report space-y-3 font-sans">
  <div class="flex items-center gap-2 border-b border-slate-200 dark:border-slate-800 pb-2.5">
    <span class="h-2 w-2 rounded-full bg-emerald-500 dark:bg-emerald-400 animate-pulse"></span>
    <span class="text-xs font-semibold uppercase tracking-wider text-emerald-600 dark:text-emerald-400 font-mono">NOC Assistant — Cell #${id}</span>
    <span class="text-[11px] text-slate-400 dark:text-slate-500 font-mono ml-auto">Active Session</span>
  </div>
  <p class="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
    NOC AI Assistant initialized for <strong>Grid #${id}</strong>. Real-time telemetry, risk predictions, and rule alerts are loaded into active context. Ask any operational question or request triage checks for this cell.
  </p>
</div>`
    }
  ];
}

function MessageBubble({ msg }) {
  const isUser = msg.role === 'user';
  const timeInfo = formatTimestamp(msg.timestamp);

  if (isUser) {
    return (
      <div className="max-w-[80%] rounded-xl px-4 py-3 bg-cyan-50 border border-cyan-200 text-cyan-950 font-mono text-sm leading-relaxed shadow-sm flex flex-col dark:bg-cyan-950/40 dark:border-cyan-800/40 dark:text-cyan-100">
        <div className="whitespace-pre-wrap">{msg.content}</div>
        {timeInfo && (
          <div
            className="mt-1.5 flex items-center justify-end gap-1 text-[10px] font-mono text-cyan-700/70 select-none self-end dark:text-cyan-300/60"
            title={timeInfo.full}
          >
            <Clock size={10} className="opacity-70" />
            <span>{timeInfo.time}</span>
          </div>
        )}
      </div>
    );
  }

  // Assistant response: strip accidental code block formatting if present
  let cleaned = (msg.content || '').trim();
  if (cleaned.startsWith('```html')) {
    cleaned = cleaned.replace(/^```html\s*/i, '').replace(/\s*```$/, '');
  } else if (cleaned.startsWith('```')) {
    cleaned = cleaned.replace(/^```\s*/, '').replace(/\s*```$/, '');
  }

  const isHtml = /<[a-z][\s\S]*>/i.test(cleaned);

  return (
    <div className="w-full max-w-[95%] rounded-xl p-4 bg-white border border-slate-200 text-slate-800 shadow-md flex flex-col dark:bg-slate-900/90 dark:border-slate-800 dark:text-slate-200">
      {/* Skill Indicator Top Banner */}
      {msg.skill_used && (
        <div className="mb-3 flex items-center justify-between border-b border-slate-100 pb-2 dark:border-slate-800/80">
          <div className="inline-flex items-center gap-1.5 rounded-full border border-cyan-500/40 bg-cyan-500/10 px-2.5 py-0.5 font-mono text-[10px] font-medium text-cyan-700 dark:border-cyan-400/40 dark:bg-cyan-950/70 dark:text-cyan-300 shadow-sm">
            <Zap size={11} className="text-cyan-600 dark:text-cyan-400 animate-pulse fill-cyan-500/20" />
            <span className="font-bold uppercase tracking-wider text-[9px] text-cyan-600 dark:text-cyan-400">Skill Active</span>
            <span className="text-slate-300 dark:text-slate-700">·</span>
            <span className="font-semibold text-cyan-900 dark:text-cyan-100">{msg.skill_used}</span>
          </div>
          <span className="hidden sm:inline-flex items-center gap-1 text-[10px] text-slate-400 dark:text-slate-500 font-mono">
            <ShieldCheck size={11} className="text-emerald-500" /> Runbook Enforced
          </span>
        </div>
      )}

      {isHtml ? (
        <div
          className="noc-html-content text-sm leading-relaxed"
          dangerouslySetInnerHTML={{ __html: cleaned }}
        />
      ) : (
        <div className="whitespace-pre-wrap font-mono text-sm text-slate-700 leading-relaxed dark:text-slate-300">
          {msg.content}
        </div>
      )}
      {timeInfo && (
        <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between text-[11px] font-mono text-slate-500 dark:border-slate-800/80">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 dark:bg-emerald-400"></span>
              <span className="text-slate-500 text-[10px] uppercase tracking-wider dark:text-slate-400">Claude NOC Agent</span>
            </div>
            {msg.skill_used && (
              <span
                className="inline-flex items-center gap-1 rounded border border-cyan-500/30 bg-cyan-500/5 px-1.5 py-0.5 text-[9px] font-mono text-cyan-700 dark:border-cyan-500/20 dark:bg-cyan-950/40 dark:text-cyan-300"
                title={`Model call enforced with ${msg.skill_used} skill`}
              >
                <Zap size={9} className="text-cyan-500" />
                <span>skill: {msg.skill_used}</span>
              </span>
            )}
          </div>
          <div
            className="flex items-center gap-1 text-[10px] text-slate-500 hover:text-slate-700 transition-colors dark:text-slate-400 dark:hover:text-slate-300"
            title={timeInfo.full}
          >
            <Clock size={10} className="text-slate-400 dark:text-slate-500" />
            <span>{timeInfo.time}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ClaudeAssistant({ gridId, selectedModel }) {
  // Separate chat histories stored per grid ID
  const [historiesByGrid, setHistoriesByGrid] = useState(() => loadStoredHistories());
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isEvidenceLoading, setIsEvidenceLoading] = useState(true);
  
  // Real evidence state fetched from backend
  const [currentGridEvidence, setCurrentGridEvidence] = useState(null);

  // Multi-Agent Swarm state tracking
  const [subagentsCalled, setSubagentsCalled] = useState(['data_pipeline', 'network_analysis', 'ml_analysis']);
  const [currentlyRunningAgent, setCurrentlyRunningAgent] = useState('supervisor');
  const [specialistReports, setSpecialistReports] = useState({});

  // Active messages for the currently operated grid
  const currentMessages = historiesByGrid[gridId] || getInitialMessageForGrid(gridId);

  // Slash command autocomplete popout state
  const [slashIndex, setSlashIndex] = useState(0);
  const inputRef = useRef(null);
  const chatEndRef = useRef(null);


  const isEnteringSlash = input.startsWith('/');
  const slashQuery = isEnteringSlash ? input.slice(1).toLowerCase().trim() : '';
  const filteredSlashCommands = SLASH_COMMANDS.filter((cmd) => {
    if (!slashQuery) return true;
    return (
      cmd.command.slice(1).toLowerCase().includes(slashQuery) ||
      cmd.description.toLowerCase().includes(slashQuery) ||
      cmd.category.toLowerCase().includes(slashQuery)
    );
  });

  useEffect(() => {
    setSlashIndex(0);
  }, [slashQuery]);

  const selectSlashCommand = (cmd) => {
    let nextValue = cmd.command;
    if (cmd.requiresGrid) {
      nextValue = `${cmd.command} ${gridId || 4365}`;
    }
    setInput(nextValue);
    setTimeout(() => {
      inputRef.current?.focus();
    }, 50);
  };

  const handleKeyDown = (e) => {
    if (isEnteringSlash && filteredSlashCommands.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSlashIndex((prev) => (prev + 1) % filteredSlashCommands.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSlashIndex((prev) => (prev - 1 + filteredSlashCommands.length) % filteredSlashCommands.length);
        return;
      }
      if (e.key === 'Tab') {
        e.preventDefault();
        const selected = filteredSlashCommands[slashIndex] || filteredSlashCommands[0];
        if (selected) selectSlashCommand(selected);
        return;
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        const currentTrimmed = input.trim();
        const exactMatch = filteredSlashCommands.find((c) => c.command === currentTrimmed);
        if (!exactMatch && filteredSlashCommands[slashIndex] && currentTrimmed === `/${slashQuery}`) {
          e.preventDefault();
          selectSlashCommand(filteredSlashCommands[slashIndex]);
          return;
        }
      }
    }
  };


  // Load chat history from backend JSON file for the selected grid
  useEffect(() => {
    let isMounted = true;
    async function loadJsonChatHistory() {
      if (!gridId) return;
      try {
        const res = await api.getChatHistory(gridId);
        if (!isMounted) return;
        if (res && Array.isArray(res.messages) && res.messages.length > 0) {
          setHistoriesByGrid((prev) => {
            const next = { ...prev, [gridId]: res.messages };
            saveStoredHistories(next);
            return next;
          });
        }
      } catch (err) {
        console.warn('Could not load chat history from backend JSON file:', err);
      }
    }
    loadJsonChatHistory();
    return () => { isMounted = false; };
  }, [gridId]);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentMessages, isLoading, gridId]);

  const updateMessagesForGrid = (targetGridId, updater, persistToBackend = false) => {
    setHistoriesByGrid((prev) => {
      const existing = prev[targetGridId] || getInitialMessageForGrid(targetGridId);
      const updated = typeof updater === 'function' ? updater(existing) : updater;
      const next = { ...prev, [targetGridId]: updated };
      saveStoredHistories(next);
      if (persistToBackend) {
        // Persist to backend chat_history.json only when explicitly requested
        api.saveChatHistory(targetGridId, updated).catch((err) => {
          console.warn('Failed to persist chat history to backend JSON:', err);
        });
      }
      return next;
    });
  };

  const handleResetChat = async () => {
    const initial = getInitialMessageForGrid(gridId);
    updateMessagesForGrid(gridId, initial, false);
    try {
      await api.clearChatHistory(gridId);
    } catch (e) {
      console.warn('Failed to clear chat history from backend JSON:', e);
    }
  };

  // Fetch contextual evidence whenever the globally selected grid changes
  useEffect(() => {
    let mounted = true;
    
    async function loadGridContext() {
      if (!gridId) return;
      setIsEvidenceLoading(true);
      
      try {
        // Fetch ML features and predictions from your existing API service
        const [features, prediction] = await Promise.all([
          api.getGridFeatures(gridId),
          api.getGridPrediction(gridId, undefined, selectedModel)
        ]);

        if (!mounted) return;

        // Map the backend API response to the Assistant's context schema
        setCurrentGridEvidence({
          grid_id: gridId,
          timestamp: new Date().toISOString(),
          current_activity: features.avg_activity || 0, 
          baseline_activity: features.avg_activity ? features.avg_activity / (features.peak_ratio || 1) : 0,
          activity_growth: features.activity_growth || 0,
          peak_ratio: features.peak_ratio || 0,
          variability: features.variability || 0,
          internet_share: features.internet_share || 0,
          anomaly_score: prediction.probability || 0,
          direction: prediction.risk_label || 'NORMAL',
          rule_alerts: prediction.risk_label === 'HIGH_ACTIVITY_RISK' ? ['HIGH_ACTIVITY', 'MODEL_FLAG'] : []
        });
      } catch (error) {
        console.error("Failed to load grid context for AI:", error);
      } finally {
        if (mounted) setIsEvidenceLoading(false);
      }
    }

    loadGridContext();
    
    return () => { mounted = false; };
  }, [gridId, selectedModel]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    
    const userMessage = input.trim();
    const userTimestamp = new Date().toISOString();
    setInput('');
    
    const activeGridId = gridId;
    const currentList = historiesByGrid[activeGridId] || getInitialMessageForGrid(activeGridId);
    const newMessages = [...currentList, { role: 'user', content: userMessage, timestamp: userTimestamp }];
    
    updateMessagesForGrid(activeGridId, newMessages);
    setIsLoading(true);

    // Identify candidate specialist subagents for real-time UI animation
    const cleanLower = userMessage.toLowerCase();
    let targetedAgents = ['data_pipeline', 'network_analysis', 'ml_analysis'];
    if (cleanLower.startsWith('/check-pipeline') || cleanLower.startsWith('/network-health')) {
      targetedAgents = ['data_pipeline'];
    } else if (cleanLower.startsWith('/explain-grid')) {
      targetedAgents = ['network_analysis', 'ml_analysis', 'data_pipeline'];
    } else if (cleanLower.startsWith('/review-anomaly')) {
      targetedAgents = ['ml_analysis', 'network_analysis'];
    } else if (cleanLower.startsWith('/test-api')) {
      targetedAgents = ['api_agent'];
    } else if (cleanLower.includes('pipeline') || cleanLower.includes('etl') || cleanLower.includes('ingest') || cleanLower.includes('stale')) {
      targetedAgents = ['data_pipeline'];
    } else if (cleanLower.includes('api') || cleanLower.includes('endpoint') || cleanLower.includes('test')) {
      targetedAgents = ['api_agent'];
    } else if (cleanLower.includes('all') || cleanLower.includes('full') || cleanLower.includes('comprehensive') || cleanLower.includes('system')) {
      targetedAgents = ['data_pipeline', 'network_analysis', 'ml_analysis', 'api_agent'];
    }
    setSubagentsCalled(targetedAgents);
    setCurrentlyRunningAgent('supervisor');

    try {
      const BASE_URL = import.meta.env?.VITE_API_BASE_URL || 'http://localhost:8000';
      const API_KEY = import.meta.env?.VITE_API_KEY || 'development-key';

      const response = await fetch(`${BASE_URL}/chat`, {
        method: 'POST',
        headers: { 
            'Content-Type': 'application/json',
            'X-API-Key': API_KEY
        },
        body: JSON.stringify({
          grid_id: Number(activeGridId),
          message: userMessage,
          chat_history: newMessages.slice(1, -1).map(msg => ({
              role: msg.role === 'assistant' ? 'assistant' : 'user', 
              content: msg.content,
              timestamp: msg.timestamp || undefined,
              skill_used: msg.skill_used || undefined,
              skills_used: msg.skills_used || undefined
          })),
          grid_evidence: currentGridEvidence
        })
      });

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data = await response.json();
      const assistantTimestamp = data.timestamp || new Date().toISOString();
      
      if (data.subagents_called && Array.isArray(data.subagents_called) && data.subagents_called.length > 0) {
        setSubagentsCalled(data.subagents_called);
      }
      if (data.active_agent) {
        setCurrentlyRunningAgent(data.active_agent);
      }
      if (data.specialist_reports) {
        setSpecialistReports(data.specialist_reports);
      }

      updateMessagesForGrid(activeGridId, (prev) => [
        ...prev, 
        { 
          role: 'assistant', 
          content: data.reply, 
          timestamp: assistantTimestamp,
          skill_used: data.skill_used,
          skills_used: data.skills_used || (data.skill_used ? [data.skill_used] : []),
          subagents_called: data.subagents_called,
          specialist_reports: data.specialist_reports
        }
      ]);

    } catch (error) {
      const errorTimestamp = new Date().toISOString();
      updateMessagesForGrid(activeGridId, (prev) => [
        ...prev, 
        { 
          role: 'assistant', 
          timestamp: errorTimestamp,
          content: `<div class="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3.5 text-rose-300 text-xs font-mono">
            <div class="font-bold uppercase tracking-wider mb-1.5 flex items-center gap-1.5 text-rose-400">
              <span>⚠️</span> Communication Error
            </div>
            <div class="text-rose-200">Failed to reach backend NOC agent: ${error.message}</div>
          </div>` 
        }
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-full w-full overflow-hidden font-sans border border-slate-200 rounded-xl shadow-lg bg-white dark:border-slate-800 dark:bg-slate-950 transition-colors duration-150">
      
      {/* LEFT PANEL: Live Grid Evidence Context */}
      <div className="w-[300px] lg:w-[380px] border-r border-slate-200 bg-slate-50/90 p-4 sm:p-5 flex flex-col overflow-y-auto shrink-0 min-h-0 dark:border-slate-800 dark:bg-slate-900/80">
        <div className="flex items-center gap-2 mb-6 border-b border-slate-200 pb-4 shrink-0 dark:border-slate-800">
          <Activity className="text-cyan-600 dark:text-cyan-400" size={20} />
          <h2 className="text-md font-semibold text-slate-900 dark:text-slate-100 tracking-wide">Active NOC Context</h2>
        </div>

        {isEvidenceLoading || !currentGridEvidence ? (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-500 gap-3">
            <Loader2 className="animate-spin text-cyan-600 dark:text-cyan-500" size={24} />
            <p className="text-sm">Syncing grid telemetry...</p>
          </div>
        ) : (
          <div className="space-y-3 animate-in fade-in duration-300">
            {/* 1. COMPACT ACTIVE NOC TELEMETRY HUD */}
            <div className="rounded-lg border border-slate-200 bg-white/90 p-2.5 shadow-sm dark:border-slate-800 dark:bg-slate-950/60 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Map size={13} className="text-cyan-600 dark:text-cyan-400" />
                  <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Cell</span>
                  <span className="font-mono text-sm font-bold text-slate-900 dark:text-slate-100">#{currentGridEvidence.grid_id}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Cpu size={13} className="text-amber-500" />
                  <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">ML Risk</span>
                  <span className={`font-mono text-xs font-bold ${currentGridEvidence.anomaly_score > 0.5 ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                    {(currentGridEvidence.anomaly_score * 100).toFixed(1)}%
                  </span>
                  <span className="text-[9px] font-mono uppercase px-1 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500">
                    {currentGridEvidence.direction.replace('_RISK', '').replace('_', ' ')}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 pt-1.5 border-t border-slate-200 dark:border-slate-800/80 text-[11px] font-mono">
                <div className="bg-slate-50/80 dark:bg-slate-900/60 p-1.5 rounded border border-slate-200/60 dark:border-slate-800">
                  <span className="text-slate-400 block text-[9px] uppercase tracking-wider">Act / Baseline</span>
                  <span className="text-cyan-700 dark:text-cyan-400 font-semibold">{currentGridEvidence.current_activity.toFixed(1)}</span>
                  <span className="text-slate-500"> / {currentGridEvidence.baseline_activity.toFixed(1)}</span>
                </div>
                <div className="bg-slate-50/80 dark:bg-slate-900/60 p-1.5 rounded border border-slate-200/60 dark:border-slate-800">
                  <span className="text-slate-400 block text-[9px] uppercase tracking-wider">Rules Active</span>
                  <span className="text-slate-700 dark:text-slate-300 font-semibold truncate block">
                    {currentGridEvidence.rule_alerts.length > 0 ? currentGridEvidence.rule_alerts.join(', ') : 'None (Nominal)'}
                  </span>
                </div>
              </div>
            </div>

            {/* 2. SPECIALIST MULTI-AGENT SWARM TOPOLOGY & LIVE RUNNER */}
            <SubagentTopology
              subagentsCalled={subagentsCalled}
              currentlyRunningAgent={currentlyRunningAgent}
              isQuerying={isLoading}
              specialistReports={specialistReports}
              activeGridId={gridId}
            />

            <div className="text-[10px] text-slate-500 mt-1 pt-2 border-t border-slate-200 dark:border-slate-800 flex items-start gap-1.5">
              <Server size={12} className="text-cyan-600 dark:text-cyan-500 shrink-0 mt-0.5"/> 
              <p>Specialist telemetry & findings are synchronized with the Supervisor on every query.</p>
            </div>
          </div>
        )}
      </div>

      {/* RIGHT PANEL: Secure Chat Interface */}
      <div className="flex-1 flex flex-col min-w-0 bg-slate-50/40 relative overflow-hidden h-full dark:bg-slate-950">
        <div className="h-14 shrink-0 border-b border-slate-200 bg-white/90 flex items-center px-4 sm:px-6 gap-2 sm:gap-3 dark:border-slate-800 dark:bg-slate-900/50">
           <ShieldCheck className="text-emerald-500 shrink-0" size={18}/>
           <div className="flex items-center gap-2 min-w-0">
             <h1 className="text-sm font-semibold text-slate-900 dark:text-slate-200 tracking-wide truncate">Claude Network Operator</h1>
             <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-[11px] text-cyan-700 dark:text-cyan-300 shrink-0">
               #{gridId}
             </span>
           </div>
           <div className="ml-auto flex items-center gap-2 shrink-0">
             {/* Reset Chat */}
             <button
               type="button"
               onClick={handleResetChat}
               title="Clear chat history for this grid"
               className="flex items-center gap-1 text-[10px] uppercase font-mono text-slate-600 hover:text-rose-600 border border-slate-200 bg-white hover:bg-rose-50 hover:border-rose-200 px-2 py-1 rounded transition-colors dark:border-slate-800 dark:bg-slate-800/40 dark:text-slate-400 dark:hover:text-rose-300 dark:hover:bg-rose-950/30 dark:hover:border-rose-800/50"
             >
               <RotateCcw size={10} />
               <span>Reset Chat</span>
             </button>
           </div>
        </div>

        {/* Chat Log */}
        <div className="flex-1 min-h-0 overflow-y-auto p-4 sm:p-6 space-y-6">
          {currentMessages.map((msg, idx) => (
            <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <MessageBubble msg={msg} />
            </div>
          ))}
          {isLoading && (
            <div className="flex justify-start animate-in fade-in duration-300">
              <div className="bg-white border border-slate-200 rounded-xl px-4 py-3 flex items-center gap-2.5 text-slate-600 text-xs font-mono shadow-sm dark:bg-slate-900 dark:border-slate-800 dark:text-slate-300">
                <Sparkles size={14} className="text-cyan-600 dark:text-cyan-400 animate-spin shrink-0" />
                <span className="font-semibold text-cyan-700 dark:text-cyan-300">Calling model</span>
                <span className="text-slate-300 dark:text-slate-700">·</span>
                <span className="text-slate-500 dark:text-slate-400 text-[11px] animate-pulse">enforcing workspace skills & runbooks…</span>
              </div>
            </div>
          )}
          <div ref={chatEndRef} className="h-2" />
        </div>

        {/* Input Box with Slash Command Popout */}
        <div className="shrink-0 p-3 sm:p-4 bg-white/90 border-t border-slate-200 backdrop-blur-sm dark:bg-slate-900/80 dark:border-slate-800 relative">
          {/* Popout menu when input starts with '/' */}
          {isEnteringSlash && filteredSlashCommands.length > 0 && (
            <div className="absolute bottom-full mb-2 left-3 right-3 sm:left-4 sm:right-4 max-w-4xl mx-auto bg-slate-900/95 border border-cyan-500/40 rounded-xl shadow-2xl backdrop-blur-md overflow-hidden z-30 animate-in fade-in slide-in-from-bottom-2 duration-150">
              <div className="px-3.5 py-2 bg-slate-950/90 border-b border-slate-800 flex items-center justify-between text-[11px] font-mono text-slate-400">
                <div className="flex items-center gap-1.5 text-cyan-400 font-semibold">
                  <Terminal size={12} />
                  <span>PROJECT SLASH COMMANDS</span>
                </div>
                <div className="text-[10px] text-slate-500 hidden sm:block">
                  Use ↑↓ to navigate • Tab to fill • Enter to execute
                </div>
              </div>
              <div className="max-h-64 overflow-y-auto divide-y divide-slate-800/60 p-1">
                {filteredSlashCommands.map((cmd, idx) => {
                  const isSelected = idx === slashIndex;
                  return (
                    <div
                      key={cmd.command}
                      onMouseDown={(e) => {
                        e.preventDefault();
                        selectSlashCommand(cmd);
                      }}
                      onMouseEnter={() => setSlashIndex(idx)}
                      className={`px-3 py-2.5 rounded-lg cursor-pointer transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-1 sm:gap-4 ${
                        isSelected
                          ? 'bg-cyan-950/60 border-l-2 border-cyan-400 pl-2.5 text-slate-100'
                          : 'hover:bg-slate-800/50 text-slate-300'
                      }`}
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <span className="font-mono text-xs font-bold text-cyan-400 shrink-0">
                          {cmd.syntax}
                        </span>
                        <span className="text-xs text-slate-400 truncate">
                          {cmd.description}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0 self-start sm:self-auto">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold border ${cmd.badgeClass}`}>
                          {cmd.category}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <form 
            onSubmit={(e) => { e.preventDefault(); handleSend(); }}
            className="flex gap-3 max-w-4xl mx-auto"
          >
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={`Ask the NOC agent or type / for project slash commands...`}
              className="flex-1 bg-slate-50 border border-slate-300 rounded-lg px-4 py-3 text-slate-900 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 font-mono text-sm shadow-inner transition-all placeholder:text-slate-400 dark:bg-slate-950 dark:border-slate-700 dark:text-slate-200 dark:placeholder:text-slate-600"
              disabled={isLoading || isEvidenceLoading}
            />
            <button
              type="submit"
              disabled={isLoading || isEvidenceLoading || !input.trim()}
              className="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 disabled:hover:bg-cyan-600 text-white rounded-lg px-6 flex items-center justify-center transition-colors shadow-md"
            >
              <Send size={18} className={isLoading ? 'opacity-50' : ''} />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}