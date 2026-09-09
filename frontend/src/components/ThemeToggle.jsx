import React from 'react';
import { Sun, Moon } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

export default function ThemeToggle({ className = '' }) {
  const { isDark, toggleTheme } = useTheme();

  return (
    <button
      type="button"
      onClick={toggleTheme}
      title={isDark ? 'Switch to Light theme' : 'Switch to Dark theme'}
      aria-label={isDark ? 'Switch to Light theme' : 'Switch to Dark theme'}
      className={`relative inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-all duration-200 focus:outline-none focus:ring-1 focus:ring-cyan-500 ${
        isDark
          ? 'border-slate-800 bg-slate-900/80 text-slate-300 hover:border-slate-700 hover:bg-slate-800 hover:text-amber-300'
          : 'border-slate-200 bg-white/90 text-slate-700 hover:border-slate-300 hover:bg-slate-100 hover:text-indigo-600 shadow-sm'
      } ${className}`}
    >
      <span className="relative flex h-4 w-4 items-center justify-center">
        {isDark ? (
          <Sun size={14} className="text-amber-400 transition-transform duration-200 hover:rotate-45" />
        ) : (
          <Moon size={14} className="text-indigo-600 transition-transform duration-200 hover:-rotate-12" />
        )}
      </span>
      <span className="font-mono text-[11px] tracking-wide">
        {isDark ? 'Dark' : 'Light'}
      </span>
    </button>
  );
}
