import React, { createContext, useContext, useEffect, useState } from 'react';

const THEME_STORAGE_KEY = 'telecom_intelligence_theme';

const ThemeContext = createContext({
  theme: 'dark',
  isDark: true,
  toggleTheme: () => {},
  setTheme: () => {},
  chartTheme: {},
});

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    try {
      const saved = localStorage.getItem(THEME_STORAGE_KEY);
      if (saved === 'light' || saved === 'dark') return saved;
    } catch {
      // fallback
    }
    return 'dark'; // Existing default theme is dark
  });

  const isDark = theme === 'dark';

  useEffect(() => {
    const root = document.documentElement;
    if (isDark) {
      root.classList.add('dark');
      root.classList.remove('light');
      root.setAttribute('data-theme', 'dark');
      root.style.colorScheme = 'dark';
    } else {
      root.classList.remove('dark');
      root.classList.add('light');
      root.setAttribute('data-theme', 'light');
      root.style.colorScheme = 'light';
    }

    try {
      localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch (e) {
      console.warn('Failed to save theme to localStorage:', e);
    }
  }, [theme, isDark]);

  const toggleTheme = () => {
    setThemeState((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  const setTheme = (newTheme) => {
    if (newTheme === 'dark' || newTheme === 'light') {
      setThemeState(newTheme);
    }
  };

  const chartTheme = {
    gridStroke: isDark ? '#1e293b' : '#e2e8f0',
    axisTick: '#64748b',
    axisLine: isDark ? '#1e293b' : '#cbd5e1',
    emptyTrack: isDark ? '#1e293b' : '#e2e8f0',
    baselineStroke: isDark ? '#94a3b8' : '#64748b',
    tooltipContentStyle: isDark
      ? { background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, fontSize: 11, color: '#f8fafc' }
      : { background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 8, fontSize: 11, color: '#0f172a', boxShadow: '0 4px 12px -2px rgba(0,0,0,0.1)' },
    tooltipLabelStyle: { color: isDark ? '#94a3b8' : '#475569' },
  };

  return (
    <ThemeContext.Provider value={{ theme, isDark, toggleTheme, setTheme, chartTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
