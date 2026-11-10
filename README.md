# 🎬 YouTube Downloader Telegram Bot

A production-grade Telegram bot that downloads YouTube videos and audio — fast, free, and designed to run 24/7 unattended.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![aiogram 3.x](https://img.shields.io/badge/aiogram-3.x-green)](https://aiogram.dev)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

---

## ⚡ Architecture Decision Record (ADR)

* **Local Telegram Bot API server (`--local`)**: Runs alongside the bot in Docker or binary mode. Lifts Telegram's standard 50 MB upload cap to 2 GB and enables direct upload via local filesystem path rather than streaming gigabytes through memory.
* **Stream Copy Remuxing Only**: yt-dlp remuxes video via ffmpeg using stream copy (`--remux-video mp4`). We **never** re-encode streams unless forced, keeping CPU usage close to zero and completing conversions in seconds.
* **Bounded Concurrency Pool**: Uses `asyncio.Semaphore(MAX_PARALLEL)` and `asyncio.Queue` for fair FIFO scheduling, preventing process OOM and disk exhaustion.
* **Zero-Cost Embedded DB**: SQLite in WAL mode (`PRAGMA journal_mode=WAL`) allows concurrent non-blocking reads while persisting state, caching `file_id` values, and tracking rate limits with zero hosting overhead.
* **Long Polling Over Webhook**: Functions seamlessly behind NAT, domestic firewalls, dynamic residential IPs, or mobile networks without opening any public ports.

---

## 🚀 10-Minute Setup (Windows Development)

### Prerequisites
1. **Python 3.12+**: [python.org/downloads](https://python.org/downloads)
2. **FFmpeg in PATH**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) or run `winget install Gyan.FFmpeg`
3. **Docker Desktop** (optional, recommended for local Bot API server)
4. Bot token from [@BotFather](https://t.me/BotFather)
5. `API_ID` and `API_HASH` from [my.telegram.org](https://my.telegram.org)

### Quickstart
```powershell
# 1. Open PowerShell in project directory
cd "d:\projects\Eyasu\the bot of youtube"

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
copy .env.example .env
notepad .env   # Enter your BOT_TOKEN, ADMIN_ID, API_ID, API_HASH

# 5. Start local Telegram Bot API server (Docker)
docker compose up -d telegram-bot-api

# 6. Run the bot
python -m bot.main
```

### Windows Service Setup (Auto-Start at Boot, No Docker)
```powershell
# Run PowerShell as Administrator:
Set-ExecutionPolicy Bypass -Scope Process
.\deploy\windows\install-service.ps1
```
This configures NSSM to run the bot as a background service (`YTDLBot`) that restarts automatically on crash or system reboot.

---

## 🐳 Docker Deployment (Linux / Home Server)

```bash
cp .env.example .env
# Edit .env with your credentials
docker compose up -d
docker compose logs -f bot
```

---

## 🐧 Linux / Raspberry Pi Systemd

```bash
# Copy project to /opt/ytdlbot
sudo mkdir -p /opt/ytdlbot
sudo chown -R $USER:$USER /opt/ytdlbot
cp -r . /opt/ytdlbot/
cd /opt/ytdlbot

# Setup service
sudo cp deploy/systemd/ytdlbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ytdlbot

# Enable daily yt-dlp auto-update timer
sudo cp deploy/systemd/ytdlbot-update.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ytdlbot-update.timer
```

---

## ☁️ Oracle Cloud Always Free (ARM Ubuntu 22.04)

```bash
# On your local machine:
scp deploy/oracle/provision.sh ubuntu@<oracle-vm-ip>:~
ssh ubuntu@<oracle-vm-ip>

# Run automated provisioner (installs docker, ufw, fail2ban, updates)
sudo bash provision.sh
```

> ⚠️ **Datacenter IP Notice**: Oracle Cloud IPs are frequently flagged by YouTube bot detection. We strongly advise setting `COOKIES_PATH` and/or a residential `PROXY` in `.env`.

---

## 🍪 Cookies Setup (Anti-Bot Protection)

When YouTube enforces "Sign in to confirm you're not a bot", provide login cookies from a **throwaway account** (never your personal account):

1. Log into a throwaway YouTube account in your browser.
2. Export `cookies.txt` using an extension such as **Get cookies.txt LOCALLY**.
3. Place `cookies.txt` in the bot directory or specify its path in `.env`:
   ```env
   COOKIES_PATH=./cookies.txt
   ```
4. Or generate it directly using yt-dlp:
   ```bash
   yt-dlp --cookies-from-browser chrome --cookies cookies.txt "https://youtube.com"
   ```

---

## 🔄 Keeping yt-dlp Updated

YouTube frequently adjusts its endpoints. The bot includes:
- An internal daily update loop that runs `python -m pip install -U yt-dlp` and signals a reload.
- Dedicated update scripts:
  - Linux: `./scripts/update-ytdlp.sh`
  - Windows: `.\scripts\update-ytdlp.bat`

---

## 📊 Platform Comparison

| Hosting Option | Sleep / Inactivity | YouTube Block Risk | Upload Limit | Cost |
|---|---|---|---|---|
| **Home PC / RPi** | Never | **Low** (Residential IP) | 2 GB (Local API) | **$0** |
| **Oracle Cloud ARM** | Never | **High** (Datacenter IP) | 2 GB (Local API) | **$0** |
| **Render (Free)** | Sleeps after 15m idle | High | 50 MB | $0 |
| **Fly.io (Free)** | Sleeps after 3h idle | High | 50 MB | $0 |
| **Railway (Free)** | $5/mo credit limit | High | 50 MB | Paid after credit |
| **Koyeb (Free)** | Re-allocates instances | High | 50 MB | $0 |
| **HF Spaces** | Ephemeral storage | High | 50 MB | $0 |

**Verdict**: A home mini PC, Raspberry Pi, or local desktop is the most reliable option for YouTube downloading due to residential IP reputation and unmetered disk storage.

---

## 📁 Repository Structure

```
├── bot/
│   ├── __init__.py
│   ├── config.py              # Strict environment validation, fail-fast
│   ├── main.py                # Bot runner, queue supervisor, signal handlers
│   ├── db/
│   │   ├── __init__.py
│   │   └── database.py        # Async SQLite WAL: file_id cache & rate limiter
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py           # /start legal guardrail, /help
│   │   ├── download.py        # Link parsing, keyboard, download & upload pipeline
│   │   └── admin.py           # /stats, admin alerts, disk & memory health
│   ├── services/
│   │   ├── __init__.py
│   │   ├── downloader.py      # yt-dlp executor, retry, 2GB size check
│   │   ├── queue.py           # Concurrency-controlled FIFO queue
│   │   ├── updater.py         # 24h background yt-dlp self-updater
│   │   └── youtube.py         # Regex URL parsing, itag/format resolver
│   └── utils/
│       ├── __init__.py
│       ├── formatting.py      # Throttled progress bar, error classification
│       └── logging_setup.py   # Structured JSON logger
├── deploy/
│   ├── oracle/provision.sh    # Cloud VM provisioning script
│   ├── systemd/               # Linux systemd service & timer
│   └── windows/               # Windows NSSM service installer
├── scripts/
│   ├── update-ytdlp.sh        # Bash updater
│   └── update-ytdlp.bat       # Windows updater
├── tests/
│   ├── test_cache.py          # SQLite cache & rate limit tests
│   ├── test_format_selection.py
│   ├── test_formatting.py
│   └── test_url_parsing.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── pyproject.toml
└── .env.example
```

---

## ⚙️ Configuration Reference

| Parameter | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | Yes | — | Telegram Bot token from @BotFather |
| `ADMIN_ID` | Yes | — | Numeric Telegram User ID for alerts & /stats |
| `API_ID` | Yes | — | Telegram API ID from my.telegram.org |
| `API_HASH` | Yes | — | Telegram API Hash from my.telegram.org |
| `LOCAL_API_URL` | No | `http://localhost:8081` | Self-hosted Telegram Bot API endpoint |
| `COOKIES_PATH` | No | `None` | Path to Netscape format cookies file |
| `PROXY` | No | `None` | Optional proxy URL (e.g. `socks5://...`) |
| `MAX_PARALLEL` | No | `3` | Maximum concurrent downloads |
| `MAX_DURATION` | No | `10800` | Maximum video duration in seconds (3h) |
| `TMP_DIR` | No | `/tmp/ytdlbot` | Working directory for in-flight media |
| `ALLOW_PLAYLISTS` | No | `0` | Reject playlists by default (`0`) |
| `DB_PATH` | No | `data/bot.db` | Path to persistent SQLite database |

---

## 🛠️ Verification Checklist

### 1. Confirm `file_id` Caching
1. Send any standard YouTube link and choose `720p`. Observe download progress and file delivery.
2. Send the exact same link and choose `720p` again.
3. The video should arrive **instantly** (<1 second) with no downloading progress bar.
4. Verify `"cache_hit": true` in logs or run `/stats` to see cache count increment.

### 2. Confirm Uploads > 50 MB (Up to 2 GB)
1. Send a YouTube link for a long video (>1 hour) or high bitrate file (>50 MB).
2. Choose `1080p`.
3. Confirm upload completes successfully through the self-hosted Bot API server.

### 3. Confirm Crash Recovery & Orphan Cleanup
1. Initiate a download of a large file.
2. Terminate the process forcefully: `Stop-Process -Name python -Force` (Windows) or `kill -9 <pid>` (Linux).
3. Check `TMP_DIR` for leftover partial files.
4. Restart the bot (`python -m bot.main`).
5. Confirm the startup sweep deletes any orphan `job_*` temporary folders and resumes normal operation.

---

## 🧪 Running Tests

```bash
pytest tests -v
```

---

## ⚖️ Legal Notice
This bot is designed solely for personal archiving of content you own, have express permission to download, or which is released under Creative Commons or public domain licenses.

