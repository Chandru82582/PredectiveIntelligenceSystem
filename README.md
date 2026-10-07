# Telecom Italia Milan Predictive Intelligence & Anomaly Monitoring Platform

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Apache Spark 3.x](https://img.shields.io/badge/Apache_Spark-3.x-E25A1C.svg)](https://spark.apache.org/)
[![Apache Airflow](https://img.shields.io/badge/Apache_Airflow-2.x-017CEE.svg)](https://airflow.apache.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB.svg)](https://reactjs.org/)
[![Vite](https://img.shields.io/badge/Vite-5.x-646CFF.svg)](https://vitejs.dev/)
[![Anthropic Claude](https://img.shields.io/badge/Anthropic-Claude_3.5_Sonnet-D97757.svg)](https://www.anthropic.com/)

A production-ready Big Data and Predictive Intelligence platform for telecommunications activity across the Milan metropolitan area (100x100 grid, 10,000 cells). Built on the **Telecom Italia Open Big Data** dataset (November 1–7, 2013), the platform provides end-to-end distributed data processing, automated pipeline orchestration, machine learning prediction of network activity surges, an interactive high-density NOC visualization dashboard, and an autonomous NOC Copilot powered by Anthropic's Claude.

---

## Table of Contents

- [1. Executive Summary](#1-executive-summary)
- [2. System Architecture](#2-system-architecture)
- [3. Domain Invariants &amp; Schema Design](#3-domain-invariants--schema-design)
  - [Raw Grain vs. Analytics Grain](#raw-grain-vs-analytics-grain)
  - [Activity Measure Semantics](#activity-measure-semantics)
  - [High Activity vs. Confirmed Congestion](#high-activity-vs-confirmed-congestion)
  - [Geographic Coordinate System](#geographic-coordinate-system)
  - [The AS_OF Temporal Convention](#the-as_of-temporal-convention)
- [4. Repository Structure](#4-repository-structure)
- [5. Component Inventory](#5-component-inventory)
- [6. End-to-End Data Pipeline](#6-end-to-end-data-pipeline)
  - [PySpark ETL (`telecom_pipeline.py`)](#pyspark-etl-telecom_pipelinepy)
  - [Airflow Orchestration (`ingestion_dag.py`)](#airflow-orchestration-ingestion_dagpy)
  - [Storage &amp; Star Schema](#storage--star-schema)
- [7. Predictive Machine Learning](#7-predictive-machine-learning)
  - [High Activity Predictor (LightGBM)](#high-activity-predictor-lightgbm)
  - [Feature Engineering Pipeline](#feature-engineering-pipeline)
  - [High-Density 10,000-Cell Matrix Cache](#high-density-10000-cell-matrix-cache)
- [8. Claude Autonomous NOC Copilot](#8-claude-autonomous-noc-copilot)
- [9. Frontend Dashboard (React + Canvas + Leaflet)](#9-frontend-dashboard-react--canvas--leaflet)
- [10. Quickstart &amp; Installation](#10-quickstart--installation)
  - [Prerequisites](#prerequisites)
  - [Environment Configuration](#environment-configuration)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
  - [Data Pipeline Execution](#data-pipeline-execution)
- [11. API Specification](#11-api-specification)
- [12. Testing &amp; Quality Assurance](#12-testing--quality-assurance)
- [13. Model Context Protocol (MCP) Server](#13-model-context-protocol-mcp-server)
  - [Thin Wrapper Architecture &amp; Zero Business Logic](#thin-wrapper-architecture--zero-business-logic)
  - [MCP Tool Catalog](#mcp-tool-catalog)
  - [Claude Desktop Configuration](#claude-desktop-configuration)
  - [Running the MCP Server &amp; Verification](#running-the-mcp-server--verification)
- [14. Automated Lifecycle Hooks &amp; Safety Guardrails](#14-automated-lifecycle-hooks--safety-guardrails)
  - [Pre-Edit Airflow &amp; Pipeline Guard](#pre-edit-airflow--pipeline-guard)
  - [Post-Edit Spark &amp; ML Regression Guard](#post-edit-spark--ml-regression-guard)
  - [Hook Execution Audit Logs](#hook-execution-audit-logs)
- [15. Team Customization Plugin (`telecom-conventions`)](#15-team-customization-plugin-telecom-conventions)
  - [Plugin Architecture &amp; Manifest](#plugin-architecture--manifest)
  - [Operational Slash Commands](#operational-slash-commands)
  - [Clean Environment Verification](#clean-environment-verification)
  - [Versioning &amp; RACI Ownership Model](#versioning--raci-ownership-model)
- [License &amp; Dataset Attribution](#license--dataset-attribution)

---

## 1. Executive Summary

Telecommunication networks generate millions of spatial-temporal events every hour. Traditional Network Operations Centers (NOCs) struggle with retrospective alarms, siloed metrics, and unscalable visual displays.

This platform bridges the gap between raw telco event streams and actionable operations intelligence:

- **Scalable Aggregation**: Ingests raw 10-minute multi-country CDR records, rolling them up into hourly grid summaries for 10,000 spatial cells across Milan.
- **Predictive Risk Assessment**: Employs a trained LightGBM gradient-boosted tree model to forecast next-hour activity surges ($\ge 1.5\times$ intra-day baseline) with high precision.
- **Interactive High-Density Visualization**: Renders an interactive 100x100 cell canvas matrix providing instantaneous spatial visibility over all 10,000 cells without browser DOM lag.
- **Autonomous NOC AI Agent**: Features Claude 3.5 Sonnet equipped with operational tool calling, dynamic prompt composition, and multi-turn diagnostic reasoning.

---

## 2. System Architecture

```
                                    LANDING DATA
                     data/sms-call-internet-mi-2013-11-*.txt
                                         │
                                         ▼
        	1                        PYSPARK ETL ENGINE
                        flow/spark/telecom_pipeline.py
                ┌────────────────────────┴────────────────────────┐
                ▼                                                 ▼
        QUARANTINE / DEAD-LETTER                         CURATED PARQUET TABLES
       (Negative values, malformed)                   (Hourly aggregates, Daily rollups)
                                                                  │
                                                                  ▼
                                                          APACHE AIRFLOW DAG
                                                    flow/dags/ingestion_dag.py
                                                                  │
                                                                  ▼
                                                      DATABASE STORAGE LAYER
                                                    MySQL / TimescaleDB / SQLite
                                                   (hourly_grid_summary, etc.)
                                                                  │
                                                                  ▼
                                                          FASTAPI BACKEND
                                                         backend/routes.py
                                         ┌────────────────────────┴────────────────────────┐
                                         ▼                                                 ▼
                               ML PREDICTIVE ENGINE                               CLAUDE NOC COPILOT
                           backend/ml_model.py (LightGBM)                      backend/claude_agent.py
                                         │                                                 │
                                         └────────────────────────┬────────────────────────┘
                                                                  ▼
                                                       REACT 18 SPA DASHBOARD
                                              frontend/ (Vite, Canvas 100x100, Leaflet)
```

---

## 3. Domain Invariants & Schema Design

To ensure scientific accuracy and prevent misleading operational metrics, the platform strictly adheres to five core domain rules:

### Raw Grain vs. Analytics Grain

- **Raw Landing Grain**: `(datetime, Square_id, Country_code)` sampled at **10-minute intervals**.
- **Analytics Grain**: **Exactly one record per grid cell per 1-hour timestamp after country-code aggregation** `(date, hour, grid_id)`. All 10-minute intervals within the hour and all country codes are summed.

### Activity Measure Semantics

- Telecommunication telemetry fields (`sms_in`, `sms_out`, `call_in`, `call_out`, `internet_traffic_activity`, `total_activity`) represent **normalized, dimensionless activity measures** defined by Telecom Italia.
- **NEVER refer to these values as counts** (e.g., "number of calls", "number of SMS") **or byte volumes** (e.g., "megabytes", "gigabytes").

### High Activity vs. Confirmed Congestion

- High activity values **MUST NEVER be described as confirmed congestion**.
- The Telecom Italia dataset measures customer demand activity, not physical radio link metrics (e.g., Physical Resource Blocks, carrier-to-interference ratios, packet drops, or backhaul capacity). High activity must be termed **"activity surge"**, **"volume spike"**, **"elevated demand"**, or **"activity risk"**.

### Geographic Coordinate System

- Milan is divided into an exact $100 \times 100$ lattice of 10,000 square grid cells ($235\text{m} \times 235\text{m}$ each).
- When joining spatial GeoJSON features (`milano-grid.geojson`), **ALWAYS join on `properties.cellId`** (1-indexed, integers 1 through 10,000).
- **NEVER use the 0-based feature index or feature ID** (which is offset by 1).
- Formula: $\text{grid\_id} = (\text{row} \times 100) + \text{col} + 1$, where row 0 = South, row 99 = North, col 0 = West, col 99 = East.

### The `AS_OF` Temporal Convention

- The dataset represents a historical snapshot (November 1–7, 2013).
- The system operates under the **`AS_OF` temporal convention**: "now" defaults to the maximum timestamp present in the database (`2013-11-07 23:00`), or an explicit user-supplied query parameter. The system never compares timestamps to the host machine's wall-clock time (`datetime.utcnow()`).

---

## 4. Repository Structure

```
PredectiveIntelligenceSystem/
├── flow/                           # Orchestration & Data Engineering
│   ├── airflow_home/               # Airflow configurations and orchestration
│   │   ├── dags/
│   │   │   └── ingestion_dag.py    # Master pipeline DAG
│   │   ├── airflow.cfg             # Airflow configuration
│   │   └── webserver_config.py     # Airflow webserver settings
│   ├── spark/                      # Distributed PySpark processing
│   │   ├── telecom_pipeline.py     # Cleans, aggregates, rolls up, and validates data
│   │   └── .env.spark              # Spark environment defaults
│   └── sql_ingestion/              # Relational schemas, loaders, and DDL
│       ├── 05_mysql_create_tables.sql # MySQL production schema
│       ├── mysql_ingestion.py      # Batch loader with connection pooling
│       └── README.md               # Star schema technical documentation
├── DataAnalysis/                   # ML Research, Feature Engineering & Notebooks
│   ├── models/
│   │   └── lgbm_high_activity_v3.joblib # Production LightGBM model bundle (v3, v2, v1)
│   ├── preprocessor.py             # Feature engineering transformer (rolling lags)
│   ├── train.py                    # Model training, hyperparameter tuning & evaluation
│   ├── cleaner_spark.py            # Data cleaning utilities
│   └── notebooks/                  # Exploratory and prototyping notebooks
├── backend/                        # FastAPI REST API & AI Copilot
│   ├── main.py                     # FastAPI entrypoint, middleware & routing
│   ├── routes.py                   # REST endpoints (/summary, /predict, /grid-matrix, etc.)
│   ├── ml_model.py                 # In-memory ML inference runner & categorical handler
│   ├── claude_agent.py             # Claude NOC Copilot Agent with tool calling
│   ├── database.py                 # SQLAlchemy ORM models & session manager
│   ├── schemas.py                  # Pydantic request/response validation schemas
│   ├── rules.py                    # Rule-based anomaly detection engines
│   ├── auth.py                     # API key authentication middleware
│   └── grid_matrix_cache.json      # Precomputed 10,000-cell prediction cache
├── frontend/                       # React 18 + Vite Frontend Application
│   ├── src/
│   │   ├── App.jsx                 # Application shell, navigation & filters
│   │   ├── index.css               # Global styling, Tailwind tokens, scrollbar styling
│   │   ├── views/                  # Primary application views
│   │   │   ├── NetworkOverview.jsx # Executive NOC dashboard & 100x100 matrix
│   │   │   ├── GridInvestigator.jsx# Deep-dive single-cell spatial & temporal analysis
│   │   │   ├── DataExplorer.jsx    # Tabular SQL record explorer
│   │   │   └── ClaudeAssistant.jsx # Interactive conversational NOC Copilot
│   │   ├── components/             # Reusable UI components
│   │   │   ├── GridMatrix100.jsx   # HTML5 Canvas 10,000-cell interactive grid
│   │   │   ├── GeographicHeatmap.jsx# Leaflet GeoJSON choropleth map
│   │   │   ├── ActivityPrediction.jsx # Next-hour probability gauge & sparkline
│   │   │   ├── AnomalyFeed.jsx     # Real-time alert streamer
│   │   │   └── TrafficDynamics.jsx # Modality breakdown charts
│   │   └── services/
│   │       └── api.js              # Axios API client with error handling
│   └── package.json                # Frontend dependencies
├── mcp_server/                     # Model Context Protocol (MCP) server for external LLMs
│   ├── server.py                   # FastMCP stdio/SSE server (7 thin wrappers, zero business logic)
│   ├── test_server.py              # Automated MCP endpoint & tool verification suite
├── agent/                          # Multi-agent NOC Copilot system (Supervisor & specialists)
│   ├── runbooks/                   # Domain runbooks (api-review, telecom-data-quality, etc.)
│   └── slash_commands.py           # Runtime command execution engine
├── .claude/                        # Claude Code slash command configurations
│   └── commands/                   # /network-health, /check-pipeline, /explain-grid, etc.
├── data/                           # Landing directory for raw TSV/CSV files & GeoJSON
├── report/                         # Daily summary CSVs and alert export artifacts
├── report_spark/                   # Parquet analytical exports from Spark jobs
├── CLAUDE.md                       # LLM operational guidelines and repo invariants
└── README.md                       # Project documentation
```

---

## 5. Component Inventory

| Component                        | Technology              | Primary Location                                  | Key Function                                                                 |
| -------------------------------- | ----------------------- | ------------------------------------------------- | ---------------------------------------------------------------------------- |
| **Data Cleaning & Rollup** | PySpark                 | [`flow/spark/telecom_pipeline.py`](file:///D:/PredectiveIntelligenceSystem/flow/spark/telecom_pipeline.py) | Ingests 10-min records, rolls up to 1-hr, sums country codes, joins geometry |
| **Pipeline DAG**           | Apache Airflow          | [`flow/airflow_home/dags/ingestion_dag.py`](file:///D:/PredectiveIntelligenceSystem/flow/airflow_home/dags/ingestion_dag.py) | Orchestrates Spark ETL, Parquet creation, and database loading               |
| **Database Layer**         | MySQL / SQLAlchemy      | [`backend/database.py`](file:///D:/PredectiveIntelligenceSystem/backend/database.py) | Stores `hourly_grid_summary`, `enriched_spatial_hourly`, `grid_summary` |
| **API Web Service**        | FastAPI / Uvicorn       | [`backend/main.py`](file:///D:/PredectiveIntelligenceSystem/backend/main.py), [`routes.py`](file:///D:/PredectiveIntelligenceSystem/backend/routes.py) | Serves REST endpoints for dashboards, charts, alerts, and predictions        |
| **ML Inference Runner**    | LightGBM / Joblib       | [`ml/predict.py`](file:///D:/PredectiveIntelligenceSystem/ml/predict.py) | Dynamically loads highest available model (`lgbm_high_activity_v3.joblib`), runs next-hour inference |
| **Feature Transformer**    | Pandas / NumPy          | [`DataAnalysis/preprocessor.py`](file:///D:/PredectiveIntelligenceSystem/DataAnalysis/preprocessor.py) | Computes trailing rolling averages, lags, intra-day baselines                |
| **NOC AI Copilot**         | Anthropic Python SDK    | [`backend/claude_agent.py`](file:///D:/PredectiveIntelligenceSystem/backend/claude_agent.py) | Claude 3.5 Sonnet agent with dynamic system prompt and DB tool calls         |
| **100x100 Grid Matrix**    | HTML5 Canvas / React    | [`frontend/src/components/GridMatrix100.jsx`](file:///D:/PredectiveIntelligenceSystem/frontend/src/components/GridMatrix100.jsx) | High-performance canvas rendering of 10,000 cells with interactive tooltips  |
| **Spatial Heatmap**        | Leaflet / React-Leaflet | [`frontend/src/components/GeographicHeatmap.jsx`](file:///D:/PredectiveIntelligenceSystem/frontend/src/components/GeographicHeatmap.jsx) | Geographic choropleth map over Milan boundaries                              |
| **API Client**             | Axios                   | [`frontend/src/services/api.js`](file:///D:/PredectiveIntelligenceSystem/frontend/src/services/api.js) | HTTP client with automatic `X-API-Key` headers and parameter encoding       |
| **MCP Server**             | FastMCP / Python        | [`mcp_server/server.py`](file:///D:/PredectiveIntelligenceSystem/mcp_server/server.py) | FastMCP server exposing 7 thin wrapper tools with zero business logic       |
| **Domain Runbooks**        | Markdown / Runbooks    | [`agent/runbooks/`](file:///D:/PredectiveIntelligenceSystem/agent/runbooks/) | Specialized domain runbooks for data quality, pipeline troubleshooting, and anomalies |
| **Operational Slash Commands** | Claude Markdown Commands| [`.claude/commands/`](file:///D:/PredectiveIntelligenceSystem/.claude/commands/) | Operational slash commands (`/network-health`, `/check-pipeline`, `/explain-grid`, etc.) |


---

## 6. End-to-End Data Pipeline

### PySpark ETL (`telecom_pipeline.py`)

1. **Schema Standardization**: Casts incoming text fields to canonical types (`Square_id` $\to$ integer, `Time_interval` $\to$ timestamp, activity measures $\to$ double).
2. **Quality Validation & Quarantine**: Isolates records with negative activity or out-of-bound grid IDs ($< 1$ or $> 10000$) into `report_spark/quarantine/`.
3. **Temporal Rollup**: Groups 10-minute intervals into 1-hour slots (`date = to_date(timestamp)`, `hour = hour(timestamp)`).
4. **Country-Code Aggregation**: Computes the network-wide sum across all originating countries.
5. **Spatial Joining**: Enriches each record with the centroid coordinates (latitude/longitude) and sector labels derived from `data/milano-grid.geojson`.
6. **Curated Parquet Output**: Writes partitioned Parquet files to `report_spark/hourly_grid_summary/`.

### Airflow Orchestration (`ingestion_dag.py`)

The pipeline runs daily or hourly in Airflow:

- `validate_landing_files`: Verifies arrival and checksum of raw TSV files.
- `run_spark_pipeline`: Submits `telecom_pipeline.py` via `SparkSubmitOperator`.
- `stage_to_database`: Bulk loads curated Parquet output into MySQL using `mysql_ingestion.py`.
- `optimize_indexes`: Builds composite B-tree indices on `(date, hour, grid_id)` and `(total_activity)`.

### Storage & Star Schema

The relational database implements a high-performance analytics schema:

- **`dim_grid`**: 10,000 static rows holding centroid latitude, longitude, and sector tags.
- **`dim_time`**: 168 rows (for the 7-day period) capturing date, hour, day-of-week, and weekend flags.
- **`hourly_grid_summary`**: Primary fact table holding hourly `sms_in`, `sms_out`, `call_in`, `call_out`, `internet_activity`, and `total_activity`.
- **`grid_summary` / `daily_summary`**: Materialized rollups for fast historical baseline lookups.

---

## 7. Predictive Machine Learning

### High Activity Predictor (LightGBM)

The system trains a gradient-boosted decision tree (`lgbm_high_activity_v3.joblib`, dynamically loading the highest available version) to answer an essential operational question:

> *"Will this cell's activity during the upcoming hour exceed 1.5x its trailing intra-day baseline?"*

- **Target Variable**: Binary indicator `high_activity` ($\text{activity}_{t+1} \ge 1.5 \times \text{baseline}_t$).
- **Algorithm**: LightGBM Classifier with tuned tree depth, min-child-weight, and early stopping.
- **Validation**: Strict temporal split (training on Nov 1–5, validation on Nov 6, test on Nov 7) preventing lookahead bias.

### Feature Engineering Pipeline

The `DataPreprocessor` in `DataAnalysis/preprocessor.py` constructs a feature set per cell:

- **Lag Features**: Activity values at $t-1, t-2, t-3, t-6, t-12, t-24$ hours.
- **Rolling Windows**: 3-hour, 6-hour, and 24-hour rolling means, standard deviations, and min/max ranges.
- **Modality Ratios**: Proportions of SMS, voice calls, and Internet usage relative to total activity.
- **Intra-day Baseline**: Typical hourly activity for the specific cell during that hour of the day.

> [!IMPORTANT]
> **Ascending Chronological Sort Order Required**: `DataPreprocessor.transform()` calculates rolling windows sequentially. Input DataFrames **must be sorted in ascending chronological order** (`date ASC, hour ASC`). Descending sort orders result in all-NaN rolling features and complete data omission.

### High-Density 10,000-Cell Matrix Cache

Evaluating the LightGBM model dynamically across all 10,000 cells in a single web request requires significant CPU time (~8–12 seconds). To ensure instantaneous sub-10ms UI performance, the system maintains a precomputed matrix cache:

- **Location**: `backend/grid_matrix_cache.json`
- **Structure**: Pre-computed predicted high-activity flags, surge probabilities, and historical baselines for all 10,000 cells at the latest operational hour.
- **Fallback**: If the cache file is absent, `backend/routes.py` dynamically falls back to in-memory vectorized batch inference.

---

## 8. Claude Autonomous NOC Copilot

The platform integrates an autonomous NOC Copilot (`backend/claude_agent.py`) using Anthropic's Claude 3.5 Sonnet. Rather than acting as a static chatbot, the copilot acts as a specialized operations engineer.

### Dynamic Context-Aware System Prompt

The prompt is constructed dynamically at runtime, injecting:

- Current operational timestamp (`as_of` temporal convention).
- Data pipeline operational health, ingestion latency, and trustworthiness score.
- Active target cell telemetry (if the user is triaging a specific cell in the UI).
- Pre-loaded evidence context (current activity, baseline activity, ML anomaly scores, and rule alerts).

### Tool Calling Capabilities

Claude has access to backend tools to query live telemetry on demand:

1. `get_network_summary()`: Retrieves network-wide activity totals, active cell counts, and 24-hour trends.
2. `get_active_alerts(min_severity)`: Fetches open anomalies, sudden drops, and activity surges.
3. `get_grid_details(grid_id)`: Fetches trailing hourly activity history, modality breakdown, and baseline stats.
4. `predict_high_activity(grid_id)`: Evaluates the LightGBM model for a specified cell.
5. `get_anomaly_score(grid_id)`: Returns the current multi-dimensional anomaly score and deviation direction.
6. `get_pipeline_status()`: Verifies data pipeline latency and quarantine record counts.
7. `execute_db_query(sql_query)`: Executes safe read-only `SELECT` queries for custom investigations.

---

## 9. Frontend Dashboard (React + Canvas + Leaflet)

The UI is built with React 18 and Vite, organized into four specialized NOC views:

1. **Network Overview (`NetworkOverview.jsx`)**:
   - High-level KPIs: Active Cells, Total Activity, High-Activity Warning Count.
   - 24-Hour Trend Area Charts: Internet, Voice, and SMS breakdown over time.
   - **Interactive 100x100 Grid Matrix (`GridMatrix100.jsx`)**: An optimized HTML5 Canvas element mapping all 10,000 grid cells into a $100 \times 100$ visual lattice. Cells are color-coded (Red = Predicted High Activity Surge, Green = Normal, Grey = Inactive). Users can hover for instantaneous cell previews or click to trigger deep-dive diagnostic inspection cards.
   - Real-Time Anomaly Feed: Streaming list of open rule alerts with severity badges.
2. **Grid Investigator (`GridInvestigator.jsx`)**:
   - Dedicated diagnostic workbench for any selected cell (1 to 10,000).
   - Activity confidence bands, peak-hour dials, and modality decomposition bar charts.
   - Live predictive scoring card with probability progress meters.
3. **Data Explorer (`DataExplorer.jsx`)**:
   - Tabular inspector for database tables (`hourly_grid_summary`, `enriched_spatial_hourly`, `daily_summary`).
   - Paginated grid with search, date filtering, and CSV export.
4. **Claude Assistant (`ClaudeAssistant.jsx`)**:
   - Full-screen conversational NOC Copilot interface.
   - Supports markdown rendering, interactive diagnostic tables, and autonomous tool-call execution logs.

---

## 10. Quickstart & Installation

### Prerequisites

- **Python**: Version 3.9, 3.10, or 3.11
- **Node.js**: Version 18.x or 20.x
- **MySQL / MariaDB**: Version 8.0+ (or SQLite 3 for local development)
- **Apache Spark**: Version 3.4+ (optional, required only for running raw ETL)

### Environment Configuration

Create a `.env` file in the root directory:

```env
# Backend & API Configuration
API_KEY=secret-key-change-in-production
DATABASE_URL=mysql+mysqlconnector://root:root@localhost/telecom_activity
# For SQLite local development:
# DATABASE_URL=sqlite:///./telecom_activity.db

# Anthropic Claude API Key (Required for ClaudeAssistant)
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

### Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the FastAPI server
python -m uvicorn main:app --reload --port 8000
```

- API Docs: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/health`

### Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install Node dependencies
npm install

# Start the Vite development server
npm run dev
```

- Web Application: `http://localhost:5173`

### Data Pipeline Execution

To execute the PySpark processing pipeline on raw data:

```bash
cd flow/spark
spark-submit \
  --master "local[*]" \
  --driver-memory 4g \
  telecom_pipeline.py \
  --input-dir ../../data/ \
  --output-dir ../../report_spark/ \
  --geojson ../../data/milano-grid.geojson
```

---

## 11. API Specification

All `/api/*` endpoints require the `X-API-Key` header.

| Method   | Endpoint                   | Query Parameters                       | Description                                                               |
| -------- | -------------------------- | -------------------------------------- | ------------------------------------------------------------------------- |
| `GET`  | `/api/summary`           | `as_of` (ISO datetime)               | Returns network-wide KPIs, active cells, and 24-hour activity trend       |
| `GET`  | `/api/alerts`            | `min_severity`, `limit`, `as_of` | Returns active rule-based anomalies and surge alerts                      |
| `GET`  | `/api/hotspots`          | `limit`, `as_of`                   | Returns top cells ranked by total activity                                |
| `GET`  | `/api/grids/{grid_id}`   | `as_of`, `hours` (default 24)      | Returns trailing hourly activity history and modality breakdown           |
| `GET`  | `/api/predict/{grid_id}` | `as_of`                              | Runs LightGBM inference for the specified cell                            |
| `POST` | `/api/predict/batch`     | Body:`{ grid_ids: [...] }`           | Vectorized batch inference for a list of cells                            |
| `GET`  | `/api/grid-matrix`       | `as_of`                              | Returns status and probabilities for all 10,000 cells (served from cache) |
| `POST` | `/api/chat`              | Body:`ChatRequest`                   | Submits user prompt to Claude NOC Copilot with tool calling               |
| `GET`  | `/api/chat/history`      | `session_id`                         | Retrieves persistent conversation history                                 |
| `GET`  | `/api/data/{table_name}` | `page`, `page_size`, `sort_by`   | Paginated tabular records for DataExplorer                                |

---

## 12. Testing & Quality Assurance

### Preprocessor & Inference Integrity

Verify that the ML feature pipeline produces valid non-null outputs:

```bash
python -c "
from backend.ml_model import get_predictor
p = get_predictor()
print('Model bundle loaded successfully. Features:', len(p.feature_names))
"
```

### 100x100 Matrix Integrity

Ensure that all 10,000 cells are mapped accurately to the grid:

```bash
python -c "
import json
with open('backend/grid_matrix_cache.json') as f:
    data = json.load(f)
assert data['total_grids'] == 10000, f'Expected 10000 grids, got {data[\"total_grids\"]}'
print('Matrix cache verified: 10,000 cells present.')
"
```

---

## 13. Model Context Protocol (MCP) Server

The platform features an official Model Context Protocol (MCP) server located in [`mcp_server/`](file:///D:/PredectiveIntelligenceSystem/mcp_server/) that provides standardized, tool-based API access for Anthropic's Claude Desktop, Claude Code, and autonomous AI agents.

### Thin Wrapper Architecture & Zero Business Logic

The MCP server ([`mcp_server/server.py`](file:///D:/PredectiveIntelligenceSystem/mcp_server/server.py)) is implemented using FastMCP and strictly follows the **Thin Wrapper Pattern**:

- **Zero Business Logic Invariant**: The MCP server never computes, aggregates, thresholds, or interprets telemetry data. All metrics, spatial operations, baseline evaluations, and risk scoring are delegated exclusively to the backend REST API endpoints (`/network/*` and `/pipeline/*`). If a new calculation is needed, it must be added to the backend API rather than the MCP layer.
- **Strict Parameter Validation**: Validates all client inputs before request forwarding:
  - `grid_id`: Constrained strictly to integers between `1` and `10000`.
  - `limit`: Constrained to integers between `1` and `1000`.
  - `severity`: Whitelisted to `LOW`, `MEDIUM`, or `HIGH`.
  - `as_of`: Verified against ISO-8601 extended format (`YYYY-MM-DDTHH:MM:SS`).
- **Security & SSRF Guardrails**: Target backend base URL is strictly validated (`http`/`https` scheme validation, loopback/private IP whitelisting, header injection prevention).

### MCP Tool Catalog

The server exposes 7 standard tools:

| Tool Name | Wrapped REST Endpoint | Description | Arguments & Types |
|---|---|---|---|
| `network_summary` | `GET /network/summary` | High-level Milan telemetry summary, active cell count, peak operational hour, and top cell by activity. | `as_of` (string, optional ISO-8601) |
| `grid_activity` | `GET /network/grid/{grid_id}` | Trailing 24-hour activity timeseries for a cell (total, sms, voice calls, internet telemetry). | `grid_id` (int, 1–10,000, required), `as_of` (string, optional), `date` (string, optional), `hour` (int, optional 0–23) |
| `grid_features` | `GET /network/grid/{grid_id}/features` | Engineered ML feature vector (trailing rolling averages, lags, intra-day baseline ratios). | `grid_id` (int, 1–10,000, required), `as_of` (string, optional) |
| `grid_location` | `GET /network/grid/{grid_id}/location` | Spatial coordinates (centroid latitude/longitude), polygon ring GeoJSON geometry, and operational sector tag. | `grid_id` (int, 1–10,000, required) |
| `hotspots` | `GET /network/hotspots` | Ranked leaderboard of grid cells with highest activity volumes across the metropolitan lattice. | `limit` (int, 1–1,000, default: 10), `severity` (string, optional), `as_of` (string, optional) |
| `alerts` | `GET /network/alerts` | Active rule-based anomalies and sudden activity surge notifications. | `limit` (int, 1–1,000, default: 50), `severity` (string, optional), `as_of` (string, optional) |
| `pipeline_status` | `GET /pipeline/status` | Ingestion pipeline health, operational staleness in minutes, and dead-letter quarantine batch metrics. | *(None)* |

### Claude Desktop Configuration

To connect Claude Desktop to the platform's MCP server, add the following entry to your `claude_desktop_config.json` (`%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "telecom-intelligence": {
      "command": "python",
      "args": [
        "D:\\PredectiveIntelligenceSystem\\mcp_server\\server.py"
      ],
      "env": {
        "PYTHONPATH": "D:\\PredectiveIntelligenceSystem",
        "TELECOM_API_URL": "http://localhost:8000",
        "TELECOM_API_KEY": "secret-key-change-in-production"
      }
    }
  }
}
```

### Running the MCP Server & Verification

```bash
# Run standalone stdio server (Claude Desktop default)
python -m mcp_server.server

# Run Server-Sent Events (SSE) server for remote agent networks
python -m mcp_server.server --transport sse --host 127.0.0.1 --port 8001

# Execute comprehensive MCP test suite across all 7 tools
python mcp_server/test_server.py
```

---

## 14. NOC Diagnostic Runbooks & Slash Commands

Operational runbooks and diagnostic workflows are maintained within [`agent/runbooks/`](file:///D:/PredectiveIntelligenceSystem/agent/runbooks) and exposed via interactive slash commands:

### Operational Slash Commands

The platform equips operators and LLM agents with 5 specialized operational shortcuts defined in [`.claude/commands/`](file:///D:/PredectiveIntelligenceSystem/.claude/commands/):

| Command | Markdown Definition | Bound Runbook | Operational Purpose |
|---|---|---|---|
| `/network-health` | [`.claude/commands/network-health.md`](file:///D:/PredectiveIntelligenceSystem/.claude/commands/network-health.md) | `telecom-data-quality` | Audits dataset grain uniqueness, 1–10,000 spatial bounds, coordinate integrity, and non-negative activity invariants. |
| `/check-pipeline` | [`.claude/commands/check-pipeline.md`](file:///D:/PredectiveIntelligenceSystem/.claude/commands/check-pipeline.md) | `pipeline-troubleshooting` | Checks ETL pipeline freshness, ingestion latency, and inspects `report_spark/quarantine/` for rejected records. |
| `/explain-grid` | [`.claude/commands/explain-grid.md`](file:///D:/PredectiveIntelligenceSystem/.claude/commands/explain-grid.md) | `network-anomaly-analysis` | Conducts a single-cell diagnostic analyzing 24h activity patterns, modality breakdown, and next-hour activity surge probability. |
| `/review-anomaly` | [`.claude/commands/review-anomaly.md`](file:///D:/PredectiveIntelligenceSystem/.claude/commands/review-anomaly.md) | `network-anomaly-analysis` | Investigates active rule alerts, threshold deviations, and sudden volume spikes across the lattice. |
| `/test-api` | [`.claude/commands/test-api.md`](file:///D:/PredectiveIntelligenceSystem/.claude/commands/test-api.md) | `api-review` | Executes the backend REST API test suite, validating endpoint contracts, HTTP status codes, and latency SLAs. |

### Operational Runbooks

The multi-agent NOC architecture in [`agent/`](file:///D:/PredectiveIntelligenceSystem/agent) dynamically leverages domain runbooks:
- **`telecom-data-quality`**: Enforces strict grain invariants `(date, hour, grid_id)`, spatial bounds (1–10,000), and non-negative activity invariants.
- **`pipeline-troubleshooting`**: Diagnoses batch rejection reasons, ETL staleness, and Airflow orchestration delays.
- **`network-anomaly-analysis`**: Investigates localized activity surges and statistical baseline deviations without mischaracterizing activity as confirmed congestion.
- **`api-review`**: Runs automated tests verifying endpoint status codes, response schemas, and latency SLAs.


---

## License & Dataset Attribution

The telecommunication dataset used in this platform is provided by **Telecom Italia** as part of the **Big Data Challenge Open Data initiative**. The dataset is distributed under the Open Database License (ODbL).

