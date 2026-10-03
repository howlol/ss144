#!/usr/bin/env bash
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NATIVE_ROOT="/tmp/ss14-native"

echo "================================================================================"
echo "🚀 Space Station 14 — Native C# Engine (Content.Server + Content.Client) + Web"
echo "================================================================================"

# 1. If /tmp/ss14-native is not populated yet, fetch prebuilt Bookworm bundle from git tag
if [ ! -f "$NATIVE_ROOT/ss14/bin/Content.Server/Content.Server" ]; then
  echo "[1/5] Fetching prebuilt Native C# SS14 bundle from refs/tags/ss14-bookworm-bundle..."
  rm -rf /tmp/ss14-bundle "$NATIVE_ROOT"
  mkdir -p /tmp/ss14-bundle "$NATIVE_ROOT"
  git init /tmp/ss14-bundle
  git -C /tmp/ss14-bundle fetch --depth 1 https://github.com/howlol/ss144.git refs/tags/ss14-bookworm-bundle
  git -C /tmp/ss14-bundle checkout FETCH_HEAD
  cat /tmp/ss14-bundle/bundle.tar.gz.part_* | tar -xzf - -C "$NATIVE_ROOT"
  rm -rf /tmp/ss14-bundle
fi

if [ -d "$NATIVE_ROOT/debs" ]; then
  echo "[1b/5] Installing Debian 12 Xvfb + Mesa OpenGL + x11vnc + noVNC packages..."
  sudo dpkg -i --force-all "$NATIVE_ROOT/debs/"*.deb >/dev/null 2>&1 || true
  rm -rf "$NATIVE_ROOT/debs"
fi

if [ ! -d "$NATIVE_ROOT/ss14/RobustToolbox/Resources" ]; then
  echo "[1c/5] Mounting RobustToolbox shared engine resources..."
  git clone --depth 1 https://github.com/space-wizards/RobustToolbox.git "$NATIVE_ROOT/ss14/RobustToolbox"
fi

# 2. Customize /usr/share/novnc/vnc_lite.html for borderless fullscreen & auto-reconnect
sudo tee /usr/share/novnc/vnc_lite.html >/dev/null <<'EOF'
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Space Station 14 — Native C# Client (OpenGL)</title>
  <style>
    html, body {
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      background-color: #020409;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      font-family: Inter, system-ui, sans-serif;
    }
    #loading_banner {
      position: absolute;
      top: 12px;
      right: 16px;
      background: rgba(15, 23, 42, 0.85);
      border: 1px solid #334155;
      color: #38bdf8;
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      z-index: 10;
      pointer-events: none;
      transition: opacity 0.3s ease;
    }
    #loading_banner.hidden {
      opacity: 0;
    }
    #screen {
      flex: 1;
      width: 100%;
      height: 100%;
      overflow: hidden;
    }
  </style>
  <script type="module" crossorigin="anonymous">
    import RFB from './core/rfb.js';
    let rfb;
    const banner = document.getElementById('loading_banner');

    function connectVnc() {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const host = window.location.hostname;
      const port = window.location.port ? (':' + window.location.port) : '';
      const url = `${proto}://${host}${port}/websockify`;

      try {
        rfb = new RFB(document.getElementById('screen'), url);
        rfb.scaleViewport = true;
        rfb.resizeSession = false;
        rfb.focusOnClick = true;

        rfb.addEventListener('connect', () => {
          if (banner) {
            banner.textContent = '🟢 Нативный C# клиент Space Station 14 подключён (кликните по экрану для управления)';
            setTimeout(() => banner.classList.add('hidden'), 4000);
          }
          rfb.focus();
        });

        rfb.addEventListener('disconnect', () => {
          if (banner) {
            banner.classList.remove('hidden');
            banner.textContent = '⏳ Переподключение к X11/OpenGL окну Space Station 14...';
          }
          setTimeout(connectVnc, 1500);
        });
      } catch (e) {
        setTimeout(connectVnc, 1500);
      }
    }

    window.addEventListener('DOMContentLoaded', connectVnc);
    window.addEventListener('click', () => { try { rfb && rfb.focus(); } catch(_e){} });
  </script>
</head>
<body>
  <div id="loading_banner">⏳ Подключение к нативному C# клиенту Space Station 14 (OpenGL)...</div>
  <div id="screen"></div>
</body>
</html>
EOF

# 3. Configure Openbox so Content.Client is borderless and maximized to 1280x720
mkdir -p ~/.config/openbox
cat << 'EOF' > ~/.config/openbox/rc.xml
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc" xmlns:xi="http://www.w3.org/2001/XInclude">
  <applications>
    <application class="*">
      <decor>no</decor>
      <maximized>true</maximized>
    </application>
  </applications>
</openbox_config>
EOF

# 4. Copy fast Saltern server config & apply latest Content.Server.dll patch if available
cp "$REPO_ROOT/ss14_mod/Resources/ConfigPresets/Build/ai_station.toml" "$NATIVE_ROOT/ss14/bin/Content.Server/server_config.toml"
if [ ! -f "$NATIVE_ROOT/ss14/.patched_v2" ]; then
  if git ls-remote --tags https://github.com/howlol/ss144.git refs/tags/ss14-server-patch | grep -q "ss14-server-patch"; then
    rm -rf /tmp/ss14-patch
    mkdir -p /tmp/ss14-patch
    git init /tmp/ss14-patch >/dev/null 2>&1
    git -C /tmp/ss14-patch fetch --depth 1 https://github.com/howlol/ss144.git refs/tags/ss14-server-patch >/dev/null 2>&1
    git -C /tmp/ss14-patch checkout FETCH_HEAD >/dev/null 2>&1
    cp /tmp/ss14-patch/Content.Server.dll "$NATIVE_ROOT/ss14/bin/Content.Server/Content.Server.dll"
    rm -rf /tmp/ss14-patch
    touch "$NATIVE_ROOT/ss14/.patched_v2"
  fi
fi

export DISPLAY=:99
export LIBGL_ALWAYS_SOFTWARE=1
export ALSOFT_DRIVERS=null
export DOTNET_ROOT="$NATIVE_ROOT/dotnet"
export PATH="$NATIVE_ROOT/dotnet:$PATH"

# Launch Xvfb + x11vnc + Content.Server + Content.Client AFTER port 8000 is listening
# so 0.0.0.0:8000 is the primary preview port registered by the host environment.
(
  for _ in $(seq 1 30); do
    if curl -s http://127.0.0.1:8000/api/native_status >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
  sleep 2

  if ! pgrep -x Xvfb >/dev/null 2>&1; then
    echo "[2/5] Starting Xvfb :99 (1280x720x24 OpenGL) + Openbox..."
    Xvfb :99 -screen 0 1280x720x24 -ac +extension GLX +render -noreset >/tmp/xvfb.log 2>&1 &
    sleep 1
    openbox >/tmp/openbox.log 2>&1 &
  fi

  if ! pgrep -f "x11vnc -display :99 -localhost" >/dev/null 2>&1; then
    pkill -9 -x x11vnc 2>/dev/null || true
    sleep 0.3
    x11vnc -display :99 -localhost -nopw -forever -shared -rfbport 5900 >/tmp/x11vnc.log 2>&1 &
  fi

  if ! pgrep -x Content.Server >/dev/null 2>&1; then
    echo "[3/5] Starting C# Content.Server + AIStationBridgeSystem in background..."
    cd "$NATIVE_ROOT/ss14"
    "$NATIVE_ROOT/ss14/bin/Content.Server/Content.Server" >/tmp/ss14_server.log 2>&1 &
    for i in $(seq 1 60); do
      if curl -s http://127.0.0.1:1212/status >/dev/null 2>&1; then
        echo "[Content.Server] Ready on UDP/HTTP 127.0.0.1:1212 and Bridge 127.0.0.1:12120!"
        break
      fi
      sleep 1
    done
    echo "[4/5] Launching Native C# OpenGL Content.Client connected to 127.0.0.1:1212..."
    while true; do
      "$NATIVE_ROOT/ss14/bin/Content.Client/Content.Client" \
        --connect \
        --connect-address 127.0.0.1:1212 \
        --username Player \
        --cvar display.width=1280 \
        --cvar display.height=720 \
        --cvar display.windowmode=1 \
        --cvar display.max_fps=30 \
        --cvar display.vsync=false \
        >/tmp/ss14_client.log 2>&1 || true
      sleep 2
    done
  fi
) &

echo "[5/5] Starting Web + Websockify Proxy Server on 0.0.0.0:8000..."
cd "$REPO_ROOT"
exec python3 -m uvicorn server.app:app --host 0.0.0.0 --port 8000 --log-level warning
