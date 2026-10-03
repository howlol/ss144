"""
FastAPI Web Server + WebSocket Stream for Space Station 14 AI Station & Browser Gameplay
Serves:
- Real extracted SS14 map & sprite assets (`/assets/...`)
- Live WebSocket state stream (`/ws`)
- OpenAI-compatible API configuration & Browser-Direct LLM Driver (`/api/config`, `/api/agent/next_prompt`, `/api/agent/apply_decision`)
- Full Playable SS14 Crew & Ghost Mode (`/api/player/join`, `/api/player/ghost`, `/api/agent/command`, `/api/bui/action`)
"""

from __future__ import annotations

import asyncio
import random
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Set

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .ai_orchestrator import AIStationOrchestrator
from .ss14_station_runtime import ASSET_ROOT, SS14StationRuntime


WEB_ROOT = Path(__file__).resolve().parent.parent / "web"

runtime = SS14StationRuntime()
orchestrator = AIStationOrchestrator(runtime)
connected_clients: Set[WebSocket] = set()


async def physics_and_broadcast_loop() -> None:
    last_time = time.perf_counter()
    last_broadcast = 0.0
    while True:
        now = time.perf_counter()
        dt = min(0.2, now - last_time)
        last_time = now

        runtime.tick_physics(dt)
        await runtime.check_csharp_bridge()

        # Broadcast live delta at 12 Hz for smooth 60 FPS client interpolation
        if connected_clients and (now - last_broadcast) >= 0.08:
            last_broadcast = now
            payload = {
                "type": "state",
                "state": runtime.get_live_state_delta(),
                "llm": orchestrator.get_public_config(),
                "apiLogs": orchestrator.api_logs[-15:],
                "priorityQueue": orchestrator.priority_agent_queue[:3],
            }
            dead_ws: List[WebSocket] = []
            for ws in list(connected_clients):
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead_ws.append(ws)
            for ws in dead_ws:
                connected_clients.discard(ws)

        await asyncio.sleep(0.04)


async def ai_cognition_loop() -> None:
    while True:
        try:
            await orchestrator.step_agents()
        except Exception as exc:
            orchestrator.last_error = str(exc)
        await asyncio.sleep(max(1.0, orchestrator.config.tick_interval_sec))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    t1 = asyncio.create_task(physics_and_broadcast_loop())
    t2 = asyncio.create_task(ai_cognition_loop())
    yield
    t1.cancel()
    t2.cancel()


app = FastAPI(
    title="Space Station 14 — AI Crew & Playable Browser Server",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/assets", StaticFiles(directory=str(ASSET_ROOT)), name="assets")
app.mount("/static", StaticFiles(directory=str(WEB_ROOT)), name="static")


@app.get("/")
async def index_page():
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/api/bootstrap")
async def get_bootstrap():
    return {
        "map": runtime.map_data,
        "sprites": runtime.sprite_manifest,
        "jobs": runtime.jobs_data,
        "state": runtime.get_live_state_delta(),
        "llm": orchestrator.get_public_config(),
        "apiLogs": orchestrator.api_logs[-20:],
    }


@app.get("/api/config")
async def get_config():
    return orchestrator.get_public_config()


@app.post("/api/config")
async def update_config(payload: Dict[str, Any]):
    updated = orchestrator.update_config(payload)
    return {"ok": True, "llm": updated}


@app.post("/api/config/test")
async def test_openai_connection(payload: Dict[str, Any]):
    if payload:
        orchestrator.update_config(payload)

    key = orchestrator.config.api_key.strip()
    if not key:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "Введите API ключ (API Key)."},
        )

    endpoint = f"{orchestrator.config.base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": orchestrator.config.model,
        "messages": [
            {"role": "system", "content": "Ты — бортовой ИИ станции NSS Saltern в Space Station 14. Ответь одним коротким предложением на русском."},
            {"role": "user", "content": "Проверка связи с мостика станции NSS Saltern."},
        ],
        "max_tokens": 80,
        "temperature": 0.7,
    }
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(endpoint, headers=headers, json=body)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            if resp.status_code != 200:
                return JSONResponse(
                    status_code=resp.status_code,
                    content={"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:250]}"},
                )
            data = resp.json()
            reply = data["choices"][0]["message"]["content"]
            orchestrator.total_llm_calls += 1
            orchestrator.last_error = ""
            return {
                "ok": True,
                "reply": reply,
                "latencyMs": latency_ms,
                "model": orchestrator.config.model,
                "llm": orchestrator.get_public_config(),
            }
    except Exception as exc:
        # Signal browser to run direct browser-side test if backend egress is restricted
        return {
            "ok": False,
            "useBrowserDirect": True,
            "error": f"Backend network ({type(exc).__name__}): проверка выполняется напрямую из вашего браузера",
        }


# ============================================================================
# Browser-Direct OpenAI Execution Endpoints
# ============================================================================

@app.get("/api/agent/next_prompt")
async def get_next_agent_prompt():
    return orchestrator.build_agent_prompt_payload(None)


@app.get("/api/agent/prompt/{agent_id}")
async def get_specific_agent_prompt(agent_id: str):
    return orchestrator.build_agent_prompt_payload(agent_id)


@app.post("/api/agent/apply_decision")
async def apply_agent_decision(payload: Dict[str, Any]):
    agent_id = str(payload.get("agentId") or "")
    raw_content = str(payload.get("content") or "")
    latency_ms = int(payload.get("latencyMs") or 0)
    model_used = str(payload.get("model") or "")
    source = str(payload.get("source") or "browser-direct")
    res = orchestrator.apply_external_llm_decision(agent_id, raw_content, latency_ms, model_used, source)
    return {
        **res,
        "state": runtime.get_live_state_delta(),
        "llm": orchestrator.get_public_config(),
        "apiLogs": orchestrator.api_logs[-15:],
    }


@app.post("/api/agent/llm_error")
async def report_llm_error(payload: Dict[str, Any]):
    agent_id = str(payload.get("agentId") or "")
    error_msg = str(payload.get("error") or "Unknown error")
    print(f"[Browser-LLM Error] agent={agent_id} error={error_msg}", flush=True)
    orchestrator.record_external_llm_error(agent_id, error_msg, "browser-direct")
    return {"ok": True, "llm": orchestrator.get_public_config(), "apiLogs": orchestrator.api_logs[-15:]}


# ============================================================================
# Playable Crew Mode & Ghost Mode Endpoints
# ============================================================================

@app.post("/api/player/join")
async def player_join_game(payload: Dict[str, Any]):
    """Spawns a new playable crew member or switches into an existing crew member."""
    mode = str(payload.get("mode") or "spawn")
    if mode == "takeover":
        agent_id = str(payload.get("agentId") or "")
        ag = runtime.agents.get(agent_id)
        if not ag:
            return JSONResponse(status_code=404, content={"ok": False, "error": "Персонаж не найден"})
        ag.browser_controlled = True
        return {"ok": True, "agentId": ag.id, "state": runtime.get_live_state_delta()}

    name = str(payload.get("name") or "Алекс Мерсер").strip()
    job = str(payload.get("job") or "Passenger").strip()
    room = payload.get("room")
    is_antag = bool(payload.get("isAntagonist", False))
    ag = runtime.spawn_custom_agent(
        name=name,
        job=job,
        personality=str(payload.get("personality") or f"Игрок на станции NSS Saltern ({job})."),
        secret_objective=str(payload.get("secretObjective") or "Исследовать станцию и взаимодействовать с экипажем."),
        is_antagonist=is_antag,
        room=room,
        browser_controlled=True,
        is_ghost=False,
    )
    return {"ok": True, "agentId": ag.id, "state": runtime.get_live_state_delta()}


@app.post("/api/player/ghost")
async def player_enter_ghost_mode(payload: Dict[str, Any]):
    """Spawns or returns the player's Ghost Observer entity (MobObserver)."""
    for ag in runtime.agents.values():
        if ag.is_ghost:
            if "x" in payload and "y" in payload:
                ag.x = float(payload["x"])
                ag.y = float(payload["y"])
                ag.path.clear()
            return {"ok": True, "agentId": ag.id, "state": runtime.get_live_state_delta()}

    ghost = runtime.spawn_custom_agent(
        name=str(payload.get("name") or "Призрак Наблюдателя"),
        job="Ghost",
        personality="Свободный наблюдатель станции NSS Saltern.",
        room=payload.get("room") or "Bridge",
        browser_controlled=True,
        is_ghost=True,
    )
    return {"ok": True, "agentId": ghost.id, "state": runtime.get_live_state_delta()}


@app.post("/api/agent/command")
async def command_agent(payload: Dict[str, Any]):
    agent_id = str(payload.get("agentId") or "")
    action = str(payload.get("action") or "")

    if action == "toggle_door":
        door_uid = int(payload.get("doorUid", 0))
        door = runtime.toggle_door(door_uid, agent_id or None)
        return {"ok": bool(door), "door": door, "state": runtime.get_live_state_delta()}

    agent = runtime.agents.get(agent_id)
    if not agent:
        return JSONResponse(status_code=404, content={"ok": False, "error": "Персонаж не найден"})

    bui_info = None
    extra: Dict[str, Any] = {}

    if action == "say":
        text = str(payload.get("text") or "").strip()
        runtime.command_agent_say(agent_id, text)
        # Immediately prioritize nearby AI crew so they reply to the player!
        queued = orchestrator.prioritize_nearby_agents(agent.x, agent.y, exclude_id=agent.id)
        extra["queuedAiReplies"] = queued

    elif action == "emote":
        text = str(payload.get("text") or "").strip()
        runtime.command_agent_emote(agent_id, text)
        orchestrator.prioritize_nearby_agents(agent.x, agent.y, exclude_id=agent.id)

    elif action == "thought":
        text = str(payload.get("text") or "").strip()
        agent.subconscious_prompt = text
        agent.last_thought = f"[Подсознательный импульс]: {text}"
        if agent.id not in orchestrator.priority_agent_queue:
            orchestrator.priority_agent_queue.insert(0, agent.id)

    elif action == "move_to":
        x = float(payload.get("x", agent.x))
        y = float(payload.get("y", agent.y))
        runtime.command_agent_move_to(agent_id, x, y, payload.get("task"))

    elif action == "move_to_room":
        room = str(payload.get("room") or "")
        runtime.command_agent_move_to_room(agent_id, room, payload.get("task"))

    elif action == "ghost_warp":
        room = str(payload.get("room") or "")
        target_agent_id = str(payload.get("targetAgentId") or "")
        if target_agent_id and target_agent_id in runtime.agents:
            t_ag = runtime.agents[target_agent_id]
            agent.x, agent.y = t_ag.x, t_ag.y
            agent.path.clear()
            agent.current_room = runtime.nearest_room_name(agent.x, agent.y)
        elif room:
            rc = runtime.get_room_coords(room)
            if rc:
                agent.x, agent.y, agent.current_room = rc
                agent.path.clear()

    elif action == "ghost_boo":
        msg = runtime.ghost_boo(agent_id)
        extra["message"] = msg
        orchestrator.prioritize_nearby_agents(agent.x, agent.y, exclude_id=agent.id)

    elif action == "step_dir":
        dx = float(payload.get("dx", 0))
        dy = float(payload.get("dy", 0))
        agent.path.clear()
        step_size = 1.25 if agent.is_ghost else 0.85
        nx = agent.x + dx * step_size
        ny = agent.y + dy * step_size
        tx, ty = int(nx // 1), int(ny // 1)
        if runtime._is_tile_passable(tx, ty, agent.access, is_ghost=agent.is_ghost):
            if not agent.is_ghost:
                door = runtime.doors_by_tile.get((tx, ty))
                if door and not door.get("open") and not door.get("bolted"):
                    door["open"] = True
                    runtime.door_close_timers[int(door["uid"])] = time.time() + 3.5
            agent.x = nx
            agent.y = ny
            agent.current_room = runtime.nearest_room_name(agent.x, agent.y)
            runtime._check_tile_hazards(agent)
        if abs(dx) > abs(dy):
            agent.direction = "east" if dx > 0 else "west"
        elif abs(dy) > 0:
            agent.direction = "north" if dy > 0 else "south"

    elif action == "swap_hands":
        runtime.swap_hands(agent_id)

    elif action == "drop_item":
        runtime.drop_active_item(agent_id)

    elif action == "pickup_item":
        uid = int(payload.get("uid", 0))
        runtime.pickup_floor_item(agent_id, uid)

    elif action == "use_hand":
        msg = runtime.use_item_in_hand(agent_id)
        extra["message"] = msg

    elif action == "equip_inv":
        idx = int(payload.get("index", -1))
        runtime.equip_from_inventory(agent_id, idx)

    elif action == "toggle_combat":
        agent.combat_mode = not agent.combat_mode

    elif action == "interact_agent":
        target_id = str(payload.get("targetAgentId") or "")
        res = runtime.attack_or_interact_target_agent(agent_id, target_id)
        extra.update(res)
        if target_id in runtime.agents:
            t_ag = runtime.agents[target_id]
            orchestrator.prioritize_nearby_agents(t_ag.x, t_ag.y, exclude_id=agent.id)

    elif action == "interact":
        uid = int(payload.get("uid", 0))
        res = runtime.interact_with_object(agent_id, uid)
        extra.update(res)
        bui_info = res.get("bui")

    elif action == "interact_nearest":
        res = runtime.interact_nearest(agent_id)
        extra.update(res)
        bui_info = res.get("bui")

    elif action == "toggle_browser_control":
        agent.browser_controlled = bool(payload.get("enabled", not agent.browser_controlled))

    elif action == "force_llm_step":
        res = await orchestrator.query_openai_for_agent(agent)
        if res:
            orchestrator._apply_decision(agent, res)
            return {"ok": True, "decision": res, "state": runtime.get_live_state_delta()}
        else:
            # Return prompt so browser can execute it directly!
            prompt_payload = orchestrator.build_agent_prompt_payload(agent.id)
            return {
                "ok": False,
                "executeInBrowser": True,
                "promptPayload": prompt_payload,
                "error": orchestrator.last_error or "Выполняется напрямую через браузер",
            }

    return {"ok": True, "bui": bui_info, **extra, "state": runtime.get_live_state_delta()}


@app.post("/api/bui/action")
async def handle_station_bui_action(payload: Dict[str, Any]):
    """Handles interactions inside SS14 Machine/Console Bound User Interfaces (Cargo, Vending, Comms, Uplink, MedScanner)."""
    agent_id = str(payload.get("agentId") or "")
    bui_type = str(payload.get("buiType") or "")
    sub_action = str(payload.get("subAction") or "")
    item_id = str(payload.get("itemId") or "")

    agent = runtime.agents.get(agent_id)
    if not agent:
        return JSONResponse(status_code=404, content={"ok": False, "error": "Персонаж не найден"})

    msg = ""
    if bui_type in ("vending", "chem_master"):
        item_name = runtime.give_item_to_agent(agent_id, item_id or "DrinkMug")
        msg = f"Автомат выдал: {item_name}"

    elif bui_type == "uplink":
        cost = int(payload.get("cost", 4))
        if agent.telecrystals < cost:
            return {"ok": False, "error": f"Недостаточно телекристаллов ({agent.telecrystals} TC < {cost} TC)"}
        agent.telecrystals -= cost
        item_name = runtime.give_item_to_agent(agent_id, item_id or "EnergySword")
        msg = f"Загружено из Аплинка Синдиката: {item_name} (-{cost} TC)"

    elif bui_type == "cargo_console":
        crate_type = str(payload.get("crate") or "medical")
        cost = int(payload.get("cost", 800))
        if runtime.cargo_balance < cost:
            return {"ok": False, "error": "Недостаточно космокредитов на балансе Карго!"}
        runtime.cargo_balance -= cost
        crate_items = {
            "medical": ["Medkit", "Brutekit", "Burnkit", "Medipen"],
            "engineering": ["RCD", "Multitool", "Welder", "Crowbar", "GasAnalyzer"],
            "armory": ["Disabler", "Shotgun", "WT550", "Stunbaton"],
            "party": ["Whiskey", "DrinkMug", "Banana", "BikeHorn"],
        }.get(crate_type, ["Medkit", "Crowbar"])
        for it in crate_items:
            runtime.spawn_floor_item(it, agent.x + random.uniform(-0.8, 0.8), agent.y + random.uniform(-0.8, 0.8))
        runtime.add_chat_message(
            speaker_uid=0,
            speaker_id="cargo-shuttle",
            speaker_name="Консоль Снабжения Карго",
            speaker_job="Supply",
            speaker_dept="Cargo",
            channel="Cargo",
            message=f"{agent.name} оформил доставку ящика «{crate_type.upper()}» в отсек {agent.current_room} (-{cost} кредитов).",
            x=agent.x,
            y=agent.y,
        )
        msg = f"Доставлен заказ Карго: {crate_type.upper()}"

    elif bui_type == "comms_console":
        if sub_action == "announce":
            text = str(payload.get("text") or "Внимание экипажу станции!")
            runtime.trigger_station_event("custom", f"[Консоль Связи Мостика — {agent.name}]: {text}")
            msg = "Объявление отправлено по всей станции!"
        elif sub_action in ("green_alert", "blue_alert", "red_alert"):
            runtime.trigger_station_event(sub_action)
            msg = f"Код безопасности изменён на {runtime.alert_level.upper()}"

    elif bui_type == "med_scanner":
        for other in runtime.agents.values():
            if not other.is_ghost and ((other.x - agent.x) ** 2 + (other.y - agent.y) ** 2) ** 0.5 <= 3.5:
                other.health = other.max_health
                other.status = "Alive"
                other.stunned_until = 0.0
                runtime.add_visual_effect("heal", other.x, other.y, other.x, other.y, "#22c55e", 0.8)
        msg = "Медицинский сканер исцелил всех пациентов рядом!"

    elif bui_type == "id_console":
        if "AllAccess" not in agent.access:
            agent.access.append("AllAccess")
        msg = f"На ID-карту {agent.name} записан полный доступ (AllAccess)!"

    return {"ok": True, "message": msg, "state": runtime.get_live_state_delta()}


@app.post("/api/agents/spawn")
async def spawn_agent_endpoint(payload: Dict[str, Any]):
    name = str(payload.get("name") or "Новый Сотрудник").strip()
    job = str(payload.get("job") or "Passenger").strip()
    personality = str(payload.get("personality") or "").strip()
    secret_objective = str(payload.get("secretObjective") or "").strip()
    is_antagonist = bool(payload.get("isAntagonist", False))
    room = payload.get("room")
    browser_controlled = bool(payload.get("browserControlled", False))

    ag = runtime.spawn_custom_agent(
        name=name,
        job=job,
        personality=personality,
        secret_objective=secret_objective,
        is_antagonist=is_antagonist,
        room=room,
        browser_controlled=browser_controlled,
    )
    return {"ok": True, "agentId": ag.id, "state": runtime.get_live_state_delta()}


@app.post("/api/station/event")
async def trigger_event_endpoint(payload: Dict[str, Any]):
    ev_type = str(payload.get("eventType") or "red_alert")
    custom_text = str(payload.get("customText") or "")
    res = runtime.trigger_station_event(ev_type, custom_text)
    return {**res, "state": runtime.get_live_state_delta()}


@app.post("/api/station/reset")
async def reset_station_round():
    runtime.round_id += 1
    runtime.round_start_time = time.time()
    runtime.alert_level = "green"
    runtime.station_power_kw = 480.0
    runtime.atmos_status = "Nominal (21% O2 / 79% N2, 101.3 kPa)"
    runtime._spawn_initial_crew()
    runtime._spawn_initial_floor_items()
    return {"ok": True, "state": runtime.get_live_state_delta()}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.add(ws)
    try:
        await ws.send_json({
            "type": "state",
            "state": runtime.get_live_state_delta(),
            "llm": orchestrator.get_public_config(),
            "apiLogs": orchestrator.api_logs[-15:],
            "priorityQueue": orchestrator.priority_agent_queue[:3],
        })
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")
            if mtype == "ping":
                await ws.send_json({"type": "pong"})
            elif mtype == "player_move":
                aid = str(msg.get("agentId") or "")
                ag = runtime.agents.get(aid)
                if ag:
                    nx = float(msg.get("x", ag.x))
                    ny = float(msg.get("y", ag.y))
                    direction = str(msg.get("direction") or ag.direction)
                    ag.path.clear()
                    tx, ty = int(nx // 1), int(ny // 1)
                    if runtime._is_tile_passable(tx, ty, ag.access, is_ghost=ag.is_ghost):
                        if not ag.is_ghost:
                            door = runtime.doors_by_tile.get((tx, ty))
                            if door and not door.get("open") and not door.get("bolted"):
                                door["open"] = True
                                runtime.door_close_timers[int(door["uid"])] = time.time() + 3.5
                        ag.x = nx
                        ag.y = ny
                        ag.direction = direction
                        ag.current_room = runtime.nearest_room_name(ag.x, ag.y)
                        runtime._check_tile_hazards(ag)
    except WebSocketDisconnect:
        connected_clients.discard(ws)
    except Exception:
        connected_clients.discard(ws)
