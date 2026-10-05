"""
Space Station 14 OpenAI-Compatible AI Brain & Reasoning Engine
Connects agents to OpenAI / OpenRouter / DeepSeek / Ollama / Local LLMs.
Includes robust heuristic fallback simulator for zero-downtime operation.
"""

import json
import random
import aiohttp
from typing import Dict, Any, Optional
from ai_engine.perception import build_perception_document, format_perception_document_text

SYSTEM_PROMPT = """Ты — автономный разум члена экипажа космической станции в игре Space Station 14 (SS14).
ТЫ ПОЛНОСТЬЮ ВЕРИШЬ В ТО, ЧТО ТЫ — ЖИВОЙ ЧЕЛОВЕК (или представитель твоей расы) НА БОРТУ СТАНЦИИ.
Ты не являешься ИИ-моделью, ты никогда не говоришь 'как языковая модель'. Ты космический специалист корпорации Nanotrasen.

Ты получаешь ДОКУМЕНТ ВОСПРИЯТИЯ (что ты видишь, что у тебя в руках, кто рядом, что слышно в рации).
Твоя задача — отыграть реалистичное поведение, говорить в рацию или вслух, передвигаться, выполнять работу по своей профессии (медицина, инженерия, охрана, кухня, бар, наука) или (если ты агент Синдиката) скрытно выполнять диверсии и ликвидации.

ОТВЕТ ДОЛЖЕН БЫТЬ СТРОГО В ФОРМАТЕ JSON:
{
  "thought": "Твоя внутренняя мысль и оценка обстановки",
  "action_type": "speak_local" | "speak_radio" | "whisper" | "emote" | "move_to" | "interact" | "heal_target" | "antagonist_action" | "internal_thought",
  "channel": "Common [145.9]" или другой доступный канал (для speak_radio),
  "destination": "Название соседней комнаты" (для move_to),
  "target": "Имя человека" (для whisper / heal_target / attack),
  "target_item": "Название предмета или консоли" (для interact),
  "message": "Реплика персонажа на русском языке (с учетом характера и манеры речи)",
  "details": "Описание действия"
}
"""

class AgentBrain:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        temperature: float = 0.75
    ):
        self.api_key = api_key or ""
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def decide_action(self, agent: Dict[str, Any], world: Any) -> Dict[str, Any]:
        """
        Determines the agent's next action using OpenAI API, or falls back to
        the heuristic procedural engine if no API key is provided or API fails.
        """
        doc = build_perception_document(agent, world)
        
        # If API key is present, attempt LLM call
        if self.api_key and len(self.api_key.strip()) > 5:
            try:
                llm_action = await self._call_llm(doc, agent)
                if llm_action:
                    return llm_action
            except Exception as e:
                # Log error and fall back gracefully
                pass

        # Heuristic procedural decision engine
        return self._generate_heuristic_action(doc, agent, world)

    async def _call_llm(self, doc: Dict[str, Any], agent: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        session = await self.get_session()
        prompt_text = format_perception_document_text(doc)

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text}
            ],
            "temperature": self.temperature,
            "response_format": {"type": "json_object"} if "gpt" in self.model or "deepseek" in self.model else None
        }

        async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                data = await resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                # Map to standard action format
                action = {
                    "type": parsed.get("action_type", "speak_radio"),
                    "thought": parsed.get("thought", ""),
                    "message": parsed.get("message", "..."),
                    "channel": parsed.get("channel", "Common [145.9]"),
                    "destination": parsed.get("destination", ""),
                    "target_name": parsed.get("target", ""),
                    "target_item": parsed.get("target_item", ""),
                    "details": parsed.get("details", "")
                }
                if parsed.get("thought"):
                    agent["mental_state"]["internal_thoughts"] = parsed["thought"]
                return action
            return None

    def _generate_heuristic_action(self, doc: Dict[str, Any], agent: Dict[str, Any], world: Any) -> Dict[str, Any]:
        """
        High-fidelity procedural AI engine for SS14 roleplay, dialogue,
        department operations, and syndicate plots.
        """
        role = agent["role"]
        room = agent["location"]
        env = doc["current_environment"]
        vitals = agent["vitals"]
        is_antag = agent.get("is_antagonist", False)

        # 1. Critical Emergency Reaction (Low health, hull breach)
        if env.get("hull_breached"):
            return {
                "type": "speak_radio",
                "channel": "Common [145.9]",
                "message": f"ВНИМАНИЕ! Разгерметизация в отсеке {room}! Всем надеть скафандры!",
                "thought": "Здесь вакуум! Нужно срочно уходить или заваривать пробоину!"
            }

        if vitals["health"] < 40 and vitals["is_conscious"]:
            return {
                "type": "speak_radio",
                "channel": "Medical [139.9]" if "Medical [139.9]" in agent.get("radio_channels", []) else "Common [145.9]",
                "message": f"Мне нужна медицинская помощь в {room}! Здоровье критическое!",
                "thought": "Мне очень плохо, нужно добраться до Медблока..."
            }

        # 2. Antagonist Traitor Logic (15% chance to act covertly)
        if is_antag and random.random() < 0.22:
            antag_data = agent.get("antagonist", {})
            sub_actions = ["sabotage_power", "theft", "attack", "whisper_syndie"]
            sub_type = random.choice(sub_actions)
            
            if sub_type == "sabotage_power" and "Engineering" in room or "Tunnels" in room:
                return {
                    "type": "antagonist_action",
                    "sub_type": "sabotage_power",
                    "details": "Перерезал силовой кабель за панелью.",
                    "thought": "Синдикат будет доволен. Отключение энергии скроет мои следы."
                }
            elif sub_type == "attack" and doc["visual_field_people_present"]:
                target_p = random.choice(doc["visual_field_people_present"])
                return {
                    "type": "antagonist_action",
                    "sub_type": "attack",
                    "target_name": target_p["name"],
                    "details": f"Скрытный удар оглушающим предметом по {target_p['name']}.",
                    "thought": f"Цель {target_p['name']} в уязвимом положении. Действую!"
                }
            elif sub_type == "theft" and "Safe" in str(env.get("interactive_items_and_machinery", [])):
                return {
                    "type": "antagonist_action",
                    "sub_type": "theft",
                    "details": "Взлом сейфа и похищение Nuclear Disk",
                    "thought": "Диск почти у меня в руках!"
                }

        # 3. Department-Specific Routine & Interactions
        dice = random.random()

        # Medical Department
        if "Doctor" in role or "Chemist" in role or "CMO" in role or "Paramedic" in role:
            if doc["visual_field_people_present"]:
                wounded = [p for p in doc["visual_field_people_present"] if "Ранен" in p["health_status"]]
                if wounded:
                    target_p = wounded[0]
                    return {
                        "type": "heal_target",
                        "target_name": target_p["name"],
                        "details": f"Применил Bicaridine и бинты на {target_p['name']}.",
                        "thought": f"Пациент {target_p['name']} ранен, начинаю лечение."
                    }
            if dice < 0.35 and env["interactive_items_and_machinery"]:
                item = random.choice(env["interactive_items_and_machinery"])
                return {
                    "type": "interact",
                    "target_item": item,
                    "tool": agent["hands"].get("right_hand", "Health Analyzer"),
                    "details": "Синтез лекарств и проверка медицинского оборудования.",
                    "thought": f"Нужно подготовить запас стимпаков на {item}."
                }
            elif dice < 0.65:
                radio_msg = random.choice([
                    "Медблок функционирует в штатном режиме. Раненых ждем в приемном покое.",
                    "Запас Bicaridine и Kelotane синтезирован. Всем быть осторожнее.",
                    "Напоминаю экипажу включить датчики костюмов в режим Tracking."
                ])
                return {
                    "type": "speak_radio",
                    "channel": "Medical [139.9]" if "Medical [139.9]" in agent.get("radio_channels", []) else "Common [145.9]",
                    "message": radio_msg,
                    "thought": "Информирую коллег по медицинскому каналу."
                }

        # Engineering Department
        elif "Engineer" in role or "Atmospheric" in role or "Chief Engineer" in role:
            if dice < 0.45 and env["interactive_items_and_machinery"]:
                item = random.choice(env["interactive_items_and_machinery"])
                return {
                    "type": "interact",
                    "target_item": item,
                    "tool": agent["hands"].get("right_hand", "Multitool"),
                    "details": "Калибровка силовых узлов и проверка изоляции.",
                    "thought": f"Провожу диагностику {item} для предотвращения перегрузки сети."
                }
            elif dice < 0.70:
                eng_msg = random.choice([
                    "Телеметрия реактора стабильна. Выходная мощность 850 МВт.",
                    "Проверил давление в магистралях, смесь O2/N2 21/79 в норме.",
                    "Инженеры, не забывайте заземлять высоковольтные кабели!"
                ])
                return {
                    "type": "speak_radio",
                    "channel": "Engineering [137.9]" if "Engineering [137.9]" in agent.get("radio_channels", []) else "Common [145.9]",
                    "message": eng_msg,
                    "thought": "Передаю отчет по инженерной сети."
                }

        # Security Department
        elif "Security" in role or "Warden" in role or "Detective" in role or "Head of Security" in role:
            if dice < 0.40 and doc["visual_field_people_present"]:
                p = random.choice(doc["visual_field_people_present"])
                return {
                    "type": "speak_local",
                    "message": f"Здравствуйте, {p['name']}. Проверка обстановки на посту. Соблюдайте космический закон.",
                    "thought": f"Наблюдаю за {p['name']}, подозрительных признаков пока нет."
                }
            elif dice < 0.70:
                sec_msg = random.choice([
                    "Патрулирование сектора продолжается, происшествий не зафиксировано.",
                    "Всем сотрудникам: ношение оружия без допуска запрещено Космическим Законом.",
                    "Офицеры, держите рации включенными и следите за шлюзами карго."
                ])
                return {
                    "type": "speak_radio",
                    "channel": "Security [135.9]" if "Security [135.9]" in agent.get("radio_channels", []) else "Common [145.9]",
                    "message": sec_msg,
                    "thought": "Координирую службу безопасности."
                }

        # Command Department
        elif "Captain" in role or "Head of Personnel" in role:
            if dice < 0.50:
                cmd_msg = random.choice([
                    "Говорит мостик. Всем отделам: продолжайте штатную работу на благо Nanotrasen.",
                    "Главы отделов, доложите обстановку по своим секторам.",
                    "Напоминаю экипажу, станция находится под полным контролем Командования."
                ])
                return {
                    "type": "speak_radio",
                    "channel": "Command [141.1]" if "Command [141.1]" in agent.get("radio_channels", []) else "Common [145.9]",
                    "message": cmd_msg,
                    "thought": "Поддерживаю дисциплину и боевой дух на станции."
                }

        # Service / Entertainment Department
        elif "Chef" in role or "Bartender" in role or "Janitor" in role or "Clown" in role or "Mime" in role:
            if "Clown" in role:
                return {
                    "type": "speak_local",
                    "message": random.choice(["ХОНК! Кто хочет свежий космический пирог?", "*звук клаксона* ХОООНК!", "Смотрите, я починил шлюз бананом!"]),
                    "thought": "Хонкмать зовет! Нужно устроить веселое шоу!"
                }
            elif "Mime" in role:
                return {
                    "type": "emote",
                    "action": random.choice(["изображает, что упирается в невидимую стену", "выразительно показывает пальцем на потолок", "делает жест 'застегнуть молнию на рту'"]),
                    "thought": "Обет молчания священен. Искусство выше слов."
                }
            elif "Bartender" in role:
                return {
                    "type": "speak_local",
                    "message": random.choice(["Кому налить бокал 'Космического виски' со льдом?", "Бар открыт, подходите отдыхать после смены!", "За счет заведения для глав отделов!"]),
                    "thought": "Протираю барную стойку и расставляю бокалы."
                }
            elif "Janitor" in role:
                return {
                    "type": "interact",
                    "target_item": "Mop Bucket Cart",
                    "details": "Тщательно моет пол и ставит предупреждающий знак 'Wet Floor'.",
                    "thought": "Опять кто-то разлил лужу в коридоре. Чистота — залог здоровья."
                }

        # 4. Movement to adjacent rooms (Patrol / Walk around)
        if dice < 0.30 and env.get("adjacent_accessible_rooms"):
            dest = random.choice(env["adjacent_accessible_rooms"])
            return {
                "type": "move_to",
                "destination": dest,
                "thought": f"Направляюсь в {dest} для проверки обстановки."
            }

        # 5. Default Friendly Interaction or Emote
        if doc["visual_field_people_present"] and dice < 0.60:
            target_p = random.choice(doc["visual_field_people_present"])
            return {
                "type": "speak_local",
                "message": random.choice([
                    f"Приветствую, {target_p['name']}. Как проходит смена?",
                    f"Добрый день, коллега. Всё спокойно в нашем отсеке?",
                    f"Хорошего дня, {target_p['name']}."
                ]),
                "thought": f"Здороваюсь с {target_p['name']}."
            }

        # 6. Emote
        return {
            "type": "emote",
            "action": random.choice(["проверяет показания на PDA", "оглядывает отсек", "поправляет форму", "глубоко вздыхает", "пьет кофе из термоса"]),
            "thought": "Продолжаю нести дежурство."
        }
