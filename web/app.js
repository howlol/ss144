/**
 * Space Station 14 — High-Performance 60 FPS Browser Gameplay, Ghost Mode & OpenAI Multi-Agent Client
 * Features:
 * - Viewport-culled O(visible_tiles) renderer with 60 FPS entity interpolation
 * - Direct Browser + Server OpenAI-Compatible API Execution (works with OpenAI, OpenRouter, DeepSeek, Groq & localhost Ollama)
 * - Full Playable SS14 Crew Mode (WASD, Left/Right Hands, Belt Inventory, Floor Items, Combat/Lasers/Stun, RCD, Door Hacking, BUI Consoles)
 * - Ghost Mode (MobObserver: fly through walls, Ghost Warp, Ghost Boo, Possess any crew member)
 * - 53 Surveillance Cameras + 4-Camera Quad Split-Screen
 */

const TILE_PX = 32;

const state = {
  map: null,
  sprites: null,
  jobs: null,
  live: null,
  llm: null,
  apiLogs: [],

  // Spatial lookup maps built once at bootstrap for 60 FPS viewport culling
  spatial: {
    tiles: new Map(),     // "tx,ty" -> [tname, variant]
    walls: new Map(),     // "tx,ty" -> wallObj
    windows: new Map(),   // "tx,ty" -> winObj
    objects: new Map(),   // "tx,ty" -> [obj, ...]
    doorsByTile: new Map(), // "tx,ty" -> doorObj
  },

  // Smooth 60 FPS interpolated positions per agent id
  renderPos: new Map(), // agentId -> { x, y }

  // Gameplay & Viewport mode: "play" | "ghost" | "cctv"
  gameMode: "play",
  previousPlayAgentId: "captain-vance",

  // Camera state
  viewMode: "follow", // "follow" | "single" | "quad" | "free"
  activeCameraId: null,
  quadCameraIds: ["Bridge", "Bar", "Medbay", "Security"],
  camX: 3.5,
  camY: 28.5,
  zoom: 1.35,
  showNames: true,
  showPaths: true,
  crtEnabled: false,

  // Active player/selected character
  selectedAgentId: "captain-vance",

  // Dragging & keyboard state
  isDragging: false,
  dragMoved: false,
  dragStartX: 0,
  dragStartY: 0,
  camStartX: 0,
  camStartY: 0,
  keysDown: new Set(),
  lastWasdTime: 0,

  // Image cache
  imageCache: new Map(),

  // Browser-Direct OpenAI API settings (persisted in localStorage)
  browserLlm: {
    apiKey: localStorage.getItem("ss14_openai_key") || "",
    baseUrl: localStorage.getItem("ss14_openai_url") || "https://api.openai.com/v1",
    model: localStorage.getItem("ss14_openai_model") || "gpt-4o-mini",
    intervalSec: parseFloat(localStorage.getItem("ss14_openai_interval") || "2.5"),
    inFlight: false,
    lastCallTime: 0,
  },

  // Fingerprints to avoid unnecessary DOM rebuilds
  domHashes: {
    crew: "",
    chat: 0,
    apiLogs: 0,
    hud: "",
    inspector: "",
  },

  // FPS counter
  fpsFrames: 0,
  fpsLastTime: performance.now(),
  currentFps: 60,
};

// ============================================================================
// Image Loader & Sprite Atlas Resolver
// ============================================================================

function getSpriteImage(url) {
  if (!url) return null;
  if (state.imageCache.has(url)) {
    return state.imageCache.get(url);
  }
  const img = new Image();
  img.src = url;
  state.imageCache.set(url, img);
  return img;
}

function drawFirstFrame(ctx, img, dx, dy, dw, dh) {
  if (!img || !img.complete || img.naturalWidth === 0) return false;
  const nw = img.naturalWidth;
  const nh = img.naturalHeight;
  if (nw > 32 || nh > 32) {
    const frameW = nw >= 32 ? 32 : nw;
    const frameH = nh >= 32 ? 32 : nh;
    ctx.drawImage(img, 0, 0, frameW, frameH, dx, dy, dw, dh);
  } else {
    ctx.drawImage(img, dx, dy, dw, dh);
  }
  return true;
}

function drawDirectionalFrame(ctx, img, direction, dx, dy, dw, dh) {
  if (!img || !img.complete || img.naturalWidth === 0) return false;
  const nw = img.naturalWidth;
  const nh = img.naturalHeight;
  if (nw >= 128 && nh >= 32) {
    const dirMap = { south: 0, north: 1, east: 2, west: 3 };
    const dirIdx = dirMap[direction] ?? 0;
    ctx.drawImage(img, dirIdx * 32, 0, 32, 32, dx, dy, dw, dh);
  } else {
    drawFirstFrame(ctx, img, dx, dy, dw, dh);
  }
  return true;
}

function worldToScreen(wx, wy, canvasWidth, canvasHeight, centerCamX, centerCamY, zoom) {
  const scale = TILE_PX * zoom;
  const sx = canvasWidth / 2 + (wx - centerCamX) * scale;
  const sy = canvasHeight / 2 - (wy - centerCamY) * scale;
  return [sx, sy, scale];
}

function screenToWorld(sx, sy, canvasWidth, canvasHeight, centerCamX, centerCamY, zoom) {
  const scale = TILE_PX * zoom;
  const wx = centerCamX + (sx - canvasWidth / 2) / scale;
  const wy = centerCamY - (sy - canvasHeight / 2) / scale;
  return [wx, wy];
}

// ============================================================================
// Spatial Map Indexing (O(1) Tile & Entity Lookup)
// ============================================================================

function buildSpatialIndex() {
  if (!state.map) return;
  state.spatial.tiles.clear();
  state.spatial.walls.clear();
  state.spatial.windows.clear();
  state.spatial.objects.clear();
  state.spatial.doorsByTile.clear();

  for (const [tx, ty, tname, variant] of state.map.tiles) {
    state.spatial.tiles.set(`${tx},${ty}`, [tname, variant]);
  }
  for (const w of state.map.walls) {
    const tx = Math.floor(w.x);
    const ty = Math.floor(w.y);
    state.spatial.walls.set(`${tx},${ty}`, w);
  }
  for (const win of state.map.windows) {
    const tx = Math.floor(win.x);
    const ty = Math.floor(win.y);
    state.spatial.windows.set(`${tx},${ty}`, win);
  }
  for (const d of state.map.doors) {
    const tx = Math.floor(d.x);
    const ty = Math.floor(d.y);
    state.spatial.doorsByTile.set(`${tx},${ty}`, d);
  }
  for (const obj of state.map.objects) {
    const tx = Math.floor(obj.x);
    const ty = Math.floor(obj.y);
    const key = `${tx},${ty}`;
    if (!state.spatial.objects.has(key)) {
      state.spatial.objects.set(key, []);
    }
    state.spatial.objects.get(key).push(obj);
  }
}

// ============================================================================
// Initialization & WebSocket Stream
// ============================================================================

async function initApp() {
  const res = await fetch("/api/bootstrap");
  const data = await res.json();

  state.map = data.map;
  state.sprites = data.sprites;
  state.jobs = data.jobs;
  state.live = data.state;
  state.llm = data.llm;
  state.apiLogs = data.apiLogs || [];

  buildSpatialIndex();

  // Preload core textures
  if (state.sprites) {
    Object.values(state.sprites.tiles || {}).forEach(getSpriteImage);
    Object.values(state.sprites.humanoid || {}).forEach(getSpriteImage);
    Object.values(state.sprites.items || {}).forEach((it) => getSpriteImage(it.url));
  }

  // Sync saved browser API key to server on startup if present
  if (state.browserLlm.apiKey) {
    fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        apiKey: state.browserLlm.apiKey,
        baseUrl: state.browserLlm.baseUrl,
        model: state.browserLlm.model,
        tickIntervalSec: state.browserLlm.intervalSec,
      }),
    }).catch(() => {});
  }

  populateCameraLists();
  populateBeaconsAndRooms();
  bindUIEvents();
  updateTopTelemetry();
  renderCrewRoster(true);
  renderInspector(true);
  renderPlayerHud(true);
  renderChatFeed(true);
  renderApiLogs(true);

  connectWebSocket();
  startBrowserDirectLlmLoop();
  requestAnimationFrame(renderLoop);
}

function connectWebSocket() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/ws`);

  ws.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === "state") {
        // Keep walls synced if RCD modified them
        state.live = payload.state;
        state.llm = payload.llm;
        state.apiLogs = payload.apiLogs || [];
        updateTopTelemetry();
        renderCrewRoster(false);
        renderInspector(false);
        renderPlayerHud(false);
        renderChatFeed(false);
        renderApiLogs(false);
      }
    } catch (e) {
      console.error("WS parse error:", e);
    }
  };

  ws.onclose = () => {
    setTimeout(connectWebSocket, 2000);
  };
}

// ============================================================================
// Direct Browser OpenAI API Execution Engine
// ============================================================================

function getActiveApiKey() {
  return (state.browserLlm.apiKey || "").trim();
}

function startBrowserDirectLlmLoop() {
  setInterval(() => {
    const key = getActiveApiKey();
    if (!key || state.browserLlm.inFlight) return;
    const now = performance.now();
    const waitMs = Math.max(1200, (state.browserLlm.intervalSec || 2.5) * 1000);
    if (now - state.browserLlm.lastCallTime >= waitMs) {
      runBrowserDirectLlmStep( null );
    }
  }, 600);
}

async function runBrowserDirectLlmStep(specificAgentId = null) {
  const apiKey = getActiveApiKey();
  if (!apiKey) return { ok: false, error: "API ключ не задан" };
  if (state.browserLlm.inFlight) return { ok: false, error: "Запрос уже выполняется" };

  state.browserLlm.inFlight = true;
  state.browserLlm.lastCallTime = performance.now();
  updateTopTelemetry();

  const statusEl = document.getElementById("apiDirectStatusText");
  let promptData = null;

  try {
    const promptUrl = specificAgentId
      ? `/api/agent/prompt/${encodeURIComponent(specificAgentId)}`
      : `/api/agent/next_prompt`;
    const pRes = await fetch(promptUrl);
    promptData = await pRes.json();
    if (!promptData.ok) {
      state.browserLlm.inFlight = false;
      updateTopTelemetry();
      return promptData;
    }

    const baseUrl = (state.browserLlm.baseUrl || "https://api.openai.com/v1").trim().replace(/\/+$/, "");
    const endpoint = baseUrl.endsWith("/chat/completions") ? baseUrl : `${baseUrl}/chat/completions`;
    const model = (state.browserLlm.model || "gpt-4o-mini").trim();

    if (statusEl) {
      statusEl.textContent = `📡 Запрос к ${model} для «${promptData.agentName}»...`;
    }

    const t0 = performance.now();
    const llmRes = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages: promptData.messages,
        temperature: 0.85,
        max_tokens: 320,
      }),
    });

    const latencyMs = Math.round(performance.now() - t0);

    if (!llmRes.ok) {
      const errTxt = (await llmRes.text()).slice(0, 220);
      await fetch("/api/agent/llm_error", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agentId: promptData.agentId,
          error: `HTTP ${llmRes.status}: ${errTxt}`,
        }),
      });
      if (statusEl) {
        statusEl.textContent = `❌ Ошибка HTTP ${llmRes.status}`;
      }
      state.browserLlm.inFlight = false;
      updateTopTelemetry();
      return { ok: false, error: `HTTP ${llmRes.status}: ${errTxt}` };
    }

    const data = await llmRes.json();
    const content = data?.choices?.[0]?.message?.content || "";

    const applyRes = await fetch("/api/agent/apply_decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agentId: promptData.agentId,
        content,
        latencyMs,
        model,
        source: "browser-direct",
      }),
    });
    const applied = await applyRes.json();
    if (applied.state) {
      state.live = applied.state;
      state.llm = applied.llm;
      state.apiLogs = applied.apiLogs || state.apiLogs;
      renderCrewRoster(false);
      renderInspector(false);
      renderPlayerHud(false);
      renderChatFeed(false);
      renderApiLogs(true);
    }
    if (statusEl) {
      statusEl.textContent = `✅ Ответ от ${model} за ${latencyMs} мс (${promptData.agentName})`;
    }
    state.browserLlm.inFlight = false;
    updateTopTelemetry();
    return applied;
  } catch (err) {
    if (promptData?.agentId) {
      fetch("/api/agent/llm_error", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agentId: promptData.agentId,
          error: String(err.message || err),
        }),
      }).catch(() => {});
    }
    if (statusEl) {
      statusEl.textContent = `⚠️ Сетевая ошибка: ${err.message || err}`;
    }
    state.browserLlm.inFlight = false;
    updateTopTelemetry();
    return { ok: false, error: String(err.message || err) };
  }
}

// ============================================================================
// High-Performance 60 FPS Viewport-Culled Canvas Renderer
// ============================================================================

function renderLoop(now) {
  state.fpsFrames++;
  if (now - state.fpsLastTime >= 1000) {
    state.currentFps = state.fpsFrames;
    state.fpsFrames = 0;
    state.fpsLastTime = now;
    const fpsEl = document.getElementById("fpsCounter");
    if (fpsEl) fpsEl.textContent = `${state.currentFps} FPS`;
  }

  handleContinuousWasd(now);
  interpolateAgents();

  if (state.viewMode === "quad") {
    renderQuadViewports();
  } else {
    renderMainViewport();
  }

  requestAnimationFrame(renderLoop);
}

function interpolateAgents() {
  if (!state.live || !state.live.agents) return;
  for (const ag of state.live.agents) {
    const cur = state.renderPos.get(ag.id);
    if (!cur || Math.hypot(ag.x - cur.x, ag.y - cur.y) > 6.0) {
      state.renderPos.set(ag.id, { x: ag.x, y: ag.y });
    } else {
      cur.x += (ag.x - cur.x) * 0.28;
      cur.y += (ag.y - cur.y) * 0.28;
    }
  }

  // In "play" or "ghost" mode with follow camera, keep camera centered on active agent
  if (state.viewMode === "follow" && state.selectedAgentId) {
    const rpos = state.renderPos.get(state.selectedAgentId);
    if (rpos) {
      state.camX += (rpos.x - state.camX) * 0.22;
      state.camY += (rpos.y - state.camY) * 0.22;
    }
  }
}

function renderMainViewport() {
  const canvas = document.getElementById("stationCanvas");
  if (!canvas || !state.map) return;

  const rect = canvas.parentElement.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
  const targetW = Math.floor(rect.width * dpr);
  const targetH = Math.floor(rect.height * dpr);
  if (canvas.width !== targetW || canvas.height !== targetH) {
    canvas.width = targetW;
    canvas.height = targetH;
  }

  const ctx = canvas.getContext("2d");
  ctx.save();
  ctx.scale(dpr, dpr);
  renderStationScene(ctx, rect.width, rect.height, state.camX, state.camY, state.zoom, true);
  ctx.restore();
}

function renderQuadViewports() {
  for (let i = 0; i < 4; i++) {
    const canvas = document.getElementById(`quadCanvas${i}`);
    if (!canvas) continue;
    const rect = canvas.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    if (canvas.width !== Math.floor(rect.width) || canvas.height !== Math.floor(rect.height)) {
      canvas.width = Math.floor(rect.width);
      canvas.height = Math.floor(rect.height);
    }

    const camId = state.quadCameraIds[i];
    const camObj = (state.map?.cameras || []).find((c) => c.id === camId) || { x: 0, y: 0 };
    const ctx = canvas.getContext("2d");
    renderStationScene(ctx, rect.width, rect.height, camObj.x, camObj.y, 1.05, false);
  }
}

function renderStationScene(ctx, width, height, centerCamX, centerCamY, zoom, isInteractive) {
  ctx.imageSmoothingEnabled = false;

  // 1. Deep space background
  ctx.fillStyle = "#040710";
  ctx.fillRect(0, 0, width, height);

  if (!state.map || !state.sprites) return;

  const scale = TILE_PX * zoom;
  const halfCols = Math.ceil(width / scale / 2) + 2;
  const halfRows = Math.ceil(height / scale / 2) + 2;

  const minTx = Math.floor(centerCamX) - halfCols;
  const maxTx = Math.floor(centerCamX) + halfCols;
  const minTy = Math.floor(centerCamY) - halfRows;
  const maxTy = Math.floor(centerCamY) + halfRows;

  const tileSprites = state.sprites.tiles || {};
  const protoSprites = state.sprites.prototypes || {};
  const openDoors = new Set(state.live?.openDoorUids || []);
  const boltedDoors = new Set(state.live?.boltedDoorUids || []);

  // 2. Viewport-culled Floors, Walls, Windows & Static Objects (O(visible_tiles)!)
  for (let ty = maxTy; ty >= minTy; ty--) {
    for (let tx = minTx; tx <= maxTx; tx++) {
      const key = `${tx},${ty}`;
      const tileInfo = state.spatial.tiles.get(key);
      if (!tileInfo) continue;

      const sx = Math.floor(width / 2 + (tx - centerCamX) * scale);
      const sy = Math.floor(height / 2 - (ty + 1 - centerCamY) * scale);
      const drawSize = Math.ceil(scale);

      // Floor tile
      const tname = tileInfo[0];
      if (tname === "FloorLattice") {
        ctx.strokeStyle = "#334155";
        ctx.lineWidth = 1;
        ctx.strokeRect(sx + 2, sy + 2, drawSize - 4, drawSize - 4);
      } else {
        const tUrl = tileSprites[tname] || tileSprites["FloorSteel"];
        const tImg = getSpriteImage(tUrl);
        if (!drawFirstFrame(ctx, tImg, sx, sy, drawSize, drawSize)) {
          ctx.fillStyle = "#1e293b";
          ctx.fillRect(sx, sy, drawSize, drawSize);
        }
      }

      // Objects on this tile
      const objs = state.spatial.objects.get(key);
      if (objs) {
        for (const obj of objs) {
          const pInfo = protoSprites[obj.proto];
          const oImg = pInfo ? getSpriteImage(pInfo.url) : null;
          if (!drawFirstFrame(ctx, oImg, sx, sy, drawSize, drawSize)) {
            ctx.fillStyle = obj.category === "console" ? "#0284c7" : "#475569";
            ctx.fillRect(sx + 4, sy + 4, drawSize - 8, drawSize - 8);
          }
        }
      }

      // Wall on this tile
      const wall = state.spatial.walls.get(key);
      if (wall) {
        const pInfo = protoSprites[wall.proto] || protoSprites["WallSolid"];
        const wImg = pInfo ? getSpriteImage(pInfo.url) : null;
        if (!drawFirstFrame(ctx, wImg, sx, sy, drawSize, drawSize)) {
          ctx.fillStyle = "#475569";
          ctx.fillRect(sx, sy, drawSize, drawSize);
        }
      }

      // Window on this tile
      const win = state.spatial.windows.get(key);
      if (win) {
        const pInfo = protoSprites[win.proto] || protoSprites["Window"];
        const winImg = pInfo ? getSpriteImage(pInfo.url) : null;
        if (!drawFirstFrame(ctx, winImg, sx, sy, drawSize, drawSize)) {
          ctx.fillStyle = "rgba(56, 189, 248, 0.35)";
          ctx.fillRect(sx + 2, sy + 2, drawSize - 4, drawSize - 4);
        }
      }

      // Door / Airlock on this tile
      const door = state.spatial.doorsByTile.get(key);
      if (door) {
        const isOpen = openDoors.has(door.uid);
        const isBolted = boltedDoors.has(door.uid);
        const pInfo = protoSprites[door.proto] || protoSprites["Airlock"];
        if (isOpen) {
          ctx.strokeStyle = "rgba(34, 197, 94, 0.65)";
          ctx.lineWidth = Math.max(1, 1.5 * zoom);
          ctx.strokeRect(sx + 2, sy + 2, drawSize - 4, drawSize - 4);
        } else {
          const dImg = pInfo ? getSpriteImage(pInfo.url) : null;
          if (!drawFirstFrame(ctx, dImg, sx, sy, drawSize, drawSize)) {
            ctx.fillStyle = "#334155";
            ctx.fillRect(sx, sy, drawSize, drawSize);
          }
          if (isBolted) {
            ctx.strokeStyle = "#ef4444";
            ctx.lineWidth = 2;
            ctx.strokeRect(sx + 1, sy + 1, drawSize - 2, drawSize - 2);
          }
        }
      }
    }
  }

  // 3. Floor Items (Pickable SS14 items lying on the station floor)
  if (state.live?.floorItems) {
    for (const fi of state.live.floorItems) {
      if (fi.x < minTx || fi.x > maxTx || fi.y < minTy || fi.y > maxTy) continue;
      const [sx, sy] = worldToScreen(fi.x, fi.y, width, height, centerCamX, centerCamY, zoom);
      const itemSize = scale * 0.72;
      const img = getSpriteImage(fi.url);
      drawFirstFrame(ctx, img, sx - itemSize / 2, sy - itemSize / 2, itemSize, itemSize);
    }
  }

  // 4. Room Beacons (subtle labels)
  if (zoom >= 0.75) {
    ctx.font = `700 ${Math.max(9, Math.floor(10 * zoom))}px Inter, sans-serif`;
    ctx.textAlign = "center";
    for (const b of state.map.beacons) {
      if (b.x < minTx || b.x > maxTx || b.y < minTy || b.y > maxTy) continue;
      const [sx, sy] = worldToScreen(b.x, b.y, width, height, centerCamX, centerCamY, zoom);
      ctx.fillStyle = "rgba(56, 189, 248, 0.25)";
      ctx.fillText(b.name.toUpperCase(), sx, sy);
    }
  }

  // 5. AI Navigation Paths
  if (state.showPaths && state.live?.agents && isInteractive) {
    for (const ag of state.live.agents) {
      if (!ag.path || ag.path.length === 0) continue;
      const rpos = state.renderPos.get(ag.id) || ag;
      ctx.save();
      ctx.strokeStyle = ag.color || "#38bdf8";
      ctx.globalAlpha = ag.id === state.selectedAgentId ? 0.65 : 0.22;
      ctx.lineWidth = Math.max(1.5, 2 * zoom);
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      const [startSx, startSy] = worldToScreen(rpos.x, rpos.y, width, height, centerCamX, centerCamY, zoom);
      ctx.moveTo(startSx, startSy);
      for (const [px, py] of ag.path) {
        const [psx, psy] = worldToScreen(px, py, width, height, centerCamX, centerCamY, zoom);
        ctx.lineTo(psx, psy);
      }
      ctx.stroke();
      ctx.restore();
    }
  }

  // 6. Visual Effects (Laser Beams, Stun Slash, Healing Aura, HONK, Ghost Boo)
  if (state.live?.effects) {
    for (const ef of state.live.effects) {
      const [sx1, sy1] = worldToScreen(ef.x1, ef.y1, width, height, centerCamX, centerCamY, zoom);
      const [sx2, sy2] = worldToScreen(ef.x2, ef.y2, width, height, centerCamX, centerCamY, zoom);
      ctx.save();
      if (ef.type === "beam") {
        ctx.strokeStyle = ef.color || "#ef4444";
        ctx.lineWidth = Math.max(3, 4 * zoom);
        ctx.shadowColor = ef.color || "#ef4444";
        ctx.shadowBlur = 12;
        ctx.beginPath();
        ctx.moveTo(sx1, sy1);
        ctx.lineTo(sx2, sy2);
        ctx.stroke();
      } else if (ef.type === "heal" || ef.type === "boo" || ef.type === "explosion" || ef.type === "honk") {
        ctx.strokeStyle = ef.color || "#22c55e";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(sx1, sy1, scale * 0.75, 0, Math.PI * 2);
        ctx.stroke();
        if (ef.type === "honk") {
          ctx.fillStyle = "#fde047";
          ctx.font = `900 ${Math.floor(13 * zoom)}px Inter, sans-serif`;
          ctx.textAlign = "center";
          ctx.fillText("ХОНК!!", sx1, sy1 - scale * 0.8);
        }
      } else if (ef.type === "slash") {
        ctx.strokeStyle = "#ef4444";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(sx2 - 10, sy2 - 10);
        ctx.lineTo(sx2 + 10, sy2 + 10);
        ctx.stroke();
      }
      ctx.restore();
    }
  }

  // 7. Render Crew Agents & Ghost Observers
  if (state.live?.agents) {
    const hum = state.sprites.humanoid || {};
    const outfits = state.sprites.job_outfits || {};

    for (const ag of state.live.agents) {
      const rpos = state.renderPos.get(ag.id) || ag;
      if (rpos.x < minTx - 1 || rpos.x > maxTx + 1 || rpos.y < minTy - 1 || rpos.y > maxTy + 1) continue;

      const [sx, sy] = worldToScreen(rpos.x, rpos.y, width, height, centerCamX, centerCamY, zoom);
      const drawX = sx - scale / 2;
      const drawY = sy - scale / 2;

      // Selection ring
      if (ag.id === state.selectedAgentId) {
        ctx.save();
        ctx.strokeStyle = ag.combatMode ? "#ef4444" : (ag.isGhost ? "#a855f7" : "#38bdf8");
        ctx.lineWidth = Math.max(2, 2.5 * zoom);
        ctx.beginPath();
        ctx.arc(sx, sy, scale * 0.58, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }

      ctx.save();
      if (ag.isGhost) {
        ctx.globalAlpha = 0.78;
        const ghostImg = getSpriteImage(hum.ghost);
        if (!drawDirectionalFrame(ctx, ghostImg, ag.direction, drawX, drawY, scale, scale)) {
          ctx.fillStyle = "#a855f7";
          ctx.beginPath();
          ctx.arc(sx, sy, scale * 0.38, 0, Math.PI * 2);
          ctx.fill();
        }
      } else {
        // Stunned / Dead rotation
        if (ag.status === "Dead" || ag.stunned) {
          ctx.translate(sx, sy);
          ctx.rotate(Math.PI / 2);
          ctx.translate(-sx, -sy);
        }

        const bodyParts = [hum.chest, hum.head, hum.l_arm, hum.r_arm, hum.l_leg, hum.r_leg, hum.l_hand, hum.r_hand, hum.l_foot, hum.r_foot, hum.eyes];
        let drewBody = false;
        for (const partUrl of bodyParts) {
          const img = getSpriteImage(partUrl);
          if (drawDirectionalFrame(ctx, img, ag.direction, drawX, drawY, scale, scale)) {
            drewBody = true;
          }
        }

        const outfit = outfits[ag.job] || outfits["Passenger"] || {};
        if (outfit.jumpsuit) {
          drawDirectionalFrame(ctx, getSpriteImage(outfit.jumpsuit), ag.direction, drawX, drawY, scale, scale);
        }
        if (outfit.shoes) {
          drawDirectionalFrame(ctx, getSpriteImage(outfit.shoes), ag.direction, drawX, drawY, scale, scale);
        }
        if (outfit.outer) {
          drawDirectionalFrame(ctx, getSpriteImage(outfit.outer), ag.direction, drawX, drawY, scale, scale);
        }
        if (outfit.head) {
          drawDirectionalFrame(ctx, getSpriteImage(outfit.head), ag.direction, drawX, drawY, scale, scale);
        }

        // Draw held item icon in hand
        const activeHandObj = ag.activeHand === "left" ? ag.leftHand : ag.rightHand;
        if (activeHandObj && activeHandObj.url) {
          const itemImg = getSpriteImage(activeHandObj.url);
          drawFirstFrame(ctx, itemImg, sx + scale * 0.05, sy - scale * 0.05, scale * 0.45, scale * 0.45);
        }

        if (!drewBody) {
          ctx.fillStyle = ag.color || "#38bdf8";
          ctx.beginPath();
          ctx.arc(sx, sy, scale * 0.38, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      ctx.restore();

      // Status icons above head (Stunned / Cuffed / Dead)
      if (ag.stunned || ag.cuffed || ag.status === "Dead") {
        ctx.font = `700 ${Math.max(10, Math.floor(11 * zoom))}px Inter, sans-serif`;
        ctx.textAlign = "center";
        ctx.fillStyle = "#fde047";
        const badge = ag.status === "Dead" ? "💀 МЁРТВ" : (ag.cuffed ? "⛓️ В НАРУЧНИКАХ" : "💫 ОГЛУШЁН");
        ctx.fillText(badge, sx, drawY - 16 * zoom);
      }

      // Nameplate & Speech Bubble
      if (state.showNames && zoom >= 0.5) {
        ctx.font = `700 ${Math.max(9, Math.floor(10.5 * zoom))}px Inter, sans-serif`;
        ctx.textAlign = "center";
        const labelY = drawY - 4 * zoom;

        const nameW = ctx.measureText(ag.name).width + 8;
        ctx.fillStyle = "rgba(9, 13, 22, 0.82)";
        ctx.fillRect(sx - nameW / 2, labelY - 10 * zoom, nameW, 13 * zoom);

        ctx.fillStyle = ag.color || "#f8fafc";
        ctx.fillText(ag.name, sx, labelY);

        if (ag.lastSpeech) {
          const bubbleText = ag.lastSpeech.length > 56 ? ag.lastSpeech.slice(0, 56) + "…" : ag.lastSpeech;
          ctx.font = `600 ${Math.max(9, Math.floor(10 * zoom))}px Inter, sans-serif`;
          const bw = ctx.measureText(bubbleText).width + 12;
          const by = labelY - 26 * zoom;

          ctx.fillStyle = "rgba(15, 23, 42, 0.94)";
          ctx.strokeStyle = ag.color || "#38bdf8";
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          ctx.roundRect(sx - bw / 2, by, bw, 16 * zoom, 5);
          ctx.fill();
          ctx.stroke();

          ctx.fillStyle = "#f8fafc";
          ctx.fillText(bubbleText, sx, by + 11.5 * zoom);
        }
      }
    }
  }
}

// ============================================================================
// Player HUD, Crew Roster, Inspector & Chat (Diff-Throttled DOM Updates)
// ============================================================================

function updateTopTelemetry() {
  if (!state.live) return;
  document.getElementById("roundClock").textContent = state.live.roundClock || "00:00";
  document.getElementById("cargoTelemetry").textContent = `${state.live.cargoBalance ?? 4500} ₡`;

  const alertBadge = document.getElementById("alertBadge");
  const lvl = (state.live.alertLevel || "green").toLowerCase();
  alertBadge.className = `alert-badge ${lvl}`;
  const lvlRu = { green: "ЗЕЛЁНЫЙ", blue: "СИНИЙ", red: "КРАСНЫЙ" };
  alertBadge.textContent = lvlRu[lvl] || lvl.toUpperCase();

  const llmBadge = document.getElementById("llmStatusBadge");
  const hasKey = Boolean(getActiveApiKey()) || Boolean(state.llm?.hasApiKey);
  const totalCalls = state.llm?.totalLlmCalls || 0;
  if (state.browserLlm.inFlight) {
    llmBadge.className = "engine-badge busy";
    llmBadge.textContent = `📡 Запрос к ${state.browserLlm.model}...`;
  } else if (hasKey) {
    llmBadge.className = "engine-badge online";
    llmBadge.textContent = `🟢 OpenAI (${totalCalls} выз.)`;
  } else {
    llmBadge.className = "engine-badge autonomous";
    llmBadge.textContent = "⚙️ Введите API ключ";
  }

  document.getElementById("apiCallCountTab").textContent = String(totalCalls);
}

function renderPlayerHud(force = false) {
  if (!state.live?.agents) return;
  const ag = state.live.agents.find((a) => a.id === state.selectedAgentId) || state.live.agents[0];
  if (!ag) return;

  const hash = JSON.stringify([
    ag.id,
    ag.name,
    ag.health,
    ag.currentRoom,
    ag.activeHand,
    ag.leftHand?.id,
    ag.rightHand?.id,
    ag.combatMode,
    ag.isGhost,
    (ag.inventory || []).map((i) => i.id),
  ]);
  if (!force && state.domHashes.hud === hash) return;
  state.domHashes.hud = hash;

  document.getElementById("hudCharName").textContent = ag.name;
  document.getElementById("hudCharJob").textContent = ag.jobTitleRu;
  document.getElementById("hudHealthFill").style.width = `${Math.max(0, Math.min(100, ag.health))}%`;
  document.getElementById("hudHealthText").textContent = `${Math.round(ag.health)}%`;
  document.getElementById("hudRoomBadge").textContent = `📍 ${ag.currentRoom}`;

  // Left Hand
  const lhSlot = document.getElementById("hudLeftHand");
  const lhImg = document.getElementById("hudLeftImg");
  const lhName = document.getElementById("hudLeftName");
  lhSlot.classList.toggle("active", ag.activeHand === "left");
  if (ag.leftHand && ag.leftHand.id) {
    lhImg.src = ag.leftHand.url;
    lhImg.classList.remove("hidden");
    lhName.textContent = ag.leftHand.name;
  } else {
    lhImg.classList.add("hidden");
    lhName.textContent = "Пусто";
  }

  // Right Hand
  const rhSlot = document.getElementById("hudRightHand");
  const rhImg = document.getElementById("hudRightImg");
  const rhName = document.getElementById("hudRightName");
  rhSlot.classList.toggle("active", ag.activeHand === "right");
  if (ag.rightHand && ag.rightHand.id) {
    rhImg.src = ag.rightHand.url;
    rhImg.classList.remove("hidden");
    rhName.textContent = ag.rightHand.name;
  } else {
    rhImg.classList.add("hidden");
    rhName.textContent = "Пусто";
  }

  // Inventory Bar
  const invBar = document.getElementById("hudInventoryBar");
  invBar.innerHTML = "";
  const invList = ag.inventory || [];
  for (let i = 0; i < 5; i++) {
    const item = invList[i];
    const slot = document.createElement("div");
    slot.className = "inv-slot";
    if (item && item.id) {
      slot.title = `Кликните, чтобы взять «${item.name}» в активную руку`;
      slot.innerHTML = `<img src="${item.url}" alt="" /><span>${item.name}</span>`;
      slot.onclick = () => sendAgentCommand({ agentId: ag.id, action: "equip_inv", index: i });
    } else {
      slot.innerHTML = `<span>Слот ${i + 1}</span>`;
    }
    invBar.appendChild(slot);
  }

  // Combat Button
  const combatBtn = document.getElementById("hudCombatBtn");
  if (ag.combatMode) {
    combatBtn.className = "hud-combat-btn harm";
    combatBtn.textContent = "⚔️ БОЙ [C]";
  } else {
    combatBtn.className = "hud-combat-btn";
    combatBtn.textContent = "🛡️ МИР [C]";
  }

  // Ghost Banner visibility
  const ghostBanner = document.getElementById("ghostHudBanner");
  ghostBanner.classList.toggle("hidden", !ag.isGhost);
}

function renderCrewRoster(force = false) {
  const container = document.getElementById("crewRosterList");
  if (!container || !state.live?.agents) return;

  const hash = state.live.agents
    .map((a) => `${a.id}:${a.currentRoom}:${a.currentTask}:${a.id === state.selectedAgentId}`)
    .join("|");
  if (!force && state.domHashes.crew === hash) return;
  state.domHashes.crew = hash;

  container.innerHTML = "";
  for (const ag of state.live.agents) {
    const div = document.createElement("div");
    div.className = `crew-card ${ag.id === state.selectedAgentId ? "active" : ""}`;
    div.innerHTML = `
      <div class="crew-top">
        <span class="crew-name" style="color:${ag.color}">${ag.isGhost ? "👻 " : ""}${ag.name}</span>
        <span class="crew-dept">${ag.browserControlled ? "🎮 ИГРОК" : "🤖 ИИ"}</span>
      </div>
      <div class="crew-sub">
        <span>${ag.jobTitleRu}</span>
        <span>📍 ${ag.currentRoom}</span>
      </div>
    `;
    div.onclick = () => {
      state.selectedAgentId = ag.id;
      if (state.gameMode === "play" || state.gameMode === "ghost") {
        state.viewMode = "follow";
      } else {
        state.camX = ag.x;
        state.camY = ag.y;
      }
      renderCrewRoster(true);
      renderInspector(true);
      renderPlayerHud(true);
    };
    container.appendChild(div);
  }
}

function renderInspector(force = false) {
  if (!state.live?.agents) return;
  const ag = state.live.agents.find((a) => a.id === state.selectedAgentId) || state.live.agents[0];
  if (!ag) return;

  const hash = `${ag.id}|${ag.currentRoom}|${Math.round(ag.health)}|${ag.llmCallsCount}|${ag.lastThought}|${ag.currentTask}|${ag.browserControlled}`;
  if (!force && state.domHashes.inspector === hash) return;
  state.domHashes.inspector = hash;

  document.getElementById("inspName").textContent = ag.name;
  document.getElementById("inspName").style.color = ag.color;
  document.getElementById("inspJob").textContent = `${ag.jobTitleRu} (${ag.department})`;
  document.getElementById("inspRoom").textContent = `📍 ${ag.currentRoom}`;
  document.getElementById("inspHealth").textContent = `❤️ ${Math.round(ag.health)}% (${ag.status})`;
  document.getElementById("inspLlmCalls").textContent = `🤖 API: ${ag.llmCallsCount} (${ag.lastLlmLatencyMs}ms)`;
  document.getElementById("inspThought").textContent = ag.lastThought || "Осматриваюсь в отсеке...";
  document.getElementById("inspTask").textContent = ag.currentTask || "На смене";
}

function renderChatFeed(force = false) {
  const feed = document.getElementById("chatFeed");
  if (!feed || !state.live?.chat) return;
  const lastId = state.live.chat.length ? state.live.chat[state.live.chat.length - 1].id : 0;
  if (!force && state.domHashes.chat === lastId) return;
  state.domHashes.chat = lastId;

  const wasAtBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 60;
  feed.innerHTML = "";

  for (const msg of state.live.chat) {
    const div = document.createElement("div");
    div.className = `chat-msg ${msg.channel}`;
    div.innerHTML = `
      <div class="chat-meta">
        <span>[${msg.time}] <strong>${msg.speakerName}</strong> (${msg.speakerJob})</span>
        <span>${msg.channel} • ${msg.room}</span>
      </div>
      <div>${msg.message}</div>
    `;
    feed.appendChild(div);
  }

  if (wasAtBottom || force) {
    feed.scrollTop = feed.scrollHeight;
  }
}

function renderApiLogs(force = false) {
  const feed = document.getElementById("apiLogsFeed");
  if (!feed) return;
  if (!force && state.domHashes.apiLogs === state.apiLogs.length) return;
  state.domHashes.apiLogs = state.apiLogs.length;

  feed.innerHTML = "";
  if (!state.apiLogs.length) {
    feed.innerHTML = `<div class="chat-msg">Нажмите «⚙️ API Модель (OpenAI)», введите ваш API Key и нажмите «Сохранить» — здесь в реальном времени пойдут запросы и JSON-ответы модели для каждого члена экипажа.</div>`;
    return;
  }

  for (const log of [...state.apiLogs].reverse()) {
    const div = document.createElement("div");
    div.className = "chat-msg Science";
    div.innerHTML = `
      <div class="chat-meta">
        <span>[${log.time}] <strong>${log.agent}</strong> (${log.job || ""})</span>
        <span>${log.model} • ${log.latencyMs}ms</span>
      </div>
      <div>💭 <em>${log.thought || "—"}</em></div>
      ${log.say ? `<div>🗣️ «${log.say}»</div>` : ""}
      ${log.move ? `<div>🚶 Маршрут: ${log.move}</div>` : ""}
    `;
    feed.appendChild(div);
  }
}

// ============================================================================
// Camera Lists, Beacons & Ghost Warp Dropdown
// ============================================================================

function populateCameraLists(filterText = "") {
  const listEl = document.getElementById("cameraList");
  if (!listEl || !state.map) return;
  listEl.innerHTML = "";

  const q = filterText.trim().toLowerCase();
  const cams = state.map.cameras.filter(
    (c) => !q || c.id.toLowerCase().includes(q) || c.department.toLowerCase().includes(q)
  );

  for (const cam of cams) {
    const div = document.createElement("div");
    div.className = `camera-item ${state.activeCameraId === cam.id ? "active" : ""}`;
    div.innerHTML = `
      <div class="cam-top">
        <span class="cam-name">📹 ${cam.id}</span>
        <span class="cam-dept">${cam.department}</span>
      </div>
    `;
    div.onclick = () => selectCamera(cam);
    listEl.appendChild(div);
  }

  document.querySelectorAll(".quad-cam-select").forEach((sel) => {
    const slot = Number(sel.dataset.slot);
    if (sel.options.length === 0) {
      for (const cam of state.map.cameras) {
        const opt = document.createElement("option");
        opt.value = cam.id;
        opt.textContent = `${cam.id} (${cam.department})`;
        sel.appendChild(opt);
      }
      sel.value = state.quadCameraIds[slot] || state.map.cameras[slot]?.id;
      sel.onchange = () => {
        state.quadCameraIds[slot] = sel.value;
      };
    }
  });
}

function selectCamera(cam) {
  state.activeCameraId = cam.id;
  state.camX = cam.x;
  state.camY = cam.y;
  if (state.viewMode === "follow") {
    state.viewMode = "single";
  }
  document.getElementById("activeCameraTitle").textContent = `CAM // ${cam.id.toUpperCase()} [${cam.department.toUpperCase()}]`;
  populateCameraLists(document.getElementById("cameraSearchInput").value);
}

function populateBeaconsAndRooms(filterText = "") {
  const listEl = document.getElementById("beaconList");
  const moveSelect = document.getElementById("moveRoomSelect");
  const ghostWarp = document.getElementById("ghostWarpSelect");
  if (!listEl || !state.map) return;

  listEl.innerHTML = "";
  const q = filterText.trim().toLowerCase();

  for (const b of state.map.beacons) {
    if (q && !b.name.toLowerCase().includes(q)) continue;
    const div = document.createElement("div");
    div.className = "camera-item";
    div.innerHTML = `
      <div class="cam-top">
        <span class="cam-name">🧭 ${b.name}</span>
        <span class="cam-dept">(${Math.round(b.x)}, ${Math.round(b.y)})</span>
      </div>
    `;
    div.onclick = () => {
      state.viewMode = "free";
      state.camX = b.x;
      state.camY = b.y;
      document.getElementById("activeCameraTitle").textContent = `СЕКТОР // ${b.name.toUpperCase()}`;
    };
    listEl.appendChild(div);
  }

  if (moveSelect && moveSelect.options.length <= 1) {
    for (const b of state.map.beacons) {
      const opt = document.createElement("option");
      opt.value = b.name;
      opt.textContent = b.name;
      moveSelect.appendChild(opt);
    }
  }

  if (ghostWarp && ghostWarp.options.length <= 1) {
    for (const b of state.map.beacons) {
      const opt = document.createElement("option");
      opt.value = `room:${b.name}`;
      opt.textContent = `📍 Отсек: ${b.name}`;
      ghostWarp.appendChild(opt);
    }
  }
}

// ============================================================================
// Interactive SS14 Machine BUI Windows & Syndicate Uplink
// ============================================================================

function openBuiWindow(bui) {
  const win = document.getElementById("buiWindow");
  const title = document.getElementById("buiTitle");
  const body = document.getElementById("buiBody");
  if (!win || !bui) return;

  win.classList.remove("hidden");
  title.textContent = `🖥️ ${bui.name || "Терминал станции"}`;
  body.innerHTML = "";

  const itemsCatalog = state.sprites?.items || {};
  const makeItemBtn = (itemId, subText, onClick) => {
    const info = itemsCatalog[itemId] || { name: itemId, url: "/assets/textures/Objects/Devices/pda.rsi/pda.png" };
    const btn = document.createElement("button");
    btn.className = "bui-item-btn";
    btn.innerHTML = `
      <img src="${info.url}" alt="" />
      <div>
        <div style="font-weight:700;font-size:11.5px">${info.name}</div>
        <div style="font-size:10px;color:#94a3b8">${subText}</div>
      </div>
    `;
    btn.onclick = onClick;
    return btn;
  };

  if (bui.type === "vending" || bui.type === "chem_master") {
    const list = bui.type === "chem_master"
      ? ["Medkit", "Brutekit", "Burnkit", "Medipen", "Beaker", "Syringe"]
      : ["DrinkMug", "Whiskey", "Shaker", "Banana", "Soap", "Crowbar", "Multitool", "Flash"];
    const grid = document.createElement("div");
    grid.className = "bui-grid";
    for (const id of list) {
      grid.appendChild(
        makeItemBtn(id, "Выдать бесплатно", async () => {
          await sendBuiAction({ agentId: state.selectedAgentId, buiType: bui.type, itemId: id });
        })
      );
    }
    body.appendChild(grid);
  } else if (bui.type === "uplink") {
    const ag = state.live?.agents?.find((a) => a.id === state.selectedAgentId);
    const tc = ag?.telecrystals ?? 20;
    title.textContent = `🗡️ Аплинк Синдиката — Баланс: ${tc} TC`;
    const offers = [
      ["EnergySword", 8, "8 TC • Лазерный меч (35 урона)"],
      ["PistolMK58", 6, "6 TC • Боевой пистолет"],
      ["Shotgun", 8, "8 TC • Боевой дробовик"],
      ["ClownPDA", 4, "4 TC • Взломщик шлюзов (Emag)"],
      ["Stunbaton", 4, "4 TC • Оглушающая дубинка"],
      ["Medipen", 2, "2 TC • Боевой стимулятор (+40 HP)"],
      ["RCD", 6, "6 TC • Строитель/разрушитель стен"],
      ["Handcuffs", 2, "2 TC • Стальные наручники"],
    ];
    const grid = document.createElement("div");
    grid.className = "bui-grid";
    for (const [id, cost, desc] of offers) {
      grid.appendChild(
        makeItemBtn(id, desc, async () => {
          const res = await sendBuiAction({ agentId: state.selectedAgentId, buiType: "uplink", itemId: id, cost });
          if (res.ok) openBuiWindow({ type: "uplink", name: "Аплинк Синдиката" });
        })
      );
    }
    body.appendChild(grid);
  } else if (bui.type === "cargo_console") {
    title.textContent = `📦 Консоль Снабжения Карго (${state.live?.cargoBalance ?? 4500} ₡)`;
    const crates = [
      ["medical", 600, "🏥 Медицинский ящик (600 ₡)"],
      ["engineering", 800, "🔧 Инженерный ящик + РСУ (800 ₡)"],
      ["armory", 1500, "🔫 Оружейный ящик СБ (1500 ₡)"],
      ["party", 400, "🍕 Праздничный набор Бара (400 ₡)"],
    ];
    for (const [crate, cost, label] of crates) {
      const btn = document.createElement("button");
      btn.className = "btn btn-primary";
      btn.textContent = label;
      btn.onclick = () => sendBuiAction({ agentId: state.selectedAgentId, buiType: "cargo_console", crate, cost });
      body.appendChild(btn);
    }
  } else if (bui.type === "comms_console") {
    title.textContent = `📡 Консоль Связи Мостика (Bridge Comms)`;
    body.innerHTML = `
      <div class="event-grid">
        <button class="event-btn green" id="buiGreenBtn">✅ Зелёный код</button>
        <button class="event-btn blue" id="buiBlueBtn">🛡️ Синий код</button>
        <button class="event-btn red" id="buiRedBtn">🚨 Красный код</button>
      </div>
      <div class="control-row" style="margin-top:8px">
        <input id="buiAnnounceInput" class="text-input" placeholder="Текст оповещения Капитана по станции..." />
        <button id="buiAnnounceBtn" class="btn btn-primary">Объявить</button>
      </div>
    `;
    document.getElementById("buiGreenBtn").onclick = () => sendBuiAction({ agentId: state.selectedAgentId, buiType: "comms_console", subAction: "green_alert" });
    document.getElementById("buiBlueBtn").onclick = () => sendBuiAction({ agentId: state.selectedAgentId, buiType: "comms_console", subAction: "blue_alert" });
    document.getElementById("buiRedBtn").onclick = () => sendBuiAction({ agentId: state.selectedAgentId, buiType: "comms_console", subAction: "red_alert" });
    document.getElementById("buiAnnounceBtn").onclick = () => {
      const txt = document.getElementById("buiAnnounceInput").value;
      sendBuiAction({ agentId: state.selectedAgentId, buiType: "comms_console", subAction: "announce", text: txt });
    };
  } else if (bui.type === "med_scanner" || bui.type === "id_console") {
    const btn = document.createElement("button");
    btn.className = "btn btn-success";
    btn.textContent = bui.type === "id_console"
      ? "💳 Прошить полный доступ (AllAccess) на свою ID-карту"
      : "💚 Провести полное медицинское исцеление пациентов рядом";
    btn.onclick = () => sendBuiAction({ agentId: state.selectedAgentId, buiType: bui.type });
    body.appendChild(btn);
  }
}

async function sendBuiAction(payload) {
  const res = await fetch("/api/bui/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (data.state) {
    state.live = data.state;
    updateTopTelemetry();
    renderPlayerHud(true);
    renderInspector(true);
  }
  return data;
}

// ============================================================================
// Right-Click SS14 Verb Context Menu
// ============================================================================

function openContextMenu(clientX, clientY, wx, wy) {
  const menu = document.getElementById("contextMenu");
  const wrapper = document.getElementById("singleViewportContainer").getBoundingClientRect();
  menu.innerHTML = "";
  menu.classList.remove("hidden");
  menu.style.left = `${Math.min(wrapper.width - 220, clientX - wrapper.left)}px`;
  menu.style.top = `${Math.min(wrapper.height - 200, clientY - wrapper.top)}px`;

  const title = document.createElement("div");
  title.className = "ctx-title";
  title.textContent = `Взаимодействие (${wx.toFixed(1)}, ${wy.toFixed(1)})`;
  menu.appendChild(title);

  const addVerb = (label, fn) => {
    const b = document.createElement("button");
    b.className = "ctx-item";
    b.textContent = label;
    b.onclick = () => {
      menu.classList.add("hidden");
      fn();
    };
    menu.appendChild(b);
  };

  // 1. Check nearby agents
  const clickedAgent = (state.live?.agents || []).find(
    (a) => Math.hypot(a.x - wx, a.y - wy) < 0.85
  );
  if (clickedAgent) {
    addVerb(`🔍 Выбрать: ${clickedAgent.name}`, () => {
      state.selectedAgentId = clickedAgent.id;
      renderCrewRoster(true);
      renderInspector(true);
      renderPlayerHud(true);
    });
    if (clickedAgent.id !== state.selectedAgentId) {
      addVerb(`⚔️ Атаковать / Применить предмет на ${clickedAgent.name}`, async () => {
        const res = await sendAgentCommand({
          agentId: state.selectedAgentId,
          action: "interact_agent",
          targetAgentId: clickedAgent.id,
        });
        if (res.action === "possessed" && res.new_agent_id) {
          state.selectedAgentId = res.new_agent_id;
          setGameMode("play");
        }
        runBrowserDirectLlmStep(clickedAgent.id);
      });
    }
    addVerb(`🎮 Вселиться и играть за ${clickedAgent.name}`, () => {
      state.selectedAgentId = clickedAgent.id;
      setGameMode("play");
      sendAgentCommand({ agentId: clickedAgent.id, action: "toggle_browser_control", enabled: true });
    });
    addVerb(`🧠 Запросить мысль OpenAI для ${clickedAgent.name}`, () => {
      runBrowserDirectLlmStep(clickedAgent.id);
    });
  }

  // 2. Check floor items
  const clickedFloorItem = (state.live?.floorItems || []).find(
    (fi) => Math.hypot(fi.x - wx, fi.y - wy) < 0.85
  );
  if (clickedFloorItem) {
    addVerb(`✋ Поднять с пола: ${clickedFloorItem.name}`, () => {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "pickup_item", uid: clickedFloorItem.uid });
    });
  }

  // 3. Check door
  const tx = Math.floor(wx);
  const ty = Math.floor(wy);
  const door = state.spatial.doorsByTile.get(`${tx},${ty}`);
  if (door) {
    addVerb(`🚪 Открыть / Закрыть / Взломать: ${door.name}`, () => {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "toggle_door", doorUid: door.uid });
    });
  }

  // 4. Check station object/machine
  const objs = state.spatial.objects.get(`${tx},${ty}`) || [];
  for (const obj of objs) {
    addVerb(`⚙️ Использовать: ${obj.name}`, async () => {
      const res = await sendAgentCommand({ agentId: state.selectedAgentId, action: "interact", uid: obj.uid });
      if (res.bui) openBuiWindow(res.bui);
    });
  }

  // 5. Walk here
  addVerb(`🚶 Идти сюда (${Math.floor(wx)}, ${Math.floor(wy)})`, () => {
    sendAgentCommand({ agentId: state.selectedAgentId, action: "move_to", x: wx, y: wy });
  });
}

// ============================================================================
// Mode Switching (Playable Crew Mode / Ghost Mode / CCTV Mode)
// ============================================================================

async function setGameMode(mode) {
  state.gameMode = mode;
  document.getElementById("modePlayBtn").classList.toggle("active", mode === "play");
  document.getElementById("modeGhostBtn").classList.toggle("active", mode === "ghost");
  document.getElementById("modeCctvBtn").classList.toggle("active", mode === "cctv");

  if (mode === "ghost") {
    const curAg = state.live?.agents?.find((a) => a.id === state.selectedAgentId);
    if (curAg && !curAg.isGhost) {
      state.previousPlayAgentId = curAg.id;
    }
    const res = await fetch("/api/player/ghost", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        x: curAg ? curAg.x : state.camX,
        y: curAg ? curAg.y : state.camY,
      }),
    });
    const data = await res.json();
    if (data.ok) {
      state.live = data.state;
      state.selectedAgentId = data.agentId;
      state.viewMode = "follow";
      document.getElementById("singleViewportContainer").classList.remove("hidden");
      document.getElementById("quadViewportContainer").classList.add("hidden");
      document.getElementById("activeCameraTitle").textContent = "👻 РЕЖИМ ГОСТА (MobObserver) — СВОБОДНЫЙ ПОЛЁТ";
      renderCrewRoster(true);
      renderInspector(true);
      renderPlayerHud(true);
    }
  } else if (mode === "play") {
    const curAg = state.live?.agents?.find((a) => a.id === state.selectedAgentId);
    if (!curAg || curAg.isGhost) {
      state.selectedAgentId = state.previousPlayAgentId || "captain-vance";
    }
    state.viewMode = "follow";
    document.getElementById("singleViewportContainer").classList.remove("hidden");
    document.getElementById("quadViewportContainer").classList.add("hidden");
    document.getElementById("activeCameraTitle").textContent = "🎮 ИГРОВОЙ РЕЖИМ — УПРАВЛЕНИЕ ПЕРСОНАЖЕМ";
    renderCrewRoster(true);
    renderInspector(true);
    renderPlayerHud(true);
  } else if (mode === "cctv") {
    state.viewMode = "quad";
    document.getElementById("singleViewportContainer").classList.add("hidden");
    document.getElementById("quadViewportContainer").classList.remove("hidden");
  }
}

// ============================================================================
// Keyboard & Mouse Gameplay Controls
// ============================================================================

function handleContinuousWasd(now) {
  if (now - state.lastWasdTime < 95) return;
  let dx = 0;
  let dy = 0;
  if (state.keysDown.has("KeyW") || state.keysDown.has("ArrowUp")) dy += 1;
  if (state.keysDown.has("KeyS") || state.keysDown.has("ArrowDown")) dy -= 1;
  if (state.keysDown.has("KeyD") || state.keysDown.has("ArrowRight")) dx += 1;
  if (state.keysDown.has("KeyA") || state.keysDown.has("ArrowLeft")) dx -= 1;

  if (dx === 0 && dy === 0) return;
  state.lastWasdTime = now;

  if (state.selectedAgentId) {
    // Immediate client-side prediction for snappy 60 FPS feel
    const rpos = state.renderPos.get(state.selectedAgentId);
    if (rpos) {
      rpos.x += dx * 0.45;
      rpos.y += dy * 0.45;
    }
    sendAgentCommand({
      agentId: state.selectedAgentId,
      action: "step_dir",
      dx,
      dy,
    });
  }
}

function bindUIEvents() {
  // Top Mode Switcher
  document.getElementById("modePlayBtn").onclick = () => setGameMode("play");
  document.getElementById("modeGhostBtn").onclick = () => setGameMode("ghost");
  document.getElementById("modeCctvBtn").onclick = () => setGameMode("cctv");

  // Ghost Banner Actions
  document.getElementById("ghostBooBtn").onclick = () => {
    sendAgentCommand({ agentId: state.selectedAgentId, action: "ghost_boo" });
  };
  document.getElementById("ghostReturnBodyBtn").onclick = () => {
    setGameMode("play");
  };
  document.getElementById("ghostWarpSelect").onchange = (e) => {
    const val = e.target.value;
    if (!val) return;
    if (val.startsWith("room:")) {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "ghost_warp", room: val.slice(5) });
    }
    e.target.value = "";
  };

  // Bottom SS14 Player HUD Controls
  document.getElementById("hudLeftHand").onclick = () => {
    const ag = state.live?.agents?.find((a) => a.id === state.selectedAgentId);
    if (ag && ag.activeHand !== "left") {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "swap_hands" });
    } else {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "use_hand" });
    }
  };
  document.getElementById("hudRightHand").onclick = () => {
    const ag = state.live?.agents?.find((a) => a.id === state.selectedAgentId);
    if (ag && ag.activeHand !== "right") {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "swap_hands" });
    } else {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "use_hand" });
    }
  };
  document.getElementById("hudSwapHandsBtn").onclick = () => {
    sendAgentCommand({ agentId: state.selectedAgentId, action: "swap_hands" });
  };
  document.getElementById("hudUseHandBtn").onclick = () => {
    sendAgentCommand({ agentId: state.selectedAgentId, action: "use_hand" });
  };
  document.getElementById("hudDropHandBtn").onclick = () => {
    sendAgentCommand({ agentId: state.selectedAgentId, action: "drop_item" });
  };
  document.getElementById("hudCombatBtn").onclick = () => {
    sendAgentCommand({ agentId: state.selectedAgentId, action: "toggle_combat" });
  };
  document.getElementById("hudUplinkBtn").onclick = () => {
    openBuiWindow({ type: "uplink", name: "Аплинк Синдиката" });
  };
  document.getElementById("buiCloseBtn").onclick = () => {
    document.getElementById("buiWindow").classList.add("hidden");
  };

  // Sidebar Tabs
  document.querySelectorAll(".panel-tabs .tab-btn").forEach((btn) => {
    btn.onclick = () => {
      const parent = btn.closest(".sidebar, .chat-panel");
      parent.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      parent.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(btn.dataset.tab).classList.add("active");
    };
  });

  // Search filters
  document.getElementById("cameraSearchInput").oninput = (e) => populateCameraLists(e.target.value);
  document.getElementById("beaconSearchInput").oninput = (e) => populateBeaconsAndRooms(e.target.value);

  // Camera View Mode Chips
  document.getElementById("singleCamModeBtn").onclick = () => setViewMode("single");
  document.getElementById("quadCamModeBtn").onclick = () => setViewMode("quad");
  document.getElementById("freePanModeBtn").onclick = () => setViewMode("free");

  // Zoom & HUD Toggles
  document.getElementById("zoomInBtn").onclick = () => setZoom(state.zoom * 1.25);
  document.getElementById("zoomOutBtn").onclick = () => setZoom(state.zoom / 1.25);
  document.getElementById("toggleNamesBtn").onclick = (e) => {
    state.showNames = !state.showNames;
    e.currentTarget.classList.toggle("active", state.showNames);
  };
  document.getElementById("togglePathsBtn").onclick = (e) => {
    state.showPaths = !state.showPaths;
    e.currentTarget.classList.toggle("active", state.showPaths);
  };
  document.getElementById("toggleCrtBtn").onclick = (e) => {
    state.crtEnabled = !state.crtEnabled;
    e.currentTarget.classList.toggle("active", state.crtEnabled);
    document.getElementById("crtOverlay").classList.toggle("hidden", !state.crtEnabled);
  };

  // Canvas Mouse Interactions (Left-Click Playable Actions + Right-Click SS14 Verb Menu)
  const canvas = document.getElementById("stationCanvas");
  canvas.addEventListener("mousedown", (e) => {
    document.getElementById("contextMenu").classList.add("hidden");
    if (e.button === 0) {
      state.isDragging = true;
      state.dragMoved = false;
      state.dragStartX = e.clientX;
      state.dragStartY = e.clientY;
      state.camStartX = state.camX;
      state.camStartY = state.camY;
    }
  });

  window.addEventListener("mousemove", (e) => {
    if (!state.isDragging) return;
    const dx = e.clientX - state.dragStartX;
    const dy = e.clientY - state.dragStartY;
    if (Math.hypot(dx, dy) > 6) {
      state.dragMoved = true;
      state.viewMode = "free";
      const scale = TILE_PX * state.zoom;
      state.camX = state.camStartX - dx / scale;
      state.camY = state.camStartY + dy / scale;
    }
  });

  window.addEventListener("mouseup", async (e) => {
    if (state.isDragging && !state.dragMoved && e.target === canvas) {
      const rect = canvas.getBoundingClientRect();
      const [wx, wy] = screenToWorld(
        e.clientX - rect.left,
        e.clientY - rect.top,
        rect.width,
        rect.height,
        state.camX,
        state.camY,
        state.zoom
      );
      await handleCanvasClick(wx, wy);
    }
    state.isDragging = false;
  });

  canvas.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const [wx, wy] = screenToWorld(
      e.clientX - rect.left,
      e.clientY - rect.top,
      rect.width,
      rect.height,
      state.camX,
      state.camY,
      state.zoom
    );
    openContextMenu(e.clientX, e.clientY, wx, wy);
  });

  canvas.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      setZoom(state.zoom * factor);
    },
    { passive: false }
  );

  // Keyboard shortcuts (WASD + SS14 Hotkeys X, Z, Q, C)
  window.addEventListener("keydown", (e) => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
    state.keysDown.add(e.code);

    if (["KeyW", "KeyA", "KeyS", "KeyD", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.code)) {
      state.viewMode = "follow";
    } else if (e.code === "KeyX") {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "swap_hands" });
    } else if (e.code === "KeyZ") {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "use_hand" });
    } else if (e.code === "KeyQ") {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "drop_item" });
    } else if (e.code === "KeyC") {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "toggle_combat" });
    }
  });

  window.addEventListener("keyup", (e) => {
    state.keysDown.delete(e.code);
  });

  // Inspector & Direct Commands
  document.getElementById("playAsSelectedBtn").onclick = () => {
    setGameMode("play");
    sendAgentCommand({ agentId: state.selectedAgentId, action: "toggle_browser_control", enabled: true });
  };

  document.getElementById("forceLlmStepBtn").onclick = async () => {
    const btn = document.getElementById("forceLlmStepBtn");
    btn.textContent = "⏳ Запрос...";
    await runBrowserDirectLlmStep(state.selectedAgentId);
    btn.textContent = "🧠 Запрос к ИИ";
  };

  document.getElementById("runNextAgentNowBtn").onclick = () => {
    runBrowserDirectLlmStep(null);
  };

  document.getElementById("sendSayBtn").onclick = sendSay;
  document.getElementById("directSayInput").onkeydown = (e) => {
    if (e.key === "Enter") sendSay();
  };

  document.getElementById("sendThoughtBtn").onclick = sendThought;
  document.getElementById("subconsciousInput").onkeydown = (e) => {
    if (e.key === "Enter") sendThought();
  };

  document.getElementById("sendMoveRoomBtn").onclick = () => {
    const room = document.getElementById("moveRoomSelect").value;
    if (room && state.selectedAgentId) {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "move_to_room", room });
    }
  };

  // Modals
  document.getElementById("openApiModalBtn").onclick = () => openModal("apiModal");
  document.getElementById("llmStatusBadge").onclick = () => openModal("apiModal");
  document.getElementById("openJoinModalBtn").onclick = () => openModal("joinModal");
  document.getElementById("openEventModalBtn").onclick = () => openModal("eventModal");

  document.querySelectorAll(".modal-close").forEach((btn) => {
    btn.onclick = () => document.getElementById(btn.dataset.close).classList.add("hidden");
  });

  document.querySelectorAll(".preset-chip").forEach((chip) => {
    chip.onclick = () => {
      document.getElementById("apiBaseUrlInput").value = chip.dataset.url;
      document.getElementById("apiModelInput").value = chip.dataset.model;
    };
  });

  document.getElementById("saveApiBtn").onclick = saveApiConfig;
  document.getElementById("testApiBtn").onclick = testApiConfig;
  document.getElementById("confirmJoinBtn").onclick = joinAsCustomPlayer;
  document.getElementById("joinAsGhostModalBtn").onclick = () => {
    document.getElementById("joinModal").classList.add("hidden");
    setGameMode("ghost");
  };

  document.querySelectorAll(".event-btn").forEach((btn) => {
    btn.onclick = async () => {
      await fetch("/api/station/event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ eventType: btn.dataset.event }),
      });
      document.getElementById("eventModal").classList.add("hidden");
    };
  });

  document.getElementById("sendCentcommBtn").onclick = async () => {
    const txt = document.getElementById("customCentcommInput").value.trim();
    if (!txt) return;
    await fetch("/api/station/event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ eventType: "custom", customText: txt }),
    });
    document.getElementById("customCentcommInput").value = "";
    document.getElementById("eventModal").classList.add("hidden");
  };
}

async function handleCanvasClick(wx, wy) {
  const curAg = state.live?.agents?.find((a) => a.id === state.selectedAgentId);

  // 1. Check if clicked another character
  const clickedAgent = (state.live?.agents || []).find(
    (a) => Math.hypot(a.x - wx, a.y - wy) < 0.78
  );
  if (clickedAgent) {
    // If we are in Combat Mode or Ghost Mode or holding Medical/Cuffs, interact with target character!
    if (curAg && clickedAgent.id !== curAg.id && (curAg.combatMode || curAg.isGhost)) {
      const res = await sendAgentCommand({
        agentId: curAg.id,
        action: "interact_agent",
        targetAgentId: clickedAgent.id,
      });
      if (res.action === "possessed" && res.new_agent_id) {
        state.selectedAgentId = res.new_agent_id;
        setGameMode("play");
      } else {
        runBrowserDirectLlmStep(clickedAgent.id);
      }
      return;
    }
    state.selectedAgentId = clickedAgent.id;
    renderCrewRoster(true);
    renderInspector(true);
    renderPlayerHud(true);
    return;
  }

  // 2. Check if clicked a floor item -> pick it up!
  const clickedFloorItem = (state.live?.floorItems || []).find(
    (fi) => Math.hypot(fi.x - wx, fi.y - wy) < 0.7
  );
  if (clickedFloorItem && curAg && !curAg.isGhost) {
    await sendAgentCommand({
      agentId: curAg.id,
      action: "pickup_item",
      uid: clickedFloorItem.uid,
    });
    return;
  }

  // 3. Check if clicked a door -> toggle or hack/pry door
  const tx = Math.floor(wx);
  const ty = Math.floor(wy);
  const door = state.spatial.doorsByTile.get(`${tx},${ty}`);
  if (door) {
    await sendAgentCommand({
      agentId: state.selectedAgentId,
      action: "toggle_door",
      doorUid: door.uid,
    });
    return;
  }

  // 4. Check if clicked an interactive station object (Vending, Console, Locker, Bed)
  const objs = state.spatial.objects.get(`${tx},${ty}`);
  if (objs && objs.length > 0) {
    const res = await sendAgentCommand({
      agentId: state.selectedAgentId,
      action: "interact",
      uid: objs[0].uid,
    });
    if (res.bui) {
      openBuiWindow(res.bui);
    }
    return;
  }

  // 5. Otherwise walk/fly to clicked tile!
  if (state.selectedAgentId) {
    await sendAgentCommand({
      agentId: state.selectedAgentId,
      action: "move_to",
      x: wx,
      y: wy,
    });
  }
}

function setViewMode(mode) {
  state.viewMode = mode;
  document.getElementById("singleCamModeBtn").classList.toggle("active", mode === "single");
  document.getElementById("quadCamModeBtn").classList.toggle("active", mode === "quad");
  document.getElementById("freePanModeBtn").classList.toggle("active", mode === "free");

  document.getElementById("singleViewportContainer").classList.toggle("hidden", mode === "quad");
  document.getElementById("quadViewportContainer").classList.toggle("hidden", mode !== "quad");
}

function setZoom(newZoom) {
  state.zoom = Math.max(0.4, Math.min(3.5, newZoom));
  document.getElementById("zoomLabel").textContent = `${Math.round(state.zoom * 100)}%`;
}

async function sendAgentCommand(payload) {
  const res = await fetch("/api/agent/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (data.state) {
    state.live = data.state;
    renderPlayerHud(false);
    renderInspector(false);
    renderChatFeed(false);
  }
  return data;
}

async function sendSay() {
  const input = document.getElementById("directSayInput");
  const text = input.value.trim();
  if (!text || !state.selectedAgentId) return;
  input.value = "";
  const res = await sendAgentCommand({ agentId: state.selectedAgentId, action: "say", text });
  // Immediately trigger OpenAI API reply from the closest AI crew member!
  if (res.queuedAiReplies && res.queuedAiReplies.length > 0) {
    runBrowserDirectLlmStep(res.queuedAiReplies[0]);
  } else {
    runBrowserDirectLlmStep(null);
  }
}

async function sendThought() {
  const input = document.getElementById("subconsciousInput");
  const text = input.value.trim();
  if (!text || !state.selectedAgentId) return;
  input.value = "";
  await sendAgentCommand({ agentId: state.selectedAgentId, action: "thought", text });
  runBrowserDirectLlmStep(state.selectedAgentId);
}

function openModal(id) {
  if (id === "apiModal") {
    document.getElementById("apiBaseUrlInput").value = state.browserLlm.baseUrl || state.llm?.baseUrl || "https://api.openai.com/v1";
    document.getElementById("apiModelInput").value = state.browserLlm.model || state.llm?.model || "gpt-4o-mini";
    document.getElementById("apiIntervalInput").value = state.browserLlm.intervalSec || state.llm?.tickIntervalSec || 2.5;
    if (state.browserLlm.apiKey) {
      document.getElementById("apiKeyInput").value = state.browserLlm.apiKey;
    }
  }
  document.getElementById(id).classList.remove("hidden");
}

function gatherApiForm() {
  const keyVal = document.getElementById("apiKeyInput").value.trim();
  const baseUrl = document.getElementById("apiBaseUrlInput").value.trim().replace(/\/+$/, "");
  const model = document.getElementById("apiModelInput").value.trim();
  const tickIntervalSec = Number(document.getElementById("apiIntervalInput").value || 2.5);

  if (keyVal) state.browserLlm.apiKey = keyVal;
  state.browserLlm.baseUrl = baseUrl;
  state.browserLlm.model = model;
  state.browserLlm.intervalSec = tickIntervalSec;

  localStorage.setItem("ss14_openai_key", state.browserLlm.apiKey);
  localStorage.setItem("ss14_openai_url", state.browserLlm.baseUrl);
  localStorage.setItem("ss14_openai_model", state.browserLlm.model);
  localStorage.setItem("ss14_openai_interval", String(state.browserLlm.intervalSec));

  return {
    apiKey: state.browserLlm.apiKey,
    baseUrl,
    model,
    tickIntervalSec,
  };
}

async function saveApiConfig() {
  const payload = gatherApiForm();
  const res = await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (data.llm) {
    state.llm = data.llm;
    updateTopTelemetry();
  }
  document.getElementById("apiModal").classList.add("hidden");
  // Immediately fire first OpenAI API call!
  runBrowserDirectLlmStep(null);
}

async function testApiConfig() {
  const resBox = document.getElementById("apiTestResult");
  resBox.classList.remove("hidden", "ok", "err");
  resBox.textContent = "⏳ Отправка реального запроса к модели OpenAI API напрямую из браузера...";

  const payload = gatherApiForm();
  await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).catch(() => {});

  if (!payload.apiKey) {
    resBox.classList.add("err");
    resBox.textContent = "❌ Введите API ключ (Bearer Token)";
    return;
  }

  // Execute live test directly from the user's browser AND apply a real agent decision!
  const stepResult = await runBrowserDirectLlmStep(state.selectedAgentId);
  if (stepResult && stepResult.ok) {
    resBox.classList.add("ok");
    const d = stepResult.decision || {};
    resBox.innerHTML = `✅ <strong>Модель ответила успешно!</strong><br/>💭 Мысль персонажа: «${d.thought || "—"}»<br/>🗣️ Реплика: «${d.say || "—"}»`;
  } else {
    resBox.classList.add("err");
    resBox.textContent = `❌ Ошибка вызова API: ${stepResult?.error || "Проверьте ключ, URL и CORS провайдера"}`;
  }
}

async function joinAsCustomPlayer() {
  const payload = {
    mode: "spawn",
    name: document.getElementById("joinNameInput").value.trim(),
    job: document.getElementById("joinJobSelect").value,
    room: document.getElementById("joinRoomSelect").value || null,
    isAntagonist: document.getElementById("joinAntagCheck").checked,
  };
  const res = await fetch("/api/player/join", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (data.ok) {
    state.live = data.state;
    state.selectedAgentId = data.agentId;
    state.previousPlayAgentId = data.agentId;
    setGameMode("play");
    document.getElementById("joinModal").classList.add("hidden");
  }
}

window.addEventListener("DOMContentLoaded", initApp);
