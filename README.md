# Contractor Ops AI - Job Costing + WIP Platform

Near real-time visibility into job profitability and Work in Progress (WIP) for contractors. Combines labor data (ADP payroll/time exports), materials and subcontractors (QuickBooks Online), estimates/budgets, and billing progress into actionable job cost summaries and WIP reports.

## Architecture

```
ADP CSV ──┐                    ┌─── REST API (FastAPI)
           ├─► Ingestion ─► Postgres ─┤
QBO CSV ──┘    + Mapping       │       └─── Metabase Dashboards
                               │
Budget CSV ───────────────────►│
                               │
                    Cost Engine + WIP Engine
```

**Stack**: Python 3.11, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16, Metabase, Docker Compose

## Quick Start

### Using Docker Compose (recommended)

```bash
docker compose up --build
```

This starts:
- **API** at http://localhost:8000 (Swagger docs at `/docs`)
- **PostgreSQL** on port 5432
- **Metabase** at http://localhost:3000

### Local Development

```bash
# Create a virtual environment
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Set up environment
cp .env.example .env
# Edit .env with your Postgres connection string

# Run migrations
alembic upgrade head

# Create SQL views for Metabase
psql $DATABASE_URL -f sql/views.sql

# Start the API server
uvicorn app.main:app --reload
```

### Running Tests

```bash
pip install -e ".[dev]"
pytest -v
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/token` | Get JWT token (POC: admin/admin, ops/ops, viewer/viewer) |
| `POST` | `/ingest/adp` | Upload ADP payroll/time CSV |
| `POST` | `/ingest/qbo` | Upload QuickBooks transaction CSV |
| `POST` | `/ingest/budgets` | Upload budget/estimate CSV |
| `GET` | `/jobs` | List jobs (filters: status, customer, search) |
| `POST` | `/jobs` | Create a job |
| `GET` | `/jobs/{id}/summary` | Job cost summary: planned vs actual |
| `GET` | `/wip` | WIP report for all active jobs |
| `GET` | `/exceptions` | Data quality exceptions and flags |
| `POST` | `/exceptions/{id}/resolve` | Resolve an exception |
| `POST` | `/mappings` | Create source key to job mapping |
| `GET` | `/mappings` | List all mappings |
| `GET` | `/mappings/unresolved` | Unmapped source keys needing resolution |
| `POST` | `/seed/demo` | Seed database with demo data (admin only) |
| `DELETE` | `/seed/demo` | Clear all data (remove all rows, keep schema, admin only) |
| `GET` | `/ui` | Simple browser UI for login + CSV uploads + seeding |
| `POST` | `/research/building-systems` | AI-assisted building system age research by address or ZIP discovery mode |

Research endpoint uses an internal research-agent workflow with pluggable public-data tools. Current tools include OpenStreetMap Nominatim (address/metadata discovery) and Open-Meteo climate archive (context-aware stress signals) to drive flexible component age/risk determinations with explicit source strings.

Outbound public-data requests send a configurable `User-Agent` via `RESEARCH_USER_AGENT` to comply with provider usage policies and identify the calling app.

The service supports a true LLM-agent synthesis mode when `OPENAI_API_KEY` is configured: after data tools gather evidence, it calls the OpenAI Responses API (`OPENAI_RESEARCH_MODEL`) to produce component-level age/risk judgments from that evidence. If no API key is configured or the call fails, it falls back to deterministic rule-based scoring.

Full interactive docs available at `/docs` when the API is running.

## Data Flow

1. **Ingest**: Upload ADP time/payroll CSV and QBO transaction CSV via the API
2. **Map**: Resolve source keys (ADP project codes, QBO customer:job) to internal jobs via the mapping endpoints
3. **Compute**: Cost engine calculates burdened labor costs; WIP engine computes percent complete and earned revenue
4. **Report**: Query job cost summaries and WIP reports via the API or Metabase dashboards

## Key Computations

### Burdened Labor Cost
```
direct_cost = hours * pay_rate  (or use gross_pay if available)
burden_multiplier = 1 + FICA% + FUTA% + SUTA% + workers_comp%
burdened_cost = direct_cost * burden_multiplier + benefits_per_hour * hours
```

### WIP (Earned Value)
```
pct_complete = actual_total_cost / budget_total_cost  (capped at 120%)
earned_revenue = pct_complete * contract_value
over_under_billing = billed_to_date - earned_revenue
```

## Database Schema

Core tables: `jobs`, `employees`, `cost_codes`, `time_entries`, `gl_transactions`, `job_budgets`, `job_billing`, `job_mappings`, `labor_burden_rates`, `exceptions`, `job_daily_metrics`

Metabase views: `v_job_cost_summary`, `v_wip_report`, `v_exceptions`

## Demo Data & Client Presentation

To seed the database with realistic demo data (8 jobs, 15 employees, hundreds of time entries and transactions):

```bash
# Via CLI (after docker compose up)
docker compose exec api python -m scripts.seed_demo_data --reset

# Or via the API (requires admin token)
POST /seed/demo?reset=true
Authorization: Bearer <admin-token>
```

This creates:
- **8 contractor jobs** at various stages: active renovation, office build-out, electrical upgrade, roofing (overrun!), facade restoration, townhome development, HVAC retrofit (on hold), kitchen remodel (closed)
- **15 employees** across trades (foremen, electricians, plumbers, carpenters, laborers, etc.)
- **~400+ time entries** with burdened labor costs spread across 8 weeks
- **~80+ GL transactions** (materials, subcontractors, equipment rentals, permits)
- **Budgets** for every job with planned labor/material/sub costs
- **Billing records** showing progress invoicing
- **Job mappings** for ADP and QBO source keys
- **Exceptions**: unmapped entries, job overrun flags, margin drift warnings
- **Daily metric snapshots** for trend charts in Metabase

### Remote Hosting for Client Demo

See [docs/DEPLOY.md](docs/DEPLOY.md) for detailed instructions on deploying to:
- **EC2** (cheapest, most control) -- ~$15/mo, 30 min setup
- **Railway** (zero-ops) -- ~$10/mo, 15 min setup
- **Render** or **Fly.io** as alternatives


### Railway quick notes

- Set `DATABASE_URL` to Railway Postgres' provided variable (`${{Postgres.DATABASE_URL}}` preferred).
- The app startup runs `python -m scripts.start` (DB readiness check + migrations) so schema tables exist before requests are served.
- Logs like `Context impl PostgresqlImpl` and `Will assume transactional DDL` are normal Alembic startup messages.
- Demo data is **not** auto-populated on startup. You must seed explicitly via `POST /seed/demo?reset=true` or `python -m scripts.seed_demo_data --reset`.
- To clear demo data before loading live data: call `DELETE /seed/demo` (admin token) to remove all rows (schema stays).
- If you see "relation does not exist", verify both the API service and any seed command are using the exact same `DATABASE_URL`.
- Use `GET /ui` for a simple upload interface (login, seed/clear, ADP/QBO/Budget uploads).

## Metabase quick connect

1. Deploy a Metabase service (e.g. `metabase/metabase:latest`) on Railway.
2. In Metabase setup, add a PostgreSQL connection using the same Railway Postgres values used by the API.
3. Use database name from Railway (often `railway`) and SSL mode `require` when using public connection details.
4. Query these views for dashboards: `v_job_cost_summary`, `v_wip_report`, `v_exceptions`.
5. For Railway Metabase, set `MB_JETTY_PORT` to `${{PORT}}` (not `${PORT}`) to avoid startup `NumberFormatException`.
6. If Metabase URL shows 502, wait for first boot and verify logs include `Metabase Initialization COMPLETE` plus `MB_JETTY_PORT=${{PORT}}`.

## Sample CSV Files

The `sample_data/` directory includes example CSVs for testing ingestion:
- `adp_time_export.csv` - ADP time/payroll entries
- `qbo_transactions.csv` - QuickBooks Online transactions
- `budgets.csv` - Job budgets/estimates

## Exception Types

| Type | Description |
|------|-------------|
| `UNMAPPED_TIME_ENTRY` | ADP time entry with no job mapping |
| `UNMAPPED_TRANSACTION` | QBO transaction with no job mapping |
| `JOB_OVERRUN_RISK` | Job percent complete exceeds threshold |
| `MARGIN_DRIFT` | Actual margin below target |
| `DATA_INTEGRITY` | Duplicates, missing required fields |

## Project Structure

```
├── app/
│   ├── api/           # FastAPI route handlers
│   ├── models/        # SQLAlchemy ORM models
│   ├── schemas/       # Pydantic request/response models
│   ├── services/      # Business logic (ingestion, cost engine, WIP)
│   ├── auth.py        # JWT authentication (POC)
│   ├── config.py      # Settings via pydantic-settings
│   ├── database.py    # SQLAlchemy engine + session
│   └── main.py        # FastAPI app entry point
├── alembic/           # Database migrations
├── sql/               # Metabase views
├── sample_data/       # Example CSV files
├── scripts/           # CLI utilities (seed_demo_data.py)
├── docs/              # Deployment guides
├── tests/             # Pytest test suite
├── docker-compose.yml # Local dev stack
├── Dockerfile
└── pyproject.toml
```
