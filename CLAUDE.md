# CLAUDE.md - Telecom Italia Milan Predictive Intelligence System
## Telemetry Analytics, Predictive Intelligence, MCP Server, Hooks & Team Conventions

## 1. System Overview & Core Invariants

This repository implements an end-to-end Big Data & Predictive Intelligence platform for telecommunications activity across the Milan metropolitan area (100x100 grid, 10,000 cells) using the Telecom Italia Open Big Data dataset (November 1–7, 2013).

### Non-Negotiable Domain Rules

1. **Raw vs. Analytics Grain**:
   - **Raw Landing Grain**: `(datetime, Square_id, Country_code)` at **10-minute intervals**.
   - **Analytics Grain**: **Exactly one record per grid cell per 1-hour timestamp after country-code aggregation** `(date, hour, grid_id)`. All 10-minute intervals within the hour and all country codes are summed. Table: `HourlyGridSummary` / `hourly_grid_summary`.
2. **Activity Semantics (Proportional Measures, NOT Counts or MB)**:
   - Activity metrics (`total_activity`, `sms_in_activity`, `sms_out_activity`, `call_in_activity`, `call_out_activity`, `internet_traffic_activity`) are **proportional, dimensionless activity measures** normalized by Telecom Italia.
   - **NEVER** refer to these values as counts (e.g., "number of calls", "number of SMS") or data volumes (e.g., "megabytes", "gigabytes").
3. **High Activity vs. Congestion**:
   - High activity values **MUST NEVER be described as confirmed congestion**.
   - Because network capacity, radio bearer allocations, and physical link utilization (e.g., PRBs) are unknown, use terms such as **"high activity"**, **"activity surge"**, **"volume spike"**, **"elevated demand"**, or **"activity risk"**.
4. **Geographic Joins**:
   - When joining spatial GeoJSON data (`milano-grid.geojson`), **ALWAYS join on `properties.cellId`** (1-indexed, integers 1 through 10,000).
   - **NEVER use the 0-based feature index or feature ID** (which is offset by 1).
   - Lattice coordinate layout: $grid\_id = row \times 100 + col + 1$, where row 0 = South, row 99 = North, col 0 = West, col 99 = East.
5. **The `AS_OF` Temporal Convention**:
   - The dataset is historical (November 1–7, 2013). **The `AS_OF` convention defines operational "now"**.
   - Default "current" time across queries and backend endpoints is `MAX(date, hour)` in `HourlyGridSummary` (`2013-11-07 23:00`), or an explicit `as_of` query parameter.
   - **NEVER query against `datetime.utcnow()`** expecting live streaming data.

---

## 2. Repository Map

```
PredectiveIntelligenceSystem/
├── flow/                   # Orchestration, Spark pipelines, and DB ingestion
│   ├── airflow_home/       # Airflow configuration, logs, and DAG definitions
│   │   └── dags/           # Airflow DAGs (ingestion_dag.py)
│   ├── spark/              # PySpark data processing jobs (telecom_pipeline.py)
│   └── sql_ingestion/      # Database schemas, table creation, and batch loaders
├── DataAnalysis/           # Exploratory data analysis, ML feature engineering & training
│   ├── models/             # Trained ML model artifacts (lgbm_high_activity_v3.joblib, v2, v1)
│   ├── preprocessor.py     # DataPreprocessor pipeline for lag/rolling features
│   ├── train.py            # LightGBM training and evaluation script
│   └── notebooks/          # DataAnalysis.ipynb, featuring.ipynb
├── backend/                # FastAPI REST API & Claude NOC Copilot Agent
│   ├── main.py             # FastAPI entrypoint and CORS setup
│   ├── routes.py           # API endpoints (metrics, prediction, grid matrix, chat)
│   ├── ml_model.py         # LightGBM inference runner and model loader
│   ├── claude_agent.py     # Autonomous NOC Copilot Agent with tool calling
│   ├── database.py         # SQLAlchemy models and connection pool
│   ├── schemas.py          # Pydantic response/request models
│   ├── rules.py            # Rule-based threshold & anomaly detection analyzers
│   └── grid_matrix_cache.json # Precomputed 10,000-cell prediction cache
├── frontend/               # React 18 + Vite SPA Dashboard
│   ├── src/
│   │   ├── App.jsx         # App shell, navigation, global filters
│   │   ├── views/          # Primary views (NetworkOverview, GridInvestigator, DataExplorer, ClaudeAssistant)
│   │   ├── components/     # UI components (GridMatrix100, GeographicHeatmap, ActivityPrediction, etc.)
│   │   └── services/api.js # Axios HTTP API client
│   └── package.json        # Frontend dependencies and Vite build scripts
├── mcp_server/             # Model Context Protocol (MCP) server for external LLM tools
│   ├── server.py           # FastMCP stdio/SSE server (7 thin wrappers, zero business logic)
│   ├── test_server.py      # Automated MCP endpoint & tool verification suite
│   └── README.md           # MCP architecture & Claude Desktop integration guide
├── .agents/                # Antigravity agent configuration, plugins, skills & hooks
│   ├── hooks.json          # Lifecycle hook definitions (PreToolUse & PostToolUse)
│   ├── hooks/              # Hook implementations (pre_edit_guard.py, post_edit_test.py)
│   ├── logs/               # Audit execution logs (hooks.log)
│   ├── skills/             # Domain skills (api-review, telecom-data-quality, etc.)
│   └── plugins/            # Team convention plugins
│       └── telecom-conventions/ # Packaged conventions, rules, skills, commands & hooks
├── .claude/                # Claude Code slash command configurations
│   └── commands/           # /network-health, /check-pipeline, /explain-grid, etc.
├── data/                   # Landing data, raw TSV/CSV archives, GeoJSON boundary files
├── report/                 # System architecture and performance reports
└── report_spark/           # Spark job benchmarking and execution metrics
```

---

## 3. End-to-End Data Flow

```
1. Landing CSVs (data/sms-call-internet-mi-2013-11-*.txt)
   Grain: 10-minute intervals, by Square_id and Country_code
      │
      ▼
2. PySpark ETL Pipeline (flow/spark/telecom_pipeline.py)
   - Cleans nulls, validates schema, converts epoch timestamps
   - Aggregates 10-min slots into 1-hour windows
   - Sums all country codes into a single activity figure per grid
   - Joins spatial centroids and sector definitions
   - Computes daily & hourly statistical summaries
      │
      ▼
3. Storage Layer (MySQL / TimescaleDB / SQLite)
   - hourly_grid_summary (Analytics grain: date, hour, grid_id)
   - enriched_spatial_hourly (Hourly grid records + lat/long/sector)
   - grid_summary (Grid-level baseline and peak metrics)
   - daily_summary (Day-level aggregates)
      │
      ▼
4. Backend API & ML Scoring (backend/routes.py, ml_model.py)
   - Resolves `as_of` timestamp (defaults to MAX(date, hour))
   - Feature engineering with DataPreprocessor (rolling lags, hourly baselines)
   - High activity prediction (LightGBM next-hour classifier)
   - Claude NOC Copilot dynamic investigation (backend/claude_agent.py)
      │
      ▼
5. React Dashboard (frontend/src/)
   - NetworkOverview: 100x100 Grid Matrix, alert feeds, KPIs
   - GridInvestigator: Deep-dive grid activity and predictions
   - DataExplorer: Queryable tabular inspection
   - ClaudeAssistant: NOC AI Copilot conversational UI
```

---

## 4. Component Inventory (Where Things Live)

| Component | File Path | Key Responsibilities |
|---|---|---|
| **Spark Pipeline** | [`flow/spark/telecom_pipeline.py`](file:///D:/PredectiveIntelligenceSystem/flow/spark/telecom_pipeline.py) | Schema casting, 10-min to 1-hr aggregation, country code summation, spatial enrichment |
| **Airflow DAG** | [`flow/airflow_home/dags/ingestion_dag.py`](file:///D:/PredectiveIntelligenceSystem/flow/airflow_home/dags/ingestion_dag.py) | Orchestrates Spark pipeline, DB ingestion, and table indexing |
| **API Routes** | [`backend/routes.py`](file:///D:/PredectiveIntelligenceSystem/backend/routes.py) | `/api/summary`, `/api/alerts`, `/api/grids`, `/api/predict/*`, `/api/grid-matrix`, `/api/chat` |
| **ML Inference** | [`ml/predict.py`](file:///D:/PredectiveIntelligenceSystem/ml/predict.py) | `HighActivityPredictor`, dynamically loads highest model version (`lgbm_high_activity_v3.joblib`), invokes `DataPreprocessor` |
| **ML Feature Pipeline**| [`DataAnalysis/preprocessor.py`](file:///D:/PredectiveIntelligenceSystem/DataAnalysis/preprocessor.py) | Rolling averages, lags, baseline ratios. **Requires chronological ordering** |
| **Claude Agent** | [`backend/claude_agent.py`](file:///D:/PredectiveIntelligenceSystem/backend/claude_agent.py) | Dynamic system prompt, tool execution (`get_network_summary`, `predict_high_activity`, etc.) |
| **100x100 Grid Matrix** | [`frontend/src/components/GridMatrix100.jsx`](file:///D:/PredectiveIntelligenceSystem/frontend/src/components/GridMatrix100.jsx) | Canvas-rendered 10,000-cell interactive grid with hover/click detail modal |
| **React Views** | [`frontend/src/views/`](file:///D:/PredectiveIntelligenceSystem/frontend/src/views/) | `NetworkOverview.jsx`, `GridInvestigator.jsx`, `DataExplorer.jsx`, `ClaudeAssistant.jsx` |
| **API Client** | [`frontend/src/services/api.js`](file:///D:/PredectiveIntelligenceSystem/frontend/src/services/api.js) | Axios client with `X-API-Key` auth header and endpoint methods |
| **MCP Server** | [`mcp_server/server.py`](file:///D:/PredectiveIntelligenceSystem/mcp_server/server.py) | Standardized FastMCP interface exposing 7 thin REST wrapper tools with zero business logic |
| **Pre-Edit Guard Hook** | [`.agents/hooks/pre_edit_guard.py`](file:///D:/PredectiveIntelligenceSystem/.agents/hooks/pre_edit_guard.py) | `PreToolUse` hook prompting confirmation before modifications to Airflow DAGs/pipeline configs |
| **Post-Edit Regression Guard** | [`.agents/hooks/post_edit_test.py`](file:///D:/PredectiveIntelligenceSystem/.agents/hooks/post_edit_test.py) | `PostToolUse` hook running grain duplicate checks and ML2 feature leakage tests on Spark/ML edits |
| **Team Conventions Plugin** | [`.agents/plugins/telecom-conventions/plugin.json`](file:///D:/PredectiveIntelligenceSystem/.agents/plugins/telecom-conventions/plugin.json) | Distributable plugin bundle containing rules, skills, slash commands, hooks, and MCP config |
| **Slash Commands** | [`.claude/commands/`](file:///D:/PredectiveIntelligenceSystem/.claude/commands/) | Operational shortcuts (`/network-health`, `/check-pipeline`, `/explain-grid`, `/review-anomaly`, `/test-api`) |

---

## 5. Development & Operational Commands

### Backend (FastAPI)
```bash
cd backend
python -m venv venv
venv\Scripts\activate            # Windows
# or: source venv/bin/activate    # Linux/Mac
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```
- API Documentation: `http://localhost:8000/docs`
- Health check: `GET http://localhost:8000/health`
- Note: Endpoints require `X-API-Key: secret-key-change-in-production` (or `test-key`).

### Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev                      # Dev server on http://localhost:5173
npm run build                    # Production bundle
```

### ML Matrix Cache Rebuilding
When underlying database records change or models are retrained, regenerate the 10,000-cell prediction cache:
```bash
python -c "from ml_model import get_predictor; from database import SessionLocal; p = get_predictor(); db = SessionLocal(); ..."
```

---

## 6. Critical Engineering Gotchas & Conventions

1. **Chronological Sorting for ML Feature Transformation**:
   - `DataPreprocessor.transform()` in `DataAnalysis/preprocessor.py` computes rolling features (e.g. 3h, 6h, 24h rolling means).
   - Input DataFrames **must be sorted in strictly ascending chronological order** (`.sort_values(["date", "hour"])`).
   - If input is descending, rolling windows will produce all `NaN` values and the preprocessor will drop all rows.
2. **LightGBM Categorical `grid_id` Encoding**:
   - `grid_id` was categorical-encoded as **strings** during training (e.g., `"1"`, `"4365"`).
   - In `backend/ml_model.py`, `grid_id` must be re-encoded as a pandas `Categorical` matching the bundle's `grid_categories` before calling `predict_proba`.
3. **10,000-Cell Grid Matrix Caching**:
   - Scoring all 10,000 cells dynamically takes ~10 seconds.
   - `backend/routes.py` serves `/api/grid-matrix` from `backend/grid_matrix_cache.json` for sub-10ms response times.
4. **Database Connection Pooling**:
   - Use `get_db` FastAPI dependency for database sessions (`backend/database.py`).
   - Always close or yield sessions properly to prevent connection exhaustion.

---

## 7. Model Context Protocol (MCP) Server & Agent Tooling

The platform includes a dedicated Model Context Protocol (MCP) server in [`mcp_server/server.py`](file:///D:/PredectiveIntelligenceSystem/mcp_server/server.py) providing standardized tool access for external LLM agents (Claude Desktop, Claude Code, Antigravity).

### Thin-Wrapper Architecture & Zero Business Logic Invariant
- **Zero Business Logic Rule**: The MCP layer contains NO calculations, aggregations, thresholding, or statistical interpretation. If a metric or calculation is needed, it must be implemented in the backend REST API.
- **Strict Parameter Validation & Constraints**: Validates `grid_id` (integer 1–10,000), `limit` (integer 1–1,000), `severity` (`LOW`, `MEDIUM`, `HIGH`), ISO-8601 timestamps, and enforces URL scheme/SSRF protection.
- **Transports**: Standard I/O (`stdio`, default for Claude Desktop) and Server-Sent Events (`sse`, `--port 8001`).

### Tool Inventory

| Tool Name | Backend Endpoint | Description | Key Parameters |
|---|---|---|---|
| `network_summary` | `GET /network/summary` | High-level telemetry summary, active cell count, peak hour, and top cell | `as_of` (optional ISO-8601) |
| `grid_activity` | `GET /network/grid/{grid_id}` | Trailing 24-hour activity timeseries for a cell (total, sms, calls, internet) | `grid_id` (1–10,000), `as_of`, `date`, `hour` |
| `grid_features` | `GET /network/grid/{grid_id}/features` | Engineered ML telemetry features (rolling averages, lag metrics, baseline ratios) | `grid_id` (1–10,000), `as_of` |
| `grid_location` | `GET /network/grid/{grid_id}/location` | Spatial coordinates (centroid lat/lon), polygon ring boundaries, and sector | `grid_id` (1–10,000) |
| `hotspots` | `GET /network/hotspots` | Leaderboard of grid cells ranked by total activity volume | `limit` (1–1,000, default 10), `severity`, `as_of` |
| `alerts` | `GET /network/alerts` | Active rule-based and statistical anomaly alerts | `limit` (1–1,000, default 50), `severity`, `as_of` |
| `pipeline_status` | `GET /pipeline/status` | ETL ingestion status, staleness duration, and rejected batch details | *(None)* |

### Test & Execution Commands
```bash
# Run standalone stdio server
python -m mcp_server.server

# Run test suite across all 7 tools
python mcp_server/test_server.py
```

---

## 8. Lifecycle Hooks & Safety Guardrails

Automated Antigravity lifecycle hooks configured in [`.agents/hooks.json`](file:///D:/PredectiveIntelligenceSystem/.agents/hooks.json) protect against pipeline misconfigurations and silent data corruption:

1. **Pre-Edit Airflow & Pipeline Guard (`airflow-pipeline-guard`)**:
   - Trigger: `PreToolUse` on `replace_file_content` and `write_to_file`.
   - Implementation: [`.agents/hooks/pre_edit_guard.py`](file:///D:/PredectiveIntelligenceSystem/.agents/hooks/pre_edit_guard.py).
   - Behavior: Detects edits targeting `flow/airflow_home/`, `flow/sql_ingestion/`, `ingestion_dag.py`, or pipeline configurations. Returns `{"decision": "force_ask"}` to mandate explicit user confirmation prior to modifying pipeline orchestration code. Non-pipeline files return `{"decision": "allow"}`.
2. **Post-Edit Spark/ML Regression Guard (`spark-ml-regression-guard`)**:
   - Trigger: `PostToolUse` on `replace_file_content` and `write_to_file`.
   - Implementation: [`.agents/hooks/post_edit_test.py`](file:///D:/PredectiveIntelligenceSystem/.agents/hooks/post_edit_test.py) using shared checks in [`.agents/hooks/common.py`](file:///D:/PredectiveIntelligenceSystem/.agents/hooks/common.py).
   - Behavior: Automatically executes two critical tests whenever code under `flow/spark/` or `DataAnalysis/` is modified:
     - **Analytics Grain Uniqueness Check**: Queries the operational grain `(date, hour, grid_id)` on `hourly_grid_summary` for `MAX(date)` (`2013-11-07`) to verify 0 duplicate records.
     - **ML2 Feature Leakage Test**: Validates that all lag and rolling window features in `DataAnalysis/preprocessor.py` are strictly backward-looking ($t-1, t-2, \dots$) and contain no target or future-period leakage.
3. **Execution Audit Logging**:
   - Every hook execution (timestamp, tool, target path, outcome, pass/fail status) is appended to [`.agents/logs/hooks.log`](file:///D:/PredectiveIntelligenceSystem/.agents/logs/hooks.log).

---

## 9. Team Customization Plugin (`telecom-conventions`) & Slash Commands

Project standards, domain guardrails, and diagnostic skills are packaged as an installable plugin in [`.agents/plugins/telecom-conventions/`](file:///D:/PredectiveIntelligenceSystem/.agents/plugins/telecom-conventions/plugin.json).

### Packaged Slash Commands

| Command | Definition File | Primary Skill / Purpose |
|---|---|---|
| `/network-health` | [`.claude/commands/network-health.md`](file:///D:/PredectiveIntelligenceSystem/.claude/commands/network-health.md) | Audits grain uniqueness `(date, hour, grid_id)`, spatial bounds (1–10,000), and activity sanity |
| `/check-pipeline` | [`.claude/commands/check-pipeline.md`](file:///D:/PredectiveIntelligenceSystem/.claude/commands/check-pipeline.md) | Evaluates ETL freshness, ingestion latency, and dead-letter quarantine batches |
| `/explain-grid` | [`.claude/commands/explain-grid.md`](file:///D:/PredectiveIntelligenceSystem/.claude/commands/explain-grid.md) | Deep-dive single-cell diagnostic analyzing 24h trend, modality breakdown, and surge probability |
| `/review-anomaly` | [`.claude/commands/review-anomaly.md`](file:///D:/PredectiveIntelligenceSystem/.claude/commands/review-anomaly.md) | Investigates active rule alerts and multidimensional statistical deviations |
| `/test-api` | [`.claude/commands/test-api.md`](file:///D:/PredectiveIntelligenceSystem/.claude/commands/test-api.md) | Executes the backend REST API test suite, validating endpoints and latency contracts |

### Plugin Architecture & Manifest
- **Manifest**: [`.agents/plugins/telecom-conventions/plugin.json`](file:///D:/PredectiveIntelligenceSystem/.agents/plugins/telecom-conventions/plugin.json) declares rules, skills, slash commands, hooks, and approved MCP server definitions.
- **Domain Invariant Rules**: Bundles [`.agents/plugins/telecom-conventions/rules/AGENTS.md`](file:///D:/PredectiveIntelligenceSystem/.agents/plugins/telecom-conventions/rules/AGENTS.md) enforcing the non-negotiable terminology safeguard: high activity must never be termed congestion.
- **MCP Configuration**: Provides [`.agents/plugins/telecom-conventions/mcp_config.json`](file:///D:/PredectiveIntelligenceSystem/.agents/plugins/telecom-conventions/mcp_config.json) for instant IDE/agent binding.
- **Ownership & Versioning**: Maintained by the Telecom Data Intelligence Platform Team under Semantic Versioning (`MAJOR.MINOR.PATCH`).

