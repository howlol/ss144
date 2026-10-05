#!/usr/bin/env python3
"""
Space Station 14 Autonomous AI Server - Master Launcher
Starts the SS14 Server, AI Swarm (20-40 Agents), Director Web Dashboard, and Public Tunnels.
"""

import os
import sys
import argparse
import asyncio
import uvicorn
import logging

from ai_engine.orchestrator import SimulationOrchestrator
from ss14_server.server_manager import SS14ServerManager
from tunnels.tunnel_manager import TunnelManager
import dashboard.app as dashboard_module

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SS14_MasterLauncher")

def parse_args():
    parser = argparse.ArgumentParser(description="Space Station 14 AI Server Launcher")
    parser.add_argument("--crew", type=int, default=30, help="Number of AI crew members (20-40)")
    parser.add_argument("--api-key", type=str, default=os.getenv("OPENAI_API_KEY", ""), help="OpenAI / LLM API Key")
    parser.add_argument("--base-url", type=str, default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"), help="OpenAI API Base URL")
    parser.add_argument("--model", type=str, default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), help="Model name")
    parser.add_argument("--port", type=int, default=8000, help="Web Dashboard Port")
    parser.add_argument("--game-port", type=int, default=1212, help="SS14 UDP Game Port")
    parser.add_argument("--rcon-port", type=int, default=1213, help="SS14 RCON Port")
    parser.add_argument("--ngrok-token", type=str, default=os.getenv("NGROK_AUTHTOKEN", ""), help="Ngrok Auth Token")
    parser.add_argument("--enable-tunnels", action="store_true", default=False, help="Enable Cloudflared / Playit tunnels")
    parser.add_argument("--download-server", action="store_true", default=False, help="Download SS14 server binaries")
    return parser.parse_args()

async def main():
    args = parse_args()

    print("""
========================================================================
🚀 SPACE STATION 14 - AUTONOMOUS AI SERVER & DIRECTOR DECK 🚀
========================================================================
- AI Crew Population:  {crew} Agents (100% AI Driven)
- OpenAI Compatible:   {model} ({base_url})
- Web Dashboard Port:  http://0.0.0.0:{port}
- SS14 Game Port:      UDP 0.0.0.0:{game_port}
========================================================================
""".format(
        crew=args.crew,
        model=args.model,
        base_url=args.base_url,
        port=args.port,
        game_port=args.game_port
    ))

    # 1. Initialize Server Manager
    server_mgr = SS14ServerManager(port=args.game_port, rcon_port=args.rcon_port)
    server_mgr.write_configuration()
    if args.download_server and not server_mgr.is_installed():
        logger.info("Attempting download of SS14 server binary...")
        server_mgr.download_server()

    # Try starting server process if binary exists
    if server_mgr.is_installed():
        server_mgr.start_server()

    # 2. Initialize Tunnels
    tunnel_mgr = TunnelManager(game_port=args.game_port, dashboard_port=args.port)
    if args.enable_tunnels:
        logger.info("Starting public tunnels for Colab / Internet access...")
        tunnel_mgr.start_cloudflared(port=args.port)
        if args.ngrok_token:
            tunnel_mgr.start_ngrok(args.ngrok_token, tunnel_type="tcp", port=args.game_port)
        else:
            tunnel_mgr.start_playit()

    # 3. Initialize AI Simulation Orchestrator
    orchestrator = SimulationOrchestrator(
        crew_count=args.crew,
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model
    )
    await orchestrator.start()

    # Bind singletons to dashboard app
    dashboard_module.orchestrator = orchestrator
    dashboard_module.server_manager = server_mgr
    dashboard_module.tunnel_manager = tunnel_mgr

    # 4. Start Uvicorn Server
    config = uvicorn.Config(
        dashboard_module.app,
        host="0.0.0.0",
        port=args.port,
        log_level="info",
        access_log=False
    )
    server = uvicorn.Server(config)
    
    logger.info(f"Director Dashboard running on http://0.0.0.0:{args.port}")
    if tunnel_mgr.active_tunnels:
        for t_name, t_url in tunnel_mgr.active_tunnels.items():
            logger.info(f"🌐 Public Tunnel [{t_name}]: {t_url}")

    try:
        await server.serve()
    finally:
        await orchestrator.stop()
        server_mgr.stop_server()
        tunnel_mgr.stop_all()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete.")
