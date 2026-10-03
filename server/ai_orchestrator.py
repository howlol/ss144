"""
OpenAI-Compatible Multi-Agent Cognitive Orchestrator for Space Station 14
Supports:
- Browser-Direct OpenAI API mode (browser calls `${baseUrl}/chat/completions` directly — bypasses sandbox/proxy restrictions and supports localhost Ollama/LM Studio!)
- Backend OpenAI API mode (server calls `${baseUrl}/chat/completions` directly in Google Colab / local server)
- Priority reaction queue (when the player speaks or attacks, nearby AI characters immediately query the OpenAI API to respond!)
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import httpx

from .ss14_station_runtime import SS14StationRuntime, StationAgent


SYSTEM_PROMPT_RU = """Ты — живой человек, член экипажа космической станции NSS Saltern во вселенной Space Station 14 (SS14).
ВАЖНОЕ ПРАВИЛО: Ты искренне убеждён, что ты настоящий сотрудник станции на орбите. Ты НЕ ИИ, НЕ языковая модель, НЕ бот. Никогда не выходи из роли!

Твоя задача — анализировать окружающую обстановку (кто рядом, какие предметы и шлюзы вокруг, что говорят по рации и вслух, твоё здоровье, твоя личность и секретная цель) и принимать ОДНО осмысленное решение в формате строгого JSON.

Доступные радиоканалы (если используешь радио в поле `say`, добавляй префикс в начале фразы):
- Без префикса: сказать вслух (слышат все в радиусе 10 тайлов в твоём отсеке)
- `;` — Общий канал станции (Common, слышат все на станции, например: `;Докладывает СБ, в Баре всё спокойно.`)
- `:c` — Командный канал (Command)
- `:s` — Канал Службы Безопасности (Security)
- `:e` — Канал Инженерного отдела (Engineering)
- `:m` — Канал Медицинского отдела (Medical)
- `:n` — Канал Научного отдела (Science)
- `:u` — Канал Снабжения / Карго (Cargo)

Отвечай СТРОГО валидным JSON-объектом следующей структуры (без лишнего текста вне JSON):
{
  "thought": "Твоя внутренняя мысль от первого лица (1-2 предложения: что ты сейчас чувствуешь, видишь и планируешь сделать)",
  "task": "Краткое описание текущего действия для статуса (например: Проверяю генератор AME / Патрулирую Бар)",
  "say": "Фраза, которую ты произносишь вслух или в рацию (или пустая строка \"\", если сейчас лучше промолчать)",
  "emote": "Невербальное действие от третьего лица (например: \"поправляет фуражку и хмурится\", или \"\")",
  "move_to_room": "Название отсека из списка available_station_rooms, куда ты хочешь пойти (или \"\", если остаёшься на месте)",
  "interact_uid": null,
  "memory_note": "Краткая запись в долговременную память о важном событии (или \"\")"
}
"""


@dataclass
class LLMConfig:
    api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    base_url: str = field(default_factory=lambda: os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    model: str = field(default_factory=lambda: os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    temperature: float = 0.85
    max_tokens: int = 320
    tick_interval_sec: float = 2.0
    concurrent_agents_per_tick: int = 2
    enabled: bool = True
    browser_direct_llm: bool = True  # Browser executes fetch() directly to OpenAI endpoint + server fallback


class AIStationOrchestrator:
    def __init__(self, runtime: SS14StationRuntime) -> None:
        self.runtime = runtime
        self.config = LLMConfig()
        self.total_llm_calls: int = 0
        self.total_llm_errors: int = 0
        self.last_error: str = ""
        self.api_logs: List[Dict[str, Any]] = []
        self._agent_rr_index: int = 0
        self.priority_agent_queue: List[str] = []
        self._last_browser_llm_ping: float = 0.0
        self._running: bool = False

    def get_public_config(self) -> Dict[str, Any]:
        masked_key = ""
        if self.config.api_key:
            if len(self.config.api_key) > 8:
                masked_key = self.config.api_key[:4] + "..." + self.config.api_key[-4:]
            else:
                masked_key = "***"
        return {
            "hasApiKey": bool(self.config.api_key.strip()),
            "maskedApiKey": masked_key,
            "baseUrl": self.config.base_url,
            "model": self.config.model,
            "temperature": self.config.temperature,
            "maxTokens": self.config.max_tokens,
            "tickIntervalSec": self.config.tick_interval_sec,
            "concurrentAgentsPerTick": self.config.concurrent_agents_per_tick,
            "enabled": self.config.enabled,
            "browserDirectLlm": self.config.browser_direct_llm,
            "totalLlmCalls": self.total_llm_calls,
            "totalLlmErrors": self.total_llm_errors,
            "lastError": self.last_error,
        }

    def update_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if "apiKey" in payload and payload["apiKey"] is not None:
            raw_key = str(payload["apiKey"]).strip()
            if raw_key or payload.get("clearKey"):
                self.config.api_key = raw_key
        if "baseUrl" in payload and payload["baseUrl"]:
            url = str(payload["baseUrl"]).strip().rstrip("/")
            if url.endswith("/chat/completions"):
                url = url[: -len("/chat/completions")]
            self.config.base_url = url
        if "model" in payload and payload["model"]:
            self.config.model = str(payload["model"]).strip()
        if "temperature" in payload:
            self.config.temperature = max(0.0, min(1.5, float(payload["temperature"])))
        if "tickIntervalSec" in payload:
            self.config.tick_interval_sec = max(0.8, min(30.0, float(payload["tickIntervalSec"])))
        if "concurrentAgentsPerTick" in payload:
            self.config.concurrent_agents_per_tick = max(1, min(6, int(payload["concurrentAgentsPerTick"])))
        if "enabled" in payload:
            self.config.enabled = bool(payload["enabled"])
        if "browserDirectLlm" in payload:
            self.config.browser_direct_llm = bool(payload["browserDirectLlm"])
        self.last_error = ""
        return self.get_public_config()

    def prioritize_nearby_agents(self, x: float, y: float, exclude_id: str = "") -> List[str]:
        """Queue closest AI agents to immediately react via OpenAI API when player speaks or acts."""
        candidates = []
        for ag in self.runtime.agents.values():
            if ag.id == exclude_id or ag.is_ghost or ag.browser_controlled or ag.status == "Dead":
                continue
            dist = ((ag.x - x) ** 2 + (ag.y - y) ** 2) ** 0.5
            if dist <= 14.0:
                candidates.append((dist, ag.id))
        candidates.sort(key=lambda item: item[0])
        chosen_ids = [cid for _d, cid in candidates[:3]]
        for cid in reversed(chosen_ids):
            if cid not in self.priority_agent_queue:
                self.priority_agent_queue.insert(0, cid)
        return chosen_ids

    def pick_next_agent_for_llm(self) -> Optional[StationAgent]:
        while self.priority_agent_queue:
            aid = self.priority_agent_queue.pop(0)
            ag = self.runtime.agents.get(aid)
            if ag and not ag.browser_controlled and not ag.is_ghost and ag.status != "Dead":
                return ag

        ai_agents = [
            a for a in self.runtime.agents.values()
            if not a.browser_controlled and not a.is_ghost and a.status != "Dead"
        ]
        if not ai_agents:
            return None
        agent = ai_agents[self._agent_rr_index % len(ai_agents)]
        self._agent_rr_index += 1
        return agent

    def build_agent_prompt_payload(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Returns the exact OpenAI messages payload for the specified (or next scheduled) AI agent."""
        self._last_browser_llm_ping = time.time()
        agent = self.runtime.agents.get(agent_id) if agent_id else self.pick_next_agent_for_llm()
        if not agent:
            return {"ok": False, "error": "Нет доступных ИИ-персонажей"}

        perception = self.runtime.build_agent_perception(agent.id)
        user_prompt = (
            "Текущее восприятие твоего персонажа на станции NSS Saltern:\n"
            f"{json.dumps(perception, ensure_ascii=False, indent=2)}\n\n"
            "Прими следующее решение в роли этого персонажа и верни JSON."
        )
        return {
            "ok": True,
            "agentId": agent.id,
            "agentName": agent.name,
            "agentJob": agent.job_title_ru,
            "systemPrompt": SYSTEM_PROMPT_RU,
            "userPrompt": user_prompt,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_RU},
                {"role": "user", "content": user_prompt},
            ],
        }

    def apply_external_llm_decision(
        self,
        agent_id: str,
        raw_content: str,
        latency_ms: int = 0,
        model_used: str = "",
        source: str = "browser-openai",
    ) -> Dict[str, Any]:
        self._last_browser_llm_ping = time.time()
        agent = self.runtime.agents.get(agent_id)
        if not agent:
            return {"ok": False, "error": "Персонаж не найден"}

        decision = self._extract_json_object(raw_content)
        if not decision:
            self.total_llm_errors += 1
            self.last_error = f"Не удалось распарсить JSON от модели ({source})"
            return {"ok": False, "error": self.last_error, "raw": raw_content[:300]}

        self.total_llm_calls += 1
        agent.llm_calls_count += 1
        agent.last_llm_latency_ms = int(latency_ms)
        agent.last_llm_time = time.time()
        self.last_error = ""

        self.api_logs.append({
            "time": self.runtime.get_round_clock(),
            "agent": agent.name,
            "job": agent.job_title_ru,
            "model": f"{model_used or self.config.model} ({source})",
            "latencyMs": int(latency_ms),
            "thought": decision.get("thought", ""),
            "say": decision.get("say", ""),
            "move": decision.get("move_to_room", ""),
        })
        if len(self.api_logs) > 60:
            self.api_logs = self.api_logs[-60:]

        self._apply_decision(agent, decision)
        return {"ok": True, "decision": decision, "totalLlmCalls": self.total_llm_calls}

    def record_external_llm_error(self, agent_id: str, error_msg: str, source: str = "browser-openai") -> None:
        self.total_llm_errors += 1
        self.last_error = f"[{source}] {error_msg}"
        ag = self.runtime.agents.get(agent_id)
        self.api_logs.append({
            "time": self.runtime.get_round_clock(),
            "agent": ag.name if ag else agent_id,
            "job": ag.job_title_ru if ag else "",
            "model": f"ERROR ({source})",
            "latencyMs": 0,
            "thought": f"Ошибка API: {error_msg}",
            "say": "",
            "move": "",
        })

    def _extract_json_object(self, raw_text: str) -> Optional[Dict[str, Any]]:
        if not raw_text:
            return None
        cleaned = raw_text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except Exception:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    return None
        return None

    async def query_openai_for_agent(self, agent: StationAgent) -> Optional[Dict[str, Any]]:
        if not self.config.api_key.strip():
            return None

        perception = self.runtime.build_agent_perception(agent.id)
        user_prompt = (
            "Текущее восприятие твоего персонажа на станции NSS Saltern:\n"
            f"{json.dumps(perception, ensure_ascii=False, indent=2)}\n\n"
            "Прими следующее решение в роли этого персонажа и верни JSON."
        )

        endpoint = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key.strip()}",
            "Content-Type": "application/json",
        }
        body: Dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_RU},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(endpoint, headers=headers, json=body)
                latency_ms = int((time.perf_counter() - t0) * 1000)

                if resp.status_code != 200:
                    err_txt = resp.text[:200]
                    self.last_error = f"HTTP {resp.status_code}: {err_txt}"
                    self.total_llm_errors += 1
                    return None

                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = self._extract_json_object(content)
                if not parsed:
                    self.last_error = "Модель вернула ответ не в формате JSON"
                    self.total_llm_errors += 1
                    return None

                self.total_llm_calls += 1
                agent.llm_calls_count += 1
                agent.last_llm_latency_ms = latency_ms
                agent.last_llm_time = time.time()
                self.last_error = ""

                self.api_logs.append({
                    "time": self.runtime.get_round_clock(),
                    "agent": agent.name,
                    "job": agent.job_title_ru,
                    "model": f"{self.config.model} (server)",
                    "latencyMs": latency_ms,
                    "thought": parsed.get("thought", ""),
                    "say": parsed.get("say", ""),
                    "move": parsed.get("move_to_room", ""),
                })
                if len(self.api_logs) > 60:
                    self.api_logs = self.api_logs[-60:]

                return parsed
        except Exception as exc:
            self.last_error = f"Backend network ({type(exc).__name__}): переключено на прямой вызов из браузера"
            return None

    def _generate_autonomous_routine_decision(self, agent: StationAgent) -> Dict[str, Any]:
        """Autonomous SS14 roleplay routines when waiting for LLM turn."""
        dept_rooms = {
            "Command": ["Bridge", "Captain", "HoP", "Bar", "CargoBay"],
            "Security": ["Brig", "Security", "Armory", "Bar", "CargoBay", "Medbay"],
            "Engineering": ["Engineering", "AME", "Atmospherics", "TechVault", "Power", "ToolStorage"],
            "Medical": ["Medbay", "Chemistry", "Cloning", "Cryogenics", "Morgue", "Bar"],
            "Science": ["Science", "ArtifactLab", "AnomalyGenerator", "ServerRoom", "Medbay"],
            "Cargo": ["CargoBay", "Quartermaster", "Salvage", "Bar", "ToolStorage"],
            "Service": ["Bar", "Kitchen", "Hydroponics", "Janitor", "Chapel", "Theatre"],
        }

        role_lines = {
            "Captain": [
                (";Главы отделов, доложите обстановку на станции NSS Saltern!", "Запрашиваю сводку у глав отделов по общей рации."),
                (":c Проверяю показатели жизнеобеспечения и сохранность ядерного диска на Мостике.", "Контролирую приборы на Мостике."),
            ],
            "HeadOfPersonnel": [
                (";Напоминаю персоналу: окно выдачи доступов в офисе ГП открыто.", "Проверяю манифест экипажа и бланки заявлений."),
                ("Порядок в документах — порядок на станции.", "Подписываю отчёты снабжения."),
            ],
            "HeadOfSecurity": [
                (":s Офицеры, усилить патрулирование коридоров и Бара. Следите за подозрительными лицами.", "Координирую патрули Службы Безопасности."),
                (";Служба Безопасности напоминает: проникновение в технические тоннели без допуска запрещено.", "Проверяю оружейную и камеры Брига."),
            ],
            "SecurityOfficer": [
                (":s Патрулирую сектор, обстановка штатная, нарушителей не обнаружено.", "Осматриваю коридор и проверяю шлюзы."),
                ("Гражданин, не задерживайтесь у шлюзов повышенной секретности.", "Присматриваю за порядком в отсеке."),
            ],
            "Detective": [
                ("На этой станции у каждого второго скелет в шкафчике...", "Изучаю отпечатки пальцев на сканере."),
                (":s Детектив на связи. Проверяю одну любопытную зацепку.", "Делаю пометки в блокноте."),
            ],
            "ChiefEngineer": [
                (":e Питание от двигателя антиматерии стабильное, СМЭС заряжены на 98%.", "Проверяю диагностику энергосети."),
                (";Инженерный отдел на связи: не перегружайте ЛКП в отсеках!", "Подтягиваю крепления кабеля мультитулом."),
            ],
            "AtmosphericTechnician": [
                (":e Давление в магистрали 101.3 кПа, смесь кислорода и азота в норме.", "Сверяю показания газоанализатора."),
                ("Фильтры в Атмосе работают чисто, утечек плазмы нет.", "Проверяю клапаны газовых труб."),
            ],
            "ChiefMedicalOfficer": [
                (";Экипаж, не забывайте переключать датчики костюмов в режим координат!", "Проверяю мониторы здоровья экипажа в Медбее."),
                (":m Химия, как продвигается синтез бикардина и дермалина?", "Осматриваю медицинское оборудование."),
            ],
            "Chemist": [
                (":m Новая партия бикардина и дексалина готова на стойке химлаборатории!", "Дозирую реагенты в мензурке."),
                ("Точная пропорция — залог быстрого исцеления.", "Работаю за раздатчиком химреактивов."),
            ],
            "ResearchDirector": [
                (":n Показания аномалии растут, готовим сканер для следующей фазы.", "Анализирую энергетический спектр артефакта."),
                (";Научный отдел проводит плановое сканирование артефактов, без паники.", "Записываю данные исследования в терминал."),
            ],
            "Quartermaster": [
                (";Карго принимает заказы от отделов! Пишите заявки на консоль снабжения.", "Считаю баланс космокредитов Карго."),
                (":u Оформляю накладные на новую поставку со склада ЦК.", "Проверяю ящики в погрузочном доке."),
            ],
            "Bartender": [
                (";Бар станции открыт! Свежие коктейли, виски и газировка для всех желающих!", "Натираю стакан до блеска за барной стойкой."),
                ("Что будем пить сегодня, коллега?", "Взбалтываю шейкер со льдом."),
            ],
            "Janitor": [
                ("Опять наследили грязными ботинками по чистому полу!", "Выжимаю швабру в ведро."),
                (";Смотрите под ноги, в центральном коридоре вымыт пол!", "Убираю мусор и пятна в отсеке."),
            ],
            "Clown": [
                ("ХОНК! Улыбнитесь, вас снимает скрытая камера клоуна!", "Коварно хихикаю и присматриваюсь к шлюзам Командования."),
                (";Внимание экипажу: объявлен код БАНАНОВЫЙ! Всем получить порцию смеха! ХОНК!", "Кручу в руках банановую кожуру и клаксон."),
            ],
        }

        lines = role_lines.get(agent.job, [("Продолжаю работу по смене.", "Осматриваю отсек.")])
        chosen_say, chosen_thought = random.choice(lines)
        should_speak = random.random() < 0.35
        should_move = not agent.path and random.random() < 0.55

        target_room = ""
        if should_move:
            candidates = dept_rooms.get(agent.department, ["Bar", "Medbay", "CargoBay"])
            target_room = random.choice(candidates)

        return {
            "thought": chosen_thought,
            "task": f"Работает в отсеке {agent.current_room}" if not target_room else f"Направляется в {target_room}",
            "say": chosen_say if should_speak else "",
            "emote": "",
            "move_to_room": target_room,
            "interact_uid": None,
            "memory_note": "",
        }

    def _apply_decision(self, agent: StationAgent, decision: Dict[str, Any]) -> None:
        thought = str(decision.get("thought") or "").strip()
        if thought:
            agent.last_thought = thought
            if agent.subconscious_prompt:
                agent.subconscious_prompt = ""

        task = str(decision.get("task") or "").strip()
        if task:
            agent.current_task = task

        emote = str(decision.get("emote") or "").strip()
        if emote:
            self.runtime.command_agent_emote(agent.id, emote)

        say = str(decision.get("say") or "").strip()
        if say:
            self.runtime.command_agent_say(agent.id, say)

        move_room = str(decision.get("move_to_room") or "").strip()
        if move_room:
            self.runtime.command_agent_move_to_room(agent.id, move_room, task or f"Идёт в {move_room}")

        interact_uid = decision.get("interact_uid")
        if interact_uid is not None:
            try:
                self.runtime.interact_with_object(agent.id, int(interact_uid))
            except Exception:
                pass

        mem = str(decision.get("memory_note") or "").strip()
        if mem:
            agent.memories.append({
                "time": self.runtime.get_round_clock(),
                "text": mem,
            })
            if len(agent.memories) > 25:
                agent.memories = agent.memories[-25:]

    async def step_agents(self) -> None:
        if not self.config.enabled:
            return

        # If browser is actively driving OpenAI calls within the last 8 seconds, let the browser drive LLM calls
        # and only keep idle movement smooth!
        browser_driving = self.config.browser_direct_llm and (time.time() - self._last_browser_llm_ping) < 8.0

        ai_agents = [
            a for a in self.runtime.agents.values()
            if not a.browser_controlled and not a.is_ghost and a.status != "Dead"
        ]
        if not ai_agents:
            return

        batch: List[StationAgent] = []
        for _ in range(min(self.config.concurrent_agents_per_tick, len(ai_agents))):
            ag = self.pick_next_agent_for_llm()
            if ag and ag not in batch:
                batch.append(ag)

        if self.config.api_key.strip() and not browser_driving:
            tasks = [self.query_openai_for_agent(ag) for ag in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for ag, res in zip(batch, results):
                if isinstance(res, dict) and res:
                    self._apply_decision(ag, res)
                else:
                    if not ag.path and (time.time() - ag.last_llm_time > 10.0):
                        fallback = self._generate_autonomous_routine_decision(ag)
                        self._apply_decision(ag, fallback)
        else:
            # Either no key or browser is driving LLM calls: keep non-queued idle agents moving smoothly
            for ag in batch:
                if not ag.path and (time.time() - ag.last_llm_time > 14.0):
                    fallback = self._generate_autonomous_routine_decision(ag)
                    self._apply_decision(ag, fallback)
                    ag.last_llm_time = time.time()
