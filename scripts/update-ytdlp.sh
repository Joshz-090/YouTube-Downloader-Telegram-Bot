#!/usr/bin/env bash
# Update yt-dlp and restart the bot service
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/ytdlbot}"

echo "[$(date -Iseconds)] Updating yt-dlp..."

# Update inside the bot container
if docker compose -f "$INSTALL_DIR/docker-compose.yml" ps --format json 2>/dev/null | grep -q "bot"; then
    docker compose -f "$INSTALL_DIR/docker-compose.yml" exec -T bot \
        python -m pip install --upgrade yt-dlp --quiet
    echo "[$(date -Iseconds)] yt-dlp updated inside container. Restarting bot..."
    docker compose -f "$INSTALL_DIR/docker-compose.yml" restart bot
else
    # Fallback: update in current venv
    python3 -m pip install --upgrade yt-dlp
    echo "[$(date -Iseconds)] yt-dlp updated. Please restart the bot manually."
fi

echo "[$(date -Iseconds)] Done."
