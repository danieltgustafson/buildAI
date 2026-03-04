# Deployment Guide -- Remote Demo Hosting

This guide covers how to deploy the Contractor Ops AI POC so a client can access and explore it without a screenshare.

## Recommended: Single EC2 Instance with Docker Compose

The fastest path to a client-accessible demo. One `t3.small` ($0.02/hr) or `t3.medium` runs everything.

### 1. Launch an EC2 Instance

- **AMI**: Amazon Linux 2023 or Ubuntu 22.04
- **Instance type**: `t3.small` (2 vCPU, 2 GB) is fine for demo; `t3.medium` if you want headroom
- **Storage**: 20 GB gp3
- **Security group**: Open ports `8000` (API), `3000` (Metabase), `22` (SSH)
- **Key pair**: Create or reuse one for SSH access

### 2. Install Docker

```bash
# Amazon Linux 2023
sudo dnf install -y docker
sudo systemctl start docker && sudo systemctl enable docker
sudo usermod -aG docker ec2-user

# Install Docker Compose plugin
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Log out and back in for group change
exit
```

### 3. Clone and Start

```bash
git clone https://github.com/danieltgustafson/buildAI.git
cd buildAI

# Start everything
docker compose up -d --build

# Wait ~30 seconds for Postgres to be ready, then seed demo data
docker compose exec api python -m scripts.seed_demo_data --reset

# Create the Metabase SQL views
docker compose exec postgres psql -U contractor_ops -d contractor_ops -f /docker-entrypoint-initdb.d/views.sql
```

### 4. Access

- **API + Swagger docs**: `http://<EC2-PUBLIC-IP>:8000/docs`
- **Metabase dashboards**: `http://<EC2-PUBLIC-IP>:3000`

### 5. Set Up Metabase (first time)

1. Open `http://<EC2-PUBLIC-IP>:3000`
2. Walk through Metabase setup wizard
3. When asked for database, select "I already have my data" and connect to:
   - **Type**: PostgreSQL
   - **Host**: `postgres` (Docker internal hostname)
   - **Port**: 5432
   - **Database**: `contractor_ops`
   - **User**: `contractor_ops`
   - **Password**: `contractor_ops_dev`
4. Create dashboards using the views:
   - `v_job_cost_summary` -- Job cost overview
   - `v_wip_report` -- WIP / earned value
   - `v_exceptions` -- Data quality flags

### 6. Optional: Add a Domain + HTTPS

For a more polished demo URL:

```bash
# Install Caddy (auto-HTTPS reverse proxy)
sudo dnf install -y caddy   # or apt install caddy

# Create /etc/caddy/Caddyfile
cat <<EOF | sudo tee /etc/caddy/Caddyfile
demo.yourcompany.com {
    handle /api/* {
        reverse_proxy localhost:8000
    }
    handle /* {
        reverse_proxy localhost:3000
    }
}
EOF

sudo systemctl start caddy
```

Point your DNS A record for `demo.yourcompany.com` to the EC2 public IP. Caddy auto-provisions HTTPS via Let's Encrypt.

---

## Alternative: Railway / Render (Zero-ops)

If you want to avoid managing an EC2 instance:

### Railway ($5/mo)

1. Push to GitHub
2. Go to [railway.app](https://railway.app), create a new project
3. Add services: **PostgreSQL** (managed) + **Docker** (from repo)
4. Set environment variables:
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}` (preferred) or `${{Postgres.DATABASE_PUBLIC_URL}}`
   - `SECRET_KEY` = some random string
5. Railway auto-deploys on push. This repo runs `alembic upgrade head` before starting the API so tables are created automatically.
6. Seed demo data once deployment is healthy:
   - `POST /seed/demo?reset=true` (admin token), or
   - open Railway service shell and run `python -m scripts.seed_demo_data --reset`
7. For Metabase, add a separate service using the `metabase/metabase` Docker image

**Railway Postgres notes**
- A URL like `.../railway` is normal; `railway` is the default database name Railway provisions.
- "relation does not exist" errors usually mean migrations were not run against the same `DATABASE_URL` the API is using.
- If you copy a URL manually and it begins with `postgres://`, this app now normalizes it automatically for SQLAlchemy.

### Render

1. Create a **Web Service** from the repo (Docker)
2. Create a **PostgreSQL** database
3. Set `DATABASE_URL` to Render's Postgres connection string
4. For Metabase, create another Web Service using `metabase/metabase` image

---

## Alternative: Fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Launch the API
fly launch --name contractor-ops-api --region ewr

# Create a Postgres cluster
fly postgres create --name contractor-ops-db --region ewr

# Attach the database
fly postgres attach contractor-ops-db --app contractor-ops-api

# Deploy
fly deploy
```

---

## Quick Cost Comparison

| Option | Monthly Cost | Setup Time | Maintenance |
|--------|-------------|------------|-------------|
| EC2 t3.small | ~$15 | 30 min | You manage |
| Railway | ~$10 | 15 min | Zero |
| Render | ~$15 | 15 min | Zero |
| Fly.io | ~$10 | 20 min | Minimal |

For a client demo that runs for a week or two, EC2 or Railway are the best bets. EC2 gives you the most control (and you can stop the instance when not demoing to save cost). Railway/Render are easier if you don't want to SSH into anything.

---

## Demo Walkthrough Script

Once deployed and seeded, walk the client through:

1. **API Swagger UI** (`/docs`)
   - Show `GET /jobs` -- all 8 demo jobs
   - Show `GET /jobs/{id}/summary` -- pick the Main St renovation
   - Show `GET /wip` -- WIP report across all active jobs
   - Show `GET /exceptions` -- data quality flags

2. **Metabase Dashboards**
   - Job Cost Summary dashboard (planned vs actual)
   - WIP Report dashboard (over/under billing)
   - Exceptions dashboard (flags needing attention)
   - Drill into individual jobs

3. **Key Talking Points**
   - "River Rd Roof is at 112% of budget -- flagged automatically"
   - "Parkview Facade margin is drifting below target"
   - "15 time entries need job mapping -- one-click resolution"
   - "All of this updates daily as payroll and QBO data flows in"
