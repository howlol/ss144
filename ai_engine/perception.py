"""
Space Station 14 Sensory & Perception Engine
Builds structured Perception Documents ("Специальные Документы Восприятия")
giving AI agents rich real-time awareness of their body, hands, surroundings,
nearby crew members, radio chatter, and station alerts.
"""

from typing import Dict, Any, List

def build_perception_document(agent: Dict[str, Any], world: Any) -> Dict[str, Any]:
    """
    Constructs a comprehensive perception document for an AI crew member.
    This document serves as the agent's sensory reality of the SS14 game world.
    """
    room_name = agent.get("location", "Main Hallway (Главный коридор станции)")
    room_data = world.rooms.get(room_name, {})
    
    # Other people in the same room
    other_agents = [
        a for a in world.get_room_agents(room_name)
        if a["id"] != agent["id"]
    ]
    
    nearby_people = []
    for other in other_agents:
        lh = other.get("hands", {}).get("left_hand", "Empty")
        rh = other.get("hands", {}).get("right_hand", "Empty")
        vitals = other.get("vitals", {})
        health_stat = "Здоров" if vitals.get("health", 100) > 80 else ("Ранен" if vitals.get("health", 100) > 30 else "Тяжело ранен")
        
        nearby_people.append({
            "name": other["name"],
            "role": other["role"],
            "species": other.get("species", "Human"),
            "health_status": health_stat,
            "holding": f"В левой руке: {lh}, в правой руке: {rh}",
            "uniform": other.get("inventory", {}).get("suit", "Uniform"),
            "is_conscious": vitals.get("is_conscious", True)
        })

    # Relevant radio logs from the last few messages
    agent_channels = agent.get("radio_channels", ["Common [145.9]"])
    recent_radio = [
        f"[{r['channel']}] {r['sender']}: {r['message']}"
        for r in world.radio_logs[-12:]
        if r.get("channel") in agent_channels
    ]

    # Recent announcements
    recent_announcements = [
        f"📢 [{a['sender']}]: {a['message']}"
        for a in world.announcements[-3:]
    ]

    # Shuttle status
    shuttle = world.emergency_shuttle
    shuttle_text = "Не вызван"
    if shuttle["status"] == "InTransit":
        shuttle_text = f"В пути! Прибытие через {int(shuttle['eta_seconds'])} сек. в Шлюз Эвакуации"
    elif shuttle["status"] == "Docked":
        shuttle_text = "ПРИСТЫКОВАН! Идет посадка экипажа!"

    # Syndicate covert payload
    syndicate_dossier = None
    if agent.get("is_antagonist") and agent.get("antagonist"):
        antag = agent["antagonist"]
        syndicate_dossier = {
            "role_title": antag["title"],
            "description": antag["description"],
            "syndicate_codeword": antag["syndicate_code"],
            "uplink_frequency": antag["uplink_code"],
            "telecrystals": antag.get("telecrystals", 20),
            "covert_objectives": antag["objectives"],
            "completed_objectives": antag.get("completed_objectives", []),
            "tactical_advice": "Действуйте скрытно. Поддерживайте видимость честного сотрудника Nanotrasen. Используйте технические туннели и рации для координации или дезинформации."
        }

    doc = {
        "document_type": "SS14_SENSORY_PERCEPTION_FRAME",
        "station_name": world.station_name,
        "station_alert_level": world.alert_level,
        "shuttle_status": shuttle_text,
        "identity": {
            "name": agent["name"],
            "gender": agent["gender"],
            "species": agent["species"],
            "species_traits": agent.get("species_desc", ""),
            "role": agent["role"],
            "title": agent["title"],
            "security_clearance": agent["access_level"],
            "personality_traits": agent["personality"],
            "speech_mannerism": agent["speech_pattern"],
            "absolute_belief": "Вы — настоящий живой человек (или представитель выбранной расы) на борту Space Station 14. Вы глубоко погружены в жизнь станции и выполняете свои обязанности."
        },
        "physical_embodiment": {
            "left_hand": agent["hands"].get("left_hand", "Empty"),
            "right_hand": agent["hands"].get("right_hand", "Empty"),
            "id_card_slot": agent["inventory"].get("id_card"),
            "pda_slot": agent["inventory"].get("pda"),
            "headset_slot": agent["inventory"].get("headset"),
            "suit_slot": agent["inventory"].get("suit"),
            "belt_slot": agent["inventory"].get("belt"),
            "back_slot": agent["inventory"].get("back"),
            "pocket1": agent["inventory"].get("pocket1"),
            "pocket2": agent["inventory"].get("pocket2"),
        },
        "vitals_and_health": {
            "health_points": f"{agent['vitals']['health']}/100",
            "brute_trauma": agent["vitals"]["brute_damage"],
            "burn_damage": agent["vitals"]["burn_damage"],
            "toxin_damage": agent["vitals"]["toxin_damage"],
            "suffocation": agent["vitals"]["suffocation_damage"],
            "stamina": agent["vitals"]["stamina"],
            "overall_condition": agent["vitals"]["status_text"]
        },
        "current_environment": {
            "room_name": room_name,
            "department": room_data.get("dept", "Public"),
            "atmospheric_pressure": f"{room_data.get('pressure_kpa', 101.3)} kPa (Норма: 101.3 kPa)",
            "temperature": f"{room_data.get('temperature_k', 293.15)} K (Комнатная)",
            "hull_breached": room_data.get("breached", False),
            "power_status": "ВКЛЮЧЕНО (Питание в норме)" if room_data.get("powered", True) else "ОБЕСТОЧЕНО (Блэкаут)",
            "adjacent_accessible_rooms": room_data.get("connections", []),
            "interactive_items_and_machinery": room_data.get("items", []),
        },
        "visual_field_people_present": nearby_people,
        "auditory_field": {
            "radio_chatter_recent": recent_radio,
            "station_announcements": recent_announcements,
            "subscribed_radio_channels": agent_channels
        },
        "mental_state_and_memory": {
            "current_mood": agent["mental_state"]["mood"],
            "stress_level": f"{agent['mental_state']['stress_level']}/100",
            "current_intent": agent["mental_state"]["current_intent"],
            "last_thought": agent["mental_state"]["internal_thoughts"],
            "recent_memories": agent["mental_state"]["recent_memories"][-4:]
        },
        "station_responsibilities_and_goals": agent.get("station_goals", []),
        "syndicate_classified_dossier": syndicate_dossier
    }

    return doc


def format_perception_document_text(doc: Dict[str, Any]) -> str:
    """
    Renders perception document as clean human and LLM-readable text format.
    """
    ident = doc["identity"]
    env = doc["current_environment"]
    hands = doc["physical_embodiment"]
    vitals = doc["vitals_and_health"]
    
    text = f"""=== ДОКУМЕНТ ВОСПРИЯТИЯ: {ident['name']} ({ident['title']}) ===
[СТАНЦИЯ: {doc['station_name']} | ТРЕВОГА: {doc['station_alert_level']} | ШАТТЛ: {doc['shuttle_status']}]

1. ЛИЧНОСТЬ И СТАТУС:
- Имя: {ident['name']} | Раса: {ident['species']} ({ident['species_traits']})
- Должность: {ident['title']} (Допуск: {ident['security_clearance']})
- Характер: {ident['personality_traits']}
- Манера речи: {ident['speech_mannerism']}

2. ВАШИ РУКИ И ЭКИПИРОВКА:
- Левая рука: {hands['left_hand']}
- Правая рука: {hands['right_hand']}
- Пояс: {hands['belt_slot']} | Карманы: [{hands['pocket1']}], [{hands['pocket2']}]
- Одежда / Броня: {hands['suit_slot']} | Рюкзак: {hands['back_slot']}

3. ВАШЕ САМОЧУВСТВИЕ:
- Здоровье: {vitals['health_points']} (Урон: физ. {vitals['brute_trauma']}, ожоги {vitals['burn_damage']}, токсины {vitals['toxin_damage']})
- Состояние: {vitals['overall_condition']}

4. ОКРУЖЕНИЕ (ГДЕ ВЫ СЕЙЧАС):
- Отсек: {env['room_name']} ({env['department']})
- Давление и Атмосфера: {env['atmospheric_pressure']} | Энергия: {env['power_status']}
- Предметы и устройства рядом: {', '.join(env['interactive_items_and_machinery'])}
- Соседние двери/проходы: {', '.join(env['adjacent_accessible_rooms'])}

5. ЛЮДИ РЯДОМ В ЭТОМ ОТСЕКЕ:
"""
    if doc["visual_field_people_present"]:
        for p in doc["visual_field_people_present"]:
            text += f"- {p['name']} ({p['role']}, {p['species']}) — {p['health_status']}, {p['holding']}\n"
    else:
        text += "- В отсеке сейчас никого нет, вы одни.\n"

    text += "\n6. ЭФИР РАЦИИ И ОБЪЯВЛЕНИЯ:\n"
    if doc["auditory_field"]["station_announcements"]:
        for a in doc["auditory_field"]["station_announcements"]:
            text += f"{a}\n"
    if doc["auditory_field"]["radio_chatter_recent"]:
        for r in doc["auditory_field"]["radio_chatter_recent"][-5:]:
            text += f"{r}\n"
    else:
        text += "- В радиоэфире пока тихо.\n"

    text += f"\n7. ВАШИ ЦЕЛИ И МЫСЛИ:\n"
    for g in doc["station_responsibilities_and_goals"]:
        text += f"• Цель: {g}\n"
    text += f"• Последняя мысль: {doc['mental_state_and_memory']['last_thought']}\n"

    if doc.get("syndicate_classified_dossier"):
        syn = doc["syndicate_classified_dossier"]
        text += f"\n🔴 [СЕКРЕТНЫЙ АПЛИНК СИНДИКАТА - {syn['role_title']}]:\n"
        text += f"Пароль: {syn['syndicate_codeword']} | Телекристаллы: {syn['telecrystals']} TC\n"
        for obj in syn['covert_objectives']:
            text += f"⚡ СЕКРЕТНАЯ ЗАДАЧА: {obj}\n"

    return text
