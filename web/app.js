/**
 * Space Station 14 — Fullscreen Browser Game Client (NSS Saltern)
 * Authentic Content.Client StyleNano UI + 60 FPS Viewport-Culled Engine + Direct Browser OpenAI API
 */

const TILE_PX = 32;

// Generate 180 parallax stars for deep space background
const STARFIELD = Array.from({ length: 180 }, () => ({
  x: Math.random() * 2400,
  y: Math.random() * 1600,
  size: Math.random() < 0.25 ? 2 : 1.2,
  alpha: 0.3 + Math.random() * 0.7,
  depth: 0.08 + Math.random() * 0.18,
  color: Math.random() < 0.2 ? "#bae6fd" : (Math.random() < 0.15 ? "#fde68a" : "#f8fafc"),
}));

const state = {
  map: null,
  sprites: null,
  jobs: null,
  live: null,
  llm: null,
  apiLogs: [],
  floorItemsCache: [],

  // Spatial lookup maps built once at bootstrap for 60 FPS viewport culling
  spatial: {
    tiles: new Map(),       // "tx,ty" -> [tname, variant]
    walls: new Map(),       // "tx,ty" -> wallObj
    windows: new Map(),     // "tx,ty" -> winObj
    objects: new Map(),     // "tx,ty" -> [obj, ...]
    lights: new Map(),      // "tx,ty" -> lightObj
    doorsByTile: new Map(), // "tx,ty" -> doorObj
    floorByTile: new Map(), // "tx,ty" -> [floorItem, ...]
  },

  // Smooth 60 FPS interpolated positions per agent id
  renderPos: new Map(), // agentId -> { x, y, moving }

  // Gameplay mode: "play" | "ghost" | "cctv"
  gameMode: "play",
  previousPlayAgentId: "captain-vance",

  // Camera state
  viewMode: "follow", // "follow" | "single" | "free"
  activeCameraId: null,
  quadCameraIds: ["Bridge", "Bar", "Medbay", "Security"],
  camX: 3.5,
  camY: 28.5,
  zoom: 1.5,
  soundEnabled: true,
  lightingEnabled: true,
  minimapEnabled: true,
  showNames: true,
  showPaths: false,

  selectedAgentId: "captain-vance",

  // Input & WebSocket state
  ws: null,
  isDragging: false,
  dragMoved: false,
  dragStartX: 0,
  dragStartY: 0,
  camStartX: 0,
  camStartY: 0,
  keysDown: new Set(),
  lastWasdTime: 0,
  lastFrameMoveTime: 0,
  lastUserMoveInputTime: 0,

  imageCache: new Map(),
  seenEffectIds: new Set(),
  minimapBaseCanvas: null,
  audioCtx: null,

  // Browser-Direct OpenAI API settings
  browserLlm: {
    apiKey: localStorage.getItem("ss14_openai_key") || "",
    baseUrl: localStorage.getItem("ss14_openai_url") || "https://api.openai.com/v1",
    model: localStorage.getItem("ss14_openai_model") || "gpt-4o-mini",
    intervalSec: parseFloat(localStorage.getItem("ss14_openai_interval") || "2.5"),
    inFlight: false,
    lastCallTime: 0,
  },

  domHashes: {
    crew: "",
    chat: 0,
    apiLogs: 0,
    hud: "",
    inspector: "",
    equip: "",
  },

  fpsFrames: 0,
  fpsLastTime: performance.now(),
  currentFps: 60,
};

// ============================================================================
// Image Loader & Sprite Atlas Resolver
// ============================================================================

function getSpriteImage(urlOrObj) {
  if (!urlOrObj) return null;
  const url = typeof urlOrObj === "string" ? urlOrObj : urlOrObj.url;
  if (!url || typeof url !== "string") return null;
  if (state.imageCache.has(url)) {
    return state.imageCache.get(url);
  }
  const img = new Image();
  img.src = url;
  state.imageCache.set(url, img);
  return img;
}

function drawRsiDirectionalTile(ctx, img, dirIdx, dx, dy, dw, dh) {
  const nw = img.naturalWidth;
  const nh = img.naturalHeight;
  const cols = Math.max(1, Math.floor(nw / 32));
  const rows = Math.max(1, Math.floor(nh / 32));
  const totalFrames = cols * rows;
  const idx = dirIdx < totalFrames ? dirIdx : 0;
  const sx = (idx % cols) * 32;
  const sy = Math.floor(idx / cols) * 32;
  ctx.drawImage(img, sx, sy, 32, 32, dx, dy, dw, dh);
}

function rotToDirIdx(rot) {
  // In SS14 world coordinates: 0 = South, pi = North, pi/2 = East, 3*pi/2 = West
  const twoPi = Math.PI * 2;
  const norm = ((rot % twoPi) + twoPi) % twoPi;
  if (Math.abs(norm - Math.PI) < 0.65) return 1; // North
  if (Math.abs(norm - Math.PI / 2) < 0.65) return 2; // East
  if (Math.abs(norm - (3 * Math.PI) / 2) < 0.65) return 3; // West
  return 0; // South
}

function drawFirstFrame(ctx, img, dx, dy, dw, dh, rot = 0) {
  if (!img || !img.complete || img.naturalWidth === 0) return false;
  const nw = img.naturalWidth;
  const nh = img.naturalHeight;
  const isFourDirSheet = (nw === 64 && nh === 64) || (nw >= 128 && nh >= 32);

  if (Math.abs(rot) > 0.05) {
    if (isFourDirSheet) {
      const dirIdx = rotToDirIdx(rot);
      drawRsiDirectionalTile(ctx, img, dirIdx, dx, dy, dw, dh);
      return true;
    }
    ctx.save();
    ctx.translate(dx + dw / 2, dy + dh / 2);
    ctx.rotate(-rot);
    const frameW = nw >= 32 ? 32 : nw;
    const frameH = nh >= 32 ? 32 : nh;
    ctx.drawImage(img, 0, 0, frameW, frameH, -dw / 2, -dh / 2, dw, dh);
    ctx.restore();
    return true;
  }

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
  if ((nw >= 64 && nh >= 64) || (nw >= 128 && nh >= 32)) {
    const dirMap = { south: 0, north: 1, east: 2, west: 3 };
    const dirIdx = dirMap[direction] ?? 0;
    drawRsiDirectionalTile(ctx, img, dirIdx, dx, dy, dw, dh);
  } else {
    drawFirstFrame(ctx, img, dx, dy, dw, dh, 0);
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
// Spatial Map & Floor Item Indexing (O(visible_tiles))
// ============================================================================

function buildSpatialIndex() {
  if (!state.map) return;
  state.spatial.tiles.clear();
  state.spatial.walls.clear();
  state.spatial.windows.clear();
  state.spatial.objects.clear();
  state.spatial.lights.clear();
  state.spatial.doorsByTile.clear();

  for (const [tx, ty, tname, variant] of state.map.tiles) {
    state.spatial.tiles.set(`${tx},${ty}`, [tname, variant]);
  }
  for (const w of state.map.walls) {
    if ((w.proto || "").includes("Wallmount")) continue;
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
    if ((obj.proto || "").toLowerCase().includes("light")) {
      state.spatial.lights.set(key, obj);
    }
  }
  buildMinimapBase();
}

function rebuildFloorItemsSpatial(floorItems) {
  state.floorItemsCache = floorItems || [];
  state.spatial.floorByTile.clear();
  for (const fi of state.floorItemsCache) {
    const tx = Math.floor(fi.x);
    const ty = Math.floor(fi.y);
    const key = `${tx},${ty}`;
    if (!state.spatial.floorByTile.has(key)) {
      state.spatial.floorByTile.set(key, []);
    }
    state.spatial.floorByTile.get(key).push(fi);
  }
}

// ============================================================================
// Procedural SS14 Sound Effects (Web Audio API) & Minimap Radar
// ============================================================================

function playSs14Sound(type) {
  if (!state.soundEnabled) return;
  try {
    if (!state.audioCtx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      state.audioCtx = new AudioCtx();
    }
    const ctx = state.audioCtx;
    if (ctx.state === "suspended") ctx.resume();

    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);

    if (type === "honk") {
      osc.type = "triangle";
      osc.frequency.setValueAtTime(510, now);
      osc.frequency.setValueAtTime(680, now + 0.11);
      gain.gain.setValueAtTime(0.14, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.28);
      osc.start(now);
      osc.stop(now + 0.29);
    } else if (type === "beam") {
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(920, now);
      osc.frequency.exponentialRampToValueAtTime(160, now + 0.18);
      gain.gain.setValueAtTime(0.11, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.19);
      osc.start(now);
      osc.stop(now + 0.2);
    } else if (type === "slash" || type === "explosion") {
      osc.type = "square";
      osc.frequency.setValueAtTime(160, now);
      osc.frequency.exponentialRampToValueAtTime(48, now + 0.14);
      gain.gain.setValueAtTime(0.12, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
      osc.start(now);
      osc.stop(now + 0.16);
    } else if (type === "heal") {
      osc.type = "sine";
      osc.frequency.setValueAtTime(523.25, now);
      osc.frequency.setValueAtTime(659.25, now + 0.08);
      osc.frequency.setValueAtTime(783.99, now + 0.16);
      gain.gain.setValueAtTime(0.09, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.28);
      osc.start(now);
      osc.stop(now + 0.29);
    } else if (type === "boo") {
      osc.type = "sine";
      osc.frequency.setValueAtTime(340, now);
      osc.frequency.linearRampToValueAtTime(210, now + 0.35);
      gain.gain.setValueAtTime(0.11, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.36);
      osc.start(now);
      osc.stop(now + 0.37);
    } else if (type === "radio") {
      osc.type = "sine";
      osc.frequency.setValueAtTime(1350, now);
      gain.gain.setValueAtTime(0.025, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.045);
      osc.start(now);
      osc.stop(now + 0.05);
    }
  } catch (_e) {}
}

function buildMinimapBase() {
  if (!state.map) return;
  const off = document.createElement("canvas");
  off.width = 168;
  off.height = 110;
  const ctx = off.getContext("2d");
  ctx.fillStyle = "#04070f";
  ctx.fillRect(0, 0, off.width, off.height);

  const b = state.map.bounds || { minX: -55, maxX: 82, minY: -48, maxY: 38 };
  const spanX = Math.max(1, b.maxX - b.minX + 6);
  const spanY = Math.max(1, b.maxY - b.minY + 6);

  ctx.fillStyle = "#1e293b";
  for (const [tx, ty] of state.map.tiles) {
    const mx = ((tx - b.minX + 3) / spanX) * off.width;
    const my = ((b.maxY - ty + 3) / spanY) * off.height;
    ctx.fillRect(mx, my, 1.5, 1.5);
  }

  ctx.fillStyle = "#475569";
  for (const w of state.map.walls) {
    const mx = ((w.x - b.minX + 3) / spanX) * off.width;
    const my = ((b.maxY - w.y + 3) / spanY) * off.height;
    ctx.fillRect(mx, my, 1.5, 1.5);
  }

  state.minimapBaseCanvas = off;
}

function renderMinimap() {
  if (!state.minimapEnabled || !state.map || !state.minimapBaseCanvas) return;
  const canvas = document.getElementById("minimapCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(state.minimapBaseCanvas, 0, 0);

  const b = state.map.bounds || { minX: -55, maxX: 82, minY: -48, maxY: 38 };
  const spanX = Math.max(1, b.maxX - b.minX + 6);
  const spanY = Math.max(1, b.maxY - b.minY + 6);

  if (state.live?.agents) {
    for (const ag of state.live.agents) {
      const rpos = state.renderPos.get(ag.id) || ag;
      const mx = ((rpos.x - b.minX + 3) / spanX) * canvas.width;
      const my = ((b.maxY - rpos.y + 3) / spanY) * canvas.height;
      ctx.fillStyle = ag.id === state.selectedAgentId ? "#ffffff" : (ag.color || "#38bdf8");
      ctx.beginPath();
      ctx.arc(mx, my, ag.id === state.selectedAgentId ? 3.0 : 2.0, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  const cx = ((state.camX - b.minX + 3) / spanX) * canvas.width;
  const cy = ((b.maxY - state.camY + 3) / spanY) * canvas.height;
  ctx.strokeStyle = "#38bdf8";
  ctx.lineWidth = 1;
  ctx.strokeRect(cx - 10, cy - 7, 20, 14);
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
  if (state.live?.floorItems) {
    rebuildFloorItemsSpatial(state.live.floorItems);
  }

  if (state.sprites) {
    Object.values(state.sprites.tiles || {}).forEach(getSpriteImage);
    Object.values(state.sprites.humanoid || {}).forEach(getSpriteImage);
    Object.values(state.sprites.items || {}).forEach((it) => getSpriteImage(it.url));
    Object.values(state.sprites.job_outfits || {}).forEach((jo) => {
      Object.values(jo.layers || {}).forEach(getSpriteImage);
    });
  }

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
  renderEquipWindow(true);
  renderChatFeed(true);
  renderApiLogs(true);

  connectWebSocket();
  startBrowserDirectLlmLoop();
  requestAnimationFrame(renderLoop);
}

function connectWebSocket() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/ws`);
  state.ws = ws;

  ws.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === "state") {
        if (payload.state.floorItems) {
          rebuildFloorItemsSpatial(payload.state.floorItems);
        }
        state.live = payload.state;
        state.llm = payload.llm;
        state.apiLogs = payload.apiLogs || [];
        updateTopTelemetry();
        renderCrewRoster(false);
        renderInspector(false);
        renderPlayerHud(false);
        renderEquipWindow(false);
        renderChatFeed(false);
        renderApiLogs(false);
      }
    } catch (e) {
      console.error("WS parse error:", e);
    }
  };

  ws.onclose = () => {
    state.ws = null;
    setTimeout(connectWebSocket, 2000);
  };
}

// ============================================================================
// Direct Browser OpenAI API Execution Engine
// ============================================================================

function getActiveApiKey() {
  return (state.browserLlm.apiKey || "").trim();
}

function normalizeOpenAiEndpoint(rawUrl) {
  let u = (rawUrl || "https://api.openai.com/v1").trim().replace(/\/+$/, "");
  if (!/^https?:\/\//i.test(u)) {
    u = "https://" + u;
  }
  if (u.endsWith("/chat/completions")) {
    return u;
  }
  if (/\/v\d+$/i.test(u) || /\/openai$/i.test(u)) {
    return `${u}/chat/completions`;
  }
  return `${u}/v1/chat/completions`;
}

function startBrowserDirectLlmLoop() {
  setInterval(() => {
    const key = getActiveApiKey();
    if (!key || state.browserLlm.inFlight) return;
    const now = performance.now();
    const waitMs = Math.max(1200, (state.browserLlm.intervalSec || 2.5) * 1000);
    if (now - state.browserLlm.lastCallTime >= waitMs) {
      runBrowserDirectLlmStep(null);
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

    const endpoint = normalizeOpenAiEndpoint(state.browserLlm.baseUrl);
    const model = (state.browserLlm.model || "gpt-4o-mini").trim();

    if (statusEl) {
      statusEl.textContent = `📡 Запрос к ${model} (${promptData.agentName})...`;
    }

    const t0 = performance.now();
    let llmRes = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages: promptData.messages,
        temperature: 0.8,
        max_tokens: 320,
      }),
    });

    if (llmRes.status === 400) {
      llmRes = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          model,
          messages: promptData.messages,
        }),
      });
    }

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
        statusEl.textContent = `❌ HTTP ${llmRes.status}`;
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
      if (applied.state.floorItems) {
        rebuildFloorItemsSpatial(applied.state.floorItems);
      }
      state.live = applied.state;
      state.llm = applied.llm;
      state.apiLogs = applied.apiLogs || state.apiLogs;
      renderCrewRoster(false);
      renderInspector(false);
      renderPlayerHud(false);
      renderEquipWindow(false);
      renderChatFeed(false);
      renderApiLogs(true);
    }
    if (statusEl) {
      statusEl.textContent = `✅ ${model}: ${latencyMs} мс (${promptData.agentName})`;
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
      statusEl.textContent = `⚠️ Ошибка сети/CORS: ${err.message || err}`;
    }
    state.browserLlm.inFlight = false;
    updateTopTelemetry();
    return { ok: false, error: String(err.message || err) };
  }
}

// ============================================================================
// Fullscreen 60 FPS Space Station 14 Renderer (Parallax + Rotations + Lighting)
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
  renderMainViewport(now);
  renderMinimap();

  // Also render Quad CCTV canvases if the CCTV window is open
  if (!document.getElementById("cctvWindow").classList.contains("hidden")) {
    renderQuadViewports(now);
  }

  requestAnimationFrame(renderLoop);
}

function interpolateAgents() {
  if (!state.live || !state.live.agents) return;
  const now = performance.now();
  const userMovingActive = (now - (state.lastUserMoveInputTime || 0)) < 450;

  for (const ag of state.live.agents) {
    const cur = state.renderPos.get(ag.id);
    if (!cur) {
      state.renderPos.set(ag.id, { x: ag.x, y: ag.y, moving: false });
      continue;
    }
    if (ag.id === state.selectedAgentId && userMovingActive) {
      ag.x = cur.x;
      ag.y = cur.y;
      cur.moving = true;
      continue;
    }
    const dist = Math.hypot(ag.x - cur.x, ag.y - cur.y);
    if (dist > 6.0) {
      state.renderPos.set(ag.id, { x: ag.x, y: ag.y, moving: false });
    } else {
      cur.x += (ag.x - cur.x) * 0.28;
      cur.y += (ag.y - cur.y) * 0.28;
      cur.moving = dist > 0.03;
    }
  }

  if (state.viewMode === "follow" && state.selectedAgentId) {
    const rpos = state.renderPos.get(state.selectedAgentId);
    if (rpos) {
      state.camX += (rpos.x - state.camX) * 0.35;
      state.camY += (rpos.y - state.camY) * 0.35;
    }
  }
}

function renderMainViewport(now) {
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
  renderStationScene(ctx, rect.width, rect.height, state.camX, state.camY, state.zoom, true, now);
  ctx.restore();
}

function renderQuadViewports(now) {
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
    renderStationScene(ctx, rect.width, rect.height, camObj.x, camObj.y, 1.05, false, now);
  }
}

function renderStationScene(ctx, width, height, centerCamX, centerCamY, zoom, isInteractive, now = 0) {
  ctx.imageSmoothingEnabled = false;

  // 1. Deep space background + SS14 Starfield Parallax
  ctx.fillStyle = "#03050b";
  ctx.fillRect(0, 0, width, height);

  for (const st of STARFIELD) {
    const sx = ((st.x - centerCamX * 32 * st.depth) % width + width) % width;
    const sy = ((st.y + centerCamY * 32 * st.depth) % height + height) % height;
    ctx.fillStyle = st.color;
    ctx.globalAlpha = st.alpha;
    ctx.fillRect(sx, sy, st.size, st.size);
  }
  ctx.globalAlpha = 1.0;

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

  // 2. Viewport-culled Floors, Rotated Furniture/Machines, Items, Walls, Windows & Airlocks
  for (let ty = maxTy; ty >= minTy; ty--) {
    for (let tx = minTx; tx <= maxTx; tx++) {
      const key = `${tx},${ty}`;
      const tileInfo = state.spatial.tiles.get(key);
      if (!tileInfo) continue;

      const sx = Math.floor(width / 2 + (tx - centerCamX) * scale);
      const sy = Math.floor(height / 2 - (ty + 1 - centerCamY) * scale);
      const drawSize = Math.ceil(scale);

      // 2a. Floor tile
      const tname = tileInfo[0];
      if (tname === "FloorLattice") {
        ctx.strokeStyle = "#334155";
        ctx.lineWidth = 1;
        ctx.strokeRect(sx + 2, sy + 2, drawSize - 4, drawSize - 4);
      } else {
        const tUrl = tileSprites[tname] || tileSprites["FloorSteel"];
        const tImg = getSpriteImage(tUrl);
        if (!drawFirstFrame(ctx, tImg, sx, sy, drawSize, drawSize, 0)) {
          ctx.fillStyle = "#1e293b";
          ctx.fillRect(sx, sy, drawSize, drawSize);
        }
      }

      // 2b. Furniture, Tables, Chairs, Beds, Lockers, Vending & Consoles (with exact rotation!)
      const objs = state.spatial.objects.get(key);
      if (objs) {
        for (const obj of objs) {
          const pInfo = protoSprites[obj.proto];
          const oImg = pInfo ? getSpriteImage(pInfo.url) : null;
          drawFirstFrame(ctx, oImg, sx, sy, drawSize, drawSize, obj.rot || 0);
        }
      }

      // 2c. Pickable Map Items lying on this tile/table (`floorItems`)
      const fitems = state.spatial.floorByTile.get(key);
      if (fitems) {
        for (const fi of fitems) {
          const [isx, isy] = worldToScreen(fi.x, fi.y, width, height, centerCamX, centerCamY, zoom);
          const itemSize = scale * 0.72;
          const img = getSpriteImage(fi.url);
          drawFirstFrame(ctx, img, isx - itemSize / 2, isy - itemSize / 2, itemSize, itemSize, 0);
        }
      }

      // 2d. Solid Wall with 3D SS14 depth bevel
      const wall = state.spatial.walls.get(key);
      if (wall) {
        const pInfo = protoSprites[wall.proto] || protoSprites["WallSolid"];
        const wImg = pInfo ? getSpriteImage(pInfo.url) : null;
        if (!drawFirstFrame(ctx, wImg, sx, sy, drawSize, drawSize, 0)) {
          ctx.fillStyle = "#475569";
          ctx.fillRect(sx, sy, drawSize, drawSize);
        }
        // Subtle 3D top highlight & bottom shadow for wall depth
        ctx.fillStyle = "rgba(255, 255, 255, 0.08)";
        ctx.fillRect(sx, sy, drawSize, Math.max(2, drawSize * 0.1));
        ctx.fillStyle = "rgba(0, 0, 0, 0.35)";
        ctx.fillRect(sx, sy + drawSize * 0.85, drawSize, drawSize * 0.15);
      }

      // 2e. Window
      const win = state.spatial.windows.get(key);
      if (win) {
        const pInfo = protoSprites[win.proto] || protoSprites["Window"];
        const winImg = pInfo ? getSpriteImage(pInfo.url) : null;
        if (!drawFirstFrame(ctx, winImg, sx, sy, drawSize, drawSize, win.rot || 0)) {
          ctx.fillStyle = "rgba(56, 189, 248, 0.35)";
          ctx.fillRect(sx + 2, sy + 2, drawSize - 4, drawSize - 4);
        }
      }

      // 2f. Door / Airlock
      const door = state.spatial.doorsByTile.get(key);
      if (door) {
        const isOpen = openDoors.has(door.uid);
        const isBolted = boltedDoors.has(door.uid);
        const pInfo = protoSprites[door.proto] || protoSprites["Airlock"];
        if (isOpen) {
          const openUrl = pInfo?.extra?.open;
          const openImg = openUrl ? getSpriteImage(openUrl) : null;
          if (!drawFirstFrame(ctx, openImg, sx, sy, drawSize, drawSize, 0)) {
            ctx.fillStyle = "rgba(15, 23, 42, 0.55)";
            ctx.fillRect(sx, sy, drawSize * 0.16, drawSize);
            ctx.fillRect(sx + drawSize * 0.84, sy, drawSize * 0.16, drawSize);
          }
        } else {
          const dImg = pInfo ? getSpriteImage(pInfo.url) : null;
          if (!drawFirstFrame(ctx, dImg, sx, sy, drawSize, drawSize, 0)) {
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

  // 3. Dynamic Station Lighting & Lamp Glow (`Poweredlight` fixtures + Red Alert strobe)
  if (state.lightingEnabled && zoom >= 0.7) {
    const isRedAlert = state.live?.alertLevel === "red";
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    for (let ty = maxTy; ty >= minTy; ty--) {
      for (let tx = minTx; tx <= maxTx; tx++) {
        const light = state.spatial.lights.get(`${tx},${ty}`);
        if (!light) continue;
        const [lx, ly] = worldToScreen(light.x, light.y, width, height, centerCamX, centerCamY, zoom);
        const radius = scale * 2.8;
        const grad = ctx.createRadialGradient(lx, ly, scale * 0.1, lx, ly, radius);
        if (isRedAlert) {
          grad.addColorStop(0, "rgba(239, 68, 68, 0.14)");
          grad.addColorStop(1, "rgba(239, 68, 68, 0)");
        } else {
          grad.addColorStop(0, "rgba(254, 249, 195, 0.085)");
          grad.addColorStop(1, "rgba(56, 189, 248, 0)");
        }
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(lx, ly, radius, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.restore();
  }

  // 4. Optional AI Navigation Paths
  if (state.showPaths && state.live?.agents && isInteractive) {
    for (const ag of state.live.agents) {
      if (!ag.path || ag.path.length === 0) continue;
      const rpos = state.renderPos.get(ag.id) || ag;
      ctx.save();
      ctx.strokeStyle = ag.color || "#38bdf8";
      ctx.globalAlpha = ag.id === state.selectedAgentId ? 0.65 : 0.25;
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

  // 5. Visual Effects (Laser Beams, Stun Slash, Healing Aura, HONK, Ghost Boo)
  if (state.live?.effects) {
    for (const ef of state.live.effects) {
      if (!state.seenEffectIds.has(ef.id)) {
        state.seenEffectIds.add(ef.id);
        playSs14Sound(ef.type);
      }
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

  // 6. Crew Mobs & Ghost Observers (with 4-directional sprites + walking bob + shadow)
  if (state.live?.agents) {
    const hum = state.sprites.humanoid || {};
    const outfits = state.sprites.job_outfits || {};

    for (const ag of state.live.agents) {
      const rpos = state.renderPos.get(ag.id) || ag;
      if (rpos.x < minTx - 1 || rpos.x > maxTx + 1 || rpos.y < minTy - 1 || rpos.y > maxTy + 1) continue;

      const [sx, sy] = worldToScreen(rpos.x, rpos.y, width, height, centerCamX, centerCamY, zoom);
      const bobY = rpos.moving && !ag.isGhost && !ag.stunned && ag.status !== "Dead"
        ? Math.sin(now * 0.02 + ag.uid) * (2.0 * zoom)
        : 0;
      const drawX = sx - scale / 2;
      const drawY = sy - scale / 2 + bobY;

      // Drop shadow under feet
      ctx.fillStyle = "rgba(0, 0, 0, 0.42)";
      ctx.beginPath();
      ctx.ellipse(sx, sy + scale * 0.36, scale * 0.28, scale * 0.14, 0, 0, Math.PI * 2);
      ctx.fill();

      // Active player subtle indicator
      if (ag.id === state.selectedAgentId) {
        ctx.save();
        ctx.strokeStyle = ag.combatMode ? "#ef4444" : (ag.isGhost ? "#a855f7" : "rgba(56, 189, 248, 0.75)");
        ctx.lineWidth = Math.max(1.5, 2 * zoom);
        ctx.beginPath();
        ctx.arc(sx, sy, scale * 0.48, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }

      ctx.save();
      if (ag.isGhost) {
        const floatY = Math.sin(now * 0.005) * (3.0 * zoom);
        ctx.globalAlpha = 0.78;
        const ghostImg = getSpriteImage(hum.ghost);
        if (!drawDirectionalFrame(ctx, ghostImg, ag.direction, drawX, drawY + floatY, scale, scale)) {
          ctx.fillStyle = "#a855f7";
          ctx.beginPath();
          ctx.arc(sx, sy, scale * 0.38, 0, Math.PI * 2);
          ctx.fill();
        }
      } else {
        if (ag.status === "Dead" || ag.stunned) {
          ctx.translate(sx, sy);
          ctx.rotate(Math.PI / 2);
          ctx.translate(-sx, -sy);
        }

        const isFemale = ag.gender === "female";
        const bodyParts = [
          isFemale ? (hum.torso_f || hum.torso_m) : hum.torso_m,
          isFemale ? (hum.head_f || hum.head_m) : hum.head_m,
          hum.l_leg,
          hum.r_leg,
          hum.l_foot,
          hum.r_foot,
          hum.l_arm,
          hum.r_arm,
          hum.l_hand,
          hum.r_hand,
        ];
        let drewBody = false;
        for (const partObj of bodyParts) {
          const img = getSpriteImage(partObj);
          if (drawDirectionalFrame(ctx, img, ag.direction, drawX, drawY, scale, scale)) {
            drewBody = true;
          }
        }

        const outfit = outfits[ag.job] || outfits["Passenger"] || {};
        const layers = outfit.layers || outfit;
        const layerOrder = ["jumpsuit", "shoes", "gloves", "belt", "outer", "back", "ears", "eyes", "mask", "head"];
        for (const lk of layerOrder) {
          if (layers[lk]) {
            drawDirectionalFrame(ctx, getSpriteImage(layers[lk]), ag.direction, drawX, drawY, scale, scale);
          }
        }

        const activeHandObj = ag.activeHand === "left" ? ag.leftHand : ag.rightHand;
        if (activeHandObj && activeHandObj.url) {
          const itemImg = getSpriteImage(activeHandObj.url);
          drawFirstFrame(ctx, itemImg, sx + scale * 0.05, drawY + scale * 0.45, scale * 0.42, scale * 0.42, 0);
        }

        if (!drewBody) {
          ctx.fillStyle = ag.color || "#38bdf8";
          ctx.beginPath();
          ctx.arc(sx, sy, scale * 0.38, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      ctx.restore();

      if (ag.stunned || ag.cuffed || ag.status === "Dead") {
        ctx.font = `700 ${Math.max(10, Math.floor(11 * zoom))}px Inter, sans-serif`;
        ctx.textAlign = "center";
        ctx.fillStyle = "#fde047";
        const badge = ag.status === "Dead" ? "💀 МЁРТВ" : (ag.cuffed ? "⛓️ В НАРУЧНИКАХ" : "💫 ОГЛУШЁН");
        ctx.fillText(badge, sx, drawY - 14 * zoom);
      }

      if (state.showNames && zoom >= 0.55) {
        ctx.font = `700 ${Math.max(9, Math.floor(10 * zoom))}px Inter, sans-serif`;
        ctx.textAlign = "center";
        const labelY = drawY - 3 * zoom;
        ctx.fillStyle = "rgba(0, 0, 0, 0.65)";
        const nameW = ctx.measureText(ag.name).width + 6;
        ctx.fillRect(sx - nameW / 2, labelY - 9 * zoom, nameW, 12 * zoom);
        ctx.fillStyle = ag.color || "#f8fafc";
        ctx.fillText(ag.name, sx, labelY);

        if (ag.lastSpeech) {
          const bubbleText = ag.lastSpeech.length > 56 ? ag.lastSpeech.slice(0, 56) + "…" : ag.lastSpeech;
          ctx.font = `600 ${Math.max(9, Math.floor(10 * zoom))}px Inter, sans-serif`;
          const bw = ctx.measureText(bubbleText).width + 12;
          const by = labelY - 25 * zoom;

          ctx.fillStyle = "rgba(11, 16, 28, 0.92)";
          ctx.strokeStyle = ag.color || "#38bdf8";
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          ctx.roundRect(sx - bw / 2, by, bw, 15 * zoom, 4);
          ctx.fill();
          ctx.stroke();

          ctx.fillStyle = "#ffffff";
          ctx.fillText(bubbleText, sx, by + 11 * zoom);
        }
      }
    }
  }
}

// ============================================================================
// HUD, Alerts, Equipment Window & Chat Updates
// ============================================================================

function updateTopTelemetry() {
  if (!state.live) return;
  document.getElementById("roundClock").textContent = state.live.roundClock || "00:00";
  document.getElementById("cargoTelemetry").textContent = `${state.live.cargoBalance ?? 4500} ₡`;

  const alertBadge = document.getElementById("alertBadge");
  const lvl = (state.live.alertLevel || "green").toLowerCase();
  alertBadge.className = `alert-val ${lvl}`;
  const lvlRu = { green: "ЗЕЛЁНЫЙ", blue: "СИНИЙ", red: "КРАСНЫЙ" };
  alertBadge.textContent = lvlRu[lvl] || lvl.toUpperCase();

  const llmBadge = document.getElementById("llmStatusBadge");
  const hasKey = Boolean(getActiveApiKey()) || Boolean(state.llm?.hasApiKey);
  const totalCalls = state.llm?.totalLlmCalls || 0;
  if (state.browserLlm.inFlight) {
    llmBadge.className = "engine-badge busy";
    llmBadge.textContent = `Запрос...`;
  } else if (hasKey) {
    llmBadge.className = "engine-badge online";
    llmBadge.textContent = `Активен (${totalCalls})`;
  } else {
    llmBadge.className = "engine-badge autonomous";
    llmBadge.textContent = "Ввести ключ";
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

  const hpTile = document.getElementById("alertTileHealth");
  hpTile.className = `ss14-alert-tile ${ag.health > 70 ? "ok" : (ag.health > 30 ? "warn" : "danger")}`;

  const combatTile = document.getElementById("alertTileCombat");
  combatTile.className = `ss14-alert-tile ${ag.combatMode ? "danger" : "ok"}`;
  document.getElementById("alertCombatIcon").textContent = ag.combatMode ? "⚔️" : "🛡️";
  document.getElementById("alertCombatText").textContent = ag.combatMode ? "БОЙ" : "МИР";

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

  // Belt / Pocket Inventory Bar
  const invBar = document.getElementById("hudInventoryBar");
  invBar.innerHTML = "";
  const invList = ag.inventory || [];
  for (let i = 0; i < 5; i++) {
    const item = invList[i];
    const slot = document.createElement("div");
    slot.className = "inv-slot";
    if (item && item.id) {
      slot.title = `Взять «${item.name}» в активную руку`;
      slot.innerHTML = `<img src="${item.url}" alt="" /><span>${item.name}</span>`;
      slot.onclick = () => sendAgentCommand({ agentId: ag.id, action: "equip_inv", index: i });
    } else {
      slot.innerHTML = `<span>Пояс ${i + 1}</span>`;
    }
    invBar.appendChild(slot);
  }

  const combatBtn = document.getElementById("hudCombatBtn");
  if (ag.combatMode) {
    combatBtn.className = "hud-combat-btn harm";
    combatBtn.textContent = "⚔️ БОЙ [C]";
  } else {
    combatBtn.className = "hud-combat-btn";
    combatBtn.textContent = "🛡️ МИР [C]";
  }

  document.getElementById("ghostHudBanner").classList.toggle("hidden", !ag.isGhost);
}

function renderEquipWindow(force = false) {
  const win = document.getElementById("equipWindow");
  if (!win || win.classList.contains("hidden") || !state.live?.agents) return;
  const ag = state.live.agents.find((a) => a.id === state.selectedAgentId) || state.live.agents[0];
  if (!ag) return;

  const hash = JSON.stringify([ag.id, ag.job, ag.leftHand?.id, ag.rightHand?.id, (ag.inventory || []).map((i) => i.id)]);
  if (!force && state.domHashes.equip === hash) return;
  state.domHashes.equip = hash;

  const outfit = (state.sprites?.job_outfits || {})[ag.job] || {};
  const layers = outfit.layers || outfit;
  const unwrap = (v) => (typeof v === "string" ? v : v?.url || "");
  document.getElementById("equipCharSummary").innerHTML = `
    <div><strong>${ag.name}</strong> — ${ag.jobTitleRu} (${ag.department})</div>
    <div style="font-size:10.5px;color:#94a3b8;margin-top:2px">Здоровье: ${Math.round(ag.health)}% • Отсек: ${ag.currentRoom}</div>
  `;

  const grid = document.getElementById("equipSlotsGrid");
  grid.innerHTML = "";
  const slots = [
    ["Головной убор", unwrap(layers.head), "Шлем / Шапка должности"],
    ["Верхняя одежда", unwrap(layers.outer), "Броня / Халат / Скафандр"],
    ["Униформа", unwrap(layers.jumpsuit), "Комбинезон станции"],
    ["Значок должности", unwrap(layers.icon), ag.jobTitleRu],
    ["Левая рука", ag.leftHand?.url, ag.leftHand?.name || "Пусто"],
    ["Правая рука", ag.rightHand?.url, ag.rightHand?.name || "Пусто"],
  ];
  for (const [slotTitle, imgUrl, itemName] of slots) {
    const card = document.createElement("div");
    card.className = "bui-item-btn";
    card.innerHTML = `
      ${imgUrl ? `<img src="${imgUrl}" alt="" />` : `<div style="width:28px;height:28px;background:#0f172a;border-radius:4px"></div>`}
      <div>
        <div style="font-size:10px;color:#38bdf8;font-weight:800">${slotTitle}</div>
        <div style="font-size:11px;font-weight:700">${itemName}</div>
      </div>
    `;
    grid.appendChild(card);
  }
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
        <span style="color:${ag.color}">${ag.isGhost ? "👻 " : ""}${ag.name}</span>
        <span style="font-size:9.5px;color:#94a3b8">${ag.browserControlled ? "🎮 ИГРОК" : "🤖 ИИ"}</span>
      </div>
      <div class="crew-sub">
        <span>${ag.jobTitleRu}</span>
        <span>📍 ${ag.currentRoom}</span>
      </div>
    `;
    div.onclick = () => {
      state.selectedAgentId = ag.id;
      state.viewMode = "follow";
      renderCrewRoster(true);
      renderInspector(true);
      renderPlayerHud(true);
      renderEquipWindow(true);
    };
    container.appendChild(div);
  }
}

function renderInspector(force = false) {
  if (!state.live?.agents) return;
  const ag = state.live.agents.find((a) => a.id === state.selectedAgentId) || state.live.agents[0];
  if (!ag) return;

  const hash = `${ag.id}|${ag.currentRoom}|${Math.round(ag.health)}|${ag.llmCallsCount}|${ag.lastThought}|${ag.currentTask}`;
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
  if (!force && state.domHashes.chat > 0 && lastId > state.domHashes.chat) {
    playSs14Sound("radio");
  }
  state.domHashes.chat = lastId;

  const wasAtBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 60;
  feed.innerHTML = "";

  for (const msg of state.live.chat) {
    const div = document.createElement("div");
    div.className = `chat-msg ${msg.channel}`;
    div.innerHTML = `
      <div class="chat-meta">
        <span>[${msg.time}] <strong>${msg.speakerName}</strong></span>
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
    feed.innerHTML = `<div class="chat-msg">Откройте «⚙️ OpenAI API» сверху, введите API Key и нажмите «Сохранить» — здесь пойдут живые ответы модели.</div>`;
    return;
  }

  for (const log of [...state.apiLogs].reverse()) {
    const div = document.createElement("div");
    div.className = "chat-msg Science";
    div.innerHTML = `
      <div class="chat-meta">
        <span>[${log.time}] <strong>${log.agent}</strong></span>
        <span>${log.model} • ${log.latencyMs}ms</span>
      </div>
      <div>💭 <em>${log.thought || "—"}</em></div>
      ${log.say ? `<div>🗣️ «${log.say}»</div>` : ""}
    `;
    feed.appendChild(div);
  }
}

// ============================================================================
// Cameras, Beacons & Ghost Warp
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
        <span>📹 ${cam.id}</span>
        <span style="font-size:9.5px;color:#94a3b8">${cam.department}</span>
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
  state.viewMode = "single";
  state.camX = cam.x;
  state.camY = cam.y;
  populateCameraLists(document.getElementById("cameraSearchInput").value);
}

function populateBeaconsAndRooms() {
  const moveSelect = document.getElementById("moveRoomSelect");
  const ghostWarp = document.getElementById("ghostWarpSelect");
  if (!state.map) return;

  if (moveSelect && moveSelect.options.length <= 1) {
    for (const b of state.map.beacons) {
      const opt = document.createElement("option");
      opt.value = b.name;
      opt.textContent = b.name;
      moveSelect.appendChild(opt);
    }
  }

  if (ghostWarp && ghostWarp.options.length <= 1) {
    if (state.live?.agents) {
      for (const ag of state.live.agents) {
        if (ag.isGhost) continue;
        const opt = document.createElement("option");
        opt.value = `agent:${ag.id}`;
        opt.textContent = `👤 Экипаж: ${ag.name} (${ag.jobTitleRu})`;
        ghostWarp.appendChild(opt);
      }
    }
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
  if (!bui) return;
  if (bui.type === "camera_console") {
    document.getElementById("cctvWindow").classList.remove("hidden");
    return;
  }
  const win = document.getElementById("buiWindow");
  const title = document.getElementById("buiTitle");
  const body = document.getElementById("buiBody");
  if (!win) return;

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
        makeItemBtn(id, "Выдать в руку", async () => {
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
    if (data.state.floorItems) rebuildFloorItemsSpatial(data.state.floorItems);
    state.live = data.state;
    updateTopTelemetry();
    renderPlayerHud(true);
    renderInspector(true);
    renderEquipWindow(true);
  }
  return data;
}

// ============================================================================
// Right-Click SS14 Verb Context Menu
// ============================================================================

function openContextMenu(clientX, clientY, wx, wy) {
  const menu = document.getElementById("contextMenu");
  menu.innerHTML = "";
  menu.classList.remove("hidden");
  menu.style.left = `${Math.min(window.innerWidth - 230, clientX)}px`;
  menu.style.top = `${Math.min(window.innerHeight - 210, clientY)}px`;

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

  const clickedAgent = (state.live?.agents || []).find((a) => Math.hypot(a.x - wx, a.y - wy) < 0.85);
  if (clickedAgent) {
    addVerb(`🔍 Осмотреть: ${clickedAgent.name}`, () => {
      state.selectedAgentId = clickedAgent.id;
      document.getElementById("crewWindow").classList.remove("hidden");
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

  const clickedFloorItem = state.floorItemsCache.find((fi) => Math.hypot(fi.x - wx, fi.y - wy) < 0.85);
  if (clickedFloorItem) {
    addVerb(`✋ Поднять: ${clickedFloorItem.name}`, () => {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "pickup_item", uid: clickedFloorItem.uid });
    });
  }

  const tx = Math.floor(wx);
  const ty = Math.floor(wy);
  const door = state.spatial.doorsByTile.get(`${tx},${ty}`);
  if (door) {
    addVerb(`🚪 Открыть / Закрыть / Взломать: ${door.name}`, () => {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "toggle_door", doorUid: door.uid });
    });
  }

  const objs = state.spatial.objects.get(`${tx},${ty}`) || [];
  for (const obj of objs) {
    addVerb(`⚙️ Использовать: ${obj.name}`, async () => {
      const res = await sendAgentCommand({ agentId: state.selectedAgentId, action: "interact", uid: obj.uid });
      if (res.bui) openBuiWindow(res.bui);
    });
  }

  addVerb(`🎯 Кинуть предмет из руки сюда`, () => {
    sendAgentCommand({ agentId: state.selectedAgentId, action: "throw_item", x: wx, y: wy });
  });

  addVerb(`🚶 Идти сюда (${Math.floor(wx)}, ${Math.floor(wy)})`, () => {
    sendAgentCommand({ agentId: state.selectedAgentId, action: "move_to", x: wx, y: wy });
  });
}

// ============================================================================
// Mode Switching (Playable Crew Mode / Ghost Mode / CCTV Window)
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
      if (data.state.floorItems) rebuildFloorItemsSpatial(data.state.floorItems);
      state.live = data.state;
      state.selectedAgentId = data.agentId;
      state.viewMode = "follow";
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
    renderCrewRoster(true);
    renderInspector(true);
    renderPlayerHud(true);
  } else if (mode === "cctv") {
    document.getElementById("cctvWindow").classList.toggle("hidden");
  }
}

// ============================================================================
// 60 FPS Client-Side WASD Movement + WebSocket Sync
// ============================================================================

function isClientTilePassable(tx, ty, isGhost) {
  if (isGhost) return true;
  const key = `${tx},${ty}`;
  if (!state.spatial.tiles.has(key)) return false;
  if (state.spatial.walls.has(key) || state.spatial.windows.has(key)) return false;
  return true;
}

function handleContinuousWasd(now) {
  const dt = Math.min(0.05, (now - (state.lastFrameMoveTime || now)) / 1000);
  state.lastFrameMoveTime = now;

  let dx = 0;
  let dy = 0;
  if (state.keysDown.has("KeyW") || state.keysDown.has("ArrowUp")) dy += 1;
  if (state.keysDown.has("KeyS") || state.keysDown.has("ArrowDown")) dy -= 1;
  if (state.keysDown.has("KeyD") || state.keysDown.has("ArrowRight")) dx += 1;
  if (state.keysDown.has("KeyA") || state.keysDown.has("ArrowLeft")) dx -= 1;

  if (dx === 0 && dy === 0) return;

  const ag = state.live?.agents?.find((a) => a.id === state.selectedAgentId);
  if (!ag) return;
  if (!ag.isGhost && (ag.status === "Dead" || ag.stunned)) return;

  state.lastUserMoveInputTime = now;
  const len = Math.hypot(dx, dy) || 1;
  const ndx = dx / len;
  const ndy = dy / len;
  const speed = ag.isGhost ? 9.5 : 5.8;

  let rpos = state.renderPos.get(ag.id);
  if (!rpos) {
    rpos = { x: ag.x, y: ag.y, moving: true };
    state.renderPos.set(ag.id, rpos);
  }

  const nx = rpos.x + ndx * speed * dt;
  const ny = rpos.y + ndy * speed * dt;

  if (isClientTilePassable(Math.floor(nx), Math.floor(ny), ag.isGhost)) {
    rpos.x = nx;
    rpos.y = ny;
  } else if (isClientTilePassable(Math.floor(nx), Math.floor(rpos.y), ag.isGhost)) {
    rpos.x = nx;
  } else if (isClientTilePassable(Math.floor(rpos.x), Math.floor(ny), ag.isGhost)) {
    rpos.y = ny;
  }

  ag.x = rpos.x;
  ag.y = rpos.y;
  ag.path = [];
  rpos.moving = true;

  if (Math.abs(dx) > Math.abs(dy)) {
    ag.direction = dx > 0 ? "east" : "west";
  } else if (Math.abs(dy) > 0) {
    ag.direction = dy > 0 ? "north" : "south";
  }

  if (now - state.lastWasdTime >= 75) {
    state.lastWasdTime = now;
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      state.ws.send(
        JSON.stringify({
          type: "player_move",
          agentId: ag.id,
          x: Number(rpos.x.toFixed(2)),
          y: Number(rpos.y.toFixed(2)),
          direction: ag.direction,
        })
      );
    }
  }
}

// ============================================================================
// UI Events & SS14 Hotkeys
// ============================================================================

function bindUIEvents() {
  document.getElementById("modePlayBtn").onclick = () => setGameMode("play");
  document.getElementById("modeGhostBtn").onclick = () => setGameMode("ghost");
  document.getElementById("modeCctvBtn").onclick = () => setGameMode("cctv");

  document.getElementById("openEquipWindowBtn").onclick = () => {
    const win = document.getElementById("equipWindow");
    win.classList.toggle("hidden");
    renderEquipWindow(true);
  };
  document.getElementById("hotbarEquipBtn").onclick = () => {
    const win = document.getElementById("equipWindow");
    win.classList.toggle("hidden");
    renderEquipWindow(true);
  };
  document.getElementById("openCrewWindowBtn").onclick = () => {
    document.getElementById("crewWindow").classList.toggle("hidden");
  };
  document.getElementById("hotbarCharPill").onclick = () => {
    document.getElementById("crewWindow").classList.toggle("hidden");
  };
  document.getElementById("closeCctvWinBtn").onclick = () => {
    document.getElementById("cctvWindow").classList.add("hidden");
  };

  document.querySelectorAll(".nano-win-close[data-closewin]").forEach((btn) => {
    btn.onclick = () => document.getElementById(btn.dataset.closewin).classList.add("hidden");
  });

  // Ghost Banner
  document.getElementById("ghostBooBtn").onclick = () => {
    sendAgentCommand({ agentId: state.selectedAgentId, action: "ghost_boo" });
  };
  document.getElementById("ghostReturnBodyBtn").onclick = () => setGameMode("play");
  document.getElementById("ghostWarpSelect").onchange = (e) => {
    const val = e.target.value;
    if (!val) return;
    if (val.startsWith("room:")) {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "ghost_warp", room: val.slice(5) });
    } else if (val.startsWith("agent:")) {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "ghost_warp", targetAgentId: val.slice(6) });
    }
    e.target.value = "";
  };

  // Bottom Hotbar & Hands
  document.getElementById("hudInteractNearBtn").onclick = async () => {
    const res = await sendAgentCommand({ agentId: state.selectedAgentId, action: "interact_nearest" });
    if (res.bui) openBuiWindow(res.bui);
  };
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
  document.getElementById("hudThrowHandBtn").onclick = () => {
    sendAgentCommand({ agentId: state.selectedAgentId, action: "throw_item" });
  };
  document.getElementById("hudCombatBtn").onclick = () => {
    sendAgentCommand({ agentId: state.selectedAgentId, action: "toggle_combat" });
  };
  document.getElementById("alertTileCombat").onclick = () => {
    sendAgentCommand({ agentId: state.selectedAgentId, action: "toggle_combat" });
  };
  document.getElementById("hudUplinkBtn").onclick = () => {
    openBuiWindow({ type: "uplink", name: "Аплинк Синдиката" });
  };
  document.getElementById("buiCloseBtn").onclick = () => {
    document.getElementById("buiWindow").classList.add("hidden");
  };

  // Chat Overlay Tabs
  document.querySelectorAll(".chat-tab-btn").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll(".chat-tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".ss14-chat-body").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(btn.dataset.chattab).classList.add("active");
    };
  });

  document.getElementById("cameraSearchInput").oninput = (e) => populateCameraLists(e.target.value);
  document.getElementById("singleCamModeBtn").onclick = () => {
    document.getElementById("cctvWindow").classList.add("hidden");
  };
  document.getElementById("quadCamModeBtn").onclick = () => {
    document.getElementById("cctvWindow").classList.remove("hidden");
  };

  // Top Bar Icon Toggles
  document.getElementById("zoomInBtn").onclick = () => setZoom(state.zoom * 1.25);
  document.getElementById("zoomOutBtn").onclick = () => setZoom(state.zoom / 1.25);
  document.getElementById("toggleSoundBtn").onclick = (e) => {
    state.soundEnabled = !state.soundEnabled;
    e.currentTarget.classList.toggle("active", state.soundEnabled);
    if (state.soundEnabled) playSs14Sound("radio");
  };
  document.getElementById("toggleLightBtn").onclick = (e) => {
    state.lightingEnabled = !state.lightingEnabled;
    e.currentTarget.classList.toggle("active", state.lightingEnabled);
  };
  document.getElementById("toggleNamesBtn").onclick = (e) => {
    state.showNames = !state.showNames;
    e.currentTarget.classList.toggle("active", state.showNames);
  };
  document.getElementById("togglePathsBtn").onclick = (e) => {
    state.showPaths = !state.showPaths;
    e.currentTarget.classList.toggle("active", state.showPaths);
  };

  document.getElementById("minimapCanvas").onclick = (e) => {
    if (!state.map) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const rx = (e.clientX - rect.left) / rect.width;
    const ry = (e.clientY - rect.top) / rect.height;
    const b = state.map.bounds || { minX: -55, maxX: 82, minY: -48, maxY: 38 };
    const spanX = Math.max(1, b.maxX - b.minX + 6);
    const spanY = Math.max(1, b.maxY - b.minY + 6);
    const wx = rx * spanX + b.minX - 3;
    const wy = b.maxY + 3 - ry * spanY;
    sendAgentCommand({ agentId: state.selectedAgentId, action: "move_to", x: wx, y: wy });
  };

  // Canvas Mouse Interactions
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

  // Full SS14 Keyboard Shortcuts
  window.addEventListener("keydown", async (e) => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) {
      if (e.key === "Escape") document.activeElement.blur();
      return;
    }
    state.keysDown.add(e.code);

    if (["KeyW", "KeyA", "KeyS", "KeyD", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.code)) {
      state.viewMode = "follow";
    } else if (e.code === "KeyX" || e.code === "Digit1" || e.code === "Digit2") {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "swap_hands" });
    } else if (e.code === "KeyZ") {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "use_hand" });
    } else if (e.code === "KeyQ") {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "drop_item" });
    } else if (e.code === "KeyF") {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "throw_item" });
    } else if (e.code === "KeyC") {
      sendAgentCommand({ agentId: state.selectedAgentId, action: "toggle_combat" });
    } else if (e.code === "KeyE") {
      const res = await sendAgentCommand({ agentId: state.selectedAgentId, action: "interact_nearest" });
      if (res.bui) openBuiWindow(res.bui);
    } else if (e.code === "KeyI") {
      document.getElementById("openEquipWindowBtn").click();
    } else if (e.code === "KeyP") {
      document.getElementById("openCrewWindowBtn").click();
    } else if (e.code === "KeyG") {
      setGameMode(state.gameMode === "ghost" ? "play" : "ghost");
    } else if (e.code === "KeyM") {
      state.minimapEnabled = !state.minimapEnabled;
      document.getElementById("minimapBox").classList.toggle("hidden", !state.minimapEnabled);
    } else if (e.code === "KeyT") {
      e.preventDefault();
      document.getElementById("chatChannelPrefix").value = "";
      document.getElementById("directSayInput").focus();
    } else if (e.code === "KeyY") {
      e.preventDefault();
      document.getElementById("chatChannelPrefix").value = ";";
      document.getElementById("directSayInput").focus();
    } else if (e.code === "Escape") {
      openModal("joinModal");
    }
  });

  window.addEventListener("keyup", (e) => {
    state.keysDown.delete(e.code);
  });

  // Crew Inspector & Direct Commands
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
    if (e.key === "Enter") {
      sendSay();
      e.target.blur();
    }
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
  const clickedAgent = (state.live?.agents || []).find((a) => Math.hypot(a.x - wx, a.y - wy) < 0.78);
  if (clickedAgent) {
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
    renderEquipWindow(true);
    return;
  }

  // 2. Check if clicked a floor/table item -> pick it up!
  const clickedFloorItem = state.floorItemsCache.find((fi) => Math.hypot(fi.x - wx, fi.y - wy) < 0.72);
  if (clickedFloorItem && curAg && !curAg.isGhost) {
    await sendAgentCommand({
      agentId: curAg.id,
      action: "pickup_item",
      uid: clickedFloorItem.uid,
    });
    return;
  }

  // 3. Check if clicked a door
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

  // 4. Check if clicked a station machine / locker / vending / bed
  const objs = state.spatial.objects.get(`${tx},${ty}`);
  if (objs && objs.length > 0) {
    const res = await sendAgentCommand({
      agentId: state.selectedAgentId,
      action: "interact",
      uid: objs[0].uid,
    });
    if (res.bui) openBuiWindow(res.bui);
    return;
  }

  // 5. Walk/fly to clicked tile
  if (state.selectedAgentId) {
    state.viewMode = "follow";
    await sendAgentCommand({
      agentId: state.selectedAgentId,
      action: "move_to",
      x: wx,
      y: wy,
    });
  }
}

function setZoom(newZoom) {
  state.zoom = Math.max(0.45, Math.min(3.5, newZoom));
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
    if (data.state.floorItems) rebuildFloorItemsSpatial(data.state.floorItems);
    state.live = data.state;
    renderPlayerHud(false);
    renderInspector(false);
    renderEquipWindow(false);
    renderChatFeed(false);
  }
  return data;
}

async function sendSay() {
  const input = document.getElementById("directSayInput");
  const prefix = document.getElementById("chatChannelPrefix").value || "";
  const raw = input.value.trim();
  if (!raw || !state.selectedAgentId) return;
  input.value = "";
  const text = raw.startsWith(";") || raw.startsWith(":") ? raw : `${prefix}${raw}`;
  const res = await sendAgentCommand({ agentId: state.selectedAgentId, action: "say", text });
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
  runBrowserDirectLlmStep(null);
}

async function testApiConfig() {
  const resBox = document.getElementById("apiTestResult");
  resBox.classList.remove("hidden", "ok", "err");
  resBox.textContent = "⏳ Отправка реального запроса к модели OpenAI API...";

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
    if (data.state.floorItems) rebuildFloorItemsSpatial(data.state.floorItems);
    state.live = data.state;
    state.selectedAgentId = data.agentId;
    state.previousPlayAgentId = data.agentId;
    setGameMode("play");
    document.getElementById("joinModal").classList.add("hidden");
  }
}

window.addEventListener("DOMContentLoaded", initApp);
