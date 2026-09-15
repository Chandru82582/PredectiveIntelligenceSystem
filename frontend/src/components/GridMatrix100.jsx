import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import {
  Activity,
  AlertTriangle,
  ShieldCheck,
  Crosshair,
  Search,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Sliders,
  X,
  ExternalLink,
  MessageSquare,
  Flame,
  Layers,
  Sparkles,
  MapPin,
  TrendingUp,
  Cpu
} from 'lucide-react';
import * as api from '../services/api';
import { useTheme } from '../context/ThemeContext';

const GRID_DIM = 100;
const TOTAL_CELLS = 10000;

// Color helpers
function getCellColor(cell, colorMode, threshold, isDark = true) {
  const p = cell.p || 0;
  const act = cell.activity || 0;
  const isHigh = p >= threshold;
  const deadzoneColor = isDark ? 'rgba(15, 23, 42, 0.6)' : 'rgba(226, 232, 240, 0.7)';

  if (colorMode === 'prediction') {
    if (isHigh) {
      // High activity risk: Rose
      const alpha = isDark ? 0.65 + Math.min(0.35, p * 0.4) : 0.75 + Math.min(0.25, p * 0.3);
      return isDark ? `rgba(244, 63, 94, ${alpha})` : `rgba(225, 29, 72, ${alpha})`;
    }
    if (p >= threshold * 0.5) {
      // Elevated probability: Amber
      return isDark ? 'rgba(245, 158, 11, 0.75)' : 'rgba(217, 119, 6, 0.85)';
    }
    if (act > 0) {
      // Normal activity: Cyan tone with intensity scaling
      const norm = Math.min(1, Math.max(0.15, Math.log10(act + 1) / 3.5));
      return isDark ? `rgba(6, 182, 212, ${norm * 0.8})` : `rgba(2, 132, 199, ${0.3 + norm * 0.65})`;
    }
    // Deadzone / Zero activity
    return deadzoneColor;
  }

  if (colorMode === 'probability') {
    if (p >= threshold) {
      return isDark ? `rgba(244, 63, 94, ${0.7 + p * 0.3})` : `rgba(225, 29, 72, ${0.8 + p * 0.2})`;
    }
    if (p >= 0.4) {
      return isDark ? `rgba(245, 158, 11, ${0.6 + p * 0.4})` : `rgba(217, 119, 6, ${0.7 + p * 0.3})`;
    }
    if (p >= 0.15) {
      return isDark ? `rgba(6, 182, 212, ${0.4 + p * 0.5})` : `rgba(2, 132, 199, ${0.45 + p * 0.5})`;
    }
    if (act > 0) {
      return isDark ? 'rgba(16, 185, 129, 0.35)' : 'rgba(13, 148, 136, 0.45)';
    }
    return deadzoneColor;
  }

  // colorMode === 'activity'
  if (act <= 0) return deadzoneColor;
  const norm = Math.min(1, Math.log10(act + 1) / 4);
  if (norm > 0.8) return isDark ? `rgba(244, 63, 94, ${norm})` : `rgba(225, 29, 72, ${norm})`;
  if (norm > 0.5) return isDark ? `rgba(245, 158, 11, ${norm})` : `rgba(217, 119, 6, ${norm})`;
  return isDark ? `rgba(6, 182, 212, ${norm * 0.9})` : `rgba(2, 132, 199, ${Math.max(0.3, norm * 0.95)})`;
}

export default function GridMatrix100({ selectedGridId, onSelectGrid, onNavigate }) {
  const { isDark } = useTheme();
  const [matrixData, setMatrixData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Settings & Filters
  const [colorMode, setColorMode] = useState('prediction'); // 'prediction' | 'probability' | 'activity'
  const [threshold, setThreshold] = useState(0.7134);
  const [showSectors, setShowSectors] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [searchId, setSearchId] = useState('');

  // Hover & Active selection
  const [hoveredCell, setHoveredCell] = useState(null);
  const [activeCardCell, setActiveCardCell] = useState(null);

  const canvasRef = useRef(null);
  const containerRef = useRef(null);

  // Load 100x100 matrix from backend API
  useEffect(() => {
    let mounted = true;
    async function loadMatrix() {
      setLoading(true);
      try {
        const res = await api.getPredictionMatrix();
        if (!mounted) return;
        setMatrixData(res);
        if (res.threshold) {
          setThreshold(res.threshold);
        }
      } catch (err) {
        if (!mounted) return;
        setError(err.message || 'Failed to load grid matrix');
      } finally {
        if (mounted) setLoading(false);
      }
    }
    loadMatrix();
    return () => { mounted = false; };
  }, []);

  // Quick lookup map: grid_id -> cell object
  const cellMap = useMemo(() => {
    if (!matrixData?.cells) return new Map();
    const map = new Map();
    for (const c of matrixData.cells) {
      map.set(c.grid_id, c);
    }
    return map;
  }, [matrixData]);

  // Keep active card in sync if selectedGridId changes externally
  useEffect(() => {
    if (selectedGridId && cellMap.has(selectedGridId)) {
      setActiveCardCell(cellMap.get(selectedGridId));
    }
  }, [selectedGridId, cellMap]);

  // High-risk statistics based on active threshold
  const stats = useMemo(() => {
    if (!matrixData?.cells) return { highCount: 0, maxProbGrid: null, maxActGrid: null };
    let high = 0;
    let maxP = -1;
    let maxPGid = null;
    let maxA = -1;
    let maxAGid = null;

    for (const c of matrixData.cells) {
      if ((c.p || 0) >= threshold) high++;
      if ((c.p || 0) > maxP) {
        maxP = c.p;
        maxPGid = c.grid_id;
      }
      if ((c.activity || 0) > maxA) {
        maxA = c.activity;
        maxAGid = c.grid_id;
      }
    }
    return { highCount: high, maxProbGrid: maxPGid, maxProb: maxP, maxActGrid: maxAGid, maxAct: maxA };
  }, [matrixData, threshold]);

  // Render Canvas
  const renderCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !matrixData?.cells) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    ctx.clearRect(0, 0, width, height);

    const cellSize = width / GRID_DIM;
    const gap = cellSize > 6 ? 0.6 : 0.2;

    // Draw all 10,000 cells
    for (let i = 0; i < matrixData.cells.length; i++) {
      const cell = matrixData.cells[i];
      const col = cell.col; // 0..99 (West to East)
      // Display North at top: screenY 0 is Row 99
      const screenRow = 99 - cell.row;

      const x = col * cellSize;
      const y = screenRow * cellSize;

      ctx.fillStyle = getCellColor(cell, colorMode, threshold, isDark);
      ctx.fillRect(x, y, cellSize - gap, cellSize - gap);
    }

    // Draw Sector Boundaries if enabled (4x4 quadrants)
    if (showSectors) {
      ctx.strokeStyle = isDark ? 'rgba(51, 65, 85, 0.45)' : 'rgba(148, 163, 184, 0.55)';
      ctx.lineWidth = 1;
      const sectorStep = width / 4;
      for (let s = 1; s < 4; s++) {
        // Vertical sector line
        ctx.beginPath();
        ctx.moveTo(s * sectorStep, 0);
        ctx.lineTo(s * sectorStep, height);
        ctx.stroke();

        // Horizontal sector line
        ctx.beginPath();
        ctx.moveTo(0, s * sectorStep);
        ctx.lineTo(width, s * sectorStep);
        ctx.stroke();
      }
    }

    // Highlight hovered cell & crosshairs
    if (hoveredCell) {
      const hCol = hoveredCell.col;
      const hScreenRow = 99 - hoveredCell.row;

      // Crosshairs
      ctx.fillStyle = isDark ? 'rgba(6, 182, 212, 0.12)' : 'rgba(2, 132, 199, 0.14)';
      ctx.fillRect(hCol * cellSize, 0, cellSize, height);
      ctx.fillRect(0, hScreenRow * cellSize, width, cellSize);

      // Hover cell box
      ctx.strokeStyle = isDark ? '#38bdf8' : '#0284c7';
      ctx.lineWidth = 2;
      ctx.strokeRect(hCol * cellSize - 1, hScreenRow * cellSize - 1, cellSize + 2, cellSize + 2);
    }

    // Highlight active selected cell
    const targetCell = activeCardCell || (selectedGridId ? cellMap.get(selectedGridId) : null);
    if (targetCell) {
      const sCol = targetCell.col;
      const sScreenRow = 99 - targetCell.row;

      ctx.strokeStyle = isDark ? '#f8fafc' : '#0f172a';
      ctx.lineWidth = 2.5;
      ctx.strokeRect(sCol * cellSize - 1.5, sScreenRow * cellSize - 1.5, cellSize + 3, cellSize + 3);

      // Outer glowing ring
      ctx.strokeStyle = targetCell.p >= threshold ? (isDark ? '#f43f5e' : '#e11d48') : (isDark ? '#06b6d4' : '#0284c7');
      ctx.lineWidth = 1.5;
      ctx.strokeRect(sCol * cellSize - 3.5, sScreenRow * cellSize - 3.5, cellSize + 7, cellSize + 7);
    }
  }, [matrixData, colorMode, threshold, showSectors, hoveredCell, activeCardCell, selectedGridId, cellMap, isDark]);

  useEffect(() => {
    renderCanvas();
  }, [renderCanvas]);

  // Mouse interaction on Canvas
  const handleMouseMove = (e) => {
    const canvas = canvasRef.current;
    if (!canvas || !matrixData) return;

    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;

    const clientX = (e.clientX - rect.left) * scaleX;
    const clientY = (e.clientY - rect.top) * scaleY;

    const cellSize = canvas.width / GRID_DIM;
    const col = Math.floor(clientX / cellSize);
    const screenRow = Math.floor(clientY / cellSize);

    if (col >= 0 && col < GRID_DIM && screenRow >= 0 && screenRow < GRID_DIM) {
      const row = 99 - screenRow;
      const gridId = row * GRID_DIM + col + 1;
      const cell = cellMap.get(gridId);
      if (cell) {
        setHoveredCell(cell);
      }
    } else {
      setHoveredCell(null);
    }
  };

  const handleMouseLeave = () => {
    setHoveredCell(null);
  };

  const handleClick = (e) => {
    if (hoveredCell) {
      setActiveCardCell(hoveredCell);
      onSelectGrid?.(hoveredCell.grid_id);
    }
  };

  // Search Jump
  const handleSearch = (e) => {
    e.preventDefault();
    const id = parseInt(searchId.replace(/^[#\s]+/, ''), 10);
    if (id >= 1 && id <= TOTAL_CELLS && cellMap.has(id)) {
      const cell = cellMap.get(id);
      setActiveCardCell(cell);
      onSelectGrid?.(id);
      setSearchId('');
    }
  };

  return (
    <div className="flex flex-col gap-4 font-sans text-slate-200">
      
      {/* TOP CONTROLS & STATS BAR */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white/80 p-3.5 backdrop-blur shadow-sm dark:border-slate-800 dark:bg-slate-900/70 transition-colors duration-150">
        
        {/* Left: View Mode Pills */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-1.5 mr-1">
            <Layers size={13} className="text-cyan-600 dark:text-cyan-400" />
            <span>Coloring:</span>
          </div>

          <button
            type="button"
            onClick={() => setColorMode('prediction')}
            className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
              colorMode === 'prediction'
                ? 'bg-rose-500/15 text-rose-700 border border-rose-500/40 shadow-sm dark:bg-rose-500/20 dark:text-rose-300'
                : 'bg-white text-slate-700 border border-slate-200 hover:text-slate-900 dark:bg-slate-950/60 dark:text-slate-400 dark:border-slate-800 dark:hover:text-slate-200'
            }`}
          >
            Model Prediction (Risk / Normal)
          </button>

          <button
            type="button"
            onClick={() => setColorMode('probability')}
            className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
              colorMode === 'probability'
                ? 'bg-amber-500/15 text-amber-700 border border-amber-500/40 shadow-sm dark:bg-amber-500/20 dark:text-amber-300'
                : 'bg-white text-slate-700 border border-slate-200 hover:text-slate-900 dark:bg-slate-950/60 dark:text-slate-400 dark:border-slate-800 dark:hover:text-slate-200'
            }`}
          >
            Continuous Probability
          </button>

          <button
            type="button"
            onClick={() => setColorMode('activity')}
            className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-all ${
              colorMode === 'activity'
                ? 'bg-cyan-500/15 text-cyan-700 border border-cyan-500/40 shadow-sm dark:bg-cyan-500/20 dark:text-cyan-300'
                : 'bg-white text-slate-700 border border-slate-200 hover:text-slate-900 dark:bg-slate-950/60 dark:text-slate-400 dark:border-slate-800 dark:hover:text-slate-200'
            }`}
          >
            Traffic Volume
          </button>
        </div>

        {/* Right: Quick Search & Sector Toggle */}
        <div className="flex items-center gap-2.5 ml-auto">
          <form onSubmit={handleSearch} className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 dark:border-slate-800 dark:bg-slate-950">
            <Search size={12} className="text-slate-400 dark:text-slate-500" />
            <input
              type="text"
              value={searchId}
              onChange={(e) => setSearchId(e.target.value)}
              placeholder="Jump to cell (1-10000)"
              className="w-36 bg-transparent font-mono text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none dark:text-slate-200 dark:placeholder:text-slate-600"
            />
          </form>

          <button
            type="button"
            onClick={() => setShowSectors(!showSectors)}
            className={`rounded-lg border px-2.5 py-1 text-xs font-mono transition-colors ${
              showSectors
                ? 'border-cyan-500/40 bg-cyan-500/10 text-cyan-700 dark:text-cyan-300'
                : 'border-slate-200 bg-white text-slate-600 hover:text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-500 dark:hover:text-slate-300'
            }`}
            title="Toggle Milan sector quadrants (A1-D4)"
          >
            Sectors {showSectors ? 'ON' : 'OFF'}
          </button>
        </div>
      </div>

      {/* SENSITIVITY & STATS BANNER */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        
        {/* Dynamic Threshold Slider */}
        <div className="rounded-xl border border-slate-200 bg-white/80 p-3 shadow-sm flex flex-col justify-between dark:border-slate-800 dark:bg-slate-900/50">
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="text-slate-600 dark:text-slate-400 flex items-center gap-1.5">
              <Sliders size={12} className="text-amber-500 dark:text-amber-400" /> Sensitivity Threshold
            </span>
            <span className="font-mono font-semibold text-amber-600 dark:text-amber-300">
              {(threshold * 100).toFixed(1)}%
            </span>
          </div>
          <input
            type="range"
            min="0.10"
            max="0.90"
            step="0.01"
            value={threshold}
            onChange={(e) => setThreshold(parseFloat(e.target.value))}
            className="w-full accent-amber-500 cursor-pointer h-1.5 bg-slate-200 dark:bg-slate-800 rounded-lg"
          />
          <div className="flex justify-between text-[10px] font-mono text-slate-500 mt-1">
            <span>Aggressive (10%)</span>
            <span>Model Opt (76.4%)</span>
            <span>Strict (90%)</span>
          </div>
        </div>

        {/* High Risk Count Metric */}
        <div className="rounded-xl border border-slate-200 bg-white/80 p-3 shadow-sm flex items-center gap-3 dark:border-slate-800 dark:bg-slate-900/50">
          <div className={`h-10 w-10 rounded-lg flex items-center justify-center border shrink-0 ${
            stats.highCount > 0 ? 'bg-rose-500/15 border-rose-500/30 text-rose-500 dark:text-rose-400' : 'bg-emerald-500/15 border-emerald-500/30 text-emerald-500 dark:text-emerald-400'
          }`}>
            {stats.highCount > 0 ? <AlertTriangle size={18} /> : <ShieldCheck size={18} />}
          </div>
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">Flagged High-Risk</div>
            <div className="text-xl font-mono font-bold text-slate-900 dark:text-slate-100">
              {stats.highCount.toLocaleString()} <span className="text-xs font-normal text-slate-500 dark:text-slate-400">/ 10,000</span>
            </div>
            <div className="text-[10px] text-slate-500 dark:text-slate-400 truncate">
              {((stats.highCount / TOTAL_CELLS) * 100).toFixed(2)}% of metropolitan lattice
            </div>
          </div>
        </div>

        {/* Highest Anomaly Grid */}
        <div className="rounded-xl border border-slate-200 bg-white/80 p-3 shadow-sm flex items-center gap-3 dark:border-slate-800 dark:bg-slate-900/50">
          <div className="h-10 w-10 rounded-lg bg-amber-500/15 border border-amber-500/30 text-amber-500 dark:text-amber-400 flex items-center justify-center shrink-0">
            <TrendingUp size={18} />
          </div>
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">Top Anomaly Probability</div>
            <div className="text-xl font-mono font-bold text-amber-600 dark:text-amber-300">
              {stats.maxProb ? `${(stats.maxProb * 100).toFixed(1)}%` : '—'}
            </div>
            <div className="text-[10px] text-slate-500 dark:text-slate-400">
              Cell #{stats.maxProbGrid || '—'}
            </div>
          </div>
        </div>

        {/* Lattice Dimension & Ingestion Info */}
        <div className="rounded-xl border border-slate-200 bg-white/80 p-3 shadow-sm flex items-center gap-3 dark:border-slate-800 dark:bg-slate-900/50">
          <div className="h-10 w-10 rounded-lg bg-cyan-500/15 border border-cyan-500/30 text-cyan-600 dark:text-cyan-400 flex items-center justify-center shrink-0">
            <Cpu size={18} />
          </div>
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400 font-semibold">Milan Lattice Grid</div>
            <div className="text-xl font-mono font-bold text-cyan-700 dark:text-cyan-300">100 × 100</div>
            <div className="text-[10px] text-slate-500 dark:text-slate-400 truncate">
              As of {matrixData?.as_of ? new Date(matrixData.as_of).toLocaleDateString() : 'Latest Ingestion'}
            </div>
          </div>
        </div>

      </div>

      {/* MAIN VISUALIZATION AREA: 100x100 GRID + DETAIL CARD */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-5 items-start">
        
        {/* CANVAS CONTAINER (Left/Center) */}
        <div className="xl:col-span-8 flex flex-col items-center justify-center rounded-xl border border-slate-200 bg-white p-4 sm:p-5 relative overflow-hidden shadow-sm dark:border-slate-800 dark:bg-slate-950 transition-colors duration-150">
          
          {/* Compass & Sector orientation indicators */}
          <div className="absolute top-2 left-3 text-[10px] font-mono text-slate-500 dark:text-slate-400 flex items-center gap-1 select-none">
            <span className="text-cyan-600 dark:text-cyan-400 font-bold">N</span> (Row 99) · Milan North Metro
          </div>
          <div className="absolute bottom-2 left-3 text-[10px] font-mono text-slate-500 dark:text-slate-400 flex items-center gap-1 select-none">
            <span className="text-cyan-600 dark:text-cyan-400 font-bold">S</span> (Row 0) · Milan South Metro
          </div>
          <div className="absolute top-2 right-3 text-[10px] font-mono text-slate-500 dark:text-slate-400 select-none">
            East (Col 99) <span className="text-cyan-600 dark:text-cyan-400 font-bold">E</span>
          </div>

          {/* Zoom controls */}
          <div className="absolute top-3 right-3 z-10 flex items-center gap-1 bg-white/95 border border-slate-200 rounded-lg p-1 shadow-md dark:bg-slate-900/90 dark:border-slate-800">
            <button
              type="button"
              onClick={() => setZoom((z) => Math.min(2.5, z + 0.25))}
              className="p-1 hover:text-cyan-600 text-slate-500 transition-colors dark:hover:text-cyan-300 dark:text-slate-400"
              title="Zoom in"
            >
              <ZoomIn size={14} />
            </button>
            <span className="font-mono text-[10px] px-1 text-slate-700 dark:text-slate-300">{zoom.toFixed(1)}x</span>
            <button
              type="button"
              onClick={() => setZoom((z) => Math.max(1, z - 0.25))}
              className="p-1 hover:text-cyan-600 text-slate-500 transition-colors dark:hover:text-cyan-300 dark:text-slate-400"
              title="Zoom out"
            >
              <ZoomOut size={14} />
            </button>
            <button
              type="button"
              onClick={() => setZoom(1)}
              className="p-1 hover:text-amber-600 text-slate-500 transition-colors border-l border-slate-200 pl-1.5 dark:border-slate-800 dark:text-slate-400 dark:hover:text-amber-300"
              title="Reset Zoom"
            >
              <RotateCcw size={12} />
            </button>
          </div>

          {/* Interactive HTML5 Canvas */}
          <div
            ref={containerRef}
            className="relative overflow-auto max-w-full flex items-center justify-center my-4 cursor-crosshair select-none"
            style={{ maxHeight: '720px' }}
          >
            {loading ? (
              <div className="h-[640px] w-[640px] flex flex-col items-center justify-center text-slate-500 gap-3 border border-slate-200 rounded-lg bg-slate-50 dark:border-slate-800/80 dark:bg-slate-900/40">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-500 border-t-transparent"></div>
                <p className="font-mono text-xs text-cyan-600 dark:text-cyan-400">Loading 10,000 Cell Predictive Lattice…</p>
              </div>
            ) : (
              <canvas
                ref={canvasRef}
                width={700 * zoom}
                height={700 * zoom}
                onMouseMove={handleMouseMove}
                onMouseLeave={handleMouseLeave}
                onClick={handleClick}
                className="rounded border border-slate-200 dark:border-slate-800/90 shadow-md dark:shadow-2xl transition-all"
                style={{
                  width: `${640 * zoom}px`,
                  height: `${640 * zoom}px`,
                  imageRendering: 'pixelated',
                }}
              />
            )}
          </div>

          {/* Bottom Legend */}
          <div className="flex flex-wrap items-center justify-between w-full border-t border-slate-200 pt-3 px-2 text-xs dark:border-slate-800/80">
            <div className="flex flex-wrap items-center gap-4 text-[11px] text-slate-600 dark:text-slate-400 font-mono">
              <div className="flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-sm bg-rose-500 border border-rose-400/50"></span>
                <span>High-Activity Risk ({'>='}{(threshold * 100).toFixed(0)}%)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-sm bg-amber-500 border border-amber-400/50"></span>
                <span>Elevated Risk</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-sm bg-cyan-500 border border-cyan-400/50"></span>
                <span>Normal Activity</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-sm bg-slate-200 border border-slate-300 dark:bg-slate-900 dark:border-slate-700"></span>
                <span>Zero / Minimal Traffic</span>
              </div>
            </div>

            {hoveredCell && (
              <div className="font-mono text-[11px] text-cyan-700 bg-cyan-50 border border-cyan-200 dark:text-cyan-300 dark:bg-cyan-950/60 dark:border-cyan-800/50 px-2.5 py-0.5 rounded shadow-sm">
                Hovering: #{hoveredCell.grid_id} · Row {hoveredCell.row}, Col {hoveredCell.col} · Act: {hoveredCell.activity} · Prob: {((hoveredCell.p || 0) * 100).toFixed(1)}%
              </div>
            )}
          </div>

        </div>

        {/* RIGHT: INTERACTIVE GRID DETAIL CARD */}
        <div className="xl:col-span-4 flex flex-col gap-4">
          {activeCardCell ? (
            <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-lg animate-in fade-in duration-200 dark:border-slate-800 dark:bg-slate-900/90">
              
              {/* Card Header */}
              <div className="flex items-start justify-between border-b border-slate-200 pb-3.5 mb-4 dark:border-slate-800">
                <div>
                  <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
                    <MapPin size={12} className="text-cyan-600 dark:text-cyan-400" />
                    <span>Selected Cell</span>
                  </div>
                  <div className="text-2xl font-mono font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2 mt-0.5">
                    <span>#{activeCardCell.grid_id}</span>
                    <span className="text-xs font-sans font-normal px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700">
                      {activeCardCell.sector || `Sector ${Math.floor(activeCardCell.row/25)}${Math.floor(activeCardCell.col/25)}`}
                    </span>
                  </div>
                  <div className="text-[11px] font-mono text-slate-500 dark:text-slate-400 mt-1">
                    {activeCardCell.lat ? `${activeCardCell.lat.toFixed(4)}°N, ${activeCardCell.lon.toFixed(4)}°E` : `Row ${activeCardCell.row}, Col ${activeCardCell.col}`}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setActiveCardCell(null)}
                  className="rounded-lg p-1 text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:text-slate-500 dark:hover:text-slate-300 dark:hover:bg-slate-800 transition-colors"
                  title="Close Card"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Machine Learning Prediction Status */}
              <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-4 mb-4 dark:border-slate-800 dark:bg-slate-950/70">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">Model Forecast:</span>
                  {activeCardCell.p >= threshold ? (
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-rose-500/40 bg-rose-500/15 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300 flex items-center gap-1">
                      <AlertTriangle size={11} /> HIGH_ACTIVITY_RISK
                    </span>
                  ) : (
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-emerald-500/40 bg-emerald-500/15 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300 flex items-center gap-1">
                      <ShieldCheck size={11} /> NORMAL
                    </span>
                  )}
                </div>

                {/* Probability Gauge Bar */}
                <div className="mt-3">
                  <div className="flex justify-between text-xs font-mono mb-1">
                    <span className="text-slate-600 dark:text-slate-400">Risk Probability:</span>
                    <span className={`font-bold ${activeCardCell.p >= threshold ? 'text-rose-600 dark:text-rose-400' : 'text-cyan-700 dark:text-cyan-300'}`}>
                      {((activeCardCell.p || 0) * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="relative h-2 w-full bg-slate-200 dark:bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        activeCardCell.p >= threshold ? 'bg-rose-500' : 'bg-cyan-500'
                      }`}
                      style={{ width: `${Math.min(100, Math.max(2, (activeCardCell.p || 0) * 100))}%` }}
                    />
                    <div
                      className="absolute inset-y-0 w-0.5 bg-amber-500 dark:bg-amber-400/90 z-10"
                      style={{ left: `${threshold * 100}%` }}
                      title={`Model Threshold: ${(threshold * 100).toFixed(1)}%`}
                    />
                  </div>
                  <div className="flex justify-between text-[10px] font-mono text-slate-500 mt-1">
                    <span>0%</span>
                    <span className="text-amber-600 dark:text-amber-400/80">Threshold {(threshold * 100).toFixed(1)}%</span>
                    <span>100%</span>
                  </div>
                </div>

                <div className="mt-3 pt-2.5 border-t border-slate-200 dark:border-slate-800 text-[11px] leading-relaxed">
                  {activeCardCell.p >= threshold ? (
                    <p className="text-rose-700 dark:text-rose-200">
                      ⚠️ Probability exceeds decision threshold. Cell is forecasted to undergo a surge exceeding 1.5× baseline during the next operational window.
                    </p>
                  ) : (
                    <p className="text-slate-600 dark:text-slate-400">
                      ✓ Cell activity is within baseline statistical tolerances. No immediate congestion or surge risks flagged by the classifier.
                    </p>
                  )}
                </div>
              </div>

              {/* Telemetry Snapshot Cards */}
              <div className="grid grid-cols-2 gap-2.5 mb-5">
                <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-2.5 dark:border-slate-800 dark:bg-slate-950/60">
                  <div className="text-[10px] font-mono uppercase text-slate-500 dark:text-slate-400">Current Activity</div>
                  <div className="text-base font-mono font-semibold text-cyan-700 dark:text-cyan-300 mt-0.5">
                    {activeCardCell.activity?.toFixed(1) || '0.0'} <span className="text-[10px] text-slate-500 font-normal">ops/hr</span>
                  </div>
                </div>

                <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-2.5 dark:border-slate-800 dark:bg-slate-950/60">
                  <div className="text-[10px] font-mono uppercase text-slate-500 dark:text-slate-400">24h Baseline</div>
                  <div className="text-base font-mono font-semibold text-slate-700 dark:text-slate-300 mt-0.5">
                    {activeCardCell.baseline?.toFixed(1) || '0.0'} <span className="text-[10px] text-slate-500 font-normal">ops/hr</span>
                  </div>
                </div>

                <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-2.5 dark:border-slate-800 dark:bg-slate-950/60">
                  <div className="text-[10px] font-mono uppercase text-slate-500 dark:text-slate-400">Activity Growth</div>
                  <div className="text-base font-mono font-semibold text-amber-700 dark:text-amber-300 mt-0.5">
                    {activeCardCell.growth ? `${activeCardCell.growth.toFixed(2)}x` : '1.00x'}
                  </div>
                </div>

                <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-2.5 dark:border-slate-800 dark:bg-slate-950/60">
                  <div className="text-[10px] font-mono uppercase text-slate-500 dark:text-slate-400">Peak Ratio</div>
                  <div className="text-base font-mono font-semibold text-slate-700 dark:text-slate-300 mt-0.5">
                    {activeCardCell.peak_ratio ? `${activeCardCell.peak_ratio.toFixed(2)}x` : '1.00x'}
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex flex-col gap-2">
                <button
                  type="button"
                  onClick={() => onNavigate?.(activeCardCell.grid_id, 'investigator')}
                  className="w-full flex items-center justify-center gap-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold py-2.5 transition-colors shadow-sm"
                >
                  <ExternalLink size={14} />
                  <span>Investigate Cell #{activeCardCell.grid_id} in Deep-Dive</span>
                </button>

                <button
                  type="button"
                  onClick={() => onNavigate?.(activeCardCell.grid_id, 'assistant')}
                  className="w-full flex items-center justify-center gap-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-800 border border-slate-200 text-xs font-semibold py-2 transition-colors dark:bg-slate-800 dark:hover:bg-slate-700 dark:text-slate-200 dark:border-slate-700"
                >
                  <MessageSquare size={14} className="text-cyan-600 dark:text-cyan-400" />
                  <span>Ask Claude NOC Agent About Cell #{activeCardCell.grid_id}</span>
                </button>
              </div>

            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-slate-300 bg-white/70 p-6 flex flex-col items-center justify-center text-center text-slate-500 h-[360px] dark:border-slate-800 dark:bg-slate-900/40">
              <Crosshair size={32} className="text-slate-400 dark:text-slate-600 mb-3" />
              <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-300 mb-1">Click Any Cell to Inspect</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 max-w-[240px] leading-relaxed">
                Click on any of the 10,000 grid squares to inspect telemetry, ML predictions, growth dynamics, and launch triage.
              </p>
            </div>
          )}

          {/* Tips / Info Box */}
          <div className="rounded-xl border border-slate-200 bg-white/80 p-4 text-xs font-sans text-slate-600 space-y-2 dark:border-slate-800/80 dark:bg-slate-950/60 dark:text-slate-400">
            <div className="font-semibold text-slate-800 dark:text-slate-300 flex items-center gap-1.5 text-xs">
              <Sparkles size={13} className="text-cyan-600 dark:text-cyan-400" />
              <span>100×100 Lattice Architecture</span>
            </div>
            <p className="text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
              Each grid cell covers ~235m × 235m across the Milan metro area. The LightGBM classifier scores all 10,000 cells to forecast activity spikes exceeding 1.5× within-day baselines in the upcoming hour.
            </p>
          </div>

        </div>

      </div>

    </div>
  );
}
