"""
Space Station 14 Director Mode Web Dashboard & API Server
FastAPI backend with real-time WebSockets, REST endpoints, and UI views.
"""

import os
import json
import asyncio
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from ai_engine.orchestrator import SimulationOrchestrator
from ai_engine.perception import build_perception_document, format_perception_document_text
from ss14_server.server_manager import SS14ServerManager
from tunnels.tunnel_manager import TunnelManager

logger = logging.getLogger("SS14_Dashboard")

app = FastAPI(title="Space Station 14 AI Director Dashboard")

# Setup templates and static
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Shared singletons (can be set by orchestrator launcher)
orchestrator: Optional[SimulationOrchestrator] = None
server_manager: Optional[SS14ServerManager] = None
tunnel_manager: Optional[TunnelManager] = None

# Connected WebSocket clients
active_websockets: list[WebSocket] = []

class LLMConfigRequest(BaseModel):
    api_key: str
    base_url: Optional[str] = "https://api.openai.com/v1"
    model: Optional[str] = "gpt-4o-mini"

class NewRoundRequest(BaseModel):
    crew_count: Optional[int] = 30

class AlertLevelRequest(BaseModel):
    level: str
    reason: Optional[str] = ""

class TriggerEventRequest(BaseModel):
    event_id: str

class WhisperRequest(BaseModel):
    agent_id: str
    whisper_text: str

class TeleportRequest(BaseModel):
    destination: str

@app.on_event("startup")
async def startup_event():
    global orchestrator, server_manager, tunnel_manager
    if orchestrator is None:
        orchestrator = SimulationOrchestrator(crew_count=30)
        await orchestrator.start()
    if server_manager is None:
        server_manager = SS14ServerManager()
    if tunnel_manager is None:
        tunnel_manager = TunnelManager()
    # Background broadcaster
    asyncio.create_task(broadcast_state_loop())

async def broadcast_state_loop():
    """Pushes live simulation state to all connected dashboard WebSockets."""
    while True:
        try:
            if active_websockets and orchestrator:
                snapshot = orchestrator.get_state_snapshot()
                payload = json.dumps({"type": "state_update", "data": snapshot})
                for ws in list(active_websockets):
                    try:
                        await ws.send_text(payload)
                    except Exception:
                        if ws in active_websockets:
                            active_websockets.remove(ws)
            await asyncio.sleep(1.5)
        except Exception as e:
            await asyncio.sleep(2.0)

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """Renders main Director Mode dashboard."""
    station_name = orchestrator.world.station_name if orchestrator else "Space Station 14"
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"station_name": station_name}
    )

@app.get("/status")
async def ss14_launcher_status():
    """Returns official Space Station 14 launcher /status JSON format."""
    return JSONResponse({
        "name": orchestrator.world.station_name if orchestrator else "SS14 AI Station",
        "players": len(orchestrator.world.agents) if orchestrator else 30,
        "soft_max_players": 64,
        "panic_bunker": False,
        "run_level": 1,
        "tags": ["lang:ru", "rp:mrp", "region:eu_e", "ai:crew"]
    })

@app.get("/info")
async def ss14_launcher_info(request: Request):
    """Returns official Space Station 14 launcher /info JSON format."""
    public_host = server_manager.public_host if server_manager else "127.0.0.1"
    public_port = server_manager.public_port if server_manager else 1212
    host_header = request.headers.get("host", "")
    conn_addr = f"udp://{host_header}" if host_header else (f"udp://{public_host}:{public_port}" if public_host != "127.0.0.1" else "")

    return JSONResponse({
        "connect_address": conn_addr,
        "auth": {
            "mode": "Optional"
        },
        "build": {
            "fork_id": "wizards",
            "version": "94087a918a2fae4571f5a529fe14ef7f5dce29a3",
            "engine_version": "289.0.3",
            "download_url": "https://wizards.cdn.spacestation14.com/fork/wizards/version/94087a918a2fae4571f5a529fe14ef7f5dce29a3/file/SS14.Client.zip",
            "hash": "CB7F1C2E9D2397717CDFF6401F1F50085C43CAC9234408CDC6D101A71E87D857"
        },
        "desc": "Space Station 14 with 100% OpenAI-driven Crew and Director Storyteller Deck.",
        "links": [
            {
                "name": "Director Deck",
                "icon": "web",
                "url": f"http://{public_host}:8000"
            }
        ]
    })

@app.get("/api/status")
async def get_status():
    """Returns current state snapshot."""
    if not orchestrator:
        return JSONResponse({"error": "Orchestrator not initialized"}, status_code=500)
    data = orchestrator.get_state_snapshot()
    if server_manager:
        data["server_status"] = server_manager.get_status()
    if tunnel_manager:
        data["tunnel_status"] = tunnel_manager.get_tunnel_status()
    return JSONResponse(data)
    """Returns current state snapshot."""
    if not orchestrator:
        return JSONResponse({"error": "Orchestrator not initialized"}, status_code=500)
    data = orchestrator.get_state_snapshot()
    if server_manager:
        data["server_status"] = server_manager.get_status()
    if tunnel_manager:
        data["tunnel_status"] = tunnel_manager.get_tunnel_status()
    return JSONResponse(data)

@app.post("/api/action/new_round")
async def api_new_round(req: NewRoundRequest):
    """Resets round and generates 20-40 fresh AI agents."""
    if orchestrator:
        orchestrator.start_new_round(req.crew_count)
        return JSONResponse({"success": True, "message": f"Новый раунд запущен с {orchestrator.crew_count} членами экипажа."})
    return JSONResponse({"error": "Not ready"}, status_code=500)

@app.post("/api/action/set_alert")
async def api_set_alert(req: AlertLevelRequest):
    """Sets station alert level."""
    if orchestrator:
        orchestrator.world.set_alert_level(req.level, req.reason)
        return JSONResponse({"success": True, "alert_level": req.level})
    return JSONResponse({"error": "Not ready"}, status_code=500)

@app.post("/api/action/shuttle/call")
async def api_call_shuttle():
    """Calls emergency evacuation shuttle."""
    if orchestrator:
        success, msg = orchestrator.world.call_emergency_shuttle(caller="Director Dashboard")
        return JSONResponse({"success": success, "message": msg})
    return JSONResponse({"error": "Not ready"}, status_code=500)

@app.post("/api/action/shuttle/recall")
async def api_recall_shuttle():
    """Recalls emergency evacuation shuttle."""
    if orchestrator:
        success, msg = orchestrator.world.recall_emergency_shuttle(caller="Director Dashboard")
        return JSONResponse({"success": success, "message": msg})
    return JSONResponse({"error": "Not ready"}, status_code=500)

@app.post("/api/action/trigger_event")
async def api_trigger_event(req: TriggerEventRequest):
    """Triggers a disaster/event in Director mode."""
    if orchestrator:
        res = orchestrator.director.trigger_event(req.event_id, trigger_source="Director Web Deck")
        return JSONResponse(res)
    return JSONResponse({"error": "Not ready"}, status_code=500)

@app.post("/api/action/whisper")
async def api_whisper(req: WhisperRequest):
    """Injects direct thought into agent's brain."""
    if orchestrator:
        res = orchestrator.director.inject_subconscious_whisper(req.agent_id, req.whisper_text)
        return JSONResponse(res)
    return JSONResponse({"error": "Not ready"}, status_code=500)

@app.post("/api/config/llm")
async def api_config_llm(req: LLMConfigRequest):
    """Updates OpenAI / LLM configuration."""
    if orchestrator:
        orchestrator.set_api_config(
            api_key=req.api_key,
            base_url=req.base_url or "https://api.openai.com/v1",
            model=req.model or "gpt-4o-mini"
        )
        return JSONResponse({"success": True, "message": "Конфигурация OpenAI успешно обновлена!"})
    return JSONResponse({"error": "Not ready"}, status_code=500)

@app.get("/api/agent/{agent_id}/perception")
async def api_agent_perception(agent_id: str):
    """Returns exact perception document (JSON & formatted text)."""
    if not orchestrator:
        return JSONResponse({"error": "Not ready"}, status_code=500)
    agent = orchestrator.world.agents.get(agent_id)
    if not agent:
        return JSONResponse({"error": "Agent not found"}, status_code=404)
    doc = build_perception_document(agent, orchestrator.world)
    doc_text = format_perception_document_text(doc)
    return JSONResponse({
        "document_json": doc,
        "document_text": doc_text
    })

@app.post("/api/agent/{agent_id}/heal")
async def api_heal_agent(agent_id: str):
    """Fully restores agent's health."""
    if not orchestrator:
        return JSONResponse({"error": "Not ready"}, status_code=500)
    agent = orchestrator.world.agents.get(agent_id)
    if agent:
        agent["vitals"]["health"] = 100
        agent["vitals"]["brute_damage"] = 0
        agent["vitals"]["burn_damage"] = 0
        agent["vitals"]["toxin_damage"] = 0
        agent["vitals"]["suffocation_damage"] = 0
        agent["vitals"]["is_alive"] = True
        agent["vitals"]["status_text"] = "Полностью здоров (Восстановлен Режиссером)"
        return JSONResponse({"success": True, "message": f"{agent['name']} полностью исцелен!"})
    return JSONResponse({"error": "Agent not found"}, status_code=404)

@app.post("/api/agent/{agent_id}/teleport")
async def api_teleport_agent(agent_id: str, req: TeleportRequest):
    """Teleports agent to chosen room."""
    if not orchestrator:
        return JSONResponse({"error": "Not ready"}, status_code=500)
    agent = orchestrator.world.agents.get(agent_id)
    if agent and req.destination in orchestrator.world.rooms:
        agent["location"] = req.destination
        return JSONResponse({"success": True, "message": f"{agent['name']} перемещен в {req.destination}"})
    return JSONResponse({"error": "Invalid room or agent"}, status_code=400)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket stream for low-latency live telemetry."""
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        if orchestrator:
            # Send immediate initial state
            snapshot = orchestrator.get_state_snapshot()
            await websocket.send_text(json.dumps({"type": "state_update", "data": snapshot}))
        while True:
            # Listen for incoming client messages (e.g. ping)
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
    except Exception:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
