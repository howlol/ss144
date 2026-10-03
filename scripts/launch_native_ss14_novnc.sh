#!/usr/bin/env bash
# =============================================================================
# Launch Real Native Space Station 14 (Content.Server + Content.Client OpenGL)
# inside an Xvfb virtual X11 display and stream it to the Web Browser via noVNC
# =============================================================================
set -euo pipefail

echo "[1/4] Installing Xvfb, Mesa OpenGL, OpenAL, x11vnc, and noVNC/websockify..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq xvfb x11vnc novnc websockify openbox libgl1-mesa-dri libglx-mesa0 mesa-utils libopenal1 libfreetype6 libfluidsynth3 > /dev/null

echo "[2/4] Building Space Station 14 Content.Server (with AIStation mod) & Content.Client..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/build_ss14_server.sh" /tmp/ss14-src

export PATH="$HOME/.dotnet:$PATH"
cd /tmp/ss14-src
dotnet build Content.Client/Content.Client.csproj -c Release --no-restore -v minimal

echo "[3/4] Starting Xvfb :99 (1280x720x24) + Openbox + x11vnc + noVNC on port 6080..."
pkill -f "Xvfb :99" || true
pkill -f "x11vnc" || true
pkill -f "websockify" || true

Xvfb :99 -screen 0 1280x720x24 -ac +extension GLX +render -noreset &
sleep 1
export DISPLAY=:99
export LIBGL_ALWAYS_SOFTWARE=1

openbox &
x11vnc -display :99 -nopw -forever -shared -rfbport 5900 -quiet &
websockify --web=/usr/share/novnc/ 6080 localhost:5900 &

echo "[4/4] Starting SS14 Content.Server (:1212) and connecting Content.Client..."
/tmp/ss14-src/bin/Content.Server/Content.Server > /tmp/ss14_server.log 2>&1 &
sleep 5
/tmp/ss14-src/bin/Content.Client/Content.Client --connect --connect-address 127.0.0.1:1212 --cvar display.width=1280 --cvar display.height=720 > /tmp/ss14_client.log 2>&1 &

echo "✅ Native Space Station 14 Client + Server running in browser on http://127.0.0.1:6080/vnc.html?autoconnect=true"
