#!/bin/bash
# Starts: Xvfb -> openbox -> x11vnc -> websockify(noVNC) -> headed Chromium with CDP.
set -e

trap 'exit 0' TERM INT

RES="${VNC_RESOLUTION:-1280x800}"
export DISPLAY=:99

# Clear stale X locks from unclean shutdowns
rm -f /tmp/.X99-lock
rm -rf /tmp/.X11-unix/X99 2>/dev/null || true

echo "[browser] Starting Xvfb on :99 (${RES})..."
Xvfb :99 -screen 0 "${RES}x24" +extension RANDR &
sleep 2

echo "[browser] Starting openbox..."
openbox &
sleep 1

echo "[browser] Starting x11vnc (localhost:5900)..."
x11vnc -display :99 -forever -shared -rfbport 5900 -localhost -nopw \
  -ncache 10 -ncache_size 100 -xkb -quiet &
sleep 1

echo "[browser] Starting websockify/noVNC on :6080..."
/usr/bin/websockify --web /usr/share/novnc/ 6080 127.0.0.1:5900 &

CHROME_FLAGS="--no-sandbox \
  --disable-dev-shm-usage \
  --disable-gpu \
  --remote-debugging-port=9222 \
  --remote-debugging-address=0.0.0.0 \
  --user-data-dir=/profile \
  --window-size=1280,800 \
  --window-position=0,0 \
  --no-first-run \
  --no-default-browser-check \
  --password-store=basic \
  --disable-blink-features=AutomationControlled \
  --disable-features=Translate \
  --disable-infobars \
  --lang=en-US"

echo "[browser] Starting Chromium (CDP on :9222, profile at /profile)..."
# Restart Chromium if it crashes; the profile volume keeps logins.
while true; do
  # shellcheck disable=SC2086
  chromium ${CHROME_FLAGS} "about:blank" || true
  echo "[browser] Chromium exited, restarting in 5s..."
  sleep 5
done
