#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Space Station 14 (Content.Server + AiStationBridgeSystem) Builder & Launcher
# ==============================================================================
# Clones official open-source space-wizards/space-station-14 into /tmp/ss14-src,
# injects the C# AIStation mod (AiAgentComponent + AiStationBridgeSystem),
# compiles Content.Server with .NET 10 SDK, and prepares bin/Content.Server/
# ==============================================================================

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SS14_DIR="${SS14_BUILD_DIR:-/tmp/ss14-src}"
DOTNET_DIR="${DOTNET_INSTALL_DIR:-/tmp/dotnet}"
 export PATH="$DOTNET_DIR:$PATH"
export DOTNET_ROOT="$DOTNET_DIR"
export DOTNET_CLI_TELEMETRY_OPTOUT=1

echo "[1/5] Checking .NET 10 SDK..."
if ! command -v dotnet &>/dev/null || ! dotnet --list-sdks | grep -q "^10\."; then
    echo "Installing .NET 10.0 SDK into $DOTNET_DIR..."
    mkdir -p "$DOTNET_DIR"
    curl -sSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh
    chmod +x /tmp/dotnet-install.sh
    /tmp/dotnet-install.sh --channel 10.0 --install-dir "$DOTNET_DIR"
fi
dotnet --info | head -n 15

echo "[2/5] Cloning space-wizards/space-station-14 (shallow) into $SS14_DIR..."
if [ ! -d "$SS14_DIR/.git" ]; then
    git clone --depth 1 https://github.com/space-wizards/space-station-14.git "$SS14_DIR"
    cd "$SS14_DIR"
    git submodule update --init --depth 1
    cd "$SS14_DIR/RobustToolbox"
    git submodule update --init --depth 1
else
    echo "Using existing SS14 checkout at $SS14_DIR"
fi

echo "[3/5] Injecting C# AIStation Mod (Content.Server/AIStation)..."
mkdir -p "$SS14_DIR/Content.Server/AIStation"
cp -v "$REPO_ROOT/ss14_mod/Content.Server/AIStation/"*.cs "$SS14_DIR/Content.Server/AIStation/"

mkdir -p "$SS14_DIR/bin/Content.Server"
cp -v "$REPO_ROOT/ss14_mod/Resources/ConfigPresets/Build/ai_station.toml" "$SS14_DIR/bin/Content.Server/server_config.toml"

echo "[4/5] Refreshing extracted station map & textures if needed..."
if [ ! -f "$REPO_ROOT/ss14_assets/maps/saltern.json" ]; then
    python3 "$REPO_ROOT/scripts/extract_ss14_assets.py" "$SS14_DIR" "$REPO_ROOT/ss14_assets"
fi

echo "[5/5] Building Space Station 14 Content.Server (Release)..."
cd "$SS14_DIR"
dotnet restore Content.Server/Content.Server.csproj
dotnet build Content.Server/Content.Server.csproj -c Release --no-restore /p:TargetOs=Linux -p:TreatWarningsAsErrors=false -p:WarningsAsErrors="" -p:RunAnalyzers=false -p:RunAnalyzersDuringBuild=false /m

echo "=============================================================================="
echo "Space Station 14 Content.Server built successfully!"
echo "Executable: $SS14_DIR/bin/Content.Server/Content.Server"
echo "Bridge Port: 12120 (HTTP JSON) | Game Port: 1212 (UDP/HTTP Status)"
echo "=============================================================================="
