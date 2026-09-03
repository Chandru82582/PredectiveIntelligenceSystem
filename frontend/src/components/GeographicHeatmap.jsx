import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { ZoomIn, ZoomOut, Locate, Flame } from 'lucide-react';

const LAT_MIN = 45.40, LAT_MAX = 45.54;
const LON_MIN = 9.10, LON_MAX = 9.30;

const SEVERITY_COLOR = {
  HIGH: '#f43f5e',
  MEDIUM: '#f59e0b',
  NORMAL: '#06b6d4',
  DEADZONE: '#1e293b',
};

function classify(activity, p75, p45) {
  if (activity <= 0) return 'DEADZONE';
  if (activity > p75) return 'HIGH';
  if (activity > p45) return 'MEDIUM';
  return 'NORMAL';
}

function heatStops(intensity) {
  if (intensity > 0.75) {
    return [
      [0, 'rgba(244, 63, 94, 0.95)'],
      [0.35, 'rgba(245, 158, 11, 0.75)'],
      [0.7, 'rgba(6, 182, 212, 0.40)'],
      [1, 'rgba(6, 182, 212, 0)'],
    ];
  }
  if (intensity > 0.45) {
    return [
      [0, 'rgba(245, 158, 11, 0.90)'],
      [0.5, 'rgba(6, 182, 212, 0.60)'],
      [1, 'rgba(6, 182, 212, 0)'],
    ];
  }
  return [
    [0, 'rgba(6, 182, 212, 0.85)'],
    [0.5, 'rgba(16, 185, 129, 0.40)'],
    [1, 'rgba(16, 185, 129, 0)'],
  ];
}

export default function GeographicHeatmap({ cells, selectedGridId, onSelectGrid }) {
  const canvasRef = useRef(null);
  const wrapRef = useRef(null);
  const [dims, setDims] = useState({ w: 800, h: 500 });
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(null);
  const [intensity, setIntensity] = useState(0.75);
  const [radius, setRadius] = useState(48);
  const [severityFilter, setSeverityFilter] = useState('ALL');
  const [hover, setHover] = useState(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setDims({ w: width, h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const enriched = useMemo(() => {
    if (!cells || cells.length === 0) return [];
    const vals = cells.map((c) => c.total_activity).sort((a, b) => a - b);
    const p75 = vals[Math.floor(vals.length * 0.75)] ?? 0;
    const p45 = vals[Math.floor(vals.length * 0.45)] ?? 0;
    const max = vals[vals.length - 1] || 1;
    return cells.map((c) => ({
      ...c,
      severity: classify(c.total_activity, p75, p45),
      norm: c.total_activity / max,
    }));
  }, [cells]);

  const project = useCallback(
    (lat, lon) => {
      const x = ((lon - LON_MIN) / (LON_MAX - LON_MIN)) * dims.w;
      const y = (1 - (lat - LAT_MIN) / (LAT_MAX - LAT_MIN)) * dims.h;
      return {
        x: x * zoom + pan.x,
        y: y * zoom + pan.y,
      };
    },
    [dims, zoom, pan]
  );

  const visibleCells = useMemo(
    () => (severityFilter === 'ALL' ? enriched : enriched.filter((c) => c.severity === severityFilter)),
    [enriched, severityFilter]
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = dims.w * dpr;
    canvas.height = dims.h * dpr;
    canvas.style.width = `${dims.w}px`;
    canvas.style.height = `${dims.h}px`;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, dims.w, dims.h);
    ctx.fillStyle = '#020617';
    ctx.fillRect(0, 0, dims.w, dims.h);

    // subtle lat/lon graticule
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.08)';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 10; i++) {
      const lat = LAT_MIN + (i / 10) * (LAT_MAX - LAT_MIN);
      const p0 = project(lat, LON_MIN);
      const p1 = project(lat, LON_MAX);
      ctx.beginPath();
      ctx.moveTo(p0.x, p0.y);
      ctx.lineTo(p1.x, p1.y);
      ctx.stroke();
      const lon = LON_MIN + (i / 10) * (LON_MAX - LON_MIN);
      const q0 = project(LAT_MIN, lon);
      const q1 = project(LAT_MAX, lon);
      ctx.beginPath();
      ctx.moveTo(q0.x, q0.y);
      ctx.lineTo(q1.x, q1.y);
      ctx.stroke();
    }

    // thermal layer, screen-blended
    ctx.globalCompositeOperation = 'screen';
    visibleCells.forEach((c) => {
      const { x, y } = project(c.latitude, c.longitude);
      const r = radius * (0.5 + c.norm * 0.5) * Math.max(zoom, 0.6);
      const grad = ctx.createRadialGradient(x, y, 0, x, y, r);
      heatStops(c.norm).forEach(([stop, color]) => grad.addColorStop(stop, color));
      ctx.globalAlpha = intensity;
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'source-over';

    // cell markers
    visibleCells.forEach((c) => {
      const { x, y } = project(c.latitude, c.longitude);
      const isSelected = c.grid_id === selectedGridId;
      ctx.beginPath();
      ctx.arc(x, y, isSelected ? 5.5 : 3, 0, Math.PI * 2);
      ctx.fillStyle = SEVERITY_COLOR[c.severity];
      ctx.fill();
      if (isSelected) {
        ctx.strokeStyle = '#f8fafc';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
    });
  }, [dims, project, visibleCells, intensity, radius, selectedGridId, zoom]);

  function hitTest(px, py) {
    let closest = null;
    let closestDist = 14;
    visibleCells.forEach((c) => {
      const { x, y } = project(c.latitude, c.longitude);
      const d = Math.hypot(x - px, y - py);
      if (d < closestDist) {
        closestDist = d;
        closest = c;
      }
    });
    return closest;
  }

  function handleMouseDown(e) {
    setDragging({ startX: e.clientX, startY: e.clientY, panX: pan.x, panY: pan.y, moved: false });
  }
  function handleMouseMove(e) {
    const rect = canvasRef.current.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    if (dragging) {
      const dx = e.clientX - dragging.startX;
      const dy = e.clientY - dragging.startY;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) dragging.moved = true;
      setPan({ x: dragging.panX + dx, y: dragging.panY + dy });
      setHover(null);
    } else {
      const hit = hitTest(px, py);
      setHover(hit ? { ...hit, screenX: px, screenY: py } : null);
    }
  }
  function handleMouseUp(e) {
    if (dragging && !dragging.moved) {
      const rect = canvasRef.current.getBoundingClientRect();
      const hit = hitTest(e.clientX - rect.left, e.clientY - rect.top);
      if (hit) onSelectGrid?.(hit.grid_id);
    }
    setDragging(null);
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1.5">
          {['ALL', 'HIGH', 'MEDIUM', 'NORMAL'].map((s) => (
            <button
              key={s}
              onClick={() => setSeverityFilter(s)}
              className={`rounded px-2.5 py-1 text-[11px] font-medium tracking-wide transition-colors ${
                severityFilter === s
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                  : 'bg-slate-800/60 text-slate-400 border border-slate-800 hover:text-slate-200'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          <button onClick={() => setZoom((z) => Math.min(z + 0.3, 3))} className="rounded border border-slate-800 bg-slate-800/60 p-1.5 text-slate-300 hover:text-cyan-300">
            <ZoomIn size={14} />
          </button>
          <button onClick={() => setZoom((z) => Math.max(z - 0.3, 0.5))} className="rounded border border-slate-800 bg-slate-800/60 p-1.5 text-slate-300 hover:text-cyan-300">
            <ZoomOut size={14} />
          </button>
          <button
            onClick={() => {
              setZoom(1);
              setPan({ x: 0, y: 0 });
            }}
            className="rounded border border-slate-800 bg-slate-800/60 p-1.5 text-slate-300 hover:text-cyan-300"
          >
            <Locate size={14} />
          </button>
        </div>
      </div>

      <div
        ref={wrapRef}
        className="relative h-[420px] w-full overflow-hidden rounded-lg border border-slate-800 bg-slate-950"
      >
        <canvas
          ref={canvasRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={() => {
            setDragging(null);
            setHover(null);
          }}
          className="cursor-grab active:cursor-grabbing"
        />
        {hover && (
          <div
            className="pointer-events-none absolute z-10 rounded border border-slate-700 bg-slate-900/95 px-3 py-2 text-[11px] shadow-xl"
            style={{ left: Math.min(hover.screenX + 14, dims.w - 190), top: Math.max(hover.screenY - 60, 6) }}
          >
            <div className="font-mono text-cyan-300">GRID #{hover.grid_id}</div>
            <div className="text-slate-400">
              {hover.latitude.toFixed(4)}°N, {hover.longitude.toFixed(4)}°E
            </div>
            <div className="text-slate-400">{hover.sector_label}</div>
            <div className="mt-1 font-mono text-amber-300">{hover.total_activity.toFixed(1)} ops/hr</div>
          </div>
        )}
        <div className="absolute bottom-3 left-3 flex items-center gap-2 rounded border border-slate-800 bg-slate-950/80 px-2 py-1 text-[10px] text-slate-500">
          <Flame size={11} className="text-rose-400" />
          EPSG:4326 · Milan Metro
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="mb-1 flex justify-between text-[11px] text-slate-400">
            <span>Heatmap Intensity</span>
            <span className="font-mono text-slate-300">{intensity.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min={0.2}
            max={1}
            step={0.05}
            value={intensity}
            onChange={(e) => setIntensity(parseFloat(e.target.value))}
            className="w-full accent-cyan-500"
          />
        </div>
        <div>
          <div className="mb-1 flex justify-between text-[11px] text-slate-400">
            <span>Thermal Radius</span>
            <span className="font-mono text-slate-300">{radius}px</span>
          </div>
          <input
            type="range"
            min={24}
            max={80}
            step={2}
            value={radius}
            onChange={(e) => setRadius(parseFloat(e.target.value))}
            className="w-full accent-amber-500"
          />
        </div>
      </div>
    </div>
  );
}
