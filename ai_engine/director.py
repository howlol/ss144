"""
Space Station 14 Director Mode & AI Storyteller Engine
Allows real-time human control, telepathic suggestions, disaster injection,
and dynamic drama pacing across the entire space station.
"""

import time
import random
from typing import Dict, Any, List, Optional

EVENTS_CATALOG = [
    {
        "id": "power_failure",
        "name": "Авария на Электросети (Power Outage)",
        "description": "Перегрузка в энергосети вызывает отключение освещения и обесточивание шлюзов в нескольких отсеках.",
        "severity": "Medium",
        "action": "cut_power"
    },
    {
        "id": "meteor_shower",
        "name": "Метеоритный Дождь (Meteor Storm)",
        "description": "Рой микрометеоритов пробивает обшивку станции в технических туннелях и грузовом терминале.",
        "severity": "High",
        "action": "meteor_strike"
    },
    {
        "id": "solar_flare",
        "name": "Солнечная Вспышка (Solar Flare)",
        "description": "Ионизирующее излучение временно глушит радиосвязь и вызывает помехи на станционных частотах.",
        "severity": "Medium",
        "action": "radio_jam"
    },
    {
        "id": "virus_outbreak",
        "name": "Вспышка Вируса 'Космический Грипп' (Biohazard Outbreak)",
        "description": "Неизвестный патоген заражает нескольких членов экипажа, вызывая чихание, слабость и дезориентацию.",
        "severity": "High",
        "action": "infect_crew"
    },
    {
        "id": "clown_rebellion",
        "name": "Хонк-Апокалипсис (Clown & Mime Festival)",
        "description": "Клоун и мим получают сверхъестественное вдохновение и устраивают масштабный розыгрыш на всей станции.",
        "severity": "Low",
        "action": "clown_event"
    },
    {
        "id": "syndicate_incursion",
        "name": "Активация Кодов Синдиката (Syndicate High Alert)",
        "description": "Центральное командование перехватывает зашифрованные передачи Синдиката. Спящие агенты получают срочные приказы.",
        "severity": "Critical",
        "action": "syndicate_alert"
    },
    {
        "id": "anomaly_spawn",
        "name": "Гравитационная Аномалия (Spatial Anomaly)",
        "description": "В научном крыле материализуется пульсирующий артефакт, изменяющий гравитацию вокруг себя.",
        "severity": "Medium",
        "action": "spawn_anomaly"
    }
]

class DirectorEngine:
    def __init__(self, world: Any):
        self.world = world
        self.storyteller_mode = "Nanotrasen High Command"  # 'High Command', 'Randy Chaos', 'Suspense'
        self.auto_events_enabled = True
        self.last_event_time = time.time()
        self.event_cooldown = 120  # seconds between auto events
        self.director_log: List[Dict[str, Any]] = []

    def get_events_catalog(self) -> List[Dict[str, Any]]:
        return EVENTS_CATALOG

    def trigger_event(self, event_id: str, trigger_source: str = "Director") -> Dict[str, Any]:
        """Triggers a specific station disaster or special event."""
        event_def = next((e for e in EVENTS_CATALOG if e["id"] == event_id), None)
        if not event_def:
            return {"success": False, "message": f"Событие {event_id} не найдено."}

        action = event_def["action"]
        detail = ""

        if action == "cut_power":
            self.world.station_metrics["grid_stability_pct"] = max(15, self.world.station_metrics["grid_stability_pct"] - 50)
            self.world.broadcast_announcement(
                "Engineering Control Center",
                "⚠️ ВНИМАНИЕ: Критическое падение напряжения в главной магистрали! Аварийные генераторы активированы.",
                alert_type="Disaster"
            )
            detail = "Сброс напряжения сети до 15%."

        elif action == "meteor_strike":
            target_rooms = ["Maintenance Tunnels (Технические туннели)", "Cargo Bay (Грузовой терминал)"]
            for r_name in target_rooms:
                if r_name in self.world.rooms:
                    self.world.rooms[r_name]["breached"] = True
                    self.world.rooms[r_name]["pressure_kpa"] = 12.0
            self.world.broadcast_announcement(
                "Station Automated Sensors",
                "🚨 КРИТИЧЕСКАЯ ТРЕВОГА: Обнаружены множественные пробоины корпуса! Падение давления в Карго и Туннелях!",
                alert_type="Disaster"
            )
            self.world.set_alert_level("Red (Красный - Чрезвычайная ситуация)", "Метеоритный удар.")
            detail = "Разгерметизация отсеков Карго и Туннелей."

        elif action == "radio_jam":
            self.world.broadcast_announcement(
                "Telecommunications Array",
                "⚡ ВНИМАНИЕ: Прохождение фронта солнечной радиации. Наблюдаются сильные помехи в радиоэфире.",
                alert_type="Warning"
            )
            detail = "Помехи в радиосети."

        elif action == "infect_crew":
            # Infect 2-4 crew members with high stress / symptoms
            living = [a for a in self.world.agents.values() if a["vitals"]["is_alive"]]
            infected = random.sample(living, min(3, len(living)))
            names = []
            for agent in infected:
                agent["mental_state"]["stress_level"] = min(100, agent["mental_state"]["stress_level"] + 40)
                agent["vitals"]["toxin_damage"] += 20
                agent["mental_state"]["internal_thoughts"] = "У меня жар, голова кружится, не могу перестать кашлять..."
                names.append(agent["name"])
            self.world.broadcast_announcement(
                "Chief Medical Officer",
                "☣️ БИОЛОГИЧЕСКАЯ ОПАСНОСТЬ: В медблоке зарегистрированы симптомы патогена. Всем соблюдать масочный режим!",
                alert_type="Biohazard"
            )
            detail = f"Заражены: {', '.join(names)}"

        elif action == "clown_event":
            self.world.broadcast_announcement(
                "Station Intercom [HonkNet]",
                "🎉 ХООООООНК! Добро пожаловать на Большой Фестиваль Банановой Радости! Пироги для всех бесплатно!",
                alert_type="Entertainment"
            )
            for a in self.world.agents.values():
                if a["role"] == "Clown":
                    a["hands"]["right_hand"] = "Mega Horn of Ultimate Honk"
                    a["hands"]["left_hand"] = "Super Slippery Banana Cream Pie"
            detail = "Праздник Хонка активирован."

        elif action == "syndicate_alert":
            self.world.broadcast_radio(
                "Syndicate Encrypted [???]",
                "Syndicate High Command",
                "🔴 [ШИФРОГРАММА АГЕНТАМ]: Время пришло. Приступайте к выполнению главных задач. Награда удвоена."
            )
            self.world.set_alert_level("Blue (Синий - Повышенная готовность)", "Подозрение на диверсию.")
            detail = "Активация агентов Синдиката."

        elif action == "spawn_anomaly":
            if "R&D Research Core (Научная Лаборатория)" in self.world.rooms:
                self.world.rooms["R&D Research Core (Научная Лаборатория)"]["items"].append("Gravitational Anomaly Core")
            self.world.broadcast_announcement(
                "Research Director",
                "🌌 НАУЧНЫЙ ОТДЕЛ: Зафиксировано возникновение пространственно-временной аномалии! Ученым приступить к изучению.",
                alert_type="Science"
            )
            detail = "Аномалия заспавнена в РнД."

        log_item = {
            "time": time.time(),
            "formatted_time": time.strftime("%H:%M:%S"),
            "event_id": event_id,
            "event_name": event_def["name"],
            "source": trigger_source,
            "detail": detail
        }
        self.director_log.append(log_item)
        self.last_event_time = time.time()

        return {"success": True, "event": event_def, "detail": detail}

    def inject_subconscious_whisper(self, agent_id: str, whisper_text: str, source: str = "Director"):
        """Injects a direct thought / subconscious whisper into an AI agent's brain."""
        agent = self.world.agents.get(agent_id)
        if not agent:
            return {"success": False, "message": "Агент не найден."}

        formatted_thought = f"💭 [Внутренний Голос / Интуиция]: {whisper_text}"
        agent["mental_state"]["internal_thoughts"] = formatted_thought
        agent["mental_state"]["recent_memories"].append(f"В голове прозвучала четкая мысль: «{whisper_text}»")
        agent["mental_state"]["stress_level"] = min(100, agent["mental_state"]["stress_level"] + 10)

        log_item = {
            "time": time.time(),
            "formatted_time": time.strftime("%H:%M:%S"),
            "event_id": "whisper_injection",
            "event_name": f"Внушение: {agent['name']}",
            "source": source,
            "detail": whisper_text
        }
        self.director_log.append(log_item)

        return {"success": True, "agent_name": agent["name"], "thought": formatted_thought}

    def update_auto_director(self):
        """Paces drama automatically if enabled."""
        if not self.auto_events_enabled:
            return
        now = time.time()
        if now - self.last_event_time > self.event_cooldown:
            # Pick a random event based on storytelling mode
            event = random.choice(EVENTS_CATALOG)
            self.trigger_event(event["id"], trigger_source=f"AutoStoryteller ({self.storyteller_mode})")
