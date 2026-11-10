#!/usr/bin/env bash
# Provision Oracle Cloud Always Free ARM VM (Ubuntu 22.04) for YouTube Downloader Bot
# Run as root or with sudo: sudo bash provision.sh
set -euo pipefail

INSTALL_DIR="/opt/ytdlbot"
BOT_USER="botuser"
REPO_URL=""  # Set this if you have a git repo; otherwise copy files manually

echo "=== YouTube Bot Provisioner for Oracle Cloud ARM ==="
echo "⚠️  WARNING: Oracle Cloud datacenter IPs are often flagged by YouTube."
echo "   Set COOKIES_PATH and optionally PROXY in your .env to mitigate."
echo ""

# ── System update ─────────────────────────────────────────────────────────────
echo "[1/8] Updating system packages..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq

# ── Core packages ─────────────────────────────────────────────────────────────
echo "[2/8] Installing core packages..."
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    curl \
    wget \
    git \
    ffmpeg \
    python3.12 \
    python3.12-venv \
    python3-pip \
    ufw \
    fail2ban \
    unattended-upgrades \
    apt-listchanges

# ── Docker ────────────────────────────────────────────────────────────────────
echo "[3/8] Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
fi
# Install docker compose plugin
apt-get install -y -qq docker-compose-plugin

# ── Firewall ──────────────────────────────────────────────────────────────────
echo "[4/8] Configuring UFW firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
# No inbound ports for bot — it uses long polling (outbound only)
ufw --force enable
ufw status

# ── Fail2ban ──────────────────────────────────────────────────────────────────
echo "[5/8] Configuring fail2ban..."
systemctl enable fail2ban
systemctl start fail2ban

# ── Unattended security upgrades ──────────────────────────────────────────────
echo "[6/8] Enabling unattended security upgrades..."
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
EOF
systemctl enable unattended-upgrades

# ── Bot user and directory ────────────────────────────────────────────────────
echo "[7/8] Creating bot user and install directory..."
if ! id "$BOT_USER" &>/dev/null; then
    useradd -r -m -s /bin/bash "$BOT_USER"
fi
usermod -aG docker "$BOT_USER"
mkdir -p "$INSTALL_DIR"/{data,tmp,logs}
chown -R "$BOT_USER:$BOT_USER" "$INSTALL_DIR"

# ── Application files ─────────────────────────────────────────────────────────
echo ""
echo "=== Manual step required ==="
echo "Copy your bot files to $INSTALL_DIR:"
echo ""
echo "  # From your local machine:"
echo "  scp -r 'path/to/bot/files' ubuntu@<server-ip>:$INSTALL_DIR/"
echo ""
echo "Or clone from git:"
echo "  git clone $REPO_URL $INSTALL_DIR"
echo ""
echo "Then:"
echo "  cd $INSTALL_DIR"
echo "  cp .env.example .env"
echo "  nano .env  # Fill in BOT_TOKEN, ADMIN_ID, API_ID, API_HASH"
echo ""

# ── Cookies setup note ────────────────────────────────────────────────────────
echo "=== Cookies Setup (IMPORTANT for Oracle Cloud) ==="
echo ""
echo "Oracle Cloud IPs are frequently flagged by YouTube. You MUST use cookies:"
echo ""
echo "1. Create a THROWAWAY YouTube account (never use your main account!)"
echo "2. On your LOCAL machine, run:"
echo "   yt-dlp --cookies-from-browser chrome --cookies cookies.txt https://youtube.com"
echo "3. Copy cookies.txt to the server:"
echo "   scp cookies.txt ubuntu@<server-ip>:$INSTALL_DIR/cookies.txt"
echo "4. Set in .env:  COOKIES_PATH=/app/cookies.txt"
echo ""
echo "Alternatively, use a residential proxy:"
echo "   PROXY=socks5://user:pass@residential-proxy-host:port"
echo ""

# ── Systemd service ───────────────────────────────────────────────────────────
echo "[8/8] Installing systemd service..."
cat > /etc/systemd/system/ytdlbot.service <<EOF
[Unit]
Description=YouTube Downloader Telegram Bot
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
User=$BOT_USER
Group=docker
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=/usr/bin/docker compose up --remove-orphans
ExecStop=/usr/bin/docker compose down
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ytdlbot

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ytdlbot

echo ""
echo "=== Provisioning complete! ==="
echo ""
echo "Next steps:"
echo "  1. Copy bot files to $INSTALL_DIR"
echo "  2. Configure $INSTALL_DIR/.env"
echo "  3. Copy cookies.txt (see above)"
echo "  4. sudo systemctl start ytdlbot"
echo "  5. sudo journalctl -fu ytdlbot"
echo ""
echo "⚠️  Oracle Cloud Note: Datacenter IPs are often blocked by YouTube."
echo "   Using cookies and/or a residential proxy is strongly recommended."
