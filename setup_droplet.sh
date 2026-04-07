#!/bin/bash
# setup_droplet.sh — Provisions a Digital Ocean droplet for the Google Ads Agent
# Usage: curl -sSL https://raw.githubusercontent.com/SeanConway102/google-ads-agent-api/main/setup_droplet.sh | bash

set -e

echo "=== Google Ads Agent — Droplet Setup ==="
echo "Starting setup at $(date)"

# ── 1. System packages ────────────────────────────────────────────────────────
echo "[1/7] Updating system packages..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq

echo "[1/7] Installing Python 3.12, PostgreSQL, git, curl..."
sudo apt-get install -y -qq python3.12 python3.12-venv python3-pip postgresql postgresql-contrib git curl

# ── 2. PostgreSQL setup ──────────────────────────────────────────────────────
echo "[2/7] Configuring PostgreSQL..."
PG_PASSWORD="${PG_PASSWORD:-adsagent_pass}"

# Detect PostgreSQL version and config path
PG_VERSION=$(ls /etc/postgresql/ 2>/dev/null | sort -V | tail -1 || echo "14")
PG_CONF="/etc/postgresql/${PG_VERSION}/main/pg_hba.conf"

sudo -u postgres psql -c "CREATE USER adsagent WITH PASSWORD '${PG_PASSWORD}';" 2>/dev/null || echo "User adsagent may already exist"
sudo -u postgres psql -c "CREATE DATABASE ads_agent OWNER adsagent;" 2>/dev/null || echo "Database ads_agent may already exist"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ads_agent TO adsagent;" 2>/dev/null || true

# Enable password auth for PostgreSQL (needed for app connection)
if [ -f "$PG_CONF" ]; then
    sudo sed -i 's/local\s\+all\s\+all\s\+peer/local all all md5/' "$PG_CONF"
    sudo systemctl restart postgresql
else
    echo "  WARNING: PostgreSQL config not found at $PG_CONF. Ensure password auth is enabled."
fi

# ── 3. Clone and install app ──────────────────────────────────────────────────
echo "[3/7] Installing application..."
APP_DIR="${APP_DIR:-/opt/ads-agent}"

if [ -d "$APP_DIR/.git" ]; then
    echo "  Pulling latest from existing repo at $APP_DIR"
    cd "$APP_DIR" && sudo git pull
else
    echo "  Cloning fresh repo to $APP_DIR"
    sudo git clone https://github.com/SeanConway102/google-ads-agent-api.git "$APP_DIR"
fi

cd "$APP_DIR"
python3.12 -m venv venv
source venv/bin/activate

echo "  Installing Python dependencies..."
pip install --quiet -r requirements.txt

# ── 4. Apply DB schema ────────────────────────────────────────────────────────
echo "[4/7] Applying database schema..."
PGPASSWORD="$PG_PASSWORD" psql -h localhost -U adsagent -d ads_agent -f "$APP_DIR/src/db/schema.sql" || {
    echo "  WARNING: Schema apply failed. Ensure DATABASE_URL env var is set before running the app."
}

# ── 5. Environment variables ────────────────────────────────────────────────
echo "[5/7] Creating environment file..."
ENV_FILE="$APP_DIR/.env"
sudo tee "$ENV_FILE" > /dev/null <<EOF
# SECURITY WARNING: Change all CHANGE_ME values before running the agent!
ADMIN_API_KEY=${ADMIN_API_KEY:-CHANGE_ME}
DATABASE_URL=postgresql://adsagent:${PG_PASSWORD}@localhost:5432/ads_agent
DB_PROVIDER=postgresql
GOOGLE_ADS_DEVELOPER_TOKEN=${GOOGLE_ADS_DEVELOPER_TOKEN:-CHANGE_ME}
GOOGLE_ADS_CLIENT_ID=${GOOGLE_ADS_CLIENT_ID:-CHANGE_ME}
GOOGLE_ADS_CLIENT_SECRET=${GOOGLE_ADS_CLIENT_SECRET:-CHANGE_ME}
GOOGLE_ADS_REFRESH_TOKEN=${GOOGLE_ADS_REFRESH_TOKEN:-CHANGE_ME}
MINIMAX_API_KEY=${MINIMAX_API_KEY:-CHANGE_ME}
RESEARCH_CRON=${RESEARCH_CRON:-0 8 * * *}
MAX_DEBATE_ROUNDS=${MAX_DEBATE_ROUNDS:-5}
# HITL (Human-in-the-Loop) — email approval for high-impact proposals
HITL_ENABLED=${HITL_ENABLED:-true}
RESEND_API_KEY=${RESEND_API_KEY:-CHANGE_ME}
RESEND_INBOUND_SECRET=${RESEND_INBOUND_SECRET:-CHANGE_ME}
HITL_DEFAULT_EMAIL=${HITL_DEFAULT_EMAIL:-}
HITL_PROPOSAL_TTL_DAYS=${HITL_PROPOSAL_TTL_DAYS:-7}
HITL_WEEKLY_CRON=${HITL_WEEKLY_CRON:-0 9 * * 1}
EOF
chmod 600 "$ENV_FILE"
echo "  .env created at $ENV_FILE"
echo "  IMPORTANT: Edit $ENV_FILE and replace all CHANGE_ME values with real credentials!"

# ── 6. Cron job for daily research and weekly digest ─────────────────────────
echo "[6/7] Setting up cron jobs..."
# Daily research cycle — 8am server time
CRON_DAILY="0 8 * * * cd $APP_DIR && source venv/bin/activate && python scripts/run_research_cycle.py >> /var/log/ads-research.log 2>&1"
echo "$CRON_DAILY" | sudo tee /etc/cron.d/ads-research > /dev/null
sudo chmod 644 /etc/cron.d/ads-research
echo "  Daily research cron installed: 8am server time"

# Weekly digest — 9am UTC every Monday
CRON_WEEKLY="0 9 * * 1 cd $APP_DIR && source venv/bin/activate && python -m src.cron.weekly_digest >> /var/log/ads-weekly-digest.log 2>&1"
echo "$CRON_WEEKLY" | sudo tee /etc/cron.d/ads-weekly-digest > /dev/null
sudo chmod 644 /etc/cron.d/ads-weekly-digest
echo "  Weekly digest cron installed: Monday 9am UTC"

# ── 7. API server (systemd) ───────────────────────────────────────────────────
echo "[7/7] Setting up systemd service..."
sudo tee /etc/systemd/system/ads-agent-api.service > /dev/null <<EOF
[Unit]
Description=Google Ads Agent API
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ads-agent-api
sudo systemctl start ads-agent-api

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "=== Setup complete ==="
echo "  App directory:     $APP_DIR"
echo "  API server:        sudo systemctl status ads-agent-api"
echo "  Cron logs:         tail -f /var/log/ads-research.log"
echo "  Edit .env:         nano $APP_DIR/.env"
echo "  Restart API:       sudo systemctl restart ads-agent-api"
echo ""
echo "IMPORTANT: Edit $APP_DIR/.env with your real API keys before starting!"