/**
 * Space Station 14 AI Director Dashboard Client
 * Real-time WebSocket synchronizer, Agent Inspector, and Storyteller Controls
 */

let state = null;
let currentTab = 'tab-roster';
let activeRadioFilter = 'ALL';
let selectedRoomName = null;
let ws = null;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  initWebSocket();
  fetchInitialState();
  // Fallback polling in case WebSocket drops
  setInterval(fetchInitialState, 4000);
});

function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;
  
  ws = new WebSocket(wsUrl);
  
  ws.onopen = () => {
    console.log('[SS14 Deck] WebSocket connected.');
  };
  
  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'state_update') {
        state = msg.data;
        renderDashboard();
      }
    } catch (e) {
      console.error('Error parsing WebSocket message:', e);
    }
  };
  
  ws.onclose = () => {
    console.warn('[SS14 Deck] WebSocket closed, retrying in 3s...');
    setTimeout(initWebSocket, 3000);
  };
}

async function fetchInitialState() {
  try {
    const res = await fetch('/api/status');
    if (res.ok) {
      state = await res.json();
      renderDashboard();
    }
  } catch (e) {
    console.error('Fetch status error:', e);
  }
}

function renderDashboard() {
  if (!state) return;

  // 1. Header Status Bar
  document.getElementById('station-name-display').innerText = state.station_name || 'SPACE STATION 14';
  
  // Alert banner
  const alertEl = document.getElementById('alert-banner');
  const alertText = document.getElementById('alert-level-text');
  const alertLvl = state.alert_level || 'Green';
  alertText.innerText = alertLvl.toUpperCase();
  
  alertEl.className = 'alert-indicator-box';
  if (alertLvl.includes('Green')) alertEl.classList.add('alert-green');
  else if (alertLvl.includes('Blue')) alertEl.classList.add('alert-blue');
  else if (alertLvl.includes('Red')) alertEl.classList.add('alert-red');
  else if (alertLvl.includes('Delta')) alertEl.classList.add('alert-delta');

  // Top stats
  document.getElementById('crew-count-display').innerText = `${state.living_crew || 0} / ${state.total_crew || 0}`;
  
  const shuttle = state.emergency_shuttle || {};
  let shuttleText = 'Ожидание';
  if (shuttle.status === 'InTransit') shuttleText = `В пути (${Math.round(shuttle.eta_seconds)}с)`;
  else if (shuttle.status === 'Docked') shuttleText = '🚨 ПРИСТЫКОВАН';
  document.getElementById('shuttle-status-display').innerText = shuttleText;

  const power = state.metrics ? state.metrics.grid_stability_pct : 100;
  document.getElementById('power-status-display').innerText = `${power}%`;

  // Connect link banner
  const connectUri = (state.tunnel_status && state.tunnel_status.ss14_connect_link) 
    ? state.tunnel_status.ss14_connect_link 
    : (state.server_status ? state.server_status.connect_uri : 'ss14://127.0.0.1:1212');
  
  document.getElementById('connect-url-display').innerText = connectUri;
  const guideConnectUrl = document.getElementById('guide-connect-url');
  if (guideConnectUrl) guideConnectUrl.innerText = connectUri;

  // Render active tab contents
  if (currentTab === 'tab-roster') renderRoster();
  else if (currentTab === 'tab-map') renderMap();
  else if (currentTab === 'tab-director') renderDirectorDeck();
  else if (currentTab === 'tab-radio') renderRadioFeed();
}

function switchTab(tabId) {
  currentTab = tabId;
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

  event.currentTarget.classList.add('active');
  const targetPane = document.getElementById(tabId);
  if (targetPane) targetPane.classList.add('active');

  renderDashboard();
}

// ================= TAB 1: CREW ROSTER ================= //

function renderRoster() {
  const container = document.getElementById('crew-grid-container');
  if (!container || !state || !state.agents) return;

  const search = (document.getElementById('roster-search').value || '').toLowerCase();
  const deptFilter = document.getElementById('roster-dept-filter').value;

  const filtered = state.agents.filter(agent => {
    // Dept / Antag filter
    if (deptFilter === 'ANTAG' && !agent.is_antagonist) return false;
    if (deptFilter !== 'ALL' && deptFilter !== 'ANTAG') {
      const room = state.rooms[agent.location];
      const dept = room ? room.dept : '';
      if (!agent.role.includes(deptFilter) && dept !== deptFilter) return false;
    }

    // Text search
    if (search) {
      const matchName = agent.name.toLowerCase().includes(search);
      const matchRole = agent.role.toLowerCase().includes(search);
      const matchTitle = (agent.title || '').toLowerCase().includes(search);
      const matchLoc = (agent.location || '').toLowerCase().includes(search);
      if (!matchName && !matchRole && !matchTitle && !matchLoc) return false;
    }
    return true;
  });

  container.innerHTML = filtered.map(agent => {
    const isAntag = agent.is_antagonist;
    const hp = agent.vitals.health;
    let hpClass = '';
    if (hp < 30) hpClass = 'critical';
    else if (hp < 70) hpClass = 'damaged';

    const antagBadge = isAntag ? `<span class="agent-role-badge" style="background:#b71c1c; color:#fff;">🔴 СИНДИКАТ (${agent.antagonist.title})</span>` : '';

    return `
      <div class="agent-card ${isAntag ? 'card-antag' : ''}">
        <div class="agent-card-header">
          <div>
            <div class="agent-name">${agent.name} <small style="color:var(--text-muted);">[${agent.species}]</small></div>
            <div class="agent-location-row mt-2">
              <span class="location-pin">📍</span>
              <span>${agent.location}</span>
            </div>
          </div>
          <div>
            <span class="agent-role-badge">${agent.title || agent.role}</span>
            ${antagBadge}
          </div>
        </div>

        <div class="health-bar-container">
          <span style="font-size:10px; font-weight:700;">HP:</span>
          <div class="health-bar-bg">
            <div class="health-bar-fill ${hpClass}" style="width: ${Math.max(0, hp)}%;"></div>
          </div>
          <span class="health-val">${hp}/100</span>
        </div>

        <div class="hands-box">
          <div class="hands-row">
            <span>✋ Лев. рука:</span>
            <span class="hands-item-name">${agent.hands.left_hand}</span>
          </div>
          <div class="hands-row mt-2">
            <span>🤚 Прав. рука:</span>
            <span class="hands-item-name">${agent.hands.right_hand}</span>
          </div>
        </div>

        <div class="agent-thought-snippet">
          "${agent.mental_state.internal_thoughts || 'Выполняю служебные обязанности...'}"
        </div>

        <div class="agent-actions">
          <button class="btn btn-primary btn-sm" onclick="openPerceptionModal('${agent.id}')">🔍 Документ Восприятия</button>
          <button class="btn btn-secondary btn-sm" onclick="quickWhisperModal('${agent.id}', '${agent.name}')">💭 Внушить</button>
          <button class="btn btn-secondary btn-sm" onclick="quickHealAgent('${agent.id}')">❤️ Лечить</button>
        </div>
      </div>
    `;
  }).join('');
}

function filterRoster() {
  renderRoster();
}

// ================= TAB 2: STATION MAP ================= //

function renderMap() {
  const container = document.getElementById('station-map-grid');
  if (!container || !state || !state.rooms) return;

  const roomNames = Object.keys(state.rooms);
  container.innerHTML = roomNames.map(rName => {
    const room = state.rooms[rName];
    const occupants = (state.agents || []).filter(a => a.location === rName && a.vitals.is_alive);
    const isSelected = selectedRoomName === rName;

    return `
      <div class="room-card ${room.breached ? 'breached' : ''} ${isSelected ? 'selected' : ''}" onclick="selectRoom('${rName.replace(/'/g, "\\'")}')">
        <div class="room-name-header">${rName}</div>
        <div>
          <span class="room-badge-dept">${room.dept}</span>
          ${room.breached ? '<span class="room-badge-dept" style="background:#b71c1c; color:#fff;">⚠️ ВАКУУМ</span>' : ''}
        </div>
        <div class="room-occupants-badge">
          👥 ${occupants.length} человек
        </div>
      </div>
    `;
  }).join('');

  if (selectedRoomName) {
    renderRoomDetail(selectedRoomName);
  }
}

function selectRoom(rName) {
  selectedRoomName = rName;
  renderMap();
  renderRoomDetail(rName);
}

function renderRoomDetail(rName) {
  const detailContainer = document.getElementById('room-detail-content');
  if (!detailContainer || !state.rooms[rName]) return;

  const room = state.rooms[rName];
  const occupants = (state.agents || []).filter(a => a.location === rName && a.vitals.is_alive);

  detailContainer.innerHTML = `
    <h4 style="color:var(--nt-cyan); font-size:15px; margin-bottom:8px;">${rName}</h4>
    <div style="font-size:12px; display:flex; flex-direction:column; gap:6px;">
      <div><strong>Отдел:</strong> ${room.dept}</div>
      <div><strong>Давление:</strong> ${room.pressure_kpa} kPa</div>
      <div><strong>Температура:</strong> ${room.temperature_k} K</div>
      <div><strong>Питание:</strong> ${room.powered ? 'ВКЛЮЧЕНО' : 'ОБЕСТОЧЕНО'}</div>
      <div><strong>Оборудование:</strong> ${room.items.join(', ')}</div>
      <div><strong>Связанные шлюзы:</strong> ${room.connections.join(' ↔ ')}</div>
      
      <hr class="divider">
      <div style="margin-top:4px;"><strong>Присутствующие (${occupants.length}):</strong></div>
      ${occupants.map(o => `
        <div style="padding:4px 8px; background:rgba(0,0,0,0.2); border-radius:3px; margin-top:2px;">
          <strong>${o.name}</strong> (${o.role}) — HP: ${o.vitals.health}%
        </div>
      `).join('') || '<div class="text-muted">Никого нет</div>'}
    </div>
  `;
}

// ================= TAB 3: DIRECTOR DECK ================= //

function renderDirectorDeck() {
  // Populate event buttons
  const eventsContainer = document.getElementById('events-buttons-container');
  if (eventsContainer && state.events_catalog) {
    eventsContainer.innerHTML = state.events_catalog.map(ev => `
      <button class="btn-event" onclick="triggerEvent('${ev.id}')">
        <strong>${ev.name}</strong>
        <span>${ev.description}</span>
      </button>
    `).join('');
  }

  // Populate whisper agent selector
  const whisperSelect = document.getElementById('whisper-agent-select');
  if (whisperSelect && state.agents && whisperSelect.options.length <= 1) {
    whisperSelect.innerHTML = '<option value="">-- Выберите персонажа --</option>' +
      state.agents.map(a => `<option value="${a.id}">${a.name} (${a.role})</option>`).join('');
  }

  // Populate director log stream
  const logStream = document.getElementById('director-log-stream');
  if (logStream && state.director_log) {
    logStream.innerHTML = state.director_log.map(item => `
      <div class="log-stream-entry">
        <span style="color:var(--text-muted);">[${item.formatted_time}]</span>
        <strong style="color:var(--nt-cyan);">${item.event_name}</strong>: ${item.detail} (${item.source})
      </div>
    `).join('');
  }
}

async function triggerEvent(eventId) {
  try {
    const res = await fetch('/api/action/trigger_event', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ event_id: eventId })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`⚡ Событие активировано: ${data.event.name}`);
    }
  } catch (e) {
    showToast('Ошибка запуска события');
  }
}

async function setStationAlert(level, reason) {
  try {
    const res = await fetch('/api/action/set_alert', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ level, reason })
    });
    if (res.ok) {
      showToast(`Код тревоги изменен на: ${level}`);
    }
  } catch (e) {
    showToast('Ошибка изменения кода тревоги');
  }
}

async function callShuttle() {
  try {
    const res = await fetch('/api/action/shuttle/call', { method: 'POST' });
    const data = await res.json();
    showToast(data.message);
  } catch (e) {
    showToast('Ошибка вызова шаттла');
  }
}

async function recallShuttle() {
  try {
    const res = await fetch('/api/action/shuttle/recall', { method: 'POST' });
    const data = await res.json();
    showToast(data.message);
  } catch (e) {
    showToast('Ошибка отзыва шаттла');
  }
}

async function sendSubconsciousWhisper() {
  const agentId = document.getElementById('whisper-agent-select').value;
  const text = document.getElementById('whisper-input').value.trim();

  if (!agentId || !text) {
    showToast('Выберите персонажа и введите текст мысли!');
    return;
  }

  try {
    const res = await fetch('/api/action/whisper', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ agent_id: agentId, whisper_text: text })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`🧠 Мысль внушена: ${data.agent_name}`);
      document.getElementById('whisper-input').value = '';
    }
  } catch (e) {
    showToast('Ошибка телепатического внушения');
  }
}

async function startNewRound() {
  const count = parseInt(document.getElementById('crew-count-slider').value) || 30;
  if (!confirm(`Сгенерировать новый раунд с ${count} уникальными ИИ-персонажами?`)) return;

  try {
    const res = await fetch('/api/action/new_round', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ crew_count: count })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message);
      // Reset select
      document.getElementById('whisper-agent-select').innerHTML = '';
      fetchInitialState();
    }
  } catch (e) {
    showToast('Ошибка запуска раунда');
  }
}

// ================= TAB 4: RADIO FEED ================= //

function filterRadioChannel(channel) {
  activeRadioFilter = channel;
  document.querySelectorAll('.btn-channel').forEach(b => b.classList.remove('active'));
  event.currentTarget.classList.add('active');
  renderRadioFeed();
}

function renderRadioFeed() {
  const container = document.getElementById('radio-feed-container');
  if (!container || !state || !state.recent_radio) return;

  const logs = state.recent_radio;
  const filtered = logs.filter(item => {
    if (activeRadioFilter === 'ALL') return true;
    return item.channel === activeRadioFilter;
  });

  container.innerHTML = filtered.map(item => {
    const isSyndie = item.channel.includes('Syndicate');
    return `
      <div class="radio-message-bubble ${isSyndie ? 'channel-syndie' : ''}">
        <div class="radio-msg-meta">
          <span class="radio-sender">${item.sender}</span>
          <span>[${item.channel}] • ${item.formatted_time || ''}</span>
        </div>
        <div>${item.message}</div>
      </div>
    `;
  }).join('');

  // Scroll to bottom
  container.scrollTop = container.scrollHeight;
}

// ================= TAB 5: LLM SETTINGS ================= //

async function saveLLMConfig() {
  const key = document.getElementById('llm-api-key').value;
  const url = document.getElementById('llm-base-url').value;
  const model = document.getElementById('llm-model').value;

  try {
    const res = await fetch('/api/config/llm', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ api_key: key, base_url: url, model: model })
    });
    const data = await res.json();
    if (data.success) {
      showToast('Настройки OpenAI успешно сохранены!');
      document.getElementById('llm-save-status').innerText = '✅ Сохранено';
    }
  } catch (e) {
    showToast('Ошибка сохранения настроек');
  }
}

// ================= PERCEPTION MODAL ================= //

async function openPerceptionModal(agentId) {
  try {
    const res = await fetch(`/api/agent/${agentId}/perception`);
    if (res.ok) {
      const data = await res.json();
      document.getElementById('perception-text-content').innerText = data.document_text;
      document.getElementById('perception-json-content').innerText = JSON.stringify(data.document_json, null, 2);
      document.getElementById('perception-modal-title').innerText = `ДОКУМЕНТ ВОСПРИЯТИЯ: ${data.document_json.identity.name} (${data.document_json.identity.title})`;
      document.getElementById('perception-modal').style.display = 'flex';
      togglePerceptionView('formatted');
    }
  } catch (e) {
    showToast('Ошибка загрузки документа восприятия');
  }
}

function closePerceptionModal() {
  document.getElementById('perception-modal').style.display = 'none';
}

function togglePerceptionView(mode) {
  const textEl = document.getElementById('perception-text-content');
  const jsonEl = document.getElementById('perception-json-content');
  const btnFmt = document.getElementById('btn-view-formatted');
  const btnJson = document.getElementById('btn-view-json');

  if (mode === 'formatted') {
    textEl.style.display = 'block';
    jsonEl.style.display = 'none';
    btnFmt.classList.add('active');
    btnJson.classList.remove('active');
  } else {
    textEl.style.display = 'none';
    jsonEl.style.display = 'block';
    btnFmt.classList.remove('active');
    btnJson.classList.add('active');
  }
}

// Quick action helpers
async function quickHealAgent(agentId) {
  try {
    const res = await fetch(`/api/agent/${agentId}/heal`, { method: 'POST' });
    const data = await res.json();
    showToast(data.message || 'Агент исцелен');
  } catch (e) {
    showToast('Ошибка исцеления');
  }
}

function quickWhisperModal(agentId, agentName) {
  switchTab('tab-director');
  const select = document.getElementById('whisper-agent-select');
  if (select) select.value = agentId;
  const input = document.getElementById('whisper-input');
  if (input) {
    input.focus();
    input.placeholder = `Внушите мысль персонажу ${agentName}...`;
  }
}

function copyConnectLink() {
  const text = document.getElementById('connect-url-display').innerText;
  navigator.clipboard.writeText(text);
  showToast('📋 Адрес сервера скопирован в буфер обмена!');
}

function showConnectGuideModal() {
  document.getElementById('connect-guide-modal').style.display = 'flex';
}

function closeConnectGuideModal() {
  document.getElementById('connect-guide-modal').style.display = 'none';
}

function showToast(msg) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerText = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 4000);
}
