# Railway Deployment -- Step by Step

Railway auto-detects the Dockerfile in the repo and builds/deploys from it. Here's the full walkthrough.

## Prerequisites

- A Railway account at [railway.app](https://railway.app) (free tier works for testing, $5/mo Hobby plan for production)
- The repo pushed to GitHub (it already is at `danieltgustafson/buildAI`)

## Step 1: Create a New Project

1. Go to [railway.app/dashboard](https://railway.app/dashboard)
2. Click **"New Project"**
3. Select **"Deploy from GitHub Repo"**
4. Connect your GitHub account if not already connected
5. Search for and select `danieltgustafson/buildAI`
6. Railway will auto-detect the `Dockerfile` and `railway.toml` and start building

## Step 2: Add a PostgreSQL Database

1. In your project dashboard, click **"+ New"** (top right)
2. Select **"Database" > "Add PostgreSQL"**
3. Railway provisions a managed Postgres instance in seconds
4. Click on the Postgres service and go to **"Variables"** tab
5. Copy the `DATABASE_URL` value (it looks like `postgresql://postgres:xxx@xxx.railway.internal:5432/railway`)

## Step 3: Configure Environment Variables

1. Click on your **API service** (the one built from the repo)
2. Go to the **"Variables"** tab
3. Click **"+ New Variable"** and add:

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | Paste the Postgres URL from Step 2. **Or** use the Railway variable reference: `${{Postgres.DATABASE_URL}}` |
| `SECRET_KEY` | Any random string, e.g. `railway-demo-secret-key-2024` |
| `ENVIRONMENT` | `production` |
| `PORT` | `8000` (Railway sets this automatically, but be explicit) |

Railway's variable reference (`${{Postgres.DATABASE_URL}}`) is the cleanest approach -- it auto-links the services.

## Step 4: Deploy

Railway auto-deploys when you push to GitHub or when you change variables. The build process:

1. Railway reads `railway.toml` and uses the `Dockerfile`
2. Builds the Docker image
3. Starts the container with `python -m scripts.start` (waits for DB, runs migrations, then boots API)
4. Runs the health check at `/health`

You should see the build logs in the Railway dashboard. First deploy takes 2-3 minutes.

## Step 5: Get Your Public URL

1. Click on your API service
2. Go to **"Settings"** tab
3. Under **"Networking"**, click **"Generate Domain"**
4. Railway gives you a URL like `https://buildai-production.up.railway.app`

Test it: visit `https://your-url.up.railway.app/docs` -- you should see the Swagger UI.

## Step 6: Seed Demo Data (optional)

Railway provides a shell you can use:

> Migrations already run at startup via `python -m scripts.start`, so tables should exist before the API serves traffic.
> Demo data is **not** auto-loaded; run the seed command only when you want sample data.

**Option A: Via Railway CLI**

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link to your project
railway link

# Run the seed script
railway run python -m scripts.seed_demo_data --reset

# Create Metabase views
railway run python -c "
from app.database import engine
with open('sql/views.sql') as f:
    sql = f.read()
with engine.connect() as conn:
    for statement in sql.split(';'):
        s = statement.strip()
        if s:
            conn.execute(conn.connection.cursor().execute(s))
    conn.commit()
print('Views created')
"
```

**Option B: Via the Railway Dashboard**

1. Click on your API service
2. Click the **"Shell"** tab (or "Deploy" > three dots > "Open Shell")
3. Run:
   ```bash
   python -m scripts.seed_demo_data --reset
   ```

## Step 7: (Optional) Add Metabase

For dashboards:

1. In your project, click **"+ New" > "Docker Image"**
2. Enter image: `metabase/metabase:latest`
3. Add environment variables:
   - `MB_DB_TYPE`: `postgres`
   - `MB_DB_HOST`: `${{Postgres.PGHOST}}` (or the internal hostname)
   - `MB_DB_PORT`: `5432`
   - `MB_DB_DBNAME`: `${{Postgres.PGDATABASE}}`
   - `MB_DB_USER`: `${{Postgres.PGUSER}}`
   - `MB_DB_PASS`: `${{Postgres.PGPASSWORD}}`
4. Generate a public domain for Metabase
5. Open it and walk through the Metabase setup wizard
6. Connect to the Postgres database using the Railway internal connection details

## Architecture on Railway

```
┌─────────────────────────────────────────┐
│  Railway Project                         │
│                                          │
│  ┌──────────┐   ┌──────────┐            │
│  │  API      │   │ Postgres │            │
│  │ (Docker)  │──▶│(managed) │            │
│  │ :8000     │   │ :5432    │            │
│  └──────────┘   └──────────┘            │
│       │                 ▲                │
│       │          ┌──────┘                │
│  ┌──────────┐   │                        │
│  │ Metabase  │──┘                        │
│  │ (Docker)  │                           │
│  │ :3000     │                           │
│  └──────────┘                            │
└─────────────────────────────────────────┘
```

## Costs

- **Hobby plan**: $5/mo, includes $5 of usage credits
- **API service**: ~$2-3/mo for a small container
- **Postgres**: ~$1-2/mo for the smallest instance
- **Metabase**: ~$2-3/mo for a small container
- **Total**: ~$5-8/mo (fits within the Hobby plan credits for light demo usage)

## Sharing with Your Client

Once deployed, share these URLs:

1. **API Swagger Docs**: `https://your-app.up.railway.app/docs`
   - They can try all endpoints interactively
   - Login with `admin`/`admin` to get a token

2. **Metabase Dashboards**: `https://your-metabase.up.railway.app`
   - Set up read-only viewer accounts for clients
   - Pre-build dashboards using `v_job_cost_summary`, `v_wip_report`, `v_exceptions`

## Troubleshooting

**Build fails**: Check that the `Dockerfile` is building correctly in the deploy logs. Common issue: missing `DATABASE_URL` variable.

**Can't connect to Postgres**: Make sure you're using `${{Postgres.DATABASE_URL}}` as the variable reference, not a hardcoded URL. Railway's internal networking requires the reference syntax.

**Seed script fails**: Make sure tables are created first. The seed script calls `Base.metadata.create_all()` which should handle this, but if you're using Alembic migrations you may need to run those first.

**Alembic log lines during startup**: Messages like `Context impl PostgresqlImpl.` and `Will assume transactional DDL.` are informational and expected.

### Clear demo data before switching to live data

If you want an empty schema (no sample rows), run one of:

```bash
# API route (admin token required)
DELETE /seed/demo

# or from Railway shell
python -c "from app.database import Base, engine; Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)"
```

### Browser upload UI

Use `https://<your-api-domain>/ui` for a simple built-in page to:
- login and store token
- seed/clear demo data
- upload ADP/QBO/Budget CSVs

