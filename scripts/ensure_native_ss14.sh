#!/usr/bin/env bash
set -e

exec 9>/tmp/ss14_ensure.lock
flock -n 9 || exit 0

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NATIVE_ROOT="/tmp/ss14-native"
SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
fi

echo "[SS14 Native] Checking native C# Space Station 14 bundle in $NATIVE_ROOT..."

# 1. Fetch prebuilt Native C# SS14 bundle (Content.Server + Content.Client + .NET 10 + Resources)
if [ ! -f "$NATIVE_ROOT/ss14/bin/Content.Server/Content.Server" ]; then
  echo "[SS14 Native] Downloading prebuilt C# Content.Server + Content.Client bundle from GitHub tag..."
  rm -rf /tmp/ss14-bundle "$NATIVE_ROOT"
  mkdir -p /tmp/ss14-bundle "$NATIVE_ROOT"
  git init /tmp/ss14-bundle
  git -C /tmp/ss14-bundle fetch --depth 1 https://github.com/howlol/ss144.git refs/tags/ss14-bookworm-bundle
  git -C /tmp/ss14-bundle checkout FETCH_HEAD
  cat /tmp/ss14-bundle/bundle.tar.gz.part_* | tar -xzf - -C "$NATIVE_ROOT"
  rm -rf /tmp/ss14-bundle
fi

# 2. Apply latest Content.Server.dll AIStation patch
if [ ! -f "$NATIVE_ROOT/ss14/.patched_v2" ]; then
  if git ls-remote --tags https://github.com/howlol/ss144.git refs/tags/ss14-server-patch | grep -q "ss14-server-patch"; then
    echo "[SS14 Native] Applying latest Content.Server.dll AIStation patch..."
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

# 3. Install Xvfb + x11vnc + Openbox + Mesa OpenGL + OpenAL (supports both Ubuntu/Colab apt and Debian offline debs)
if ! command -v Xvfb >/dev/null 2>&1 || ! command -v x11vnc >/dev/null 2>&1 || ! command -v openbox >/dev/null 2>&1; then
  echo "[SS14 Native] Installing Xvfb, x11vnc, openbox, Mesa OpenGL, and OpenAL..."
  if $SUDO apt-get update -qq >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq xvfb x11vnc openbox libgl1-mesa-dri libglx-mesa0 libopenal1 libfreetype6 >/dev/null 2>&1 || true
  fi
  if (! command -v Xvfb >/dev/null 2>&1 || ! command -v x11vnc >/dev/null 2>&1) && [ -d "$NATIVE_ROOT/debs" ]; then
    $SUDO dpkg -i --force-all "$NATIVE_ROOT/debs/"*.deb >/dev/null 2>&1 || true
  fi
fi
rm -rf "$NATIVE_ROOT/debs" 2>/dev/null || true

# 4. Ensure RobustToolbox engine resources exist
if [ ! -d "$NATIVE_ROOT/ss14/RobustToolbox/Resources" ]; then
  echo "[SS14 Native] Cloning RobustToolbox shared engine resources..."
  git clone --depth 1 https://github.com/space-wizards/RobustToolbox.git "$NATIVE_ROOT/ss14/RobustToolbox"
fi

# 5. Configure Openbox borderless maximized window
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

cp "$REPO_ROOT/ss14_mod/Resources/ConfigPresets/Build/ai_station.toml" "$NATIVE_ROOT/ss14/bin/Content.Server/server_config.toml"

export DISPLAY=:99
export LIBGL_ALWAYS_SOFTWARE=1
export ALSOFT_DRIVERS=null
export DOTNET_ROOT="$NATIVE_ROOT/dotnet"
export PATH="$NATIVE_ROOT/dotnet:$PATH"

# 6. Start Xvfb :99 + Openbox + x11vnc
if ! pgrep -x Xvfb >/dev/null 2>&1; then
  echo "[SS14 Native] Starting Xvfb :99 (1280x720x24 OpenGL) + Openbox..."
  Xvfb :99 -screen 0 1280x720x24 -ac +extension GLX +render -noreset >/tmp/xvfb.log 2>&1 &
  sleep 1
  openbox >/tmp/openbox.log 2>&1 &
fi

if ! pgrep -x x11vnc >/dev/null 2>&1; then
  echo "[SS14 Native] Starting x11vnc on 127.0.0.1:5900..."
  x11vnc -display :99 -localhost -nopw -forever -shared -rfbport 5900 >/tmp/x11vnc.log 2>&1 &
fi

# 7. Start C# Content.Server and C# OpenGL Content.Client
if ! pgrep -x Content.Server >/dev/null 2>&1; then
  echo "[SS14 Native] Starting C# Content.Server (NSS Saltern + AIStationBridgeSystem)..."
  cd "$NATIVE_ROOT/ss14"
  "$NATIVE_ROOT/ss14/bin/Content.Server/Content.Server" >/tmp/ss14_server.log 2>&1 &
  for _ in $(seq 1 60); do
    if curl -s http://127.0.0.1:1212/status >/dev/null 2>&1; then
      echo "[SS14 Native] Content.Server is READY on 127.0.0.1:1212!"
      break
    fi
    sleep 1
  done
fi

if ! pgrep -x Content.Client >/dev/null 2>&1; then
  echo "[SS14 Native] Starting C# OpenGL Content.Client connected to 127.0.0.1:1212..."
  (
    cd "$NATIVE_ROOT/ss14"
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
  ) &
fi

echo "[SS14 Native] All native C# Space Station 14 processes are running!"
