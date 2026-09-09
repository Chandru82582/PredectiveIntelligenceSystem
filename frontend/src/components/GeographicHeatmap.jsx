import { useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, TileLayer, Polygon, Tooltip, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import 'leaflet.heat';
import { ZoomIn, ZoomOut, Locate, Flame } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

const MILAN_CENTER = [45.4642, 9.19];

const MAP_TILE_URL_DARK =
  import.meta.env.VITE_MAP_TILE_URL || 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
const MAP_TILE_URL_LIGHT = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';

const SEVERITY_COLOR_DARK = {
  HIGH: '#f43f5e',
  MEDIUM: '#f59e0b',
  NORMAL: '#06b6d4',
  DEADZONE: '#1e293b',
};

const SEVERITY_COLOR_LIGHT = {
  HIGH: '#e11d48',
  MEDIUM: '#d97706',
  NORMAL: '#0284c7',
  DEADZONE: '#cbd5e1',
};

function classify(activity, p75, p45) {
  if (activity <= 0) return 'DEADZONE';
  if (activity > p75) return 'HIGH';
  if (activity > p45) return 'MEDIUM';
  return 'NORMAL';
}

// leaflet.heat's multi-stop gradient keys are 0..1 offsets -> color, matching
// the brief's thermal stops per intensity tier.
function gradientFor(tier) {
  if (tier === 'high') {
    return { 0.0: 'rgba(6,182,212,0)', 0.4: 'rgba(6,182,212,0.4)', 0.7: 'rgba(245,158,11,0.75)', 1.0: 'rgba(244,63,94,0.95)' };
  }
  if (tier === 'medium') {
    return { 0.0: 'rgba(6,182,212,0)', 0.5: 'rgba(6,182,212,0.6)', 1.0: 'rgba(245,158,11,0.9)' };
  }
  return { 0.0: 'rgba(16,185,129,0)', 0.5: 'rgba(16,185,129,0.4)', 1.0: 'rgba(6,182,212,0.85)' };
}

function HeatLayer({ points, intensity, radius, isVisible }) {
  const map = useMap();
  const layerRef = useRef([]);
  const [hasValidSize, setHasValidSize] = useState(() => {
    try {
      const s = map.getSize();
      return !!(s && s.x > 0 && s.y > 0);
    } catch {
      return false;
    }
  });

  useEffect(() => {
    const checkSize = () => {
      try {
        const s = map.getSize();
        setHasValidSize(!!(s && s.x > 0 && s.y > 0));
      } catch {
        setHasValidSize(false);
      }
    };

    checkSize();
    map.on('resize', checkSize);
    const t1 = setTimeout(checkSize, 60);
    const t2 = setTimeout(checkSize, 300);

    return () => {
      map.off('resize', checkSize);
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [map, isVisible]);

  useEffect(() => {
    // If not visible or map dimensions are 0 (e.g. background container), do not draw heat canvas
    if (isVisible === false || !hasValidSize || !points.length) {
      if (layerRef.current && layerRef.current.length) {
        layerRef.current.forEach((l) => {
          try {
            map.removeLayer(l);
          } catch {
            // ignore
          }
        });
        layerRef.current = [];
      }
      return undefined;
    }

    try {
      const size = map.getSize();
      if (!size || size.x <= 0 || size.y <= 0) return undefined;

      const high = points.filter((p) => p[2] > 0.75).map((p) => [p[0], p[1], p[2]]);
      const medium = points.filter((p) => p[2] > 0.45 && p[2] <= 0.75).map((p) => [p[0], p[1], p[2]]);
      const low = points.filter((p) => p[2] <= 0.45).map((p) => [p[0], p[1], p[2]]);

      const layers = [
        L.heatLayer(low, { radius, blur: radius * 0.6, maxZoom: 17, minOpacity: intensity * 0.3, gradient: gradientFor('low') }),
        L.heatLayer(medium, { radius, blur: radius * 0.6, maxZoom: 17, minOpacity: intensity * 0.4, gradient: gradientFor('medium') }),
        L.heatLayer(high, { radius, blur: radius * 0.6, maxZoom: 17, minOpacity: intensity * 0.5, gradient: gradientFor('high') }),
      ];

      layers.forEach((l) => l.addTo(map));
      layerRef.current = layers;

      return () => {
        layers.forEach((l) => {
          try {
            map.removeLayer(l);
          } catch {
            // ignore
          }
        });
        layerRef.current = [];
      };
    } catch (err) {
      console.warn('[GeographicHeatmap] HeatLayer deferred:', err);
      return undefined;
    }
  }, [map, points, intensity, radius, isVisible, hasValidSize]);

  return null;
}

function MapControls({ severityFilter, setSeverityFilter, intensity, setIntensity, radius, setRadius }) {
  const map = useMap();
  return (
    <>
      <div className="pointer-events-auto absolute left-3 top-3 z-[500] flex items-center gap-1.5">
        {['ALL', 'HIGH', 'MEDIUM', 'NORMAL'].map((s) => (
          <button
            key={s}
            onClick={() => setSeverityFilter(s)}
            className={`rounded px-2.5 py-1 text-[11px] font-medium tracking-wide shadow transition-colors ${
              severityFilter === s
                ? 'bg-cyan-500/20 text-cyan-800 border border-cyan-500/40 dark:bg-cyan-500/30 dark:text-cyan-200 dark:border-cyan-500/50'
                : 'bg-white/90 text-slate-700 border border-slate-200 hover:text-slate-900 dark:bg-slate-900/80 dark:text-slate-400 dark:border-slate-800 dark:hover:text-slate-200'
            }`}
          >
            {s}
          </button>
        ))}
      </div>
      <div className="pointer-events-auto absolute right-3 top-3 z-[500] flex items-center gap-1.5">
        <button onClick={() => map.zoomIn()} className="rounded border border-slate-200 bg-white/90 p-1.5 text-slate-700 shadow hover:text-cyan-600 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-300 dark:hover:text-cyan-300">
          <ZoomIn size={14} />
        </button>
        <button onClick={() => map.zoomOut()} className="rounded border border-slate-200 bg-white/90 p-1.5 text-slate-700 shadow hover:text-cyan-600 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-300 dark:hover:text-cyan-300">
          <ZoomOut size={14} />
        </button>
        <button onClick={() => map.setView(MILAN_CENTER, 12)} className="rounded border border-slate-200 bg-white/90 p-1.5 text-slate-700 shadow hover:text-cyan-600 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-300 dark:hover:text-cyan-300">
          <Locate size={14} />
        </button>
      </div>
      <div className="pointer-events-auto absolute bottom-3 left-3 z-[500] flex items-center gap-2 rounded border border-slate-200 bg-white/90 px-2 py-1 text-[10px] text-slate-700 shadow dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-400">
        <Flame size={11} className="text-rose-500 dark:text-rose-400" />
        EPSG:4326 · Milan Metro
      </div>
      <div className="pointer-events-auto absolute bottom-3 right-3 z-[500] flex w-64 flex-col gap-2 rounded border border-slate-200 bg-white/95 px-3 py-2 shadow-lg dark:border-slate-800 dark:bg-slate-900/85">
        <div>
          <div className="mb-1 flex justify-between text-[10px] text-slate-600 dark:text-slate-400">
            <span>Heatmap Intensity</span>
            <span className="font-mono text-slate-800 dark:text-slate-300">{intensity.toFixed(2)}</span>
          </div>
          <input type="range" min={0.2} max={1} step={0.05} value={intensity} onChange={(e) => setIntensity(parseFloat(e.target.value))} className="w-full accent-cyan-500" />
        </div>
        <div>
          <div className="mb-1 flex justify-between text-[10px] text-slate-600 dark:text-slate-400">
            <span>Thermal Radius</span>
            <span className="font-mono text-slate-800 dark:text-slate-300">{radius}px</span>
          </div>
          <input type="range" min={24} max={80} step={2} value={radius} onChange={(e) => setRadius(parseFloat(e.target.value))} className="w-full accent-amber-500" />
        </div>
      </div>
    </>
  );
}

function MapInvalidator({ isVisible }) {
  const map = useMap();

  useEffect(() => {
    if (isVisible !== false) {
      const t1 = setTimeout(() => map.invalidateSize(), 50);
      const t2 = setTimeout(() => map.invalidateSize(), 250);
      return () => {
        clearTimeout(t1);
        clearTimeout(t2);
      };
    }
  }, [map, isVisible]);

  useEffect(() => {
    const container = map.getContainer();
    if (!container || typeof ResizeObserver === 'undefined') return;

    const observer = new ResizeObserver(() => {
      map.invalidateSize();
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [map]);

  return null;
}

export default function GeographicHeatmap({ cells, selectedGridId, onSelectGrid, isVisible }) {
  const { isDark } = useTheme();
  const [intensity, setIntensity] = useState(0.65);
  const [radius, setRadius] = useState(28);
  const [severityFilter, setSeverityFilter] = useState('ALL');

  const severityColors = isDark ? SEVERITY_COLOR_DARK : SEVERITY_COLOR_LIGHT;
  const tileUrl = isDark ? MAP_TILE_URL_DARK : MAP_TILE_URL_LIGHT;

  const enriched = useMemo(() => {
    if (!cells || cells.length === 0) return [];

    // Deduplicate cells by grid_id in case gridList contains duplicates
    const uniqueMap = new Map();
    for (const c of cells) {
      if (!c || c.grid_id == null) continue;
      const existing = uniqueMap.get(c.grid_id);
      if (!existing) {
        uniqueMap.set(c.grid_id, c);
      } else if ((c.polygon && !existing.polygon) || c.total_activity > existing.total_activity) {
        uniqueMap.set(c.grid_id, { ...existing, ...c });
      }
    }

    const uniqueCells = Array.from(uniqueMap.values());
    const vals = uniqueCells.map((c) => c.total_activity).sort((a, b) => a - b);
    const p75 = vals[Math.floor(vals.length * 0.75)] ?? 0;
    const p45 = vals[Math.floor(vals.length * 0.45)] ?? 0;
    const max = vals[vals.length - 1] || 1;
    return uniqueCells
      .filter((c) => c.polygon && c.polygon.length >= 3)
      .map((c) => ({ ...c, severity: classify(c.total_activity, p75, p45), norm: c.total_activity / max }));
  }, [cells]);

  const visibleCells = useMemo(
    () => (severityFilter === 'ALL' ? enriched : enriched.filter((c) => c.severity === severityFilter)),
    [enriched, severityFilter]
  );

  const heatPoints = useMemo(() => visibleCells.map((c) => [c.latitude, c.longitude, c.norm]), [visibleCells]);

  return (
    <div className="flex flex-col gap-3">
      <div className="relative h-[680px] w-full overflow-hidden rounded-lg border border-slate-200 dark:border-slate-800">
        <MapContainer center={MILAN_CENTER} zoom={12} className="h-full w-full bg-slate-100 dark:bg-slate-950" zoomControl={false} preferCanvas>
          <MapInvalidator isVisible={isVisible} />
          <TileLayer
            key={tileUrl}
            attribution='&copy; <a href="https://carto.com/attributions">CARTO</a> &copy; OpenStreetMap contributors'
            url={tileUrl}
            subdomains={['a', 'b', 'c', 'd']}
          />

          <HeatLayer points={heatPoints} intensity={intensity} radius={radius} isVisible={isVisible} />

          {visibleCells.map((c) => {
            const isSelected = c.grid_id === selectedGridId;
            return (
              <Polygon
                key={`grid-polygon-${c.grid_id}`}
                positions={c.polygon}
                pathOptions={{
                  color: isSelected ? (isDark ? '#f8fafc' : '#0f172a') : severityColors[c.severity],
                  weight: isSelected ? 2.5 : 1,
                  fillColor: severityColors[c.severity],
                  fillOpacity: isSelected ? 0.75 : 0.45,
                }}
                eventHandlers={{ click: () => onSelectGrid?.(c.grid_id) }}
              >
                <Tooltip direction="top" sticky>
                  <div className="font-mono text-[11px] p-0.5">
                    <div className="font-bold text-cyan-700 dark:text-cyan-400">GRID #{c.grid_id}</div>
                    <div className="text-slate-600 dark:text-slate-300">
                      {c.latitude.toFixed(4)}°N, {c.longitude.toFixed(4)}°E
                    </div>
                    <div className="text-slate-600 dark:text-slate-300">{c.sector_label}</div>
                    <div className="font-semibold text-amber-700 dark:text-amber-400">{c.total_activity.toFixed(1)} ops/hr</div>
                  </div>
                </Tooltip>
              </Polygon>
            );
          })}

          <MapControls
            severityFilter={severityFilter}
            setSeverityFilter={setSeverityFilter}
            intensity={intensity}
            setIntensity={setIntensity}
            radius={radius}
            setRadius={setRadius}
          />
        </MapContainer>
      </div>
    </div>
  );
}
