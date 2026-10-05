#!/bin/bash
# =============================================================================
# Sakhi EEE Campus Kiosk - Hands-Free Voice Kiosk Autostart (Raspberry Pi 5)
# Shri Vaishnav Vidyapeeth Vishwavidyalaya, Indore
# =============================================================================

# Switch to project directory (supports standard Pi 5 deployment or current folder)
if [ -d "/home/pi/project_help_desk" ]; then
    cd /home/pi/project_help_desk
else
    cd "$(dirname "$0")"
fi

# Activate virtual environment if present
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Cleanup on exit
cleanup() {
    echo ""
    echo "[Kiosk] Shutting down Sakhi Kiosk services..."
    if [ -n "$VOICE_PID" ]; then
        kill "$VOICE_PID" 2>/dev/null || true
    fi
    if [ -n "$SERVER_PID" ]; then
        kill "$SERVER_PID" 2>/dev/null || true
    fi
    if [ -n "$UNCLUTTER_PID" ]; then
        kill "$UNCLUTTER_PID" 2>/dev/null || true
    fi
    echo "[Kiosk] Stopped."
}
trap cleanup INT TERM EXIT

# 1. Start FastAPI backend with WebSocket support
echo "[Kiosk] Starting FastAPI backend with WebSocket support..."
python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 &
SERVER_PID=$!

# 2. Start Hands-Free Voice Daemon
echo "[Kiosk] Starting Hands-Free Voice Capture Daemon..."
python3 voice_listener.py &
VOICE_PID=$!

# Wait for server to become responsive
echo "[Kiosk] Waiting for server readiness..."
until curl -s http://127.0.0.1:8000/api/health > /dev/null 2>&1 || curl -s http://127.0.0.1:8000/ > /dev/null 2>&1; do
    sleep 0.5
done
echo "[Kiosk] Server is ready."

# 3. Disable screensaver and display power management (DPMS)
xset s off -dpms s noblank 2>/dev/null || true

# 4. Hide mouse cursor completely
if command -v unclutter >/dev/null 2>&1; then
    unclutter -idle 0 -root &
    UNCLUTTER_PID=$!
fi

# 5. Launch Chromium in hardware-accelerated, permission-free kiosk mode
BROWSER_CMD="chromium-browser"
if ! command -v chromium-browser >/dev/null 2>&1 && command -v chromium >/dev/null 2>&1; then
    BROWSER_CMD="chromium"
fi

echo "[Kiosk] Launching Chromium in fullscreen kiosk mode..."
$BROWSER_CMD \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --check-for-update-interval=31536000 \
    --enable-features=VaapiVideoDecoder \
    --ignore-gpu-blocklist \
    --enable-gpu-rasterization \
    --enable-zero-copy \
    --autoplay-policy=no-user-gesture-required \
    --use-fake-ui-for-media-stream \
    --allow-file-access-from-files \
    http://127.0.0.1:8000

# Wait for background services if browser exits
wait $SERVER_PID
