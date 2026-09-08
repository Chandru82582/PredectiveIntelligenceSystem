import React, { useState, useRef, useEffect } from 'react';
import { Send, Activity, AlertTriangle, ShieldCheck, Map, Cpu, Server, Loader2, RotateCcw, Clock } from 'lucide-react';
import * as api from '../services/api';

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
  <div class="flex items-center gap-2 border-b border-slate-800 pb-2.5">
    <span class="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
    <span class="text-xs font-semibold uppercase tracking-wider text-emerald-400 font-mono">NOC Assistant — Cell #${id}</span>
    <span class="text-[11px] text-slate-500 font-mono ml-auto">Active Session</span>
  </div>
  <p class="text-xs text-slate-300 leading-relaxed">
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
      <div className="max-w-[80%] rounded-xl px-4 py-3 bg-cyan-950/40 border border-cyan-800/40 text-cyan-100 font-mono text-sm leading-relaxed shadow-sm flex flex-col">
        <div className="whitespace-pre-wrap">{msg.content}</div>
        {timeInfo && (
          <div
            className="mt-1.5 flex items-center justify-end gap-1 text-[10px] font-mono text-cyan-300/60 select-none self-end"
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
    <div className="w-full max-w-[95%] rounded-xl p-4 bg-slate-900/90 border border-slate-800 text-slate-200 shadow-md flex flex-col">
      {isHtml ? (
        <div
          className="noc-html-content text-sm leading-relaxed"
          dangerouslySetInnerHTML={{ __html: cleaned }}
        />
      ) : (
        <div className="whitespace-pre-wrap font-mono text-sm text-slate-300 leading-relaxed">
          {msg.content}
        </div>
      )}
      {timeInfo && (
        <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[11px] font-mono text-slate-500">
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
            <span className="text-slate-400 text-[10px] uppercase tracking-wider">Claude NOC Agent</span>
          </div>
          <div
            className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-slate-300 transition-colors"
            title={timeInfo.full}
          >
            <Clock size={10} className="text-slate-500" />
            <span>{timeInfo.time}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ClaudeAssistant({ gridId }) {
  // Separate chat histories stored per grid ID
  const [historiesByGrid, setHistoriesByGrid] = useState(() => loadStoredHistories());
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isEvidenceLoading, setIsEvidenceLoading] = useState(true);
  
  // Real evidence state fetched from backend
  const [currentGridEvidence, setCurrentGridEvidence] = useState(null);

  const chatEndRef = useRef(null);

  // Active messages for the currently operated grid
  const currentMessages = historiesByGrid[gridId] || getInitialMessageForGrid(gridId);

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

  const updateMessagesForGrid = (targetGridId, updater) => {
    setHistoriesByGrid((prev) => {
      const existing = prev[targetGridId] || getInitialMessageForGrid(targetGridId);
      const updated = typeof updater === 'function' ? updater(existing) : updater;
      const next = { ...prev, [targetGridId]: updated };
      saveStoredHistories(next);
      // Persist to backend chat_history.json
      api.saveChatHistory(targetGridId, updated).catch((err) => {
        console.warn('Failed to persist chat history to backend JSON:', err);
      });
      return next;
    });
  };

  const handleResetChat = async () => {
    const initial = getInitialMessageForGrid(gridId);
    updateMessagesForGrid(gridId, initial);
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
          api.getGridPrediction(gridId)
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
  }, [gridId]);

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
              timestamp: msg.timestamp || undefined
          })),
          grid_evidence: currentGridEvidence
        })
      });

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data = await response.json();
      const assistantTimestamp = data.timestamp || new Date().toISOString();
      
      updateMessagesForGrid(activeGridId, (prev) => [
        ...prev, 
        { role: 'assistant', content: data.reply, timestamp: assistantTimestamp }
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
    <div className="flex h-full w-full overflow-hidden font-sans border border-slate-800 rounded-xl shadow-2xl bg-slate-950">
      
      {/* LEFT PANEL: Live Grid Evidence Context */}
      <div className="w-[300px] lg:w-[380px] border-r border-slate-800 bg-slate-900/80 p-4 sm:p-5 flex flex-col overflow-y-auto shrink-0 min-h-0">
        <div className="flex items-center gap-2 mb-6 border-b border-slate-800 pb-4 shrink-0">
          <Activity className="text-cyan-400" size={20} />
          <h2 className="text-md font-semibold text-slate-100 tracking-wide">Active NOC Context</h2>
        </div>

        {isEvidenceLoading || !currentGridEvidence ? (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-500 gap-3">
            <Loader2 className="animate-spin text-cyan-500" size={24} />
            <p className="text-sm">Syncing grid telemetry...</p>
          </div>
        ) : (
          <div className="space-y-4 animate-in fade-in duration-300">
            <div className="bg-slate-950/50 p-4 rounded-lg border border-slate-800 shadow-inner">
               <div className="text-xs font-semibold text-slate-500 tracking-wider uppercase mb-1 flex items-center gap-2">
                 <Map size={14}/> Target Cell
               </div>
               <div className="text-2xl font-mono text-slate-100">#{currentGridEvidence.grid_id}</div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="bg-slate-950/50 p-4 rounded-lg border border-slate-800 shadow-inner">
                  <div className="text-xs font-semibold text-slate-500 tracking-wider uppercase mb-1">Current Act.</div>
                  <div className="text-lg font-mono text-cyan-400">
                    {currentGridEvidence.current_activity.toFixed(1)}
                  </div>
              </div>
              <div className="bg-slate-950/50 p-4 rounded-lg border border-slate-800 shadow-inner">
                  <div className="text-xs font-semibold text-slate-500 tracking-wider uppercase mb-1">Baseline</div>
                  <div className="text-lg font-mono text-slate-400">
                    {currentGridEvidence.baseline_activity.toFixed(1)}
                  </div>
              </div>
            </div>

            <div className="bg-slate-950/50 p-4 rounded-lg border border-slate-800 shadow-inner">
               <div className="text-xs font-semibold text-slate-500 tracking-wider uppercase mb-2 flex items-center gap-2">
                 <Cpu size={14}/> ML Prediction Score
               </div>
               <div className="flex items-end gap-3">
                  <div className={`text-3xl font-mono ${currentGridEvidence.anomaly_score > 0.5 ? 'text-amber-500' : 'text-emerald-400'}`}>
                    {(currentGridEvidence.anomaly_score * 100).toFixed(1)}%
                  </div>
                  <div className="text-xs font-semibold text-slate-400 mb-1.5 uppercase tracking-wider">
                    {currentGridEvidence.direction.replace('_', ' ')}
                  </div>
               </div>
            </div>

            <div className="bg-slate-950/50 p-4 rounded-lg border border-slate-800 shadow-inner">
               <div className="text-xs font-semibold text-slate-500 tracking-wider uppercase mb-2 flex items-center gap-2">
                 <AlertTriangle size={14}/> Active Rules
               </div>
               <div className="flex flex-wrap gap-2">
                  {currentGridEvidence.rule_alerts.length === 0 && (
                    <span className="text-sm font-mono text-slate-600">None</span>
                  )}
                  {currentGridEvidence.rule_alerts.map(rule => (
                    <span key={rule} className="px-2 py-1 bg-amber-500/10 text-amber-400 text-[11px] font-semibold rounded border border-amber-500/20 font-mono">
                      {rule}
                    </span>
                  ))}
               </div>
            </div>
            
            <div className="text-[11px] text-slate-500 mt-6 pt-4 border-t border-slate-800 flex items-start gap-2">
              <Server size={14} className="text-cyan-500 shrink-0 mt-0.5"/> 
              <p>This telemetry is automatically injected into the Agent's context window on every request.</p>
            </div>
          </div>
        )}
      </div>

      {/* RIGHT PANEL: Secure Chat Interface */}
      <div className="flex-1 flex flex-col min-w-0 bg-slate-950 relative overflow-hidden h-full">
        <div className="h-14 shrink-0 border-b border-slate-800 flex items-center px-4 sm:px-6 bg-slate-900/50 gap-2 sm:gap-3">
           <ShieldCheck className="text-emerald-500 shrink-0" size={18}/>
           <div className="flex items-center gap-2 min-w-0">
             <h1 className="text-sm font-semibold text-slate-200 tracking-wide truncate">Claude Network Operator</h1>
             <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-[11px] text-cyan-300 shrink-0">
               #{gridId}
             </span>
           </div>
           <div className="ml-auto flex items-center gap-2 shrink-0">
             {/* Reset Chat */}
             <button
               type="button"
               onClick={handleResetChat}
               title="Clear chat history for this grid"
               className="flex items-center gap-1 text-[10px] uppercase font-mono text-slate-400 hover:text-rose-300 border border-slate-800 bg-slate-800/40 hover:bg-rose-950/30 hover:border-rose-800/50 px-2 py-1 rounded transition-colors"
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
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 flex gap-2 items-center text-slate-500 text-sm font-mono shadow-sm">
                <span className="animate-pulse text-cyan-500">Evaluating</span>
                <span className="animate-pulse delay-75">.</span>
                <span className="animate-pulse delay-150">.</span>
                <span className="animate-pulse delay-300">.</span>
              </div>
            </div>
          )}
          <div ref={chatEndRef} className="h-2" />
        </div>

        {/* Input Box */}
        <div className="shrink-0 p-3 sm:p-4 bg-slate-900/80 border-t border-slate-800 backdrop-blur-sm">
          <form 
            onSubmit={(e) => { e.preventDefault(); handleSend(); }}
            className="flex gap-3 max-w-4xl mx-auto"
          >
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder={`Ask the NOC agent to analyze grid #${gridId}...`}
              className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-4 py-3 text-slate-200 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 font-mono text-sm shadow-inner transition-all placeholder:text-slate-600"
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