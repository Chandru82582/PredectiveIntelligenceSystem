// API client bound to the Telecom Network Analytics FastAPI backend.
// Endpoints marked NEW were added to routes.py to support this dashboard
// (grid geography, weekly peak-hour drift, directional modality, grid list).
//
// If a request fails (backend not reachable, cold DB, CORS during local
// dev, etc.) every call falls back to synthetic-but-plausible data so the
// dashboard is never blank. `meta.fallback` on each response tells the UI
// whether it is looking at live or synthetic data.

import { withCache, getCached, setCached } from './cache';

const BASE_URL = import.meta.env?.VITE_API_BASE_URL || 'http://localhost:8000';
const API_KEY = import.meta.env?.VITE_API_KEY || '';

// "Live" queries (no explicit as_of/date) move forward with each batch
// ingestion, so they're cached briefly. A query pinned to a specific
// as_of/date is a fixed point in history and is cached indefinitely.
const LIVE_TTL_MS = 20_000;

async function request(path, params = {}) {
  const url = new URL(path, BASE_URL);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v);
  });

  const headers = {};
  if (API_KEY) headers['X-API-Key'] = API_KEY;

  const res = await fetch(url.toString(), { headers });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText} — ${path} ${body}`.trim());
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Deterministic synthetic fallback generators
// ---------------------------------------------------------------------------

function seededRandom(seed) {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

function diurnalCurve(hour, gridSeed) {
  const rand = seededRandom(gridSeed);
  const base = 180 + rand() * 260;
  const morning = Math.exp(-((hour - 8) ** 2) / 8) * 140;
  const evening = Math.exp(-((hour - 19) ** 2) / 10) * 190;
  const noise = (seededRandom(gridSeed + hour)() - 0.5) * 40;
  return Math.max(10, base + morning + evening + noise);
}

function fallbackTimeseries(gridId, count = 24, endTime = new Date()) {
  const out = [];
  for (let i = count - 1; i >= 0; i--) {
    const ts = new Date(endTime.getTime() - i * 3600 * 1000);
    const total = diurnalCurve(ts.getHours(), gridId);
    out.push({
      timestamp: ts.toISOString(),
      sms_activity: total * 0.18,
      call_activity: total * 0.27,
      internet_activity: total * 0.55,
      total_activity: total,
    });
  }
  return out;
}

function fallbackModality(gridId, hours = 24, endTime = new Date()) {
  const out = [];
  for (let i = hours - 1; i >= 0; i--) {
    const ts = new Date(endTime.getTime() - i * 3600 * 1000);
    const total = diurnalCurve(ts.getHours(), gridId);
    const rand = seededRandom(gridId * 31 + ts.getHours());
    out.push({
      timestamp: ts.toISOString(),
      sms_in: total * 0.09 * (0.8 + rand() * 0.4),
      sms_out: total * 0.09 * (0.8 + rand() * 0.4),
      call_in: total * 0.14 * (0.8 + rand() * 0.4),
      call_out: total * 0.13 * (0.8 + rand() * 0.4),
      internet_activity: total * 0.55,
    });
  }
  return out;
}

const GRID_DIM = 100;
const LAT_MIN = 45.3529, LAT_MAX = 45.5649;
const LON_MIN = 9.0115, LON_MAX = 9.3115;

function computeCentroid(gridId) {
  const idx = gridId - 1;
  const col = idx % GRID_DIM;
  const row = Math.floor(idx / GRID_DIM);
  const lonStep = (LON_MAX - LON_MIN) / GRID_DIM;
  const latStep = (LAT_MAX - LAT_MIN) / GRID_DIM;
  return {
    latitude: LAT_MIN + (row + 0.5) * latStep,
    longitude: LON_MIN + (col + 0.5) * lonStep,
  };
}

function computePolygon(gridId) {
  const { latitude, longitude } = computeCentroid(gridId);
  const dLat = (LAT_MAX - LAT_MIN) / GRID_DIM / 2;
  const dLon = (LON_MAX - LON_MIN) / GRID_DIM / 2;
  return [
    [latitude - dLat, longitude - dLon],
    [latitude - dLat, longitude + dLon],
    [latitude + dLat, longitude + dLon],
    [latitude + dLat, longitude - dLon],
  ];
}

function sectorLabel(gridId) {
  const idx = gridId - 1;
  const row = Math.floor(idx / GRID_DIM);
  const col = idx % GRID_DIM;
  const zoneRow = Math.min(Math.floor(row / (GRID_DIM / 4)), 3);
  const zoneCol = Math.min(Math.floor(col / (GRID_DIM / 4)), 3);
  return `Sector ${'ABCD'[zoneRow]}${zoneCol + 1}`;
}

export const QUICK_SWITCH_GRIDS = [100, 1420, 3292, 4365, 7240];

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function getNetworkSummary(asOf) {
  const key = `summary:${asOf || 'latest'}`;
  return withCache(key, asOf ? null : LIVE_TTL_MS, async () => {
    try {
      const data = await request('/network/summary', { as_of: asOf });
      return { ...data, meta: { fallback: false } };
    } catch (err) {
      console.warn('[api] getNetworkSummary fallback:', err.message);
      return {
        total_activity: 284213,
        active_grids: 6842,
        peak_hour: 19,
        top_grid: 4365,
        as_of: new Date().toISOString(),
        meta: { fallback: true },
      };
    }
  });
}

export async function getGridTimeseries(gridId, { asOf, date, hour } = {}) {
  const key = `ts:${gridId}:${date || ''}:${hour ?? ''}:${asOf || 'latest'}`;
  return withCache(key, date || asOf ? null : LIVE_TTL_MS, async () => {
    try {
      const data = await request(`/network/grid/${gridId}`, { as_of: asOf, date, hour });
      return { ...data, meta: { fallback: false } };
    } catch (err) {
      console.warn('[api] getGridTimeseries fallback:', err.message);
      return {
        grid_id: gridId,
        as_of: new Date().toISOString(),
        timeseries: fallbackTimeseries(gridId),
        meta: { fallback: true },
      };
    }
  });
}

// NEW: directional in/out breakdown, powers ModalityDecomposition's diverging bar
export async function getGridModality(gridId, { asOf, date, hours = 24 } = {}) {
  const key = `modality:${gridId}:${date || ''}:${hours}:${asOf || 'latest'}`;
  return withCache(key, date || asOf ? null : LIVE_TTL_MS, async () => {
    try {
      const data = await request(`/network/grid/${gridId}/modality`, { as_of: asOf, date, hours });
      return { ...data, meta: { fallback: false } };
    } catch (err) {
      console.warn('[api] getGridModality fallback:', err.message);
      return {
        grid_id: gridId,
        as_of: new Date().toISOString(),
        hours: fallbackModality(gridId, hours),
        meta: { fallback: true },
      };
    }
  });
}

export async function getGridFeatures(gridId, asOf) {
  const key = `features:${gridId}:${asOf || 'latest'}`;
  return withCache(key, asOf ? null : LIVE_TTL_MS, async () => {
    try {
      const data = await request(`/network/grid/${gridId}/features`, { as_of: asOf });
      return { ...data, meta: { fallback: false } };
    } catch (err) {
      console.warn('[api] getGridFeatures fallback:', err.message);
      const rand = seededRandom(gridId);
      return {
        grid_id: gridId,
        avg_activity: 220 + rand() * 300,
        activity_growth: (rand() - 0.4) * 0.6,
        active_hours: 18 + Math.floor(rand() * 6),
        peak_ratio: 1.4 + rand() * 1.6,
        variability: 60 + rand() * 140,
        internet_share: 0.45 + rand() * 0.3,
        feature_timestamp: new Date().toISOString(),
        data_quality: 'LOW',
        meta: { fallback: true },
      };
    }
  });
}

// NEW: real (or grid-math-derived) lat/lon + polygon for one cell.
// Geometry is static, so this is cached with no expiry.
export async function getGridGeography(gridId) {
  const key = `geo:${gridId}`;
  return withCache(key, null, async () => {
    try {
      const data = await request(`/network/grid/${gridId}/geography`);
      return { ...data, meta: { fallback: false } };
    } catch (err) {
      console.warn('[api] getGridGeography fallback:', err.message);
      return { grid_id: gridId, ...computeCentroid(gridId), polygon: computePolygon(gridId), sector_label: sectorLabel(gridId), source: 'computed', meta: { fallback: true } };
    }
  });
}

// NEW: bulk lat/lon + polygon lookup. Reuses whatever's already cached
// per-grid and only requests the ones that are genuinely missing.
export async function getGridsGeography(gridIds, asOf) {
  const ids = gridIds && gridIds.length ? gridIds : null;
  const cacheKeys = ids ? ids.map((id) => `geo:${id}`) : null;
  const cachedResults = {};
  let missing = ids;

  if (ids) {
    missing = [];
    ids.forEach((id, i) => {
      const hit = getCached(cacheKeys[i]);
      if (hit) cachedResults[id] = hit;
      else missing.push(id);
    });
    if (missing.length === 0) {
      return { as_of: new Date().toISOString(), grids: ids.map((id) => cachedResults[id]), meta: { fallback: false } };
    }
  }

  try {
    const data = await request('/network/grids/geography', {
      grid_ids: missing && missing.length ? missing.join(',') : undefined,
      as_of: asOf,
    });
    (data.grids || []).forEach((g) => setCached(`geo:${g.grid_id}`, { ...g, meta: { fallback: false } }, null));
    const merged = ids ? ids.map((id) => cachedResults[id] || (data.grids || []).find((g) => g.grid_id === id)).filter(Boolean) : data.grids;
    return { as_of: data.as_of, grids: merged, meta: { fallback: false } };
  } catch (err) {
    console.warn('[api] getGridsGeography fallback:', err.message);
    const fallbackIds = ids || Array.from({ length: 400 }, (_, i) => i * 25 + 1);
    const grids = fallbackIds.map(
      (id) => cachedResults[id] || { grid_id: id, ...computeCentroid(id), polygon: computePolygon(id), sector_label: sectorLabel(id), source: 'computed' }
    );
    return { as_of: new Date().toISOString(), grids, meta: { fallback: true } };
  }
}

// NEW: trailing 7-day peak-hour ribbon, powers PeakHourDial's week view
export async function getWeeklyPeak(gridId, asOf) {
  const key = `weekly:${gridId}:${asOf || 'latest'}`;
  return withCache(key, asOf ? null : LIVE_TTL_MS, async () => {
    try {
      const data = await request(`/network/grid/${gridId}/weekly-peak`, { as_of: asOf });
      return { ...data, meta: { fallback: false } };
    } catch (err) {
      console.warn('[api] getWeeklyPeak fallback:', err.message);
      const rand = seededRandom(gridId * 7);
      const days = [];
      const today = new Date();
      for (let i = 6; i >= 0; i--) {
        const d = new Date(today.getTime() - i * 86400000);
        const isWeekend = d.getDay() === 0 || d.getDay() === 6;
        const peakHour = Math.round((isWeekend ? 15.5 : 14.0) + (rand() - 0.5) * 3);
        days.push({
          date: d.toISOString().slice(0, 10),
          day_of_week: (d.getDay() + 6) % 7,
          peak_hour: peakHour,
          peak_activity: 380 + rand() * 220,
          delta_hours: 0,
        });
      }
      const avg = days.reduce((s, d) => s + d.peak_hour, 0) / days.length;
      days.forEach((d) => (d.delta_hours = +(d.peak_hour - avg).toFixed(1)));
      return { grid_id: gridId, as_of: new Date().toISOString(), trailing_avg_peak_hour: +avg.toFixed(1), days, meta: { fallback: true } };
    }
  });
}

export async function getHotspots({ limit = 10, severity = 'HIGH', asOf } = {}) {
  const key = `hotspots:${limit}:${severity}:${asOf || 'latest'}`;
  return withCache(key, asOf ? null : LIVE_TTL_MS, async () => {
    try {
      const data = await request('/network/hotspots', { limit, severity, as_of: asOf });
      return { ...data, meta: { fallback: false } };
    } catch (err) {
      console.warn('[api] getHotspots fallback:', err.message);
      const rand = seededRandom(42);
      const now = new Date().toISOString();
      const hotspots = Array.from({ length: limit }, (_, i) => {
        const gridId = 100 + Math.floor(rand() * 9800);
        return { grid_id: gridId, total_activity: 900 - i * 45 + rand() * 30, severity, timestamp: now };
      });
      return { as_of: now, hotspots, meta: { fallback: true } };
    }
  });
}

export async function getAlerts({ limit = 50, severity, asOf } = {}) {
  const key = `alerts:${limit}:${severity || ''}:${asOf || 'latest'}`;
  return withCache(key, asOf ? null : LIVE_TTL_MS, async () => {
    try {
      const data = await request('/network/alerts', { limit, severity, as_of: asOf });
      return { ...data, meta: { fallback: false } };
    } catch (err) {
      console.warn('[api] getAlerts fallback:', err.message);
      const rand = seededRandom(99);
      const types = ['HIGH_ACTIVITY', 'ACTIVITY_SPIKE', 'ACTIVITY_DROP'];
      const alerts = Array.from({ length: Math.min(limit, 8) }, (_, i) => {
        const type = types[i % types.length];
        const baseline = 200 + rand() * 150;
        const ratio = type === 'ACTIVITY_DROP' ? 0.2 + rand() * 0.3 : 1.6 + rand() * 2.2;
        return {
          grid_id: 100 + Math.floor(rand() * 9800),
          timestamp: new Date().toISOString(),
          alert_type: type,
          current_activity: baseline * ratio,
          baseline_activity: baseline,
          reason: `Current activity (${(baseline * ratio).toFixed(2)}) is ${ratio.toFixed(2)}x the within-day baseline (${baseline.toFixed(2)}).`,
        };
      });
      return { as_of: new Date().toISOString(), alerts, meta: { fallback: true } };
    }
  });
}

// NEW: next-hour high-activity risk prediction (LightGBM model served by
// backend/ml_model.py), powers the Grid Investigator's Prediction panel.
export async function getGridPrediction(gridId, asOf) {
  const key = `predict:${gridId}:${asOf || 'latest'}`;
  return withCache(key, asOf ? null : LIVE_TTL_MS, async () => {
    try {
      const data = await request(`/predict/grid/${gridId}`, { as_of: asOf });
      return { ...data, meta: { fallback: false } };
    } catch (err) {
      console.warn('[api] getGridPrediction fallback:', err.message);
      const rand = seededRandom(gridId * 13 + 5);
      const probability = Math.min(0.97, Math.max(0.01, rand() * 0.9));
      const threshold = 0.5;
      return {
        grid_id: gridId,
        as_of: new Date().toISOString(),
        feature_timestamp: new Date().toISOString(),
        probability,
        prediction: probability >= threshold ? 1 : 0,
        risk_label: probability >= threshold ? 'HIGH_ACTIVITY_RISK' : 'NORMAL',
        threshold,
        data_points_used: 48,
        features: {
          activity_growth: 0.9 + (rand() - 0.5) * 0.6,
          variability: 0.2 + rand() * 0.4,
          peak_ratio: 1.2 + rand() * 1.2,
          internet_share: 0.4 + rand() * 0.3,
          current_to_baseline_ratio: 0.8 + rand() * 1.4,
        },
        meta: { fallback: true },
      };
    }
  });
}

// NEW: flat grid list with severity, powers the quick cell switcher / search
export async function listGrids({ asOf, limit = 500 } = {}) {
  const key = `grids:${limit}:${asOf || 'latest'}`;
  return withCache(key, asOf ? null : LIVE_TTL_MS, async () => {
    try {
      const data = await request('/network/grids', { as_of: asOf, limit });
      return { ...data, meta: { fallback: false } };
    } catch (err) {
      console.warn('[api] listGrids fallback:', err.message);
      const rand = seededRandom(7);
      const grids = Array.from({ length: Math.min(limit, 400) }, (_, i) => {
        const gridId = i * 25 + 1;
        const activity = diurnalCurve(new Date().getHours(), gridId);
        return { grid_id: gridId, total_activity: activity, severity: activity > 380 ? 'HIGH' : activity > 240 ? 'MEDIUM' : 'NORMAL' };
      });
      return { as_of: new Date().toISOString(), total: grids.length, grids, meta: { fallback: true } };
    }
  });
}

// ---------------------------------------------------------------------------
// Data Explorer — filterable/paginated raw rows off each backing table.
// ---------------------------------------------------------------------------

const DATA_TTL_MS = 15_000; // short: filters/pagination change constantly, but repeat clicks (e.g. re-sorting back) shouldn't always round-trip

function fallbackDataPage({ page = 1, pageSize = 50, totalRows = 4200, rowFactory }) {
  const total = totalRows;
  const start = (page - 1) * pageSize;
  const records = Array.from({ length: Math.max(0, Math.min(pageSize, total - start)) }, (_, i) => rowFactory(start + i));
  return { total, page, page_size: pageSize, records, meta: { fallback: true } };
}

function fallbackHourlyRow(i) {
  const gridId = (i % 400) * 25 + 1;
  const daysAgo = Math.floor(i / 400 / 24);
  const hour = i % 24;
  const d = new Date(Date.now() - daysAgo * 86400000);
  const total = diurnalCurve(hour, gridId);
  return {
    id: i + 1,
    date: d.toISOString().slice(0, 10),
    hour,
    grid_id: gridId,
    sms_in: total * 0.09,
    sms_out: total * 0.09,
    call_in: total * 0.14,
    call_out: total * 0.13,
    internet_activity: total * 0.55,
    total_activity: total,
    record_count: 20 + (i % 30),
    loaded_at: d.toISOString(),
  };
}

export async function getHourlyData(filters = {}) {
  const key = `data:hourly:${JSON.stringify(filters)}`;
  return withCache(key, DATA_TTL_MS, async () => {
    try {
      const data = await request('/data/hourly', filters);
      return { ...data, meta: { fallback: false } };
    } catch (err) {
      console.warn('[api] getHourlyData fallback:', err.message);
      return fallbackDataPage({ page: filters.page, pageSize: filters.page_size, rowFactory: fallbackHourlyRow });
    }
  });
}

export async function getSpatialData(filters = {}) {
  const key = `data:spatial:${JSON.stringify(filters)}`;
  return withCache(key, DATA_TTL_MS, async () => {
    try {
      const data = await request('/data/spatial', filters);
      return { ...data, meta: { fallback: false } };
    } catch (err) {
      console.warn('[api] getSpatialData fallback:', err.message);
      return fallbackDataPage({
        page: filters.page,
        pageSize: filters.page_size,
        rowFactory: (i) => {
          const row = fallbackHourlyRow(i);
          const { record_count, ...rest } = row;
          return { ...rest, has_geometry: i % 3 === 0 };
        },
      });
    }
  });
}

export async function getGridSummaryData(filters = {}) {
  const key = `data:grid-summary:${JSON.stringify(filters)}`;
  return withCache(key, DATA_TTL_MS, async () => {
    try {
      const data = await request('/data/grid-summary', filters);
      return { ...data, meta: { fallback: false } };
    } catch (err) {
      console.warn('[api] getGridSummaryData fallback:', err.message);
      return fallbackDataPage({
        page: filters.page,
        pageSize: filters.page_size,
        totalRows: 9800,
        rowFactory: (i) => {
          const gridId = (i % 400) * 25 + 1;
          const daysAgo = Math.floor(i / 400);
          const d = new Date(Date.now() - daysAgo * 86400000);
          const rand = seededRandom(gridId * 17 + daysAgo);
          const total = 3000 + rand() * 4000;
          return {
            id: i + 1,
            date: d.toISOString().slice(0, 10),
            grid_id: gridId,
            total_sms: total * 0.18,
            total_calls: total * 0.27,
            internet_usage: total * 0.55,
            total_activity: total,
            active_hours: 14 + Math.floor(rand() * 10),
            loaded_at: d.toISOString(),
          };
        },
      });
    }
  });
}

export async function getDailySummaryData(filters = {}) {
  const key = `data:daily-summary:${JSON.stringify(filters)}`;
  return withCache(key, DATA_TTL_MS, async () => {
    try {
      const data = await request('/data/daily-summary', filters);
      return { ...data, meta: { fallback: false } };
    } catch (err) {
      console.warn('[api] getDailySummaryData fallback:', err.message);
      return fallbackDataPage({
        page: filters.page,
        pageSize: filters.page_size,
        totalRows: 60,
        rowFactory: (i) => {
          const d = new Date(Date.now() - i * 86400000);
          const rand = seededRandom(i + 3);
          const total = 260000 + rand() * 60000;
          return {
            id: i + 1,
            date: d.toISOString().slice(0, 10),
            total_sms: total * 0.18,
            total_calls: total * 0.27,
            internet_usage: total * 0.55,
            total_activity: total,
            active_grids: 6200 + Math.floor(rand() * 900),
            total_records: 230000 + Math.floor(rand() * 20000),
            loaded_at: d.toISOString(),
          };
        },
      });
    }
  });
}

// NEW: pipeline ingestion audit trail (flow/logs/audit_log.json), powers
// the Data page's Quality Check tab.
export async function getAuditLogData(filters = {}) {
  const key = `data:audit-log:${JSON.stringify(filters)}`;
  return withCache(key, DATA_TTL_MS, async () => {
    try {
      const data = await request('/data/audit-log', filters);
      return { ...data, meta: { fallback: false } };
    } catch (err) {
      console.warn('[api] getAuditLogData fallback:', err.message);
      return fallbackDataPage({
        page: filters.page,
        pageSize: filters.page_size,
        totalRows: 5,
        rowFactory: (i) => {
          const d = new Date(Date.now() - i * 3600000);
          const rejected = i % 3 === 1;
          return {
            id: i + 1,
            filename: `sms-call-internet-mi-2013-11-${String((i % 7) + 1).padStart(2, '0')}.csv`,
            status: rejected ? 'REJECTED' : 'ACCEPTED',
            row_count: rejected ? 0 : 1800000 + i * 15000,
            reason: rejected ? 'Synthetic fallback — pipeline log unreachable.' : null,
            processed_at: d.toISOString(),
            duration_seconds: rejected ? null : 40 + i * 3.2,
          };
        },
      });
    }
  });
}



export async function getChatHistory(gridId) {
  try {
    const params = gridId !== undefined && gridId !== null ? { grid_id: gridId } : {};
    return await request('/chat/history', params);
  } catch (err) {
    console.warn('[api] getChatHistory fallback:', err.message);
    return null;
  }
}

export async function saveChatHistory(gridId, messages) {
  try {
    const url = new URL('/chat/history', BASE_URL);
    const headers = { 'Content-Type': 'application/json' };
    if (API_KEY) headers['X-API-Key'] = API_KEY;
    const res = await fetch(url.toString(), {
      method: 'POST',
      headers,
      body: JSON.stringify({ grid_id: Number(gridId), messages })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('[api] saveChatHistory failed:', err.message);
    return null;
  }
}

export async function clearChatHistory(gridId) {
  try {
    const url = new URL('/chat/history', BASE_URL);
    if (gridId !== undefined && gridId !== null) {
      url.searchParams.set('grid_id', gridId);
    }
    const headers = {};
    if (API_KEY) headers['X-API-Key'] = API_KEY;
    const res = await fetch(url.toString(), {
      method: 'DELETE',
      headers
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn('[api] clearChatHistory failed:', err.message);
    return null;
  }
}

export async function getPredictionMatrix() {
  const key = 'predict:matrix';
  return withCache(key, LIVE_TTL_MS, async () => {
    try {
      const data = await request('/predict/matrix');
      return { ...data, meta: { fallback: false } };
    } catch (err) {
      console.warn('[api] getPredictionMatrix failed:', err.message);
      throw err;
    }
  });
}

export default {
  getNetworkSummary,
  getGridTimeseries,
  getGridModality,
  getGridFeatures,
  getGridGeography,
  getGridsGeography,
  getWeeklyPeak,
  getHotspots,
  getAlerts,
  getGridPrediction,
  getPredictionMatrix,
  listGrids,
  getHourlyData,
  getSpatialData,
  getGridSummaryData,
  getDailySummaryData,
  getAuditLogData,
  getChatHistory,
  saveChatHistory,
  clearChatHistory,
  QUICK_SWITCH_GRIDS,
};

