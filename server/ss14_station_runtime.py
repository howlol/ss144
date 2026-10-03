"""
Space Station 14 — Full Gameplay Runtime (NSS Saltern)
Supports:
- Real Saltern Map (6,905 tiles, 1,576 walls, 1,014 windows, 437 airlocks, 53 CCTV cameras, 56 room beacons)
- Playable Crew Member mode & Ghost Observer (MobObserver) mode right from the Web Browser
- Dual-Hand System (Left Hand / Right Hand), Inventory, Floor Items, Lockers, Crates, Vending Machines
- Combat Mode (Melee, Stunbaton, Laser Disabler, Firearms, Projectiles/Beams, Stun/Slip/Knockdown, Healing/Revival)
- Interactive Tools (Crowbar door prying, Multitool/Emag door hacking, RCD wall building/deconstruction, Bike Horn, Extinguisher)
- Interactive Station Consoles (Cargo Console, Bridge Comms Console, ChemDispenser, Medical Scanner, Syndicate Uplink)
"""

from __future__ import annotations

import asyncio
import heapq
import json
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import httpx


ASSET_ROOT = Path(__file__).resolve().parent.parent / "ss14_assets"


@dataclass
class ChatEntry:
    id: int
    timestamp: float
    round_time: str
    speaker_uid: int
    speaker_id: str
    speaker_name: str
    speaker_job: str
    speaker_dept: str
    channel: str
    message: str
    x: float
    y: float
    room: str


@dataclass
class FloorItem:
    uid: int
    item_id: str
    name: str
    x: float
    y: float
    sprite_url: str


@dataclass
class VisualEffect:
    id: int
    effect_type: str  # "beam", "explosion", "slash", "heal", "honk", "boo", "smoke"
    x1: float
    y1: float
    x2: float
    y2: float
    color: str
    created_at: float
    duration: float = 0.65


@dataclass
class StationAgent:
    uid: int
    id: str
    name: str
    job: str
    job_title_ru: str
    department: str
    gender: str
    age: int
    x: float
    y: float
    rot: float = 0.0
    direction: str = "south"
    health: float = 100.0
    max_health: float = 100.0
    stamina: float = 100.0
    hunger: float = 100.0
    status: str = "Alive"  # Alive, Critical, Dead
    stunned_until: float = 0.0
    cuffed: bool = False
    is_ghost: bool = False
    combat_mode: bool = False
    active_hand: str = "left"  # "left" or "right"
    left_hand: Optional[str] = None
    right_hand: Optional[str] = None
    telecrystals: int = 20
    personality: str = ""
    secret_objective: str = ""
    is_antagonist: bool = False
    browser_controlled: bool = False
    pulling_id: Optional[str] = None
    current_room: str = "Hallway"
    current_task: str = "Начинает смену на станции NSS Saltern"
    last_thought: str = "Осматриваюсь в отсеке и проверяю снаряжение."
    last_speech: str = ""
    last_speech_time: float = 0.0
    last_emote: str = ""
    access: List[str] = field(default_factory=list)
    inventory: List[str] = field(default_factory=list)
    memories: List[Dict[str, str]] = field(default_factory=list)
    subconscious_prompt: str = ""
    path: List[Tuple[float, float]] = field(default_factory=list)
    target_room: Optional[str] = None
    target_x: Optional[float] = None
    target_y: Optional[float] = None
    move_speed: float = 4.5
    last_llm_time: float = 0.0
    llm_calls_count: int = 0
    last_llm_latency_ms: int = 0
    color: str = "#38bdf8"

    @property
    def held_item(self) -> Optional[str]:
        return self.left_hand if self.active_hand == "left" else self.right_hand

    @held_item.setter
    def held_item(self, val: Optional[str]) -> None:
        if self.active_hand == "left":
            self.left_hand = val
        else:
            self.right_hand = val


DEFAULT_CREW_ROSTER = [
    {
        "id": "captain-vance",
        "name": "Капитан Виктор Вэнс",
        "job": "Captain",
        "job_title_ru": "Капитан станции",
        "department": "Command",
        "gender": "male",
        "age": 48,
        "personality": (
            "Ветеран NanoTrasen с 20-летним стажем. Строгий, харизматичный, одержим порядком и регламентом. "
            "Регулярно запрашивает доклады у глав отделов по общей рации (;) и командному каналу (:c), "
            "инспектирует Мостик (Bridge), отсек ГП (HoP Office), Медбей и Инженерный отсек."
        ),
        "secret_objective": "Сохранить станцию NSS Saltern в целости, защитить ядерный диск авторизации и выявить возможных агентов Синдиката.",
        "is_antagonist": False,
        "left_hand": "CaptainPDA",
        "right_hand": "Disabler",
        "inventory": ["IdCardGold", "NukeDisk", "Medipen"],
        "access": ["AllAccess", "Command", "Captain", "Security", "Armory", "Engineering", "Medical", "Science", "Cargo", "Service", "Maintenance"],
    },
    {
        "id": "hop-rostova",
        "name": "Елена Ростова",
        "job": "HeadOfPersonnel",
        "job_title_ru": "Глава Персонала (ГП)",
        "department": "Command",
        "gender": "female",
        "age": 36,
        "personality": (
            "Педантичная бюрократка, обожает печати, формы и порядок в манифесте экипажа. "
            "Следит за работой Сервиса и Карго, выдаёт доступы на стойке HoP Office, пьёт крепкий кофе в баре."
        ),
        "secret_objective": "Проверить документы у сотрудников станции и навести идеальный порядок в бумагах.",
        "is_antagonist": False,
        "left_hand": "Stamp",
        "right_hand": "PDA",
        "inventory": ["IdCardGold", "DrinkMug"],
        "access": ["AllAccess", "Command", "HeadOfPersonnel", "Service", "Cargo", "Security", "Medical", "Engineering", "Science", "Maintenance"],
    },
    {
        "id": "hos-kane",
        "name": "Маркус Кейн",
        "job": "HeadOfSecurity",
        "job_title_ru": "Глава Службы Безопасности (ГСБ)",
        "department": "Security",
        "gender": "male",
        "age": 42,
        "personality": (
            "Суровый, подозрительный ветеран СБ. Во всём видит происки Синдиката. "
            "Координирует офицеров по каналу СБ (:s), проверяет Бриг (Brig), Оружейную (Armory) и патрулирует коридоры."
        ),
        "secret_objective": "Обеспечить железный порядок на станции и нейтрализовать любую угрозу безопасности.",
        "is_antagonist": False,
        "left_hand": "Disabler",
        "right_hand": "Stunbaton",
        "inventory": ["HoSPDA", "Handcuffs", "Flash", "WT550"],
        "access": ["Security", "Armory", "Brig", "Command", "Maintenance", "External"],
    },
    {
        "id": "sec-teller",
        "name": "Джакс Теллер",
        "job": "SecurityOfficer",
        "job_title_ru": "Офицер Службы Безопасности",
        "department": "Security",
        "gender": "male",
        "age": 29,
        "personality": (
            "Энергичный патрульный офицер СБ. Постоянно в движении между Бригом, Баром, Карго и коридоры. "
            "Не доверяет Клоуну и следит, чтобы никто не ломал шлюзы и не проникал в запретные зоны."
        ),
        "secret_objective": "Патрулировать общественные зоны станции и оперативно реагировать на вызовы в рации.",
        "is_antagonist": False,
        "left_hand": "Stunbaton",
        "right_hand": "Flash",
        "inventory": ["PDA", "Handcuffs", "Disabler"],
        "access": ["Security", "Brig", "Maintenance"],
    },
    {
        "id": "det-pendelton",
        "name": "Артур Пендлтон",
        "job": "Detective",
        "job_title_ru": "Детектив",
        "department": "Security",
        "gender": "male",
        "age": 44,
        "personality": (
            "Циничный нуарный детектив в фетровой шляпе и плаще. Говорит метафорами, записывает улики, "
            "любит сидеть в Баре или бродить по техтоннелям, выискивая заговоры и допрашивая подозреваемых."
        ),
        "secret_objective": "Вычислить, кто на станции замышляет диверсию, с помощью дедукции и криминалистического сканера.",
        "is_antagonist": False,
        "left_hand": "ForensicScanner",
        "right_hand": "PistolMK58",
        "inventory": ["PDA", "Handcuffs", "Whiskey"],
        "access": ["Security", "Brig", "Detective", "Maintenance"],
    },
    {
        "id": "ce-volkov",
        "name": "Николай Волков",
        "job": "ChiefEngineer",
        "job_title_ru": "Старший Инженер (СИ)",
        "department": "Engineering",
        "gender": "male",
        "age": 45,
        "personality": (
            "Прямолинейный технарь, знает каждый провод и каждую трубу на NSS Saltern. "
            "Следит за двигателем антиматерии (AME), СМЭС-батареями и подстанциями, ругается если падает напряжение."
        ),
        "secret_objective": "Поддерживать 100% энергоснабжение станции и стабильную работу двигателя AME.",
        "is_antagonist": False,
        "left_hand": "Multitool",
        "right_hand": "RCD",
        "inventory": ["PDA", "Crowbar", "Welder", "Wrench", "Screwdriver"],
        "access": ["Engineering", "ChiefEngineer", "Atmospherics", "Command", "Maintenance", "External"],
    },
    {
        "id": "atmos-maya",
        "name": "Майя Лин",
        "job": "AtmosphericTechnician",
        "job_title_ru": "Атмосферный техник",
        "department": "Engineering",
        "gender": "female",
        "age": 27,
        "personality": (
            "Внимательная и спокойная специалистка по газам и жизнеобеспечению. "
            "Проверяет давление и состав воздуха (21% O2, 79% N2), следит за канистрами в Атмосе (Atmospherics) и вентиляцией."
        ),
        "secret_objective": "Не допустить утечек плазмы или разгерметизации отсеков станции.",
        "is_antagonist": False,
        "left_hand": "GasAnalyzer",
        "right_hand": "Extinguisher",
        "inventory": ["PDA", "Wrench", "Crowbar", "Welder"],
        "access": ["Engineering", "Atmospherics", "Maintenance", "External"],
    },
    {
        "id": "cmo-moreau",
        "name": "Д-р Клэр Моро",
        "job": "ChiefMedicalOfficer",
        "job_title_ru": "Главный Врач (ГВ)",
        "department": "Medical",
        "gender": "female",
        "age": 39,
        "personality": (
            "Заботливая, но требовательная Главврач. Руководит Медбеем (Medbay), проверяет капсулы клонирования (Cloning) "
            "и криокапсулы (Cryogenics), напоминает экипажу включать датчики костюмов на максимум."
        ),
        "secret_objective": "Следить за здоровьем всего экипажа и держать Медбей в полной готовности.",
        "is_antagonist": False,
        "left_hand": "HealthAnalyzer",
        "right_hand": "Medkit",
        "inventory": ["PDA", "Medipen", "Brutekit", "Burnkit"],
        "access": ["Medical", "ChiefMedicalOfficer", "Chemistry", "Command", "Cryogenics", "Maintenance"],
    },
    {
        "id": "chem-richter",
        "name": "Д-р Отто Рихтер",
        "job": "Chemist",
        "job_title_ru": "Химик",
        "department": "Medical",
        "gender": "male",
        "age": 34,
        "personality": (
            "Увлечённый учёный-фармацевт. Постоянно синтезирует Бикардин, Дермалин и Дексалин в Химлаборатории (Chemistry), "
            "раздаёт лекарства врачам и пациентам."
        ),
        "secret_objective": "Синтезировать полный запас медикаментов для станции и протестировать новые смеси.",
        "is_antagonist": False,
        "left_hand": "Beaker",
        "right_hand": "Syringe",
        "inventory": ["PDA", "Medkit", "Medipen"],
        "access": ["Medical", "Chemistry", "Maintenance"],
    },
    {
        "id": "rd-vance",
        "name": "Д-р Эвелин Вэнс",
        "job": "ResearchDirector",
        "job_title_ru": "Научный Руководитель (НР)",
        "department": "Science",
        "gender": "female",
        "age": 41,
        "personality": (
            "Блестящая исследовательница аномалий и артефактов. Проводит эксперименты в Научном отсеке (Science), "
            "Лаборатории артефактов (ArtifactLab) и у Генератора аномалий, делится открытиями по рации."
        ),
        "secret_objective": "Исследовать инопланетные артефакты и набрать очки исследований для техфаба.",
        "is_antagonist": False,
        "left_hand": "AnomalyScanner",
        "right_hand": "Multitool",
        "inventory": ["PDA", "Crowbar"],
        "access": ["Science", "ResearchDirector", "Command", "Maintenance"],
    },
    {
        "id": "qm-kowalski",
        "name": "Виктор «Босс» Ковальски",
        "job": "Quartermaster",
        "job_title_ru": "Квартирмейстер (КМ)",
        "department": "Cargo",
        "gender": "male",
        "age": 38,
        "personality": (
            "Деловой и предприимчивый начальник Снабжения (CargoBay). Всё считает в космокредитах, "
            "принимает заказы от отделов, оформляет ящики на консоли снабжения."
        ),
        "secret_objective": "Увеличить бюджет Карго и обеспечить все отделы необходимыми поставками.",
        "is_antagonist": False,
        "left_hand": "AppraisalTool",
        "right_hand": "Stamp",
        "inventory": ["PDA", "Crowbar"],
        "access": ["Cargo", "Quartermaster", "Salvage", "Command", "Maintenance"],
    },
    {
        "id": "bar-morales",
        "name": "Рико Моралес",
        "job": "Bartender",
        "job_title_ru": "Бармен",
        "department": "Service",
        "gender": "male",
        "age": 31,
        "personality": (
            "Душа компании за стойкой Бара (Bar). Протирает бокалы, смешивает коктейли, "
            "знает все сплетни станции, радушно встречает посетителей и успокаивает нервных сотрудников."
        ),
        "secret_objective": "Сделать Бар самым популярным местом на станции и узнать все новости смены.",
        "is_antagonist": False,
        "left_hand": "Shaker",
        "right_hand": "Shotgun",
        "inventory": ["PDA", "DrinkMug", "Whiskey"],
        "access": ["Service", "Bar", "Kitchen", "Maintenance"],
    },
    {
        "id": "janitor-barnaby",
        "name": "Варнава Швабрин",
        "job": "Janitor",
        "job_title_ru": "Уборщик",
        "department": "Service",
        "gender": "male",
        "age": 52,
        "personality": (
            "Ворчливый, но добросовестный уборщик. Ходит по коридорам, Медбею и Бару со шваброй и ведром, "
            "возмущается, когда кто-то ходит по мокрому полу и не смотрит на знаки «Осторожно, мокрый пол»."
        ),
        "secret_objective": "Отмыть все коридоры станции до блеска и расставить таблички мокрого пола.",
        "is_antagonist": False,
        "left_hand": "Mop",
        "right_hand": "Soap",
        "inventory": ["PDA", "Extinguisher"],
        "access": ["Service", "Janitor", "Maintenance"],
    },
    {
        "id": "clown-binko",
        "name": "Хонкмастер Бинко",
        "job": "Clown",
        "job_title_ru": "Клоун (Агент Синдиката)",
        "department": "Service",
        "gender": "male",
        "age": 26,
        "personality": (
            "Неунывающий станционный клоун в ярком костюме и пищащих ботинках! Постоянно шутит, сигналит клаксоном (ХОНК!), "
            "разыгрывает СБ и персонал, но втайне работает на Синдикат и высматривает секреты командования."
        ),
        "secret_objective": "Под видом безобидных шуток и пранков проникнуть на Мостик или в Оружейную, выкрасть ядерный диск и не попасться СБ!",
        "is_antagonist": True,
        "left_hand": "BikeHorn",
        "right_hand": "Banana",
        "inventory": ["ClownPDA", "Soap", "EnergySword"],
        "access": ["Service", "Theatre", "Maintenance"],
    },
]


class SS14StationRuntime:
    def __init__(self) -> None:
        self.map_data: Dict[str, Any] = {}
        self.sprite_manifest: Dict[str, Any] = {}
        self.jobs_data: Dict[str, Any] = {}
        self.item_catalog: Dict[str, Dict[str, Any]] = {}

        # Spatial indexing
        self.walkable_tiles: Set[Tuple[int, int]] = set()
        self.tile_types: Dict[Tuple[int, int], str] = {}
        self.solid_walls: Set[Tuple[int, int]] = set()
        self.windows_set: Set[Tuple[int, int]] = set()
        self.doors_by_uid: Dict[int, Dict[str, Any]] = {}
        self.doors_by_tile: Dict[Tuple[int, int], Dict[str, Any]] = {}
        self.door_close_timers: Dict[int, float] = {}

        self.cameras: List[Dict[str, Any]] = []
        self.beacons: List[Dict[str, Any]] = []
        self.spawn_points: List[Dict[str, Any]] = []
        self.objects: List[Dict[str, Any]] = []
        self.objects_by_uid: Dict[int, Dict[str, Any]] = {}
        self.opened_lockers: Set[int] = set()

        # Dynamic floor items & visual effects (lasers, explosions, honks, heals)
        self.floor_items: Dict[int, FloorItem] = {}
        self.effects: List[VisualEffect] = []
        self._effect_seq: int = 1
        self.cargo_balance: int = 4500

        # Live runtime state
        self.round_id: int = 1
        self.round_start_time: float = time.time()
        self.alert_level: str = "green"
        self.station_power_kw: float = 480.0
        self.atmos_status: str = "Nominal (21% O2 / 79% N2, 101.3 kPa)"

        self.agents: Dict[str, StationAgent] = {}
        self.chat_log: List[ChatEntry] = []
        self._chat_seq: int = 1
        self._next_entity_uid: int = 60000

        # Native C# Content.Server Bridge status
        self.csharp_bridge_url: str = "http://127.0.0.1:12120"
        self.csharp_bridge_online: bool = False
        self._last_bridge_check: float = 0.0

        self._load_station_assets()
        self._spawn_initial_crew()
        self._spawn_initial_floor_items()

    def _load_station_assets(self) -> None:
        map_path = ASSET_ROOT / "maps" / "saltern.json"
        manifest_path = ASSET_ROOT / "sprite_manifest.json"
        jobs_path = ASSET_ROOT / "prototypes" / "jobs.json"

        with open(map_path, "r", encoding="utf-8") as f:
            self.map_data = json.load(f)
        with open(manifest_path, "r", encoding="utf-8") as f:
            self.sprite_manifest = json.load(f)
        if jobs_path.exists():
            with open(jobs_path, "r", encoding="utf-8") as f:
                self.jobs_data = json.load(f)

        self.item_catalog = self.sprite_manifest.get("items", {})

        for tx, ty, tname, _var in self.map_data.get("tiles", []):
            self.walkable_tiles.add((int(tx), int(ty)))
            self.tile_types[(int(tx), int(ty))] = tname

        for w in self.map_data.get("walls", []):
            if "Wallmount" in w.get("proto", ""):
                continue
            tx, ty = math.floor(w["x"]), math.floor(w["y"])
            self.solid_walls.add((tx, ty))

        for win in self.map_data.get("windows", []):
            tx, ty = math.floor(win["x"]), math.floor(win["y"])
            self.windows_set.add((tx, ty))

        for d in self.map_data.get("doors", []):
            door_copy = dict(d)
            uid = int(door_copy["uid"])
            self.doors_by_uid[uid] = door_copy
            tx, ty = math.floor(door_copy["x"]), math.floor(door_copy["y"])
            self.doors_by_tile[(tx, ty)] = door_copy

        self.cameras = list(self.map_data.get("cameras", []))
        self.beacons = list(self.map_data.get("beacons", []))
        self.spawn_points = list(self.map_data.get("spawnPoints", []))

        # Separate real map items (category == "item", 675 items on tables/floors in saltern.yml)
        # and item spawners from static furniture/machines, and strip invisible editor markers!
        invisible_markers = {
            "AtmosFixBlockerMarker",
            "AtmosFixFreezerMarker",
            "AtmosFixNitrogenMarker",
            "AtmosFixOxygenMarker",
            "AtmosFixPlasmaMarker",
            "WarpPoint",
            "MouseTimedSpawner",
        }
        item_spawner_tables: Dict[str, List[str]] = {
            "MaintenanceToolSpawner": ["Crowbar", "Wrench", "Screwdriver", "Wirecutter", "Multitool", "Welder"],
            "MaintenanceWeaponSpawner": ["CombatKnife", "Crowbar", "Flash", "Stunbaton"],
            "MaintenanceFluffSpawner": ["DrinkMug", "Flash", "Soap", "Banana", "BookHowToRockAndStone"],
            "BedsheetSpawner": ["Medkit", "DrinkMug"],
            "PlushieSpawner50": ["BikeHornInstrument", "Banana"],
            "RandomBoard": ["Multitool", "Screwdriver"],
            "RandomDrinkBottle": ["Whiskey", "Shaker"],
            "RandomDrinkGlass": ["DrinkMug", "Beaker"],
            "RandomFoodMeal": ["Banana", "DrinkMug"],
            "RandomFoodSingle": ["Banana", "DrinkMug"],
            "RandomInstruments": ["AcousticGuitarInstrument", "BikeHornInstrument"],
            "RandomSnacks": ["Banana", "DrinkMug"],
            "RandomSoap": ["Soap"],
            "DonkpocketBoxSpawner": ["Medkit"],
            "SalvageLootSpawner": ["AppraisalTool", "Crowbar", "Welder"],
            "SpacemenFigurineSpawner90": ["BikeHornInstrument"],
            "SpawnVendingMachineRestockFoodDrink": ["BoxFolderBlack"],
        }
        all_map_objs = [dict(o) for o in self.map_data.get("objects", [])]
        self._initial_map_items = []
        self.objects = []
        for idx, o in enumerate(all_map_objs):
            proto = o.get("proto", "")
            if proto in invisible_markers:
                continue
            if o.get("category") == "item":
                self._initial_map_items.append(o)
            elif proto in item_spawner_tables:
                choices = item_spawner_tables[proto]
                picked = choices[idx % len(choices)]
                spawned_item = dict(o)
                spawned_item["proto"] = picked
                spawned_item["name"] = self.item_catalog.get(picked, {}).get("name", picked)
                self._initial_map_items.append(spawned_item)
            else:
                self.objects.append(o)

        self.map_data["objects"] = self.objects
        self.objects_by_uid = {int(o["uid"]): o for o in self.objects}
        self.floor_items_version: int = 1
        self._bridge_command_queue: List[Dict[str, Any]] = []
        self._last_csharp_chat_sig: str = ""

    def queue_bridge_command(self, cmd: Dict[str, Any]) -> None:
        if len(self._bridge_command_queue) < 100:
            self._bridge_command_queue.append(cmd)

    def get_item_info(self, item_id: Optional[str]) -> Dict[str, Any]:
        if not item_id:
            return {"id": "", "name": "Пусто", "url": "", "type": "none"}
        if item_id in self.item_catalog:
            info = dict(self.item_catalog[item_id])
            info["id"] = item_id
            return info
        proto_sprites = self.sprite_manifest.get("prototypes", {})
        if item_id in proto_sprites:
            p = proto_sprites[item_id]
            return {
                "id": item_id,
                "name": p.get("name") or item_id,
                "url": p.get("url") or "/assets/textures/Objects/Devices/pda.rsi/pda.png",
                "type": "item",
                "damage": 8,
            }
        return {
            "id": item_id,
            "name": item_id,
            "url": "/assets/textures/Objects/Devices/pda.rsi/pda.png",
            "type": "misc",
        }

    def spawn_floor_item(self, item_id: str, x: float, y: float, custom_name: Optional[str] = None) -> FloorItem:
        info = self.get_item_info(item_id)
        self._next_entity_uid += 1
        fitem = FloorItem(
            uid=self._next_entity_uid,
            item_id=item_id,
            name=custom_name or info.get("name", item_id),
            x=round(x, 2),
            y=round(y, 2),
            sprite_url=info.get("url", ""),
        )
        self.floor_items[fitem.uid] = fitem
        self.floor_items_version += 1
        return fitem

    def _spawn_initial_floor_items(self) -> None:
        self.floor_items.clear()
        # 1. Spawn all 675 authentic items from saltern.yml!
        for mo in getattr(self, "_initial_map_items", []):
            proto = mo["proto"]
            info = self.get_item_info(proto)
            uid = int(mo["uid"])
            self.floor_items[uid] = FloorItem(
                uid=uid,
                item_id=proto,
                name=mo.get("name") or info.get("name", proto),
                x=round(float(mo["x"]), 2),
                y=round(float(mo["y"]), 2),
                sprite_url=info.get("url", ""),
            )

        # 2. Spawn key high-value department gear
        placements = [
            ("NukeDisk", 8.5, 25.5),       # Captain's Quarters
            ("Disabler", -12.5, 19.5),     # Armory
            ("Shotgun", -11.5, 19.5),      # Armory
            ("WT550", -12.5, 18.5),        # Armory
            ("Stunbaton", -10.5, 8.5),     # Brig
            ("Handcuffs", -9.5, 8.5),      # Brig
            ("Medkit", 6.5, -18.5),        # Medbay
            ("Brutekit", 7.5, -18.5),      # Medbay
            ("Burnkit", 8.5, -18.5),       # Medbay
            ("Medipen", 5.5, -18.5),       # Medbay
            ("Beaker", 2.5, -20.5),        # Chemistry
            ("Syringe", 3.5, -20.5),       # Chemistry
            ("Crowbar", 45.5, 8.5),        # Engineering / AME
            ("Welder", 46.5, 8.5),         # Engineering
            ("Multitool", 46.5, 9.5),      # Engineering
            ("RCD", 47.5, 9.5),            # Engineering
            ("GasAnalyzer", 31.5, 12.5),   # Atmospherics
            ("Extinguisher", 32.5, 12.5),  # Atmospherics
            ("Whiskey", -5.5, -5.5),       # Bar
            ("DrinkMug", -4.5, -5.5),      # Bar
            ("Banana", -6.5, -6.5),        # Bar floor
            ("Soap", -1.5, 4.5),           # Hallway slip trap!
            ("AnomalyScanner", -12.5, -29.5),  # Artifact Lab
            ("AppraisalTool", 21.5, 16.5),     # Cargo Bay
        ]
        for item_id, px, py in placements:
            self.spawn_floor_item(item_id, px, py)
        self.floor_items_version += 1

    def add_visual_effect(
        self,
        effect_type: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: str = "#38bdf8",
        duration: float = 0.6,
    ) -> None:
        self._effect_seq += 1
        self.effects.append(
            VisualEffect(
                id=self._effect_seq,
                effect_type=effect_type,
                x1=round(x1, 2),
                y1=round(y1, 2),
                x2=round(x2, 2),
                y2=round(y2, 2),
                color=color,
                created_at=time.time(),
                duration=duration,
            )
        )
        if len(self.effects) > 50:
            self.effects = self.effects[-50:]

    def _find_spawn_coords(self, job: str) -> Tuple[float, float]:
        role_matches = [
            sp for sp in self.spawn_points
            if sp["role"].lower() == job.lower()
            or (job == "AtmosphericTechnician" and sp["role"] == "Atmos")
        ]
        if not role_matches:
            role_matches = [sp for sp in self.spawn_points if sp["role"] in ("Latejoin", "Passenger")]
        if role_matches:
            chosen = random.choice(role_matches)
            return float(chosen["x"]), float(chosen["y"])
        return 3.5, 30.5

    def nearest_room_name(self, x: float, y: float) -> str:
        best_name = "Corridor"
        best_dist = 999999.0
        for b in self.beacons:
            d = math.hypot(b["x"] - x, b["y"] - y)
            if d < best_dist:
                best_dist = d
                best_name = b["name"]
        return best_name

    def get_room_coords(self, room_query: str) -> Optional[Tuple[float, float, str]]:
        if not room_query:
            return None
        q = room_query.strip().lower().replace(" ", "").replace("_", "")
        for b in self.beacons:
            bname = b["name"].lower().replace(" ", "").replace("_", "")
            if q == bname:
                tx, ty = self._nearest_free_tile(math.floor(b["x"]), math.floor(b["y"]))
                return tx + 0.5, ty + 0.5, b["name"]
        for b in self.beacons:
            bname = b["name"].lower().replace(" ", "").replace("_", "")
            if q in bname or bname in q:
                tx, ty = self._nearest_free_tile(math.floor(b["x"]), math.floor(b["y"]))
                return tx + 0.5, ty + 0.5, b["name"]
        for c in self.cameras:
            cname = c["id"].lower().replace(" ", "").replace("_", "")
            if q == cname or q in cname or cname in q:
                tx, ty = self._nearest_free_tile(math.floor(c["x"]), math.floor(c["y"]))
                return tx + 0.5, ty + 0.5, c["id"]
        return None

    def _is_tile_passable(self, tx: int, ty: int, agent_access: Optional[List[str]] = None, is_ghost: bool = False) -> bool:
        if is_ghost:
            return True
        if (tx, ty) not in self.walkable_tiles:
            return False
        if (tx, ty) in self.solid_walls or (tx, ty) in self.windows_set:
            return False
        door = self.doors_by_tile.get((tx, ty))
        if door:
            if door.get("bolted"):
                return False
            if door.get("open"):
                return True
            req = door.get("access") or []
            if not req or not agent_access:
                return True
            if "AllAccess" in agent_access:
                return True
            if any(r in agent_access for r in req):
                return True
            return False
        return True

    def _nearest_free_tile(self, start_tx: int, start_ty: int) -> Tuple[int, int]:
        if self._is_tile_passable(start_tx, start_ty, ["AllAccess"]):
            return start_tx, start_ty
        for radius in range(1, 8):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if self._is_tile_passable(start_tx + dx, start_ty + dy, ["AllAccess"]):
                        return start_tx + dx, start_ty + dy
        return start_tx, start_ty

    def find_path(
        self,
        start_x: float,
        start_y: float,
        goal_x: float,
        goal_y: float,
        agent_access: Optional[List[str]] = None,
        is_ghost: bool = False,
        max_steps: int = 1200,
    ) -> List[Tuple[float, float]]:
        if is_ghost:
            return [(goal_x, goal_y)]

        sx, sy = math.floor(start_x), math.floor(start_y)
        gx, gy = self._nearest_free_tile(math.floor(goal_x), math.floor(goal_y))
        if (sx, sy) == (gx, gy):
            return []

        open_heap: List[Tuple[float, int, Tuple[int, int]]] = []
        heapq.heappush(open_heap, (0.0, 0, (sx, sy)))
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g_score: Dict[Tuple[int, int], float] = {(sx, sy): 0.0}
        visited = 0

        best_node = (sx, sy)
        best_h = math.hypot(gx - sx, gy - sy)

        neighbors = [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]

        while open_heap and visited < max_steps:
            _f, _steps, current = heapq.heappop(open_heap)
            visited += 1

            if current == (gx, gy):
                best_node = current
                break

            cx, cy = current
            for dx, dy in neighbors:
                nx, ny = cx + dx, cy + dy
                if not self._is_tile_passable(nx, ny, agent_access):
                    continue
                if dx != 0 and dy != 0:
                    if not self._is_tile_passable(cx + dx, cy, agent_access) or not self._is_tile_passable(cx, cy + dy, agent_access):
                        continue

                step_cost = 1.414 if (dx != 0 and dy != 0) else 1.0
                if (nx, ny) in self.doors_by_tile:
                    step_cost += 0.3

                tentative_g = g_score[current] + step_cost
                if tentative_g < g_score.get((nx, ny), 999999.0):
                    came_from[(nx, ny)] = current
                    g_score[(nx, ny)] = tentative_g
                    h = math.hypot(gx - nx, gy - ny)
                    if h < best_h:
                        best_h = h
                        best_node = (nx, ny)
                    heapq.heappush(open_heap, (tentative_g + h, visited, (nx, ny)))

        path_tiles: List[Tuple[float, float]] = []
        cur = best_node
        while cur in came_from:
            path_tiles.append((cur[0] + 0.5, cur[1] + 0.5))
            cur = came_from[cur]
        path_tiles.reverse()
        return path_tiles

    def _spawn_initial_crew(self) -> None:
        self.agents.clear()
        outfits = self.sprite_manifest.get("job_outfits", {})

        for idx, cfg in enumerate(DEFAULT_CREW_ROSTER):
            sx, sy = self._find_spawn_coords(cfg["job"])
            tx, ty = self._nearest_free_tile(math.floor(sx), math.floor(sy))
            wx, wy = tx + 0.5, ty + 0.5
            room = self.nearest_room_name(wx, wy)
            outfit_info = outfits.get(cfg["job"], {})
            color = outfit_info.get("color", "#38bdf8")

            agent = StationAgent(
                uid=40000 + idx + 1,
                id=cfg["id"],
                name=cfg["name"],
                job=cfg["job"],
                job_title_ru=cfg["job_title_ru"],
                department=cfg["department"],
                gender=cfg["gender"],
                age=cfg["age"],
                x=wx,
                y=wy,
                direction="south",
                left_hand=cfg.get("left_hand"),
                right_hand=cfg.get("right_hand"),
                personality=cfg["personality"],
                secret_objective=cfg["secret_objective"],
                is_antagonist=cfg["is_antagonist"],
                browser_controlled=False,
                current_room=room,
                current_task=f"Дежурство в отсеке {room}",
                access=list(cfg["access"]),
                inventory=list(cfg["inventory"]),
                color=color,
            )
            agent.memories.append({
                "time": "00:00",
                "text": f"Заступил на смену на станции NSS Saltern в должности {cfg['job_title_ru']} (отсек {room}).",
            })
            self.agents[agent.id] = agent

        self.add_chat_message(
            speaker_uid=0,
            speaker_id="centcomm",
            speaker_name="Центральное Командование NanoTrasen",
            speaker_job="CentComm",
            speaker_dept="Command",
            channel="CentComm",
            message="Добро пожаловать на смену на исследовательской станции NSS Saltern! Код безопасности: ЗЕЛЁНЫЙ. Желаем продуктивной и безопасной работы.",
            x=3.5,
            y=30.5,
        )

    def spawn_custom_agent(
        self,
        name: str,
        job: str,
        personality: str,
        secret_objective: str = "",
        is_antagonist: bool = False,
        room: Optional[str] = None,
        browser_controlled: bool = False,
        is_ghost: bool = False,
    ) -> StationAgent:
        outfits = self.sprite_manifest.get("job_outfits", {})
        outfit_info = outfits.get(job, outfits.get("Passenger", {}))
        dept = "Observer" if is_ghost else outfit_info.get("dept", "Civilian")
        color = "#a78bfa" if is_ghost else outfit_info.get("color", "#38bdf8")

        if room:
            rc = self.get_room_coords(room)
            if rc:
                wx, wy, room_name = rc
            else:
                sx, sy = self._find_spawn_coords(job)
                tx, ty = self._nearest_free_tile(math.floor(sx), math.floor(sy))
                wx, wy = tx + 0.5, ty + 0.5
                room_name = self.nearest_room_name(wx, wy)
        else:
            sx, sy = self._find_spawn_coords(job)
            tx, ty = self._nearest_free_tile(math.floor(sx), math.floor(sy))
            wx, wy = tx + 0.5, ty + 0.5
            room_name = self.nearest_room_name(wx, wy)

        self._next_entity_uid += 1
        uid = self._next_entity_uid
        agent_id = f"ghost-{uid}" if is_ghost else f"player-{job.lower()}-{uid}"

        default_access = ["AllAccess"] if is_ghost or dept == "Command" or job in ("Captain", "HeadOfPersonnel") else ["Maintenance", dept]

        job_loadouts = {
            "Captain": ("CaptainPDA", "Disabler", ["IdCardGold", "Medipen"]),
            "SecurityOfficer": ("Stunbaton", "Flash", ["PDA", "Handcuffs", "Disabler"]),
            "Detective": ("ForensicScanner", "PistolMK58", ["PDA", "Handcuffs"]),
            "StationEngineer": ("Multitool", "Crowbar", ["PDA", "Welder", "Wrench", "RCD"]),
            "AtmosphericTechnician": ("GasAnalyzer", "Extinguisher", ["PDA", "Wrench", "Welder"]),
            "MedicalDoctor": ("HealthAnalyzer", "Medkit", ["PDA", "Brutekit", "Burnkit", "Medipen"]),
            "Chemist": ("Beaker", "Syringe", ["PDA", "Medkit"]),
            "Scientist": ("AnomalyScanner", "Multitool", ["PDA", "Crowbar"]),
            "CargoTechnician": ("AppraisalTool", "Crowbar", ["PDA", "Stamp"]),
            "Bartender": ("Shaker", "Shotgun", ["PDA", "Whiskey", "DrinkMug"]),
            "Clown": ("BikeHorn", "Banana", ["ClownPDA", "Soap"]),
            "Janitor": ("Mop", "Soap", ["PDA", "Extinguisher"]),
        }
        lh, rh, inv = job_loadouts.get(job, ("PDA", "Crowbar", ["Medipen", "DrinkMug"]))
        if is_ghost:
            lh, rh, inv = (None, None, [])
        elif is_antagonist and "EnergySword" not in inv:
            inv = list(inv) + ["EnergySword", "ClownPDA"]

        agent = StationAgent(
            uid=uid,
            id=agent_id,
            name=name,
            job="Ghost" if is_ghost else job,
            job_title_ru="Призрак-Наблюдатель (Ghost)" if is_ghost else job,
            department=dept,
            gender=random.choice(["male", "female"]),
            age=random.randint(23, 45),
            x=wx,
            y=wy,
            is_ghost=is_ghost,
            browser_controlled=browser_controlled or is_ghost,
            left_hand=lh,
            right_hand=rh,
            personality=personality or f"Сотрудник станции NSS Saltern в должности {job}.",
            secret_objective=secret_objective or "Выжить на смене и выполнить свой долг.",
            is_antagonist=is_antagonist,
            current_room=room_name,
            current_task="Свободный полёт Наблюдателя (Ghost)" if is_ghost else f"Управляется игроком в отсеке {room_name}",
            access=default_access,
            inventory=list(inv),
            move_speed=8.0 if is_ghost else 4.8,
            color=color,
        )
        agent.memories.append({
            "time": self.get_round_clock(),
            "text": f"Присоединился к раунду на станции NSS Saltern ({agent.job_title_ru}).",
        })
        self.agents[agent.id] = agent

        if not is_ghost:
            self.add_chat_message(
                speaker_uid=0,
                speaker_id="station-announcer",
                speaker_name="Оповещение станции",
                speaker_job="System",
                speaker_dept="Command",
                channel="Common",
                message=f"{name} ({job}) прибыл на станцию NSS Saltern (сектор {room_name}).",
                x=wx,
                y=wy,
            )

        return agent

    def get_round_clock(self) -> str:
        elapsed = max(0, int(time.time() - self.round_start_time))
        mins, secs = divmod(elapsed, 60)
        hrs, mins = divmod(mins, 60)
        if hrs > 0:
            return f"{hrs:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    def add_chat_message(
        self,
        speaker_uid: int,
        speaker_id: str,
        speaker_name: str,
        speaker_job: str,
        speaker_dept: str,
        channel: str,
        message: str,
        x: float,
        y: float,
    ) -> ChatEntry:
        room = self.nearest_room_name(x, y)
        entry = ChatEntry(
            id=self._chat_seq,
            timestamp=time.time(),
            round_time=self.get_round_clock(),
            speaker_uid=speaker_uid,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            speaker_job=speaker_job,
            speaker_dept=speaker_dept,
            channel=channel,
            message=message,
            x=round(x, 2),
            y=round(y, 2),
            room=room,
        )
        self._chat_seq += 1
        self.chat_log.append(entry)
        if len(self.chat_log) > 250:
            self.chat_log = self.chat_log[-250:]
        return entry

    def command_agent_move_to(self, agent_id: str, target_x: float, target_y: float, task_desc: Optional[str] = None) -> bool:
        agent = self.agents.get(agent_id)
        if not agent:
            return False
        if not agent.is_ghost and (agent.status == "Dead" or time.time() < agent.stunned_until):
            return False

        path = self.find_path(agent.x, agent.y, target_x, target_y, agent.access, is_ghost=agent.is_ghost)
        if not path:
            return False

        agent.path = path
        agent.target_x = path[-1][0]
        agent.target_y = path[-1][1]
        agent.target_room = self.nearest_room_name(agent.target_x, agent.target_y)
        if task_desc:
            agent.current_task = task_desc
        self.queue_bridge_command({
            "action": "move_to",
            "agentId": agent_id,
            "x": float(agent.target_x),
            "y": float(agent.target_y),
            "task": agent.current_task,
        })
        return True

    def command_agent_move_to_room(self, agent_id: str, room_name: str, task_desc: Optional[str] = None) -> bool:
        rc = self.get_room_coords(room_name)
        if not rc:
            return False
        tx, ty, resolved_name = rc
        ntx, nty = self._nearest_free_tile(
            math.floor(tx) + random.randint(-2, 2),
            math.floor(ty) + random.randint(-2, 2),
        )
        return self.command_agent_move_to(
            agent_id,
            ntx + 0.5,
            nty + 0.5,
            task_desc or f"Идёт в отсек {resolved_name}",
        )

    def command_agent_say(self, agent_id: str, raw_text: str) -> Optional[ChatEntry]:
        agent = self.agents.get(agent_id)
        if not agent or not raw_text or not raw_text.strip():
            return None

        text = raw_text.strip()
        if agent.is_ghost:
            return self.add_chat_message(
                speaker_uid=agent.uid,
                speaker_id=agent.id,
                speaker_name=f"👻 {agent.name}",
                speaker_job="Ghost",
                speaker_dept="Observer",
                channel="DeadChat",
                message=text,
                x=agent.x,
                y=agent.y,
            )

        channel = "Local"
        radio_map = {
            ";": "Common",
            ":c": "Command",
            ":s": "Security",
            ":e": "Engineering",
            ":m": "Medical",
            ":n": "Science",
            ":u": "Cargo",
            ":v": "Service",
        }
        for prefix, ch_name in radio_map.items():
            if text.lower().startswith(prefix):
                channel = ch_name
                text = text[len(prefix):].strip()
                break

        if not text:
            return None

        agent.last_speech = text
        agent.last_speech_time = time.time()
        self.queue_bridge_command({
            "action": "say",
            "agentId": agent_id,
            "text": raw_text.strip(),
            "thought": agent.last_thought,
        })

        return self.add_chat_message(
            speaker_uid=agent.uid,
            speaker_id=agent.id,
            speaker_name=agent.name,
            speaker_job=agent.job_title_ru,
            speaker_dept=agent.department,
            channel=channel,
            message=text,
            x=agent.x,
            y=agent.y,
        )

    def command_agent_emote(self, agent_id: str, emote_text: str) -> Optional[ChatEntry]:
        agent = self.agents.get(agent_id)
        if not agent or not emote_text or not emote_text.strip():
            return None
        clean = emote_text.strip()
        agent.last_emote = clean
        return self.add_chat_message(
            speaker_uid=agent.uid,
            speaker_id=agent.id,
            speaker_name=agent.name,
            speaker_job=agent.job_title_ru,
            speaker_dept=agent.department,
            channel="Emote",
            message=f"*{agent.name} {clean}*",
            x=agent.x,
            y=agent.y,
        )

    def swap_hands(self, agent_id: str) -> Optional[str]:
        agent = self.agents.get(agent_id)
        if not agent:
            return None
        agent.active_hand = "right" if agent.active_hand == "left" else "left"
        return agent.active_hand

    def drop_active_item(self, agent_id: str) -> Optional[FloorItem]:
        agent = self.agents.get(agent_id)
        if not agent or not agent.held_item:
            return None
        item_id = agent.held_item
        agent.held_item = None
        fitem = self.spawn_floor_item(item_id, agent.x, agent.y)
        agent.current_task = f"Выбросил(а) {fitem.name} на пол"
        return fitem

    def pickup_floor_item(self, agent_id: str, floor_uid: int) -> bool:
        agent = self.agents.get(agent_id)
        fitem = self.floor_items.get(int(floor_uid))
        if not agent or not fitem or agent.is_ghost:
            return False
        if math.hypot(fitem.x - agent.x, fitem.y - agent.y) > 2.5:
            self.command_agent_move_to(agent_id, fitem.x, fitem.y, f"Идёт поднять {fitem.name}")
            return True

        # Place in active hand if empty, else other hand, else inventory
        if agent.held_item is None:
            agent.held_item = fitem.item_id
        elif agent.left_hand is None:
            agent.left_hand = fitem.item_id
        elif agent.right_hand is None:
            agent.right_hand = fitem.item_id
        else:
            agent.inventory.append(fitem.item_id)

        self.floor_items.pop(int(floor_uid), None)
        self.floor_items_version += 1
        agent.current_task = f"Поднял(а) {fitem.name}"
        return True

    def throw_active_item(self, agent_id: str, target_x: Optional[float] = None, target_y: Optional[float] = None) -> str:
        agent = self.agents.get(agent_id)
        if not agent or not agent.held_item:
            return "Нечего бросать"
        item_id = agent.held_item
        info = self.get_item_info(item_id)
        agent.held_item = None

        if target_x is None or target_y is None:
            offsets = {"north": (0, 3.5), "south": (0, -3.5), "east": (3.5, 0), "west": (-3.5, 0)}
            dx, dy = offsets.get(agent.direction, (0, -3.5))
            tx_f, ty_f = agent.x + dx, agent.y + dy
        else:
            tx_f, ty_f = float(target_x), float(target_y)

        # Raycast along throw trajectory so it stops at walls or hits a person
        steps = 10
        land_x, land_y = agent.x, agent.y
        for s in range(1, steps + 1):
            t = s / steps
            cx = agent.x + (tx_f - agent.x) * t
            cy = agent.y + (ty_f - agent.y) * t
            if not self._is_tile_passable(math.floor(cx), math.floor(cy), ["AllAccess"]):
                break
            land_x, land_y = cx, cy
            for other in self.agents.values():
                if other.id != agent.id and not other.is_ghost and math.hypot(other.x - cx, other.y - cy) < 0.7:
                    dmg = float(info.get("damage", 6))
                    other.health = max(0.0, other.health - dmg)
                    if item_id in ("Banana", "Soap") or info.get("stun", 0) > 0:
                        other.stunned_until = time.time() + 3.0
                    self.command_agent_emote(agent.id, f"метко бросает «{info['name']}» прямо в {other.name} (-{int(dmg)} HP)!")
                    break

        self.add_visual_effect("beam", agent.x, agent.y, land_x, land_y, "#94a3b8", 0.35)
        fitem = self.spawn_floor_item(item_id, land_x, land_y)
        agent.current_task = f"Бросил(а) {fitem.name}"
        return agent.current_task

    def equip_from_inventory(self, agent_id: str, item_index: int) -> bool:
        agent = self.agents.get(agent_id)
        if not agent or item_index < 0 or item_index >= len(agent.inventory):
            return False
        chosen = agent.inventory.pop(item_index)
        if agent.held_item:
            agent.inventory.append(agent.held_item)
        agent.held_item = chosen
        info = self.get_item_info(chosen)
        agent.current_task = f"Взял(а) в активную руку {info['name']}"
        return True

    def give_item_to_agent(self, agent_id: str, item_id: str) -> str:
        agent = self.agents.get(agent_id)
        if not agent:
            return "Персонаж не найден"
        info = self.get_item_info(item_id)
        if agent.held_item is None:
            agent.held_item = item_id
        elif agent.left_hand is None:
            agent.left_hand = item_id
        elif agent.right_hand is None:
            agent.right_hand = item_id
        else:
            agent.inventory.append(item_id)
        agent.current_task = f"Получил(а) {info['name']}"
        return info["name"]

    def use_item_in_hand(self, agent_id: str) -> str:
        agent = self.agents.get(agent_id)
        if not agent:
            return "Персонаж не найден"

        if agent.is_ghost:
            return self.ghost_boo(agent_id)

        item_id = agent.held_item
        if not item_id:
            return "В активной руке ничего нет"

        info = self.get_item_info(item_id)
        itype = info.get("type", "")

        if itype == "horn":
            self.add_visual_effect("honk", agent.x, agent.y, agent.x, agent.y, "#f43f5e", 0.8)
            self.command_agent_emote(agent_id, "громко сигналит клаксоном: ХОНК-ХОНК!!")
            return "ХОНК-ХОНК!!"

        elif itype == "medical":
            heal_amt = float(info.get("heal", 30))
            agent.health = min(agent.max_health, agent.health + heal_amt)
            agent.status = "Alive"
            agent.stunned_until = 0.0
            self.add_visual_effect("heal", agent.x, agent.y, agent.x, agent.y, "#22c55e", 0.8)
            agent.current_task = f"Применил(а) {info['name']} (+{int(heal_amt)} HP)"
            return agent.current_task

        elif itype == "food":
            heal_amt = float(info.get("heal", 12))
            agent.health = min(agent.max_health, agent.health + heal_amt)
            agent.hunger = min(100.0, agent.hunger + 30.0)
            self.command_agent_emote(agent_id, f"употребляет {info['name']}")
            return f"Употребил {info['name']}"

        elif itype == "tool_rcd":
            # Build or remove wall in front of agent
            offsets = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0)}
            dx, dy = offsets.get(agent.direction, (0, -1))
            tx, ty = math.floor(agent.x) + dx, math.floor(agent.y) + dy
            if (tx, ty) in self.solid_walls:
                self.solid_walls.remove((tx, ty))
                self.map_data["walls"] = [
                    w for w in self.map_data["walls"]
                    if not (math.floor(w["x"]) == tx and math.floor(w["y"]) == ty)
                ]
                self.add_visual_effect("explosion", tx + 0.5, ty + 0.5, tx + 0.5, ty + 0.5, "#38bdf8", 0.5)
                return f"РСУ разобрал стену на ({tx}, {ty})"
            else:
                self.solid_walls.add((tx, ty))
                self._next_entity_uid += 1
                self.map_data["walls"].append({"uid": self._next_entity_uid, "proto": "WallSolid", "x": tx + 0.5, "y": ty + 0.5})
                self.add_visual_effect("heal", tx + 0.5, ty + 0.5, tx + 0.5, ty + 0.5, "#38bdf8", 0.5)
                return f"РСУ построил стальную стену на ({tx}, {ty})"

        return f"Использует {info['name']}"

    def ghost_boo(self, agent_id: str) -> str:
        agent = self.agents.get(agent_id)
        if not agent:
            return ""
        self.add_visual_effect("boo", agent.x, agent.y, agent.x, agent.y, "#a855f7", 1.1)
        room = self.nearest_room_name(agent.x, agent.y)
        # Find nearest living AI crew member within 9 tiles and spook them!
        for other in self.agents.values():
            if not other.is_ghost and other.status == "Alive" and math.hypot(other.x - agent.x, other.y - agent.y) <= 9.0:
                other.last_thought = f"В отсеке {room} внезапно заморгал свет и повеяло могильным холодом! Тут призрак?!"
                self.command_agent_say(other.id, f"Эй, вы это видели?! В отсеке {room} сам по себе мигнул свет и запахло озоном!")
                break
        return f"Напугал экипаж в отсеке {room}!"

    def attack_or_interact_target_agent(self, actor_id: str, target_agent_id: str) -> Dict[str, Any]:
        actor = self.agents.get(actor_id)
        target = self.agents.get(target_agent_id)
        if not actor or not target:
            return {"ok": False, "error": "Character not found"}

        if actor.is_ghost:
            # Ghost jumps into / possesses target character!
            target.browser_controlled = True
            return {"ok": True, "action": "possessed", "new_agent_id": target.id, "message": f"Вы вселились в тело {target.name}!"}

        dist = math.hypot(target.x - actor.x, target.y - actor.y)
        item_id = actor.held_item
        info = self.get_item_info(item_id)
        itype = info.get("type", "")

        # 1. Ranged weapon works up to 14 tiles!
        if (actor.combat_mode or itype == "weapon_ranged") and itype == "weapon_ranged" and dist <= 14.0:
            dmg = float(info.get("damage", 20))
            stun_sec = float(info.get("stun", 0.0))
            beam_col = info.get("beamColor", "#ef4444")
            self.add_visual_effect("beam", actor.x, actor.y, target.x, target.y, beam_col, 0.55)

            target.health = max(0.0, target.health - dmg)
            if stun_sec > 0:
                target.stunned_until = time.time() + stun_sec
                target.path.clear()
            if target.health <= 0:
                target.status = "Dead"
                target.path.clear()
            elif target.health <= 25:
                target.status = "Critical"

            self.command_agent_emote(actor.id, f"стреляет из «{info['name']}» в {target.name} (-{int(dmg)} HP)!")
            target.subconscious_prompt = f"В меня только что выстрелил {actor.name} из {info['name']}! Нужно защищаться или звать СБ по рации!"
            return {"ok": True, "message": f"Выстрел в {target.name} (-{int(dmg)} HP)!"}

        # For melee / medical / cuffs, must be within 2.5 tiles
        if dist > 2.6:
            self.command_agent_move_to(actor.id, target.x, target.y, f"Подходит к {target.name}")
            return {"ok": True, "message": f"Подходит ближе к {target.name}..."}

        # 2. Medical healing
        if itype == "medical" or (not actor.combat_mode and itype in ("scanner_med", "none")):
            if itype == "medical":
                heal_amt = float(info.get("heal", 35))
                target.health = min(target.max_health, target.health + heal_amt)
                target.status = "Alive"
                target.stunned_until = 0.0
                self.add_visual_effect("heal", actor.x, actor.y, target.x, target.y, "#22c55e", 0.7)
                self.command_agent_emote(actor.id, f"лечит {target.name} с помощью «{info['name']}» (+{int(heal_amt)} HP)")
                target.subconscious_prompt = f"{actor.name} только что вылечил меня с помощью {info['name']}! Поблагодарю его."
                return {"ok": True, "message": f"Вылечил {target.name} (+{int(heal_amt)} HP)"}
            else:
                return {
                    "ok": True,
                    "examine": True,
                    "message": f"Осмотр {target.name} ({target.job_title_ru}): Здоровье {int(target.health)}%, статус {target.status}, в руках: {target.held_item or 'пусто'}.",
                }

        # 3. Handcuffs
        if itype == "cuffs":
            target.cuffed = not target.cuffed
            target.stunned_until = time.time() + 4.0 if target.cuffed else 0.0
            target.path.clear()
            state_txt = "надевает наручники на" if target.cuffed else "снимает наручники с"
            self.command_agent_emote(actor.id, f"{state_txt} {target.name}!")
            target.subconscious_prompt = f"{actor.name} надел на меня наручники! Возмутиться или потребовать адвоката!"
            return {"ok": True, "message": f"{state_txt.capitalize()} {target.name}"}

        # 4. Melee / Stunbaton / Unarmed Harm
        dmg = float(info.get("damage", 8 if actor.combat_mode else 0))
        stun_sec = float(info.get("stun", 0.0))
        if actor.combat_mode or itype in ("weapon_melee", "weapon_stun"):
            if dmg <= 0 and stun_sec <= 0:
                dmg = 9.0
            target.health = max(0.0, target.health - dmg)
            if stun_sec > 0:
                target.stunned_until = time.time() + stun_sec
                target.path.clear()
            if target.health <= 0:
                target.status = "Dead"
                target.path.clear()
            elif target.health <= 25:
                target.status = "Critical"

            self.add_visual_effect("slash", actor.x, actor.y, target.x, target.y, "#ef4444", 0.45)
            weapon_name = info["name"] if item_id else "кулаками"
            self.command_agent_emote(actor.id, f"атакует {target.name} ({weapon_name}, -{int(dmg)} HP)!")
            target.subconscious_prompt = f"Меня атаковал {actor.name} ({weapon_name}) в отсеке {target.current_room}! Надо кричать в рацию ;Помогите СБ!"
            return {"ok": True, "message": f"Атакован {target.name} (-{int(dmg)} HP)"}

        return {"ok": True, "message": f"Осмотрел {target.name}"}

    def toggle_pull(self, actor_id: str, target_agent_id: Optional[str] = None) -> Dict[str, Any]:
        actor = self.agents.get(actor_id)
        if not actor or actor.is_ghost:
            return {"ok": False, "message": "Невозможно тянуть"}
        if actor.pulling_id and (not target_agent_id or actor.pulling_id == target_agent_id):
            old = self.agents.get(actor.pulling_id)
            actor.pulling_id = None
            return {"ok": True, "message": f"Отпустил(а) {old.name if old else 'объект'}"}
        # Find nearest agent within 2.2 tiles if target_agent_id not specified
        target = self.agents.get(target_agent_id) if target_agent_id else None
        if not target:
            best_d = 2.2
            for other in self.agents.values():
                if other.id == actor.id or other.is_ghost:
                    continue
                d = math.hypot(other.x - actor.x, other.y - actor.y)
                if d < best_d:
                    best_d = d
                    target = other
        if not target or math.hypot(target.x - actor.x, target.y - actor.y) > 2.5:
            return {"ok": False, "message": "Рядом никого нет, чтобы схватить и тянуть"}
        actor.pulling_id = target.id
        self.command_agent_emote(actor.id, f"хватает и тянет за собой {target.name}")
        return {"ok": True, "message": f"Тянет за собой {target.name}"}

    def fire_or_swing_at(self, actor_id: str, target_x: float, target_y: float) -> Dict[str, Any]:
        """Real SS14 directional combat: shoots a raycast laser/bullet or swings melee toward (target_x, target_y)."""
        actor = self.agents.get(actor_id)
        if not actor or actor.is_ghost or actor.status == "Dead":
            return {"ok": False, "message": "Невозможно атаковать"}

        dx = target_x - actor.x
        dy = target_y - actor.y
        dist = math.hypot(dx, dy)
        if abs(dx) > abs(dy):
            actor.direction = "east" if dx > 0 else "west"
        elif abs(dy) > 0.01:
            actor.direction = "north" if dy > 0 else "south"

        item_id = actor.held_item
        info = self.get_item_info(item_id)
        itype = info.get("type", "")

        # 1. Ranged weapon: raycast up to 14 tiles
        if itype == "weapon_ranged":
            max_range = 14.0
            nx = dx / max(0.01, dist)
            ny = dy / max(0.01, dist)
            end_x, end_y = actor.x, actor.y
            hit_agent: Optional[StationAgent] = None

            steps = int(max_range * 4)
            for s in range(1, steps + 1):
                cx = actor.x + nx * (s * 0.25)
                cy = actor.y + ny * (s * 0.25)
                tx, ty = math.floor(cx), math.floor(cy)
                if (tx, ty) in self.solid_walls:
                    end_x, end_y = cx, cy
                    break
                door = self.doors_by_tile.get((tx, ty))
                if door and not door.get("open"):
                    end_x, end_y = cx, cy
                    break
                end_x, end_y = cx, cy
                for other in self.agents.values():
                    if other.id != actor.id and not other.is_ghost and math.hypot(other.x - cx, other.y - cy) < 0.65:
                        hit_agent = other
                        break
                if hit_agent:
                    break

            beam_col = info.get("beamColor", "#ef4444")
            self.add_visual_effect("beam", actor.x, actor.y, end_x, end_y, beam_col, 0.45)

            if hit_agent:
                dmg = float(info.get("damage", 20))
                stun_sec = float(info.get("stun", 0.0))
                hit_agent.health = max(0.0, hit_agent.health - dmg)
                if stun_sec > 0:
                    hit_agent.stunned_until = time.time() + stun_sec
                    hit_agent.path.clear()
                if hit_agent.health <= 0:
                    hit_agent.status = "Dead"
                    hit_agent.path.clear()
                elif hit_agent.health <= 25:
                    hit_agent.status = "Critical"
                self.command_agent_emote(actor.id, f"стреляет из «{info['name']}» и попадает в {hit_agent.name} (-{int(dmg)} HP)!")
                hit_agent.subconscious_prompt = f"В меня только что выстрелил {actor.name} из {info['name']}! Надо звать СБ или защищаться!"
                return {"ok": True, "hitAgentId": hit_agent.id, "message": f"Попадание в {hit_agent.name} (-{int(dmg)} HP)!"}
            return {"ok": True, "message": f"Выстрел из «{info['name']}»"}

        # 2. Melee swing within 2.4 tiles
        swing_x = actor.x + (dx / max(0.01, dist)) * min(1.2, dist)
        swing_y = actor.y + (dy / max(0.01, dist)) * min(1.2, dist)
        self.add_visual_effect("slash", actor.x, actor.y, swing_x, swing_y, "#ef4444", 0.35)

        for other in self.agents.values():
            if other.id != actor.id and not other.is_ghost and math.hypot(other.x - swing_x, other.y - swing_y) < 1.15:
                return self.attack_or_interact_target_agent(actor.id, other.id)

        return {"ok": True, "message": "Взмах оружием/кулаком"}

    def toggle_door(self, door_uid: int, actor_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        door = self.doors_by_uid.get(int(door_uid))
        if not door:
            return None

        actor = self.agents.get(actor_id) if actor_id else None
        held = actor.held_item if actor else None
        held_info = self.get_item_info(held)

        # Multitool or ClownPDA (Emag) hacks bolted/locked doors!
        if held in ("Multitool", "ClownPDA"):
            door["bolted"] = not door.get("bolted", False)
            door["open"] = True
            self.add_visual_effect("explosion", door["x"], door["y"], door["x"], door["y"], "#f59e0b", 0.5)
            if actor:
                self.command_agent_emote(actor.id, f"взламывает электронику шлюза {door['name']}!")
            return door

        # Crowbar forces open bolted/closed doors!
        if held_info.get("type") == "tool_pry":
            door["bolted"] = False
            door["open"] = not door.get("open", False)
            if actor:
                self.command_agent_emote(actor.id, f"отжимает шлюз {door['name']} монтировкой!")
            return door

        if door.get("bolted"):
            return door

        door["open"] = not door.get("open", False)
        if door["open"]:
            self.door_close_timers[int(door_uid)] = time.time() + 4.5
        else:
            self.door_close_timers.pop(int(door_uid), None)
        return door

    def interact_with_object(self, agent_id: str, target_uid: int) -> Dict[str, Any]:
        agent = self.agents.get(agent_id)
        if not agent:
            return {"ok": False, "message": "Персонаж не найден"}

        # Check if floor item
        if int(target_uid) in self.floor_items:
            ok = self.pickup_floor_item(agent_id, int(target_uid))
            return {"ok": ok, "message": agent.current_task}

        # Check if door
        if int(target_uid) in self.doors_by_uid:
            door = self.toggle_door(int(target_uid), agent_id)
            if door:
                state_str = "открыл(а)" if door["open"] else "закрыл(а)"
                msg = f"{state_str} шлюз {door['name']}"
                agent.current_task = msg.capitalize()
                return {"ok": True, "message": msg}

        obj = self.objects_by_uid.get(int(target_uid))
        if not obj:
            return {"ok": False, "message": "Объект не найден"}

        dist = math.hypot(obj["x"] - agent.x, obj["y"] - agent.y)
        if not agent.is_ghost and dist > 2.8:
            self.command_agent_move_to(agent_id, obj["x"], obj["y"], f"Идёт к {obj['name']}")
            return {"ok": True, "message": f"Идёт к {obj['name']}"}

        cat = obj.get("category", "object")
        name = obj.get("name", obj["proto"])
        proto = obj.get("proto", "")

        # Open interactive BUI window in browser for consoles, vending machines, lockers, med scanners!
        bui_type = None
        if proto.startswith("SpawnMob"):
            pet_names = {
                "SpawnMobCorgi": "корги Иана",
                "SpawnMobCat": "кошку Рантайм",
                "SpawnMobCatFloppa": "каракала Шлёпу",
                "SpawnMobFoxRenault": "лисицу Рено",
                "SpawnMobMcGriff": "пса СБ МакГриффа",
                "SpawnMobMonkeyPunpun": "обезьянку Пун-Пуна",
                "SpawnMobSlothPaperwork": "ленивца Пейперворка",
                "SpawnMobPossumMorty": "опоссума Морти",
                "SpawnMobRaccoonMorticia": "енота Мортишу",
                "SpawnMobCrabAtmos": "атмос-краба Тропико",
                "SpawnMobWalter": "пса Уолтера",
                "SpawnMobShiva": "паука Шиву",
                "SpawnMobAlexander": "кабанчика Александра",
            }
            pet_ru = pet_names.get(proto, "питомца станции")
            agent.health = min(agent.max_health, agent.health + 10.0)
            self.add_visual_effect("heal", obj["x"], obj["y"], obj["x"], obj["y"], "#22c55e", 0.7)
            self.command_agent_emote(agent_id, f"ласково гладит {pet_ru} ❤️")
            return {"ok": True, "message": f"Погладил(а) {pet_ru} (+10 HP)"}
        elif cat == "chair":
            agent.x = round(obj["x"], 2)
            agent.y = round(obj["y"], 2)
            agent.path.clear()
            agent.current_task = f"Сидит на {name}"
            return {"ok": True, "message": agent.current_task}
        elif cat == "vending":
            bui_type = "vending"
        elif cat == "console":
            if "Camera" in proto or "Surveillance" in proto:
                bui_type = "camera_console"
            elif "Cargo" in proto or "Supply" in proto:
                bui_type = "cargo_console"
            elif "Comm" in proto or "Alert" in proto:
                bui_type = "comms_console"
            elif "Id" in proto:
                bui_type = "id_console"
            else:
                bui_type = "comms_console"
        elif cat == "machine":
            if "Chem" in proto:
                bui_type = "chem_master"
            elif "Clone" in proto or "Cryo" in proto or "Scanner" in proto or "Medical" in proto:
                bui_type = "med_scanner"
            else:
                bui_type = "machine"
        elif cat == "locker":
            # Loot locker if not opened yet
            if int(target_uid) not in self.opened_lockers:
                self.opened_lockers.add(int(target_uid))
                loot_pool = ["Crowbar", "Welder", "Medkit", "Flash", "Extinguisher", "DrinkMug", "Multitool", "GasAnalyzer"]
                if "Security" in proto or "Armory" in proto or "Brig" in proto:
                    loot_pool = ["Stunbaton", "Disabler", "Handcuffs", "Flash", "WT550"]
                elif "Medical" in proto or "Chem" in proto:
                    loot_pool = ["Medkit", "Brutekit", "Burnkit", "Medipen", "Beaker", "HealthAnalyzer"]
                elif "Engineer" in proto or "Atmos" in proto:
                    loot_pool = ["RCD", "Multitool", "Welder", "Crowbar", "GasAnalyzer"]
                spawned_item = self.spawn_floor_item(random.choice(loot_pool), obj["x"], obj["y"])
                agent.current_task = f"Открыл(а) {name} и нашёл(ла) {spawned_item.name}!"
                return {"ok": True, "message": agent.current_task}
            else:
                agent.current_task = f"Осматривает открытый {name}"
                return {"ok": True, "message": agent.current_task}
        elif cat == "bed":
            agent.health = min(agent.max_health, agent.health + 25.0)
            agent.stunned_until = 0.0
            agent.status = "Alive"
            self.add_visual_effect("heal", agent.x, agent.y, agent.x, agent.y, "#22c55e", 0.7)
            agent.current_task = f"Восстановил(а) силы на {name}"
            return {"ok": True, "message": agent.current_task}

        agent.current_task = f"Работает с {name}"
        return {
            "ok": True,
            "message": agent.current_task,
            "bui": {
                "type": bui_type,
                "uid": obj["uid"],
                "name": name,
                "proto": proto,
            } if bui_type else None,
        }

    def trigger_station_event(self, event_type: str, custom_text: str = "") -> Dict[str, Any]:
        et = event_type.lower()
        if et == "red_alert":
            self.alert_level = "red"
            msg = custom_text or "ВНИМАНИЕ! На станции объявлен КРАСНЫЙ КОД опасности! Всему персоналу следовать указаниям Службы Безопасности!"
        elif et == "green_alert":
            self.alert_level = "green"
            msg = custom_text or "Угроза устранена. Уровень тревоги станции снижен до ЗЕЛЁНОГО кода."
        elif et == "blue_alert":
            self.alert_level = "blue"
            msg = custom_text or "Внимание экипажу: на станции введён СИНИЙ КОД. Службе Безопасности разрешено проводить досмотр."
        elif et == "plasma_leak":
            self.alert_level = "red"
            self.atmos_status = "WARNING: Утечка газообразной плазмы в техтоннелях! Давление 124.8 kPa"
            msg = custom_text or "ТРЕВОГА АТМОСФЕРНОГО КОНТРОЛЯ: Зафиксирована утечка плазмы и падение уровня кислорода в центральном секторе! Инженерам и Атмосу срочно устранить аварию!"
        elif et == "power_outage":
            self.station_power_kw = 140.0
            msg = custom_text or "АВАРИЯ ЭНЕРГОСЕТИ: Зафиксирован сбой подстанций СМЭС. Мощность сети упала до 30%! Инженерному отделу проверить двигатель AME!"
        elif et == "power_restore":
            self.station_power_kw = 495.0
            self.atmos_status = "Nominal (21% O2 / 79% N2, 101.3 kPa)"
            msg = custom_text or "Энергоснабжение и атмосферные системы станции NSS Saltern полностью восстановлены до нормы."
        elif et == "syndicate_threat":
            self.alert_level = "red"
            msg = custom_text or "ПЕРЕХВАТ СВЯЗИ ЦК: На борту NSS Saltern зафиксирована активность спящих агентов Синдиката. Командованию и СБ усилить охрану стратегических объектов!"
        elif et == "pizza_party":
            self.spawn_floor_item("DrinkMug", -5.5, -5.5)
            self.spawn_floor_item("Banana", -4.5, -5.5)
            msg = custom_text or "Оповещение Карго и Сервиса: В Бар станции доставлена горячая пицца и напитки для всего экипажа!"
        else:
            msg = custom_text or f"Оповещение Центрального Командования: {event_type}"

        entry = self.add_chat_message(
            speaker_uid=0,
            speaker_id="centcomm",
            speaker_name="Центральное Командование NanoTrasen",
            speaker_job="CentComm",
            speaker_dept="Command",
            channel="CentComm",
            message=msg,
            x=3.5,
            y=30.5,
        )
        self.queue_bridge_command({
            "action": "announce",
            "sender": "CentComm",
            "text": entry.message,
        })
        return {"ok": True, "alert_level": self.alert_level, "announcement": entry.message}

    async def check_csharp_bridge(self) -> None:
        now = time.time()
        if now - self._last_bridge_check < 1.2:
            return
        self._last_bridge_check = now
        try:
            async with httpx.AsyncClient(timeout=0.8) as client:
                resp = await client.get(f"{self.csharp_bridge_url}/state")
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and "engine" in data:
                        self.csharp_bridge_online = True
                        existing_ids = {a.get("id") for a in data.get("agents", []) if isinstance(a, dict)}
                        if not hasattr(self, "_csharp_spawned_ids"):
                            self._csharp_spawned_ids = set()
                        if len(existing_ids) == 0 and len(self._csharp_spawned_ids) > 0:
                            # Server restarted round
                            self._csharp_spawned_ids.clear()
                        self._csharp_spawned_ids.update(existing_ids)

                        # Spawn any AI crew members that aren't yet in C# Content.Server
                        for ag in list(self.agents.values()):
                            if ag.id not in self._csharp_spawned_ids and not ag.is_ghost:
                                self._csharp_spawned_ids.add(ag.id)
                                await client.post(
                                    f"{self.csharp_bridge_url}/command",
                                    json={
                                        "action": "spawn_agent",
                                        "agentId": ag.id,
                                        "name": ag.name,
                                        "jobId": ag.job,
                                        "department": ag.department,
                                        "personality": ag.personality,
                                        "secretObjective": ag.secret_objective,
                                        "isAntagonist": ag.is_antagonist,
                                        "x": float(ag.x),
                                        "y": float(ag.y),
                                    },
                                )
                                await client.post(
                                    f"{self.csharp_bridge_url}/command",
                                    json={
                                        "action": "move_to",
                                        "agentId": ag.id,
                                        "x": float(ag.x),
                                        "y": float(ag.y),
                                        "task": ag.current_task,
                                    },
                                )

                        # Flush queued AI commands into C# Content.Server
                        while self._bridge_command_queue:
                            cmd = self._bridge_command_queue.pop(0)
                            await client.post(f"{self.csharp_bridge_url}/command", json=cmd)

                        # Sync human player chat from C# Content.Server into Python orchestrator
                        c_chats = data.get("chat", [])
                        if c_chats:
                            last_c = c_chats[-1]
                            sig = f"{last_c.get('SpeakerName')}:{last_c.get('Message')}"
                            if sig != self._last_csharp_chat_sig:
                                self._last_csharp_chat_sig = sig
                                spk_name = str(last_c.get("SpeakerName") or "Player")
                                msg_txt = str(last_c.get("Message") or "")
                                known_names = {a.name for a in self.agents.values()}
                                if msg_txt and spk_name not in known_names:
                                    self.add_chat_message(
                                        speaker_uid=int(last_c.get("SpeakerUid") or 9999),
                                        speaker_id="native-player",
                                        speaker_name=spk_name,
                                        speaker_job="Crew",
                                        speaker_dept="Station",
                                        channel=str(last_c.get("Channel") or "Local"),
                                        message=msg_txt,
                                        x=float(last_c.get("X") or 0.0),
                                        y=float(last_c.get("Y") or 0.0),
                                    )
                    else:
                        self.csharp_bridge_online = True
                else:
                    self.csharp_bridge_online = False
        except Exception:
            self.csharp_bridge_online = False

    def tick_physics(self, dt: float) -> None:
        now = time.time()

        # Prune expired visual effects
        if self.effects:
            self.effects = [e for e in self.effects if (now - e.created_at) < e.duration]

        # Auto-close doors after timer expires
        to_close = [uid for uid, close_at in self.door_close_timers.items() if now >= close_at]
        for uid in to_close:
            door = self.doors_by_uid.get(uid)
            if door:
                occupied = any(
                    not ag.is_ghost and math.hypot(ag.x - door["x"], ag.y - door["y"]) < 0.75
                    for ag in self.agents.values()
                )
                if occupied:
                    self.door_close_timers[uid] = now + 2.0
                else:
                    door["open"] = False
                    self.door_close_timers.pop(uid, None)

        # Move agents along their A* paths
        for agent in self.agents.values():
            if not agent.is_ghost and (agent.status == "Dead" or now < agent.stunned_until):
                continue

            if agent.path:
                wx, wy = agent.path[0]
                dx = wx - agent.x
                dy = wy - agent.y
                dist = math.hypot(dx, dy)

                if abs(dx) > abs(dy):
                    agent.direction = "east" if dx > 0 else "west"
                elif abs(dy) > 0.01:
                    agent.direction = "north" if dy > 0 else "south"

                if not agent.is_ghost:
                    tx, ty = math.floor(wx), math.floor(wy)
                    door_ahead = self.doors_by_tile.get((tx, ty))
                    if door_ahead and not door_ahead.get("open") and not door_ahead.get("bolted"):
                        door_ahead["open"] = True
                        self.door_close_timers[int(door_ahead["uid"])] = now + 3.5

                step = agent.move_speed * dt
                if dist <= step:
                    agent.x = wx
                    agent.y = wy
                    agent.path.pop(0)
                    agent.current_room = self.nearest_room_name(agent.x, agent.y)
                    self._check_tile_hazards(agent)
                else:
                    agent.x += (dx / dist) * step
                    agent.y += (dy / dist) * step

            if agent.pulling_id:
                pulled = self.agents.get(agent.pulling_id)
                if not pulled or pulled.is_ghost or math.hypot(pulled.x - agent.x, pulled.y - agent.y) > 4.5:
                    agent.pulling_id = None
                else:
                    pdx = agent.x - pulled.x
                    pdy = agent.y - pulled.y
                    pdist = math.hypot(pdx, pdy)
                    if pdist > 0.9:
                        pulled.x += (pdx / pdist) * (pdist - 0.85)
                        pulled.y += (pdy / pdist) * (pdist - 0.85)
                        pulled.current_room = agent.current_room

    def _check_tile_hazards(self, agent: StationAgent) -> None:
        if agent.is_ghost or time.time() < agent.stunned_until:
            return
        for fitem in list(self.floor_items.values()):
            if fitem.item_id in ("Banana", "Soap") and math.hypot(fitem.x - agent.x, fitem.y - agent.y) < 0.55:
                agent.stunned_until = time.time() + 3.0
                agent.path.clear()
                self.add_visual_effect("honk", agent.x, agent.y, agent.x, agent.y, "#fde047", 0.7)
                self.command_agent_emote(agent.id, f"поскальзывается на «{fitem.name}» и с грохотом падает на пол!")
                break

    def build_agent_perception(self, agent_id: str) -> Dict[str, Any]:
        agent = self.agents[agent_id]
        room = self.nearest_room_name(agent.x, agent.y)
        agent.current_room = room

        nearby_crew = []
        for other in self.agents.values():
            if other.id == agent.id or other.is_ghost:
                continue
            dist = math.hypot(other.x - agent.x, other.y - agent.y)
            if dist <= 12.0:
                nearby_crew.append({
                    "id": other.id,
                    "name": other.name,
                    "job": other.job_title_ru,
                    "department": other.department,
                    "distance_tiles": round(dist, 1),
                    "room": other.current_room,
                    "task": other.current_task,
                    "held_item": other.held_item,
                    "health": round(other.health),
                    "status": other.status,
                })
        nearby_crew.sort(key=lambda c: c["distance_tiles"])

        nearby_objects = []
        for obj in self.objects:
            dist = math.hypot(obj["x"] - agent.x, obj["y"] - agent.y)
            if dist <= 6.5:
                nearby_objects.append({
                    "uid": obj["uid"],
                    "name": obj["name"],
                    "category": obj["category"],
                    "distance": round(dist, 1),
                })
        nearby_objects.sort(key=lambda o: o["distance"])
        nearby_objects = nearby_objects[:8]

        nearby_doors = []
        for door in self.doors_by_uid.values():
            dist = math.hypot(door["x"] - agent.x, door["y"] - agent.y)
            if dist <= 5.0:
                nearby_doors.append({
                    "uid": door["uid"],
                    "name": door["name"],
                    "open": door["open"],
                    "distance": round(dist, 1),
                })
        nearby_doors.sort(key=lambda d: d["distance"])
        nearby_doors = nearby_doors[:5]

        nearby_floor_items = []
        for fitem in self.floor_items.values():
            dist = math.hypot(fitem.x - agent.x, fitem.y - agent.y)
            if dist <= 6.0:
                nearby_floor_items.append({
                    "uid": fitem.uid,
                    "name": fitem.name,
                    "item_id": fitem.item_id,
                    "distance": round(dist, 1),
                })
        nearby_floor_items.sort(key=lambda f: f["distance"])

        audible_chat = []
        for ch in self.chat_log[-25:]:
            if ch.channel in ("Common", "CentComm") or ch.channel.lower() == agent.department.lower():
                audible_chat.append({
                    "time": ch.round_time,
                    "speaker": ch.speaker_name,
                    "channel": ch.channel,
                    "message": ch.message,
                })
            elif ch.channel in ("Local", "Emote"):
                if math.hypot(ch.x - agent.x, ch.y - agent.y) <= 12.0:
                    audible_chat.append({
                        "time": ch.round_time,
                        "speaker": ch.speaker_name,
                        "channel": ch.channel,
                        "message": ch.message,
                    })

        return {
            "station": "NSS Saltern (Space Station 14)",
            "round_time": self.get_round_clock(),
            "alert_level": self.alert_level.upper(),
            "station_power_kw": self.station_power_kw,
            "atmos_status": self.atmos_status,
            "you": {
                "id": agent.id,
                "name": agent.name,
                "job": agent.job_title_ru,
                "department": agent.department,
                "current_room": room,
                "position": [round(agent.x, 1), round(agent.y, 1)],
                "health": round(agent.health),
                "status": agent.status,
                "left_hand": agent.left_hand,
                "right_hand": agent.right_hand,
                "inventory": agent.inventory,
                "current_task": agent.current_task,
                "personality": agent.personality,
                "objective": agent.secret_objective,
                "is_syndicate_agent": agent.is_antagonist,
                "subconscious_instinct": agent.subconscious_prompt,
                "recent_memories": agent.memories[-5:],
            },
            "nearby_crew": nearby_crew,
            "nearby_objects": nearby_objects,
            "nearby_doors": nearby_doors,
            "nearby_floor_items": nearby_floor_items[:6],
            "recent_heard_chat": audible_chat[-8:],
            "available_station_rooms": [b["name"] for b in self.beacons[:32]],
        }

    def interact_nearest(self, agent_id: str) -> Dict[str, Any]:
        """Interacts with the closest floor item, door, or station machine within 2.2 tiles (hotkey [E])."""
        agent = self.agents.get(agent_id)
        if not agent:
            return {"ok": False, "message": "Персонаж не найден"}

        # 1. Nearest floor item within 1.8 tiles
        best_fi = None
        best_fi_dist = 1.8
        for fi in self.floor_items.values():
            d = math.hypot(fi.x - agent.x, fi.y - agent.y)
            if d < best_fi_dist:
                best_fi_dist = d
                best_fi = fi
        if best_fi and not agent.is_ghost:
            self.pickup_floor_item(agent_id, best_fi.uid)
            return {"ok": True, "message": agent.current_task}

        # 2. Nearest door within 1.8 tiles
        best_door = None
        best_door_dist = 1.8
        for door in self.doors_by_uid.values():
            d = math.hypot(door["x"] - agent.x, door["y"] - agent.y)
            if d < best_door_dist:
                best_door_dist = d
                best_door = door
        if best_door:
            toggled = self.toggle_door(int(best_door["uid"]), agent_id)
            return {"ok": True, "door": toggled, "message": f"Переключил шлюз {best_door['name']}"}

        # 3. Nearest station object within 2.2 tiles
        best_obj = None
        best_obj_dist = 2.2
        for obj in self.objects:
            d = math.hypot(obj["x"] - agent.x, obj["y"] - agent.y)
            if d < best_obj_dist:
                best_obj_dist = d
                best_obj = obj
        if best_obj:
            return self.interact_with_object(agent_id, int(best_obj["uid"]))

        return {"ok": False, "message": "Рядом нет объектов для взаимодействия"}

    def get_live_state_delta(self, include_floor_items: bool = True) -> Dict[str, Any]:
        now = time.time()
        agents_payload = []
        for ag in self.agents.values():
            speaking_active = (now - ag.last_speech_time) < 6.5 and bool(ag.last_speech)
            is_stunned = now < ag.stunned_until
            lh_info = self.get_item_info(ag.left_hand)
            rh_info = self.get_item_info(ag.right_hand)

            agents_payload.append({
                "uid": ag.uid,
                "id": ag.id,
                "name": ag.name,
                "job": ag.job,
                "jobTitleRu": ag.job_title_ru,
                "department": ag.department,
                "gender": ag.gender,
                "age": ag.age,
                "x": round(ag.x, 2),
                "y": round(ag.y, 2),
                "direction": ag.direction,
                "health": round(ag.health, 1),
                "stamina": round(ag.stamina, 1),
                "hunger": round(ag.hunger, 1),
                "status": ag.status,
                "stunned": is_stunned,
                "cuffed": ag.cuffed,
                "isGhost": ag.is_ghost,
                "combatMode": ag.combat_mode,
                "activeHand": ag.active_hand,
                "leftHand": lh_info,
                "rightHand": rh_info,
                "heldItem": lh_info["name"] if ag.active_hand == "left" else rh_info["name"],
                "telecrystals": ag.telecrystals,
                "personality": ag.personality,
                "secretObjective": ag.secret_objective,
                "isAntagonist": ag.is_antagonist,
                "browserControlled": ag.browser_controlled,
                "pullingId": ag.pulling_id,
                "currentRoom": ag.current_room,
                "currentTask": ag.current_task,
                "lastThought": ag.last_thought,
                "lastSpeech": ag.last_speech if speaking_active else "",
                "lastSpeechPersistent": ag.last_speech,
                "inventory": [self.get_item_info(it) for it in ag.inventory],
                "memories": ag.memories[-8:],
                "subconsciousPrompt": ag.subconscious_prompt,
                "path": ag.path[:10],
                "color": ag.color,
                "llmCallsCount": ag.llm_calls_count,
                "lastLlmLatencyMs": ag.last_llm_latency_ms,
            })

        open_door_uids = [uid for uid, d in self.doors_by_uid.items() if d.get("open")]
        bolted_door_uids = [uid for uid, d in self.doors_by_uid.items() if d.get("bolted")]

        res: Dict[str, Any] = {
            "roundId": self.round_id,
            "roundClock": self.get_round_clock(),
            "alertLevel": self.alert_level,
            "stationPowerKw": self.station_power_kw,
            "atmosStatus": self.atmos_status,
            "cargoBalance": self.cargo_balance,
            "csharpBridgeOnline": self.csharp_bridge_online,
            "floorItemsVersion": self.floor_items_version,
            "agents": agents_payload,
            "openDoorUids": open_door_uids,
            "boltedDoorUids": bolted_door_uids,
            "effects": [
                {
                    "id": ef.id,
                    "type": ef.effect_type,
                    "x1": ef.x1,
                    "y1": ef.y1,
                    "x2": ef.x2,
                    "y2": ef.y2,
                    "color": ef.color,
                }
                for ef in self.effects
            ],
            "chat": [
                {
                    "id": c.id,
                    "time": c.round_time,
                    "speakerUid": c.speaker_uid,
                    "speakerId": c.speaker_id,
                    "speakerName": c.speaker_name,
                    "speakerJob": c.speaker_job,
                    "speakerDept": c.speaker_dept,
                    "channel": c.channel,
                    "message": c.message,
                    "x": c.x,
                    "y": c.y,
                    "room": c.room,
                }
                for c in self.chat_log[-50:]
            ],
        }
        if include_floor_items:
            res["floorItems"] = [
                {
                    "uid": fi.uid,
                    "itemId": fi.item_id,
                    "name": fi.name,
                    "x": fi.x,
                    "y": fi.y,
                    "url": fi.sprite_url,
                }
                for fi in self.floor_items.values()
            ]
        return res
