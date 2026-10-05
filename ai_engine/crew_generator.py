"""
Space Station 14 AI Crew Generator
Generates 20-40 unique AI crew members with immersive personalities,
realistic department jobs, backstories, speech quirks, and secret antagonist roles.
"""

import random
import uuid
from typing import List, Dict, Any, Optional

DEPARTMENTS = {
    "Command": [
        {"role": "Captain", "title": "Капитан", "access": "All", "rank": 10},
        {"role": "Head of Personnel", "title": "Глава Персонала (HoP)", "access": "Command, Service, Cargo", "rank": 8},
        {"role": "Head of Security", "title": "Глава Службы Безопасности (HoS)", "access": "Command, Security", "rank": 8},
        {"role": "Chief Engineer", "title": "Старший Инженер (CE)", "access": "Command, Engineering", "rank": 8},
        {"role": "Research Director", "title": "Научный Руководитель (RD)", "access": "Command, Science", "rank": 8},
        {"role": "Chief Medical Officer", "title": "Главный Врач (CMO)", "access": "Command, Medical", "rank": 8},
    ],
    "Security": [
        {"role": "Warden", "title": "Смотритель БРИГа", "access": "Security, Brig, Armory", "rank": 6},
        {"role": "Detective", "title": "Детектив", "access": "Security, Crime Scenes", "rank": 5},
        {"role": "Security Officer", "title": "Офицер СБ", "access": "Security", "rank": 4},
        {"role": "Security Officer", "title": "Офицер СБ", "access": "Security", "rank": 4},
        {"role": "Security Cadet", "title": "Кадет СБ", "access": "Security-Basic", "rank": 2},
    ],
    "Engineering": [
        {"role": "Station Engineer", "title": "Инженер Станции", "access": "Engineering, Construction", "rank": 5},
        {"role": "Station Engineer", "title": "Инженер Станции", "access": "Engineering, Construction", "rank": 5},
        {"role": "Atmospheric Technician", "title": "Атмосферный Техник", "access": "Engineering, Atmospherics", "rank": 5},
        {"role": "Atmospheric Technician", "title": "Атмосферный Техник", "access": "Engineering, Atmospherics", "rank": 5},
        {"role": "Technical Assistant", "title": "Помощник Инженера", "access": "Engineering-Basic", "rank": 2},
    ],
    "Medical": [
        {"role": "Medical Doctor", "title": "Врач Терапевт", "access": "Medical, Surgery", "rank": 5},
        {"role": "Medical Doctor", "title": "Врач Хирург", "access": "Medical, Surgery", "rank": 5},
        {"role": "Chemist", "title": "Химик-Фармацевт", "access": "Medical, Chemistry", "rank": 5},
        {"role": "Paramedic", "title": "Парамедик", "access": "Medical, Maintenance", "rank": 4},
        {"role": "Virologist", "title": "Вирусолог", "access": "Medical, Virology", "rank": 5},
        {"role": "Medical Intern", "title": "Интерн Медблока", "access": "Medical-Basic", "rank": 2},
    ],
    "Science": [
        {"role": "Scientist", "title": "Ученый Исследователь", "access": "Science, R&D", "rank": 5},
        {"role": "Scientist", "title": "Ученый Экспериментатор", "access": "Science, Artifact Lab", "rank": 5},
        {"role": "Roboticist", "title": "Робототехник", "access": "Science, Robotics", "rank": 5},
        {"role": "Research Assistant", "title": "Лаборант", "access": "Science-Basic", "rank": 2},
    ],
    "Cargo": [
        {"role": "Quartermaster", "title": "Квартирмейстер (QM)", "access": "Cargo, Quartermaster", "rank": 6},
        {"role": "Cargo Technician", "title": "Грузчик Карго", "access": "Cargo", "rank": 4},
        {"role": "Cargo Technician", "title": "Грузчик Карго", "access": "Cargo", "rank": 4},
        {"role": "Salvage Specialist", "title": "Шахтер-Утилизатор", "access": "Cargo, Salvage", "rank": 4},
    ],
    "Service": [
        {"role": "Bartender", "title": "Бармен", "access": "Service, Bar", "rank": 4},
        {"role": "Chef", "title": "Шеф-Повар", "access": "Service, Kitchen", "rank": 4},
        {"role": "Botanist", "title": "Ботаник-Гидропоник", "access": "Service, Hydroponics", "rank": 4},
        {"role": "Janitor", "title": "Уборщик Станции", "access": "Service, Maintenance, Janitor", "rank": 3},
        {"role": "Clown", "title": "Клоун Станции", "access": "Service, Theater", "rank": 1},
        {"role": "Mime", "title": "Мим", "access": "Service, Theater", "rank": 1},
        {"role": "Chaplain", "title": "Капеллан", "access": "Service, Chapel", "rank": 3},
        {"role": "Passenger", "title": "Пассажир / Ассистент", "access": "Public", "rank": 1},
        {"role": "Passenger", "title": "Пассажир / Ассистент", "access": "Public", "rank": 1},
    ]
}

SPECIES = [
    {"name": "Human", "weight": 70, "desc": "Человек. Стандартный представитель Nanotrasen."},
    {"name": "Reptilian", "weight": 10, "desc": "Унатх (Рептилоид). Гордый воин из кланов Могхес, говорит с шипением (с-с-с)."},
    {"name": "Diona", "weight": 5, "desc": "Диона. Растениевидное разумное скопление нимф, мыслит медленно и философски."},
    {"name": "Slime Person", "weight": 5, "desc": "Слаймолюд. Биологическая масса, любит тепло и влагу, эластичный."},
    {"name": "Moth", "weight": 5, "desc": "Никта (Моль). Хрупкое крылатое существо, обожает яркий свет и одежду, часто шелестит."},
    {"name": "Dwarf", "weight": 5, "desc": "Дварф. Низкорослый, крепкий, бородатый космический горняк или инженер."}
]

FIRST_NAMES_MALE = [
    "Alexander", "Marcus", "Dmitri", "Jack", "Viktor", "Lucas", "Arthur", "Gabriel",
    "Leon", "Ethan", "Sergei", "Klaus", "Hiroshi", "Owen", "Felix", "Nikolai", "Raymond",
    "Gideon", "Mikhail", "Tobias", "Sean", "Valentin", "Vincent", "Hector", "Julian"
]

FIRST_NAMES_FEMALE = [
    "Elena", "Sarah", "Anastasia", "Chloe", "Valeria", "Maya", "Victoria", "Diana",
    "Zoe", "Natasha", "Irina", "Claire", "Yuki", "Astrid", "Alisa", "Tatyana", "Freya",
    "Morgan", "Svetlana", "Nadia", "Eva", "Leila", "Iris", "Sofia", "Vera"
]

LAST_NAMES = [
    "Vance", "Kowalski", "Volkov", "Sterling", "Cross", "Chen", "Novak", "Hawthorne",
    "Petrov", "Mercer", "Sinclair", "Vasiliev", "Rostova", "Blackwood", "Sokolov",
    "Mori", "Solomon", "Kane", "Richter", "Dubois", "Ashford", "Morozov", "Frost"
]

PERSONALITY_TRAITS = [
    "Параноидальный и подозрительный ко всем",
    "Педантичный идеалист, следующий протоколам Nanotrasen до буквы",
    "Циничный ветеран дальнего космоса, пьет слишком много кофе",
    "Гиперактивный энтузиаст, вечно сует нос во все дела",
    "Меланхоличный философ, часто смотрящий в иллюминаторы",
    "Добродушный шутник и любитель баек",
    "Холодный прагматик, ценящий эффективность выше жизней",
    "Нервный новичок, боящийся разгерметизации и клоуна",
    "Фанатик чистоты и порядка на станции",
    "Бунтарь, недолюбливающий корпоративное начальство",
    "Трудоголик, не покидающий рабочее место даже при сирене",
    "Жадный карьерист, мечтающий о повышении"
]

SPEECH_PATTERNS = [
    "Использует профессиональный корпоративный жаргон NT",
    "Говорит кратко, четко, по-военному",
    "Часто заикается или делает нервные паузы...",
    "Использует научные термины и заумные аналогии",
    "Разговаривает весело с шутками и космическим сленгом",
    "Говорит спокойным, умиротворяющим и уверенным тоном",
    "Ворчит и постоянно жалуется на поломки и бюрократию",
    "Шипит некоторые звуки (с-с-с, ш-ш-ш)",
    "Общается только жестами и пантомимой (Мим)",
    "Смеется невпопад и вставляет 'ХОНК!' (Клоун)"
]

ANTAGONIST_ROLES = [
    {
        "type": "Syndicate Traitor",
        "title": "Спящий Агент Синдиката",
        "description": "Тайный агент Синдиката Cybersun/Gorlex с PDA аплинком. Получил шифрованные приказы саботировать станцию или ликвидировать цель."
    },
    {
        "type": "Syndicate Infiltrator",
        "title": "Диверсант Синдиката",
        "description": "Специалист по проникновению и взлому систем станции. Задача — украсть диск ядерной аутентификации или технологии РнД."
    },
    {
        "type": "Mad Scientist / Rogue",
        "title": "Одержимый Еретик / Безумец",
        "description": "Тайно проводит запретные эксперименты или поклоняется древнему космическому существу. Жаждет открыть шлюзы в космос."
    },
    {
        "type": "Corrupt Corporate Embezzler",
        "title": "Коррумпированный Саботажник",
        "description": "Продает имущество станции контрабандистам, подделывает накладные и устраняет свидетелей."
    }
]

SYNDICATE_OBJECTIVES = [
    "Устранить Капитана и завладеть его антикварным лазерным пистолетом.",
    "Выкрасть Диск Ядерной Аутентификации (Nuclear Disk) из сейфа или капитанской каюты.",
    "Саботировать электросеть станции (отключить Сингулярность/Теслу/AME) и вызвать блэкаут.",
    "Выкрасть образец секретных исследований из РнД лаборатории.",
    "Уничтожить Главного Врача (CMO) и украсть гипоспрей с токсинами.",
    "Заминировать или разгерметизировать мостик управления станцией.",
    "Посеять панику, распространяя ложные сообщения о Синдикате по рации.",
    "Убедиться, что Глава Службы Безопасности (HoS) не доживет до конца смены.",
    "Успешно эвакуироваться на аварийном шаттле живым и свободным."
]

CREW_STATION_GOALS = [
    "Поддерживать стабильную работу реактора и не допустить обесточивания станции.",
    "Обеспечивать атмосферное давление 101.3 kPa и оптимальную концентрацию O2/N2.",
    "Своевременно лечить раненых членов экипажа и пополнять запасы медикаментов.",
    "Соблюдать Космический Закон (Space Law) и пресекать беспорядки на станции.",
    "Выполнить квоту научных исследований и улучшить оборудование станции.",
    "Обеспечить станцию едой, напитками и поддерживать чистоту в отсеках.",
    "Принять грузовой шаттл и выполнить экспортные контракты Nanotrasen.",
    "В случае критической аварии организовать безопасную эвакуацию экипажа."
]

def generate_crew_roster(target_count: int = 30, traitor_count: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Generates a full, balanced roster of 20-40 AI crew members.
    Distributes across all station departments, assigns personalities,
    starting equipment, beliefs, and secret traitor roles.
    """
    target_count = max(20, min(40, target_count))
    if traitor_count is None:
        traitor_count = max(2, min(5, int(target_count * 0.12)))

    # Collect available jobs
    all_jobs = []
    # Always include critical command roles
    all_jobs.append(DEPARTMENTS["Command"][0]) # Captain
    all_jobs.append(DEPARTMENTS["Command"][1]) # HoP
    all_jobs.append(DEPARTMENTS["Command"][2]) # HoS
    all_jobs.append(DEPARTMENTS["Command"][3]) # CE
    all_jobs.append(DEPARTMENTS["Command"][4]) # RD
    all_jobs.append(DEPARTMENTS["Command"][5]) # CMO

    # Fill department pools
    dept_pool = []
    for dept, jobs in DEPARTMENTS.items():
        if dept == "Command":
            continue
        dept_pool.extend(jobs)

    random.shuffle(dept_pool)

    # Pick jobs to reach target_count
    selected_jobs = list(all_jobs)
    while len(selected_jobs) < target_count:
        if dept_pool:
            selected_jobs.append(dept_pool.pop(0))
        else:
            # Add general passengers/assistants/engineers
            selected_jobs.append(random.choice(DEPARTMENTS["Service"] + DEPARTMENTS["Engineering"] + DEPARTMENTS["Medical"]))

    random.shuffle(selected_jobs)

    roster = []
    used_names = set()

    # Pick indices for traitors (avoiding Captain by default unless purely chaotic)
    potential_traitor_indices = [i for i, job in enumerate(selected_jobs) if job["role"] != "Captain"]
    traitor_indices = set(random.sample(potential_traitor_indices, min(traitor_count, len(potential_traitor_indices))))

    for idx, job in enumerate(selected_jobs):
        gender = random.choice(["Male", "Female"])
        first_name = random.choice(FIRST_NAMES_MALE if gender == "Male" else FIRST_NAMES_FEMALE)
        last_name = random.choice(LAST_NAMES)
        name = f"{first_name} {last_name}"
        while name in used_names:
            first_name = random.choice(FIRST_NAMES_MALE if gender == "Male" else FIRST_NAMES_FEMALE)
            last_name = random.choice(LAST_NAMES)
            name = f"{first_name} {last_name}"
        used_names.add(name)

        # Species selection
        species_choice = random.choices(
            [s["name"] for s in SPECIES],
            weights=[s["weight"] for s in SPECIES]
        )[0]
        species_info = next(s for s in SPECIES if s["name"] == species_choice)

        age = random.randint(22, 62)
        personality = random.choice(PERSONALITY_TRAITS)
        speech = random.choice(SPEECH_PATTERNS)
        if job["role"] == "Clown":
            speech = "Смеется невпопад, разбрасывает банановые кожурки и постоянно вставляет 'ХОНК!'"
        elif job["role"] == "Mime":
            speech = "Соблюдает строгий обет молчания. Изъясняется исключительно жестами, мимикой и пантомимой."

        # Assign Starting Room based on role
        starting_room = get_starting_room_for_role(job["role"])

        # Assign Starting Inventory
        hands, inventory = get_starting_inventory_for_role(job["role"], name)

        is_antagonist = idx in traitor_indices
        antag_data = None
        if is_antagonist:
            antag_template = random.choice(ANTAGONIST_ROLES)
            objectives = random.sample(SYNDICATE_OBJECTIVES, k=random.randint(2, 3))
            # If assassination objective mentions self, fix it
            fixed_objectives = []
            for obj in objectives:
                if name in obj:
                    obj = "Уничтожить станционную службу безопасности."
                fixed_objectives.append(obj)
            
            passcode = f"{random.choice(['Красный', 'Теневой', 'Секретный', 'Кибер'])} {random.randint(100, 999)}"
            antag_data = {
                "type": antag_template["type"],
                "title": antag_template["title"],
                "description": antag_template["description"],
                "syndicate_code": passcode,
                "uplink_code": f"140.{random.randint(1, 9)} MHz",
                "objectives": fixed_objectives,
                "completed_objectives": [],
                "telecrystals": 20
            }

        agent_id = f"agent_{uuid.uuid4().hex[:8]}"

        agent = {
            "id": agent_id,
            "name": name,
            "gender": gender,
            "age": age,
            "species": species_choice,
            "species_desc": species_info["desc"],
            "role": job["role"],
            "title": job["title"],
            "access_level": job["access"],
            "rank": job["rank"],
            "personality": personality,
            "speech_pattern": speech,
            "location": starting_room,
            "coordinates": {"x": random.randint(10, 80), "y": random.randint(10, 80)},
            "hands": hands,
            "inventory": inventory,
            "vitals": {
                "health": 100,
                "max_health": 100,
                "brute_damage": 0,
                "burn_damage": 0,
                "toxin_damage": 0,
                "suffocation_damage": 0,
                "stamina": 100,
                "is_conscious": True,
                "is_alive": True,
                "status_text": "Здоров, готов к работе"
            },
            "mental_state": {
                "mood": "Стабильное",
                "stress_level": random.randint(5, 25),
                "current_intent": f"Выполнять обязанности на должности {job['title']}",
                "internal_thoughts": f"Смена началась. Нужно проверить рабочее место в отсеке {starting_room}.",
                "recent_memories": [
                    f"Прибыл на станцию Space Station 14. Моя должность: {job['title']}.",
                    f"Назначен в отсек {starting_room}. Экипировка проверена."
                ]
            },
            "station_goals": random.sample(CREW_STATION_GOALS, k=2),
            "is_antagonist": is_antagonist,
            "antagonist": antag_data,
            "radio_channels": get_radio_channels_for_role(job["role"], is_antagonist),
            "total_actions": 0,
            "last_action_time": 0
        }

        roster.append(agent)

    return roster


def get_starting_room_for_role(role: str) -> str:
    mapping = {
        "Captain": "Bridge (Капитанский мостик)",
        "Head of Personnel": "Head of Personnel Office (Офис Главы Персонала)",
        "Head of Security": "Head of Security Office (Кабинет Главы СБ)",
        "Chief Engineer": "Chief Engineer Office (Кабинет Старшего Инженера)",
        "Research Director": "Research Director Office (Кабинет Научного Руководителя)",
        "Chief Medical Officer": "Chief Medical Officer Office (Кабинет Главврача)",
        "Warden": "Brig & Security Armory (Бриг и Оружейная)",
        "Detective": "Detective Office (Кабинет Детектива)",
        "Security Officer": "Security Office (Дежурная часть СБ)",
        "Security Cadet": "Security Briefing Room (Брифинг СБ)",
        "Station Engineer": "Engineering Workshop (Мастерская Инженеров)",
        "Atmospheric Technician": "Atmospherics Control (Атмосферный отсек)",
        "Technical Assistant": "Engineering Storage (Склад инструментов)",
        "Medical Doctor": "Medbay Treatment Center (Приемный покой Медблока)",
        "Chemist": "Chemistry Lab (Химическая Лаборатория)",
        "Paramedic": "Medbay Ambulance Bay (Гараж Парамедиков)",
        "Virologist": "Virology Isolation (Вирусологический бокс)",
        "Medical Intern": "Medbay Lobby (Холл Медблока)",
        "Scientist": "R&D Research Core (Научная Лаборатория)",
        "Roboticist": "Robotics Assembly (Цех Робототехники)",
        "Research Assistant": "Science Lobby (Холл Научного крыла)",
        "Quartermaster": "Cargo Office (Офис Квартирмейстера)",
        "Cargo Technician": "Cargo Bay (Грузовой терминал)",
        "Salvage Specialist": "Salvage Airlock (Шахтерский шлюз)",
        "Bartender": "Space Bar (Станционный Бар)",
        "Chef": "Kitchen & Mess Hall (Кухня и Столовая)",
        "Botanist": "Hydroponics Greenhouses (Гидропоника)",
        "Janitor": "Janitor Closet (Каморка Уборщика)",
        "Clown": "Theater / Central Hall (Театр и Центральный холл)",
        "Mime": "Theater / Stage (Сцена Театра)",
        "Chaplain": "Chapel (Часовня Космоса)",
        "Passenger": "Arrivals Hallway (Коридор Прибытия)",
    }
    return mapping.get(role, "Main Hallway (Главный коридор станции)")


def get_starting_inventory_for_role(role: str, name: str) -> tuple[Dict[str, str], Dict[str, str]]:
    hands = {"left_hand": "Empty (Пусто)", "right_hand": "Empty (Пусто)"}
    inventory = {
        "id_card": f"ID Card [{name} - {role}]",
        "pda": f"PDA [{role}] with Messenger & Flashlight",
        "headset": "Station Radio Headset",
        "suit": "Standard Uniform",
        "back": "Backpack",
        "belt": "Empty",
        "pocket1": "Emergency Survival Box (Pocket Mask + Mini O2 Tank)",
        "pocket2": "Empty"
    }

    if "Captain" in role:
        inventory["suit"] = "Captain's Armored Uniform & Cape"
        inventory["belt"] = "Antique Laser Gun Holster"
        hands["right_hand"] = "Captain's ID & Authentication Pin"
    elif "Security" in role or "Warden" in role or "Detective" in role:
        inventory["suit"] = "Security Armor Vest & Helmet"
        inventory["belt"] = "Security Belt (Stun Baton + Flashbang + Handcuffs)"
        hands["right_hand"] = "Stun Baton (Disabling)"
        if "Detective" in role:
            hands["left_hand"] = "Forensic Scanner"
            inventory["pocket2"] = "Revolver .38 Special"
    elif "Engineer" in role or "Atmospheric" in role:
        inventory["suit"] = "High-Visibility Engineering Jumpsuit"
        inventory["belt"] = "Utility Belt (Crowbar, Wrench, Screwdriver, Welder, Wirecutters)"
        inventory["back"] = "Engineering RIG & Oxygen Tank"
        hands["right_hand"] = "Multitool & Welder"
    elif "Medical" in role or "Chemist" in role or "Doctor" in role or "Virologist" in role or "Paramedic" in role:
        inventory["suit"] = "Sterile Medical Coat & Nitrile Gloves"
        inventory["belt"] = "Medical Belt (Health Analyzer, Syringe, Bicaridine, Kelotane)"
        hands["right_hand"] = "Health Analyzer"
        if "Chemist" in role:
            hands["left_hand"] = "Beaker 100ml (Empty)"
    elif "Scientist" in role or "Roboticist" in role:
        inventory["suit"] = "Science Labcoat & Protective Goggles"
        inventory["belt"] = "Scientist Belt (Network Configurator + Analyzer)"
        hands["right_hand"] = "Artifact Scanner"
    elif "Cargo" in role or "Quartermaster" in role or "Salvage" in role:
        inventory["suit"] = "Heavy Cargo Workwear"
        hands["right_hand"] = "Cargo Order Scanner Tablet"
        if "Salvage" in role:
            inventory["belt"] = "Mining Drill & Kinetic Accelerator"
    elif "Bartender" in role:
        inventory["suit"] = "Classic Bartender Vest & Bowtie"
        inventory["belt"] = "Bandolier of Glasses & Shakers"
        hands["right_hand"] = "Double-barrel Shotgun (Non-lethal Beanbag loaded)"
    elif "Chef" in role:
        inventory["suit"] = "Chef Apron & Hat"
        inventory["belt"] = "Knife Belt (Chef's Cleaver + Rolling Pin)"
        hands["right_hand"] = "Chef Knife"
    elif "Botanist" in role:
        inventory["suit"] = "Hydroponics Apron"
        inventory["belt"] = "Gardener Belt (Plant Analyzer + Weed Killer)"
        hands["right_hand"] = "Hydroponics Clippers"
    elif "Janitor" in role:
        inventory["suit"] = "Janitor Biohazard Suit"
        hands["right_hand"] = "Space Mop"
        hands["left_hand"] = "Bucket with Water & Bleach"
    elif "Clown" in role:
        inventory["suit"] = "Clown Colorful Jumpsuit & Squeaky Shoes"
        inventory["belt"] = "Horn & Whoopee Cushion"
        hands["right_hand"] = "Bike Horn (HONK!)"
        hands["left_hand"] = "Banana Peel"
    elif "Mime" in role:
        inventory["suit"] = "Black & White Striped Mime Suit & Beret"
        inventory["belt"] = "Bottle of Nothing"
        hands["right_hand"] = "Invisible Wall Generator (Mimic)"

    return hands, inventory


def get_radio_channels_for_role(role: str, is_antag: bool) -> List[str]:
    channels = ["Common [145.9]"]
    if "Captain" in role or "Head" in role or "Chief" in role or "Director" in role:
        channels.append("Command [141.1]")
    if "Security" in role or "Warden" in role or "Detective" in role or "Captain" in role or "Head of Security" in role:
        channels.append("Security [135.9]")
    if "Engineer" in role or "Atmospheric" in role or "Chief Engineer" in role or "Captain" in role:
        channels.append("Engineering [137.9]")
    if "Medical" in role or "Doctor" in role or "Chemist" in role or "Virologist" in role or "Paramedic" in role or "CMO" in role or "Captain" in role:
        channels.append("Medical [139.9]")
    if "Scientist" in role or "Roboticist" in role or "Research" in role or "Captain" in role:
        channels.append("Science [138.9]")
    if "Cargo" in role or "Quartermaster" in role or "Salvage" in role or "Captain" in role:
        channels.append("Cargo [136.9]")
    if "Bartender" in role or "Chef" in role or "Botanist" in role or "Janitor" in role or "Clown" in role or "Mime" in role or "Chaplain" in role:
        channels.append("Service [134.9]")
    if is_antag:
        channels.append("Syndicate Encrypted [???]")
    return channels
