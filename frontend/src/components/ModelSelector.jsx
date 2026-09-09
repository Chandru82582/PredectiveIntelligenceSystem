import React from 'react';
import { Cpu, ChevronDown } from 'lucide-react';

export default function ModelSelector({
  models = [],
  selectedModel = '',
  onSelectModel,
  compact = false,
  className = '',
}) {
  if (!models || models.length === 0) {
    return null;
  }

  const formatModelLabel = (name) => {
    if (!name) return 'Select Model';
    if (name.includes('v2')) return `${name} (v2 - optimized)`;
    if (name.includes('v1')) return `${name} (v1 - legacy)`;
    return name;
  };

  return (
    <div
      className={`relative inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white/90 px-2.5 py-1.5 shadow-sm transition-all duration-150 hover:border-cyan-500/40 dark:border-slate-800 dark:bg-slate-900/80 dark:hover:border-cyan-500/50 ${
        compact ? 'py-1 px-2 text-[11px]' : 'text-xs'
      } ${className}`}
      title="Select ML inference model from /ml/models"
    >
      <div className="flex items-center gap-1.5 text-cyan-600 dark:text-cyan-400">
        <Cpu size={compact ? 13 : 14} className="shrink-0 animate-pulse" />
        <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Model:
        </span>
      </div>

      <div className="relative flex items-center">
        <select
          value={selectedModel}
          onChange={(e) => onSelectModel && onSelectModel(e.target.value)}
          className="cursor-pointer appearance-none bg-transparent pr-5 font-mono text-[11px] font-medium text-slate-800 focus:outline-none dark:text-slate-200"
          aria-label="Select ML Model"
        >
          {models.map((model) => (
            <option
              key={model}
              value={model}
              className="bg-white py-1 font-mono text-xs text-slate-900 dark:bg-slate-900 dark:text-slate-100"
            >
              {formatModelLabel(model)}
            </option>
          ))}
        </select>
        <ChevronDown
          size={12}
          className="pointer-events-none absolute right-0 text-slate-400 transition-transform group-hover:text-cyan-400 dark:text-slate-500"
        />
      </div>
    </div>
  );
}
