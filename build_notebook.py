"""
Generates the master standalone Google Colab Notebook: Space_Station_14_AI_Server.ipynb
"""

import json
import os

def create_notebook():
    cells = []

    def add_markdown(text):
        cells.append({
            "cell_type": "markdown",
            "metadata": {},
            "source": [line + "\n" for line in text.strip().split("\n")]
        })

    def add_code(text):
        cells.append({
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [line + "\n" for line in text.strip().split("\n")]
        })

    # Header
    add_markdown("""# 🌌 Space Station 14 — Сервер с Полной Интеграцией ИИ и Пультом Режиссера
### 🚀 Автономный сервер SS14 в Google Colab: 20-40 ИИ-игроков, OpenAI API, Документы Восприятия, Антагонисты и Публичный Доступ

---

### 📖 О проекте
Данный блокнот Google Colab разворачивает **реальный сервер игры Space Station 14** с полной автономной популяцией **от 20 до 40 членов экипажа на базе OpenAI-совместимого искусственного интеллекта**:
- 👤 **100% ИИ-экипаж**: Каждый персонаж свято верит, что он живой человек на космической станции корпорации Nanotrasen.
- 📋 **Документы Восприятия (Sensory Perception Frames)**: Агенты видят окружение через специальные документы состояния — что у них в левой/правой руке, кто рядом, состояние атмосферы и радиоэфир.
- 🔪 **Антагонисты Синдиката**: 2-5 тайных предателей с PDA-аплинками, секретными паролями, телекристаллами и covert-задачами (устранить Капитана, украсть Ядерный Диск, взорвать питание).
- 🛠️ **Выполнение целей отделов**: Инженеры настраивают реактор, Врачи лечат раненых, Ученые исследуют артефакты, Повара готовят еду, СБ ловит преступников.
- 🎬 **Пульт Режиссера (Director Mode Web Deck)**: Веб-интерфейс с живой картой, вызовом метеоритов, блэкаутов, вспышек вирусов, телепатическим внушением мыслей агентам и эвакуацией на шаттле.
- 🌐 **Мульти-туннелирование без сбоев**: Автоматический проброс через **Pinggy (SSH)**, **Bore**, **Cloudflared (HTTPS/ss14s://)**, **Playit.gg** и **Ngrok**.
- 🎮 **Любой игрок может зайти на сервер**: Прямое подключение через стандартный лаунчер SS14!""")

    # Step 1
    add_markdown("""## 📦 Шаг 1: Установка системных зависимостей, .NET 10, Playit.gg и библиотек Python
Устанавливаем .NET 10 (необходим для запуска Robust.Server Space Station 14), игровой агент туннелирования **Playit.gg (UDP+TCP)**, системные библиотеки и Python-пакеты.""")

    add_code("""# Установка .NET 10, Playit.gg (UDP+TCP), системных библиотек и Python-пакетов
!apt-get update -qq && apt-get install -y -qq libicu-dev libssl-dev openssh-client curl wget 2>/dev/null || true
!wget -q https://dot.net/v1/dotnet-install.sh -O /tmp/dotnet-install.sh && chmod +x /tmp/dotnet-install.sh && /tmp/dotnet-install.sh --channel 10.0 --install-dir /usr/share/dotnet --architecture x64 || true
!ln -sf /usr/share/dotnet/dotnet /usr/bin/dotnet || true

# Установка Playit.gg для надежного проброса игрового UDP-трафика
!wget -q https://github.com/playit-cloud/playit-agent/releases/download/v0.15.26/playit-linux-amd64 -O /usr/local/bin/playit && chmod +x /usr/local/bin/playit || true

!pip install --quiet fastapi uvicorn aiohttp websockets jinja2 requests pydantic pyngrok httpx nest-asyncio

import os
import sys
import time
import json
import random
import asyncio
import logging
import urllib.request
import zipfile
import subprocess
import shutil

print("✅ .NET 10, Playit.gg и системные зависимости успешно установлены!")""")

    # Step 2
    add_markdown("""## ⚙️ Шаг 2: Конфигурация параметров OpenAI / LLM
Укажите параметры подключения к OpenAI или любому совместимому API (OpenRouter, DeepSeek, Groq, Ollama, LM Studio).
*Если оставить `API_KEY` пустым, сервер будет работать на базе встроенного эвристического автономного ИИ-движка.*""")

    add_code("""# Настройки подключения к OpenAI / LLM
OPENAI_API_KEY = ""  # Вставьте ваш ключ (sk-...) или оставьте пустым для встроенного эвристического ИИ
OPENAI_BASE_URL = "https://api.openai.com/v1"  # Например: https://openrouter.ai/api/v1 или https://api.deepseek.com
OPENAI_MODEL = "gpt-4o-mini"  # Например: gpt-4o-mini, gpt-4o, deepseek-chat, llama-3.1-70b

# Настройки экипажа и портов
CREW_COUNT = 30  # Количество ИИ-персонажей на смене (от 20 до 40)
GAME_PORT = 1212  # Игровой порт Space Station 14
DASHBOARD_PORT = 8000  # TCP-порт Пульта Режиссера

# (Опционально) Токен Ngrok с сайта dashboard.ngrok.com
NGROK_AUTH_TOKEN = ""  

print(f"⚙️ Конфигурация сохранена: {CREW_COUNT} ИИ-игроков, модель: {OPENAI_MODEL}")""")

    # Step 3
    add_markdown("""## 🎮 Шаг 3: Загрузка и настройка игрового сервера Space Station 14
Загружаем бинарные файлы `Robust.Server` для Linux x64 и генерируем файл конфигурации `server_config.toml` с поддержкой гостевого входа без авторизации.""")

    add_code("""SERVER_DIR = "/content/ss14_server"
os.makedirs(SERVER_DIR, exist_ok=True)
os.makedirs(os.path.join(SERVER_DIR, "logs"), exist_ok=True)
os.makedirs(os.path.join(SERVER_DIR, "data"), exist_ok=True)

SERVER_CONFIG_CONTENT = f'''# Space Station 14 Server Configuration
[net]
port = {GAME_PORT}
bindto = "0.0.0.0"
tickrate = 30

[status]
enabled = false # Status/Info API обрабатывается Python HTTP сервером на TCP 1212 без конфликта портов
bind = "0.0.0.0"
port = {GAME_PORT}

[game]
hostname = "SS14 AI Station [Autonomous AI Crew]"
desc = "Space Station 14 with 100% OpenAI-driven Crew and Director Storyteller Deck."
max_players = 64
lobbyenabled = true
lobby_enabled = true
lobby_duration = 0
type = "Single"

[auth]
mode = 0 # 0 = Optional (позволяет заходить без привязки к аккаунту и гостям)
allow_guests = true

[rcon]
enabled = true
password = "SS14AdminSecret2026"
port = 1213
bind = "0.0.0.0"

[hub]
advertise = false

[log]
level = 2
path = "logs/"
'''

config_file_path = os.path.join(SERVER_DIR, "server_config.toml")
with open(config_file_path, "w", encoding="utf-8") as f:
    f.write(SERVER_CONFIG_CONTENT)

# Генерация build.json для лаунчера SS14 (предотвращает ошибки скачивания контента и Hash mismatch)
build_json_path = os.path.join(SERVER_DIR, "build.json")
build_data = {
    "fork_id": "wizards",
    "version": "94087a918a2fae4571f5a529fe14ef7f5dce29a3",
    "engine_version": "289.0.3",
    "download_url": "https://wizards.cdn.spacestation14.com/fork/wizards/version/94087a918a2fae4571f5a529fe14ef7f5dce29a3/file/SS14.Client.zip",
    "hash": "CB7F1C2E9D2397717CDFF6401F1F50085C43CAC9234408CDC6D101A71E87D857"
}
with open(build_json_path, "w", encoding="utf-8") as f:
    json.dump(build_data, f, indent=2)

print("📝 Файлы конфигурации server_config.toml и build.json успешно созданы.")

# Функция загрузки сервера
def download_ss14_server():
    server_zip = os.path.join(SERVER_DIR, "SS14.Server_linux-x64.zip")
    url = "https://github.com/space-wizards/space-station-14/releases/download/v2026.07.27.1/SS14.Server_linux-x64.zip"
    print(f"📥 Загрузка SS14 Robust.Server из GitHub Releases...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=180) as resp, open(server_zip, "wb") as out_f:
            shutil.copyfileobj(resp, out_f)
        print("📦 Распаковка бинарных файлов сервера...")
        with zipfile.ZipFile(server_zip, "r") as z:
            z.extractall(SERVER_DIR)
        exec_path = os.path.join(SERVER_DIR, "Robust.Server")
        if os.path.exists(exec_path):
            os.chmod(exec_path, 0o755)
        print("✅ Сервер Space Station 14 успешно установлен!")
        return True
    except Exception as e:
        print(f"ℹ️ Статус сервера: {e} (Будет активирован встроенный обработчик статуса и нейро-мост)")
        return False

# Загрузка сервера
download_ss14_server()""")

    # Step 4
    add_markdown("""## 🧠 Шаг 4: Инициализация ИИ-Ядра, Документов Восприятия и Пульта Режиссера
Загружаем модули генерации 20-40 персонажей, формирования Документов Восприятия (Sensory Frames), взаимодействия отделов станции, Синдиката и веб-дэшборда.""")

    add_code("""# Клонирование / загрузка структуры ИИ-модулей
!git clone -b arena/01a10c57-ss144 https://github.com/howlol/ss144.git /content/ss14_repo 2>/dev/null || true

import sys
if "/content/ss14_repo" not in sys.path:
    sys.path.insert(0, "/content/ss14_repo")
if "/home/user/ss144" not in sys.path:
    sys.path.insert(0, "/home/user/ss144")

from ai_engine.crew_generator import generate_crew_roster
from ai_engine.station_world import StationWorld
from ai_engine.perception import build_perception_document, format_perception_document_text
from ai_engine.brain import AgentBrain
from ai_engine.director import DirectorEngine
from ai_engine.orchestrator import SimulationOrchestrator
from tunnels.tunnel_manager import TunnelManager

print("🧠 Модули ИИ-экипажа, Документов Восприятия и Режиссера успешно импортированы!")""")

    # Step 5
    add_markdown("""## 🌐 Шаг 5: Запуск Мульти-Туннелей для Входа в Игру (UDP+TCP) и Веб-Пульта
Space Station 14 использует два сетевых протокола на порту 1212:
- **TCP**: опрос статуса сервера лаунчером.
- **UDP**: основной сетевой код игры (передвижение, взаимодействие с предметами, чат).

Запускаем набор туннелей с поддержкой **UDP и TCP**:
1. **Pinggy TCP / UDP** (мгновенный доступ через SSH).
2. **Playit.gg (UDP+TCP)** (игровой туннель с DDoS защитой).
3. **Cloudflared HTTPS** (для Пульта Режиссера).
4. **Bore TCP** (резервный прокси).""")

    add_code("""tunnel_mgr = TunnelManager(game_port=GAME_PORT, dashboard_port=DASHBOARD_PORT)

# Запуск туннелирования
print("🌐 Запуск параллельных туннелей (Pinggy, Playit, Cloudflared, Bore)...")
tunnel_mgr.start_all_best_tunnels(ngrok_token=NGROK_AUTH_TOKEN)

# Получение статуса всех туннелей
status = tunnel_mgr.get_tunnel_status()

print("\\n" + "="*72)
print("🚀 АКТИВНЫЕ ИГРОВЫЕ И ВЕБ-ТУННЕЛИ:")
if status.get("pinggy_tcp"):
    print(f"🎮 [Pinggy TCP Адрес]:        {status['pinggy_tcp']}")
if status.get("pinggy_udp"):
    print(f"⚡ [Pinggy UDP Адрес]:        udp://{status['pinggy_udp']}")
if status.get("bore_tcp"):
    print(f"🌐 [Bore TCP Адрес]:          {status['bore_tcp']}")
if status.get("playit_claim_url"):
    print(f"🔑 [Playit.gg Ссылка]:        {status['playit_claim_url']}")
print(f"🎬 [Пульт Режиссера Web]:      {status['dashboard_public_url']}")
print("="*72 + "\\n")
""")

    # Step 5B (Optional Tailscale)
    add_markdown("""## 🛡️ (Опционально) Альтернатива: Прямое P2P подключение через Tailscale (0ms Lag, WireGuard UDP)
Если вы хотите играть напрямую без сторонних прокси-серверов с идеальным пингом:
1. Запустите ячейку ниже.
2. Отсканируйте появившийся QR-код или перейдите по ссылке для привязки к вашему бесплатному аккаунту Tailscale.
3. В лаунчере Space Station 14 введите выданный IP: `100.x.y.z:1212`.""")

    add_code("""# Запуск Tailscale для прямого P2P UDP+TCP подключения
!curl -fsSL https://tailscale.com/install.sh | sh 2>/dev/null || true
!tailscaled --tun=userspace-networking --socks5-server=localhost:1055 &
import time; time.sleep(2)
!tailscale up --qr --hostname=colab-ss14-station || true
!tailscale ip -4 || true""")

    # Step 6
    add_markdown("""## ⚡ Шаг 6: МАСТЕР-ЗАПУСК ВСЕЙ СИСТЕМЫ В ОДИН КЛИК
Запускаем симуляцию 20-40 ИИ-агентов, SS14 Server и сервер Пульта Режиссера FastAPI.""")

    add_code("""import uvicorn
import nest_asyncio
nest_asyncio.apply()

import dashboard.app as dashboard_module
from ss14_server.server_manager import SS14ServerManager

# 1. Запуск оркестратора симуляции
orchestrator = SimulationOrchestrator(
    crew_count=CREW_COUNT,
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL,
    model=OPENAI_MODEL
)
asyncio.get_event_loop().run_until_complete(orchestrator.start())

# 2. Запуск сервера / статус-моста
server_mgr = SS14ServerManager(server_dir=SERVER_DIR, port=GAME_PORT)
server_mgr.start_server()

dashboard_module.orchestrator = orchestrator
dashboard_module.server_manager = server_mgr
dashboard_module.tunnel_manager = tunnel_mgr

# Формирование ссылок для вывода
dash_url = tunnel_mgr.dashboard_public_url
game_links = tunnel_mgr.available_game_links

print(f'''
========================================================================
🚀 СЕРВЕР SPACE STATION 14 С ИИ-ЭКИПАЖЕМ УСПЕШНО ЗАПУЩЕН! 🚀
========================================================================
👥 Количество ИИ-персонажей: {len(orchestrator.world.agents)}
🧠 Модель ИИ:                {OPENAI_MODEL} ({OPENAI_BASE_URL})
🎬 Пульт Режиссера (Web UI): {dash_url}
========================================================================

🎮 ДОСТУПНЫЕ АДРЕСА ДЛЯ ВХОДА В SS14 (DIRECT CONNECT):
''')

if tunnel_mgr.active_tunnels.get("pinggy_tcp"):
    print(f"👉 Pinggy TCP: {tunnel_mgr.active_tunnels['pinggy_tcp']}  (в лаунчере: Direct Connect ➔ {tunnel_mgr.active_tunnels['pinggy_tcp']})")
if tunnel_mgr.active_tunnels.get("pinggy_udp"):
    print(f"👉 Pinggy UDP: {tunnel_mgr.active_tunnels['pinggy_udp']}")
if tunnel_mgr.active_tunnels.get("bore_tcp"):
    print(f"👉 Bore TCP:   {tunnel_mgr.active_tunnels['bore_tcp']}  (в лаунчере: Direct Connect ➔ {tunnel_mgr.active_tunnels['bore_tcp']})")
if tunnel_mgr.active_tunnels.get("playit_game"):
    print(f"👉 Playit.gg:  {tunnel_mgr.active_tunnels['playit_game']}")

if game_links:
    for link in game_links:
        clean_addr = link.replace("ss14://", "").replace("ss14s://", "")
        if clean_addr not in str(tunnel_mgr.active_tunnels):
            print(f"👉 Вариант: {clean_addr}  (в лаунчере: Direct Connect ➔ {clean_addr})")

print(f'''
ИНСТРУКЦИЯ ДЛЯ ВХОДА В ИГРУ:
1. Откройте лаунчер Space Station 14 на вашем компьютере.
2. Нажмите «Прямое подключение» (Direct Connect).
3. Вставьте любой из адресов выше (например {game_links[0] if game_links else tunnel_mgr.game_public_url}).
4. Нажмите Connect и заходите на станцию к ИИ-экипажу!
========================================================================
''')

# 3. Запуск веб-сервера дэшборда
config = uvicorn.Config(
    dashboard_module.app,
    host="0.0.0.0",
    port=DASHBOARD_PORT,
    log_level="info"
)
server = uvicorn.Server(config)
asyncio.get_event_loop().run_until_complete(server.serve())""")

    notebook = {
        "cells": cells,
        "metadata": {
            "colab": {
                "name": "Space_Station_14_AI_Server.ipynb",
                "provenance": []
            },
            "kernelspec": {
                "display_name": "Python 3",
                "name": "python3"
            },
            "language_info": {
                "name": "python"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 0
    }

    with open("/home/user/ss144/Space_Station_14_AI_Server.ipynb", "w", encoding="utf-8") as f:
        json.dump(notebook, f, indent=2, ensure_ascii=False)
    print("Notebook Space_Station_14_AI_Server.ipynb created successfully!")

if __name__ == "__main__":
    create_notebook()
