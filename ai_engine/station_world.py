"""
Space Station 14 World State & Simulation Engine
Maintains station topology, interactive entities, atmospheric conditions,
radio networks, station objectives, antagonist goals, and resolves all agent actions.
"""

import time
import random
from typing import Dict, List, Any, Optional

STATION_MAP = {
    "Bridge (Капитанский мостик)": {
        "dept": "Command",
        "connections": ["Command Hallway", "Captain Quarters", "EVA Storage"],
        "items": ["Captain's Desk", "Station Alert Console", "Communications Console", "Nuclear Authentication Safe", "Command Chair", "ID Computer"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Captain Quarters": {
        "dept": "Command",
        "connections": ["Bridge (Капитанский мостик)"],
        "items": ["Antique Wooden Desk", "Armor Locker", "Captain's Bed", "Secure Safe (Nuclear Disk)", "Fox Pet (Ian)"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Head of Personnel Office (Офис Главы Персонала)": {
        "dept": "Command",
        "connections": ["Command Hallway", "Main Hallway (Главный коридор станции)"],
        "items": ["HoP Desk", "ID Card Terminal", "Corgi Pet (Ian)", "Civilian Uniform Closet"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Head of Security Office (Кабинет Главы СБ)": {
        "dept": "Command",
        "connections": ["Brig & Security Armory (Бриг и Оружейная)", "Security Office (Дежурная часть СБ)"],
        "items": ["HoS Terminal", "Weapon Rack", "Secure Armory Locker", "Laser Pistol Charger"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Chief Engineer Office (Кабинет Старшего Инженерa)": {
        "dept": "Command",
        "connections": ["Engineering Workshop (Мастерская Инженеров)"],
        "items": ["CE Blueprint Desk", "Advanced Hardsuit Locker", "Power Grid Telemetry Console"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Chief Medical Officer Office (Кабинет Главврача)": {
        "dept": "Command",
        "connections": ["Medbay Treatment Center (Приемный покой Медблока)"],
        "items": ["CMO Medical Desk", "Compact Defibrillator", "Hypospray Case", "Medical Records Terminal"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Research Director Office (Кабинет Научного Руководителя)": {
        "dept": "Command",
        "connections": ["R&D Research Core (Научная Лаборатория)"],
        "items": ["RD Console", "Exosuit Control Console", "Research Node Database", "Teleporter Remote"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Command Hallway": {
        "dept": "Command",
        "connections": ["Bridge (Капитанский мостик)", "Head of Personnel Office (Офис Главы Персонала)", "Main Hallway (Главный коридор станции)"],
        "items": ["Security Camera", "Fire Alarm", "Atmospheric Vent", "Red Light Lamp"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Security Office (Дежурная часть СБ)": {
        "dept": "Security",
        "connections": ["Main Hallway (Главный коридор станции)", "Security Briefing Room (Брифинг СБ)", "Brig & Security Armory (Бриг и Оружейная)"],
        "items": ["Security Checkpoint", "Security Records Computer", "Stun Baton Charger", "Flashlight Vendor"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Security Briefing Room (Брифинг СБ)": {
        "dept": "Security",
        "connections": ["Security Office (Дежурная часть СБ)"],
        "items": ["Briefing Table & Chairs", "Holoprojector", "Donut Box", "Tactical Map"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Brig & Security Armory (Бриг и Оружейная)": {
        "dept": "Security",
        "connections": ["Security Office (Дежурная часть СБ)", "Detective Office (Кабинет Детектива)"],
        "items": ["Prisoner Holding Cells (3x)", "Locked Armory Vault (Shotguns, Armor, Flashes)", "Warden Console", "Handcuffs Rack"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Detective Office (Кабинет Детектива)": {
        "dept": "Security",
        "connections": ["Brig & Security Armory (Бриг и Оружейная)", "Main Hallway (Главный коридор станции)"],
        "items": ["Detective Desk", "Forensic Scanner Dock", "Filing Cabinets", "Bottle of Whiskey", "Tape Recorder"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Engineering Workshop (Мастерская Инженеров)": {
        "dept": "Engineering",
        "connections": ["Main Hallway (Главный коридор станции)", "Engineering Storage (Склад инструментов)", "Atmospherics Control (Атмосферный отсек)", "Engine Room (Реакторный отсек)"],
        "items": ["Tool Vendors (YouTool)", "Workbench", "Welder Refueling Tank", "Metal Sheets Stack", "Glass Sheets Stack", "Cable Coil Box"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Engineering Storage (Склад инструментов)": {
        "dept": "Engineering",
        "connections": ["Engineering Workshop (Мастерская Инженеров)"],
        "items": ["Spare RIG Suits", "Inflatable Barriers", "Solar Control Console", "Emitter Parts"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Engine Room (Реакторный отсек)": {
        "dept": "Engineering",
        "connections": ["Engineering Workshop (Мастерская Инженеров)"],
        "items": ["Singularity / Tesla Generator Chamber", "Containment Field Emitters (Active)", "Particle Accelerator Console", "SMES Power Storage Banks (100% Charged)"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Atmospherics Control (Атмосферный отсек)": {
        "dept": "Engineering",
        "connections": ["Engineering Workshop (Мастерская Инженеров)", "Maintenance Tunnels (Технические туннели)"],
        "items": ["Gas Mix Distribution Console", "O2/N2 Gas Storage Tanks", "Plasma Fuel Filters", "Fire Axe Locker", "Gas Scrubber Matrix"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Medbay Treatment Center (Приемный покой Медблока)": {
        "dept": "Medical",
        "connections": ["Main Hallway (Главный коридор станции)", "Medbay Lobby (Холл Медблока)", "Chemistry Lab (Химическая Лаборатория)", "Virology Isolation (Вирусологический бокс)", "Medbay Ambulance Bay (Гараж Парамедиков)"],
        "items": ["Operating Surgery Table", "Sleeper Regeneration Pod", "Defibrillator Unit", "First-Aid Vendor (NanoMed)", "Roller Beds", "IV Drips (Blood Pack)"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Medbay Lobby (Холл Медблока)": {
        "dept": "Medical",
        "connections": ["Main Hallway (Главный коридор станции)", "Medbay Treatment Center (Приемный покой Медблока)"],
        "items": ["Reception Counter", "Waiting Chairs", "Vending Machine (Water/Snacks)", "Health Scanner Kiosk"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Chemistry Lab (Химическая Лаборатория)": {
        "dept": "Medical",
        "connections": ["Medbay Treatment Center (Приемный покой Медблока)"],
        "items": ["ChemDispenser (30 Reagents)", "ChemMaster 4000 (Pill/Bottle press)", "Centrifuge Reagent Mixer", "Beakers Rack (100ml)", "Biohazard Disposal"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Virology Isolation (Вирусологический бокс)": {
        "dept": "Medical",
        "connections": ["Medbay Treatment Center (Приемный покой Медблока)"],
        "items": ["Virus Synthesis Incubator", "Decontamination Shower", "Cryogenic Quarantine Pod", "Antibody Analyzer"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Medbay Ambulance Bay (Гараж Парамедиков)": {
        "dept": "Medical",
        "connections": ["Medbay Treatment Center (Приемный покой Медблока)", "Maintenance Tunnels (Технические туннели)"],
        "items": ["Paramedic Ambulance Cart", "Stretcher Unit", "Oxygen Refill Station"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "R&D Research Core (Научная Лаборатория)": {
        "dept": "Science",
        "connections": ["Main Hallway (Главный коридор станции)", "Science Lobby (Холл Научного крыла)", "Robotics Assembly (Цех Робототехники)"],
        "items": ["Research Server", "Protolathe Constructor", "Circuit Imprinter", "Destructive Analyzer", "Artifact Analysis Chamber"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Science Lobby (Холл Научного крыла)": {
        "dept": "Science",
        "connections": ["Main Hallway (Главный коридор станции)", "R&D Research Core (Научная Лаборатория)"],
        "items": ["Display Case with Alien Relic", "Safety Goggles Vendor", "Whiteboard"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Robotics Assembly (Цех Робототехники)": {
        "dept": "Science",
        "connections": ["R&D Research Core (Научная Лаборатория)"],
        "items": ["Exosuit Fabricator", "Cyborg Recharging Station", "Ripley APLU Mech Chassis", "Positronic Brain Locker"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Cargo Bay (Грузовой терминал)": {
        "dept": "Cargo",
        "connections": ["Main Hallway (Главный коридор станции)", "Cargo Office (Офис Квартирмейстера)", "Salvage Airlock (Шахтерский шлюз)"],
        "items": ["Supply Shuttle Loading Dock", "Crate Opener Crowbar", "Forklift", "Automated Conveyor Belt", "Supply Ordering Console"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Cargo Office (Офис Квартирмейстера)": {
        "dept": "Cargo",
        "connections": ["Cargo Bay (Грузовой терминал)"],
        "items": ["QM Desk", "Station Budget Account Terminal (5,000 Credits)", "Stamp of Approval", "Coffee Maker"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Salvage Airlock (Шахтерский шлюз)": {
        "dept": "Cargo",
        "connections": ["Cargo Bay (Грузовой терминал)"],
        "items": ["Ore Redemption Machine", "Mining Shuttle Airbag", "Space Survival Lockers", "Kinetic Accelerator Charger"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Space Bar (Станционный Бар)": {
        "dept": "Service",
        "connections": ["Main Hallway (Главный коридор станции)", "Kitchen & Mess Hall (Кухня и Столовая)", "Theater / Central Hall (Театр и Центральный холл)"],
        "items": ["Drink Dispenser (Booze-O-Mat)", "Bar Counter & Stools", "Jukebox (Space Rock)", "Pool Table", "Glasses Rack", "Whiskey Bottles"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Kitchen & Mess Hall (Кухня и Столовая)": {
        "dept": "Service",
        "connections": ["Space Bar (Станционный Бар)", "Hydroponics Greenhouses (Гидропоника)"],
        "items": ["Microwave Oven", "Meat Grinder", "Deep Fryer", "Chef's Chopping Block", "Dining Tables", "Flour & Meat Locker"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Hydroponics Greenhouses (Гидропоника)": {
        "dept": "Service",
        "connections": ["Kitchen & Mess Hall (Кухня и Столовая)"],
        "items": ["Hydroponic Trays (Tomatoes, Wheat, Space Shrooms, Cannabis)", "Nutrient Dispenser (EZ-Nutrient)", "Seed Extractor", "Water Sink"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Janitor Closet (Каморка Уборщика)": {
        "dept": "Service",
        "connections": ["Main Hallway (Главный коридор станции)", "Maintenance Tunnels (Технические туннели)"],
        "items": ["Mop Bucket Cart", "Wet Floor Signs", "Space Cleaner Spray Bottles", "Cleaner Grenade Box", "Spare Light Tubes Crate"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Theater / Central Hall (Театр и Центральный холл)": {
        "dept": "Service",
        "connections": ["Space Bar (Станционный Бар)", "Theater / Stage (Сцена Театра)", "Main Hallway (Главный коридор станции)"],
        "items": ["Costume Wardrobe", "Banana Tree Pot", "Cream Pies Box", "Spotlights", "Squeaky Toys Basket"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Theater / Stage (Сцена Театра)": {
        "dept": "Service",
        "connections": ["Theater / Central Hall (Театр и Центральный холл)"],
        "items": ["Wooden Stage", "Mime Invisible Wall Props", "Red Velvet Curtains", "Microphone Stand"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Chapel (Часовня Космоса)": {
        "dept": "Service",
        "connections": ["Main Hallway (Главный коридор станции)"],
        "items": ["Altar of the Singulo", "Holy Bible", "Holy Water Font", "Confessional Booth", "Pews (Benches)"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Arrivals Hallway (Коридор Прибытия)": {
        "dept": "Public",
        "connections": ["Main Hallway (Главный коридор станции)", "Escape Shuttle Dock (Шлюз Эвакуации)"],
        "items": ["Arrival Shuttle Airlock", "Public PDA Terminal", "Luggage Baggage Claim", "Vending Machine"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Escape Shuttle Dock (Шлюз Эвакуации)": {
        "dept": "Public",
        "connections": ["Arrivals Hallway (Коридор Прибытия)", "Main Hallway (Главный коридор станции)"],
        "items": ["Emergency Shuttle Blast Doors (Status: DOCKED / LOCKED)", "Shuttle Call Button", "Emergency Eva Suit Wall Locker"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Main Hallway (Главный коридор станции)": {
        "dept": "Public",
        "connections": [
            "Command Hallway", "Security Office (Дежурная часть СБ)", "Medbay Lobby (Холл Медблока)",
            "Engineering Workshop (Мастерская Инженеров)", "Science Lobby (Холл Научного крыла)",
            "Cargo Bay (Грузовой терминал)", "Space Bar (Станционный Бар)", "Theater / Central Hall (Театр и Центральный холл)",
            "Chapel (Часовня Космоса)", "Janitor Closet (Каморка Уборщика)", "Arrivals Hallway (Коридор Прибытия)",
            "Escape Shuttle Dock (Шлюз Эвакуации)", "Maintenance Tunnels (Технические туннели)"
        ],
        "items": ["Intercom Speaker (Common)", "Fire Extinguisher on Wall", "Security Camera", "Station Map Hologram", "Trash Bin"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    },
    "Maintenance Tunnels (Технические туннели)": {
        "dept": "Maintenance",
        "connections": [
            "Main Hallway (Главный коридор станции)", "Atmospherics Control (Атмосферный отсек)",
            "Medbay Ambulance Bay (Гараж Парамедиков)", "Janitor Closet (Каморка Уборщика)"
        ],
        "items": ["Exposed Wiring", "Steam Vent", "Flickering Light", "Hidden Tool Cache", "Rat Nest", "Emergency Crowbar"],
        "pressure_kpa": 101.3,
        "temperature_k": 293.15,
        "breached": False,
        "powered": True
    }
}


class StationWorld:
    """
    Simulates the Space Station 14 physical and social environment.
    Tracks all agents, rooms, events, radio channels, station metrics, and objectives.
    """

    def __init__(self, station_name: str = "Space Station 14 - Outpost Delta"):
        self.station_name = station_name
        self.rooms: Dict[str, Dict[str, Any]] = {k: dict(v) for k, v in STATION_MAP.items()}
        self.agents: Dict[str, Dict[str, Any]] = {}
        self.round_start_time = time.time()
        self.round_id = random.randint(1000, 9999)
        self.alert_level = "Green (Зеленый - Норма)"
        self.emergency_shuttle = {
            "status": "Idle",  # Idle, Called, InTransit, Docked, Escaped
            "eta_seconds": 0,
            "call_time": 0
        }
        self.station_metrics = {
            "power_grid_mw": 850.0,
            "grid_stability_pct": 100,
            "air_quality_pct": 100,
            "treated_patients": 0,
            "research_points": 1200,
            "cargo_credits": 5000,
            "arrested_criminals": 0,
            "meals_cooked": 0,
            "drinks_served": 0,
            "floors_cleaned": 0,
            "total_incidents": 0
        }
        self.radio_logs: List[Dict[str, Any]] = []
        self.announcements: List[Dict[str, Any]] = []
        self.action_history: List[Dict[str, Any]] = []
        self.active_events: List[Dict[str, Any]] = []

    def register_agents(self, roster: List[Dict[str, Any]]):
        """Populate world with generated crew members."""
        self.agents.clear()
        for agent in roster:
            self.agents[agent["id"]] = agent

    def get_room_agents(self, room_name: str) -> List[Dict[str, Any]]:
        """Get all living agents currently in a specific room."""
        return [
            agent for agent in self.agents.values()
            if agent.get("location") == room_name and agent["vitals"]["is_alive"]
        ]

    def broadcast_announcement(self, sender: str, message: str, alert_type: str = "General"):
        """Broadcast an official station announcement to all crew."""
        item = {
            "time": time.time() - self.round_start_time,
            "sender": sender,
            "message": message,
            "type": alert_type
        }
        self.announcements.append(item)
        # Also log to common radio
        self.broadcast_radio("Common [145.9]", sender, f"📢 [ВНИМАНИЕ ВСЕМУ ЭКИПАЖУ]: {message}")

    def broadcast_radio(self, channel: str, sender_name: str, message: str):
        """Broadcast a message over a station radio frequency."""
        entry = {
            "time": time.time() - self.round_start_time,
            "formatted_time": time.strftime("%H:%M:%S", time.gmtime(time.time() - self.round_start_time)),
            "channel": channel,
            "sender": sender_name,
            "message": message
        }
        self.radio_logs.append(entry)
        if len(self.radio_logs) > 300:
            self.radio_logs.pop(0)

    def log_action(self, agent_id: str, action_type: str, details: str):
        """Record an action in station history."""
        agent = self.agents.get(agent_id, {})
        entry = {
            "time": time.time() - self.round_start_time,
            "agent_id": agent_id,
            "agent_name": agent.get("name", "Unknown"),
            "role": agent.get("role", "Unknown"),
            "location": agent.get("location", "Unknown"),
            "action_type": action_type,
            "details": details
        }
        self.action_history.append(entry)
        if len(self.action_history) > 500:
            self.action_history.pop(0)

    def set_alert_level(self, new_level: str, reason: str = ""):
        """Change station alert level (Green, Blue, Red, Delta)."""
        self.alert_level = new_level
        self.broadcast_announcement(
            "Station AI / Central Command",
            f"Внимание экипажу! Уровень тревоги изменен на: {new_level}. {reason}",
            alert_type="AlertChange"
        )

    def call_emergency_shuttle(self, caller: str = "Captain"):
        """Call emergency evacuation shuttle."""
        if self.emergency_shuttle["status"] in ["Called", "InTransit", "Docked"]:
            return False, "Шаттл уже вызван!"
        self.emergency_shuttle["status"] = "InTransit"
        self.emergency_shuttle["eta_seconds"] = 300  # 5 minutes
        self.emergency_shuttle["call_time"] = time.time()
        self.set_alert_level("Red (Красный - Чрезвычайная ситуация)", "Вызван аварийно-спасательный шаттл.")
        self.broadcast_announcement(
            "Central Command Dispatch",
            f"Аварийный эвакуационный шаттл вызван ({caller}). Время прибытия: 5 минут. Всем приготовиться к посадке в Шлюзе Эвакуации.",
            alert_type="ShuttleCall"
        )
        return True, "Аварийный шаттл вызван!"

    def recall_emergency_shuttle(self, caller: str = "Captain"):
        """Recall emergency shuttle back to Central Command."""
        if self.emergency_shuttle["status"] != "InTransit":
            return False, "Невозможно отозвать шаттл на текущем этапе!"
        self.emergency_shuttle["status"] = "Idle"
        self.emergency_shuttle["eta_seconds"] = 0
        self.broadcast_announcement(
            "Central Command Dispatch",
            f"Вызов эвакуационного шаттла отозван авторизованным лицом ({caller}). Станция возвращается к штатному режиму.",
            alert_type="ShuttleRecall"
        )
        return True, "Вызов шаттла отозван."

    def resolve_action(self, agent_id: str, action: Dict[str, Any]) -> str:
        """
        Executes an agent's intended action and updates world state.
        Supports: speak_local, speak_radio, whisper, emote, move_to, interact,
                  manage_inventory, heal_target, attack_target, sabotage, internal_thought.
        """
        agent = self.agents.get(agent_id)
        if not agent or not agent["vitals"]["is_alive"]:
            return "Агент мертв или отсутствует."

        action_type = action.get("type", "idle")
        result_desc = ""

        if action_type == "speak_local":
            msg = action.get("message", "...")
            room = agent["location"]
            result_desc = f"{agent['name']} говорит вслух: «{msg}»"
            self.log_action(agent_id, "speak_local", msg)

        elif action_type == "speak_radio":
            channel = action.get("channel", "Common [145.9]")
            msg = action.get("message", "...")
            # Validate channel access
            if channel in agent.get("radio_channels", []):
                self.broadcast_radio(channel, f"{agent['name']} ({agent['role']})", msg)
                result_desc = f"{agent['name']} передает по рации [{channel}]: «{msg}»"
                self.log_action(agent_id, "speak_radio", f"[{channel}] {msg}")
            else:
                result_desc = f"{agent['name']} попытался настроить неизвестную частоту рации."

        elif action_type == "whisper":
            target_name = action.get("target", "собеседник")
            msg = action.get("message", "...")
            result_desc = f"{agent['name']} шепчет {target_name}: «{msg}»"
            self.log_action(agent_id, "whisper", f"Кому: {target_name}: {msg}")

        elif action_type == "emote":
            emote_text = action.get("action", "оглядывается по сторонам")
            result_desc = f"*{agent['name']} {emote_text}*"
            self.log_action(agent_id, "emote", emote_text)

        elif action_type == "move_to":
            destination = action.get("destination")
            current_room = self.rooms.get(agent["location"])
            if current_room and destination in current_room.get("connections", []):
                agent["location"] = destination
                result_desc = f"{agent['name']} переходит в отсек {destination}."
                self.log_action(agent_id, "move_to", f"Переместился в {destination}")
            elif destination in self.rooms:
                # Path through main hallways
                agent["location"] = destination
                result_desc = f"{agent['name']} прибыл в {destination}."
                self.log_action(agent_id, "move_to", f"Прибыл в {destination}")
            else:
                result_desc = f"{agent['name']} не может пройти в {destination} — проход заблокирован."

        elif action_type == "interact":
            target_item = action.get("target_item", "оборудование")
            tool_used = action.get("tool", agent["hands"].get("right_hand", "руки"))
            sub_action = action.get("details", "использует предмет")

            # Progress relevant station metrics
            role = agent["role"]
            if "Engineer" in role or "Atmospheric" in role:
                self.station_metrics["grid_stability_pct"] = min(100, self.station_metrics["grid_stability_pct"] + random.randint(1, 3))
                result_desc = f"{agent['name']} проводит техобслуживание {target_item} с помощью {tool_used}."
            elif "Doctor" in role or "Chemist" in role or "CMO" in role:
                self.station_metrics["treated_patients"] += 1
                result_desc = f"{agent['name']} готовит растворы и медикаменты на {target_item}."
            elif "Scientist" in role or "Roboticist" in role or "RD" in role:
                self.station_metrics["research_points"] += random.randint(50, 150)
                result_desc = f"{agent['name']} проводит эксперимент на {target_item}, получая научные данные."
            elif "Chef" in role:
                self.station_metrics["meals_cooked"] += 1
                result_desc = f"{agent['name']} готовит вкусное космическое блюдо на {target_item}."
            elif "Bartender" in role:
                self.station_metrics["drinks_served"] += 1
                result_desc = f"{agent['name']} смешивает фирменный коктейль за стойкой."
            elif "Janitor" in role:
                self.station_metrics["floors_cleaned"] += 1
                result_desc = f"{agent['name']} начисто моет полы и устраняет загрязнения."
            elif "Cargo" in role or "Quartermaster" in role:
                self.station_metrics["cargo_credits"] += random.randint(100, 300)
                result_desc = f"{agent['name']} проводит инвентаризацию и отправляет грузовой манифест."
            elif "Security" in role or "HoS" in role or "Warden" in role or "Detective" in role:
                result_desc = f"{agent['name']} сканирует окружение и проверяет сохранность {target_item}."
            elif "Clown" in role:
                result_desc = f"{agent['name']} устраивает забавный розыгрыш с {target_item}! ХОНК!"
            elif "Mime" in role:
                result_desc = f"*{agent['name']} выразительно жестикулирует возле {target_item}*"
            else:
                result_desc = f"{agent['name']} взаимодействует с {target_item}."

            self.log_action(agent_id, "interact", f"{target_item} ({tool_used}) - {result_desc}")

        elif action_type == "heal_target":
            target_name = action.get("target_name")
            target_agent = next((a for a in self.agents.values() if a["name"] == target_name), None)
            if target_agent and target_agent["vitals"]["is_alive"]:
                heal_amount = random.randint(15, 30)
                target_agent["vitals"]["brute_damage"] = max(0, target_agent["vitals"]["brute_damage"] - heal_amount)
                target_agent["vitals"]["burn_damage"] = max(0, target_agent["vitals"]["burn_damage"] - heal_amount)
                target_agent["vitals"]["health"] = min(100, target_agent["vitals"]["health"] + heal_amount)
                self.station_metrics["treated_patients"] += 1
                result_desc = f"{agent['name']} оказал медицинскую помощь {target_name} (+{heal_amount} HP)."
                self.log_action(agent_id, "heal_target", f"Помощь {target_name}")
            else:
                result_desc = f"{agent['name']} не нашел пациента для оказания помощи."

        elif action_type == "antagonist_action":
            # Covert sabotage, theft, or ambush
            sub_type = action.get("sub_type", "sabotage")
            desc = action.get("details", "действует скрытно")
            if agent.get("is_antagonist"):
                antag_data = agent.get("antagonist", {})
                self.station_metrics["total_incidents"] += 1
                if sub_type == "sabotage_power":
                    self.station_metrics["grid_stability_pct"] = max(20, self.station_metrics["grid_stability_pct"] - 25)
                    self.broadcast_radio("Engineering [137.9]", "Station Telemetry", "⚠️ ВНИМАНИЕ: Зафиксировано падение мощности в подсистеме энергоснабжения!")
                    result_desc = f"⚠️ {agent['name']} скрытно саботировал линию питания!"
                elif sub_type == "theft":
                    result_desc = f"⚠️ {agent['name']} тайно похитил целевой предмет: {desc}!"
                    if "Nuclear" in desc:
                        antag_data["completed_objectives"].append("Выкрасть Диск Ядерной Аутентификации")
                elif sub_type == "attack":
                    target_name = action.get("target_name")
                    target_agent = next((a for a in self.agents.values() if a["name"] == target_name), None)
                    if target_agent:
                        dmg = random.randint(25, 45)
                        target_agent["vitals"]["brute_damage"] += dmg
                        target_agent["vitals"]["health"] -= dmg
                        if target_agent["vitals"]["health"] <= 0:
                            target_agent["vitals"]["is_alive"] = False
                            target_agent["vitals"]["health"] = 0
                            target_agent["vitals"]["status_text"] = "Мертв (Критический урон)"
                            result_desc = f"💀 {agent['name']} совершил смертельное нападение на {target_name}!"
                            self.broadcast_radio("Medical [139.9]", "Suit Sensors", f"🚨 СРОЧНО: Биосканер зафиксировал остановку сердца сотрудника: {target_name} в {agent['location']}!")
                        else:
                            result_desc = f"⚠️ {agent['name']} внезапно атаковал {target_name} ({dmg} урона)!"
                    else:
                        result_desc = f"{agent['name']} провел разведку целей Синдиката."
                else:
                    result_desc = f"⚠️ {agent['name']} провел тайную диверсию: {desc}"

                self.log_action(agent_id, "antagonist_action", result_desc)
            else:
                result_desc = f"{agent['name']} почувствовал подозрительную активность."

        elif action_type == "manage_inventory":
            slot = action.get("slot", "right_hand")
            item = action.get("item", "Empty")
            op = action.get("operation", "equip")
            if slot in agent["hands"]:
                agent["hands"][slot] = item if op == "equip" else "Empty"
            elif slot in agent["inventory"]:
                agent["inventory"][slot] = item if op == "equip" else "Empty"
            result_desc = f"{agent['name']} переложил {item} в {slot}."

        elif action_type == "internal_thought":
            thought = action.get("thought", "")
            agent["mental_state"]["internal_thoughts"] = thought
            agent["mental_state"]["recent_memories"].append(thought)
            if len(agent["mental_state"]["recent_memories"]) > 8:
                agent["mental_state"]["recent_memories"].pop(0)
            result_desc = f"({agent['name']} задумался: {thought})"

        else:
            result_desc = f"{agent['name']} дежурит на посту в {agent['location']}."

        agent["total_actions"] = agent.get("total_actions", 0) + 1
        agent["last_action_time"] = time.time()
        return result_desc
