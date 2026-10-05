"""
Space Station 14 Simulation Orchestrator
Master coordinator running the multi-agent decision loop, world ticking,
round generation (20-40 AI agents), Director mode, and SS14 server synchronization.
"""

import asyncio
import time
import random
import logging
from typing import Dict, Any, List, Optional
from ai_engine.crew_generator import generate_crew_roster
from ai_engine.station_world import StationWorld
from ai_engine.brain import AgentBrain
from ai_engine.director import DirectorEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SS14_Orchestrator")

class SimulationOrchestrator:
    def __init__(
        self,
        crew_count: int = 30,
        api_key: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        tick_interval: float = 2.5
    ):
        self.crew_count = max(20, min(40, crew_count))
        self.tick_interval = tick_interval
        self.is_running = False
        self.is_paused = False
        self.current_tick = 0
        
        self.world = StationWorld(station_name="Space Station 14 - Outpost Delta")
        self.brain = AgentBrain(api_key=api_key, base_url=base_url, model=model)
        self.director = DirectorEngine(self.world)
        self.rcon_bridge = None  # Bound if SS14 server is running
        
        # Initialize initial round
        self.start_new_round(self.crew_count)
        self._task: Optional[asyncio.Task] = None

    def start_new_round(self, count: Optional[int] = None):
        """Generates a fresh round with 20-40 AI crew members."""
        if count is not None:
            self.crew_count = max(20, min(40, count))
        
        logger.info(f"Generating new SS14 round with {self.crew_count} AI crew members...")
        self.world = StationWorld(station_name="Space Station 14 - Outpost Delta")
        self.director.world = self.world
        
        roster = generate_crew_roster(target_count=self.crew_count)
        self.world.register_agents(roster)
        
        # Initial greeting announcement
        self.world.broadcast_announcement(
            "Station AI / Central Command",
            f"Добро пожаловать на борт Space Station 14! На смене зарегистрировано {len(roster)} членов экипажа. Всем отделам занять рабочие посты.",
            alert_type="RoundStart"
        )
        logger.info(f"Round {self.world.round_id} successfully initialized with {len(roster)} agents.")

    def set_api_config(self, api_key: str, base_url: str = "https://api.openai.com/v1", model: str = "gpt-4o-mini"):
        """Update OpenAI API parameters on the fly."""
        self.brain.api_key = api_key
        self.brain.base_url = base_url.rstrip("/")
        self.brain.model = model
        logger.info(f"Updated AI Brain config: model={model}, base_url={base_url}, api_key_set={'yes' if api_key else 'no'}")

    async def start(self):
        """Start the background simulation loop."""
        if self.is_running:
            return
        self.is_running = True
        self.is_paused = False
        self._task = asyncio.create_task(self._simulation_loop())
        logger.info("Simulation orchestrator started.")

    async def stop(self):
        """Stop the background simulation loop."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.brain.close()
        logger.info("Simulation orchestrator stopped.")

    async def step(self):
        """Executes a single simulation tick manually."""
        await self._tick()

    async def _simulation_loop(self):
        """Main execution loop."""
        while self.is_running:
            try:
                if not self.is_paused:
                    await self._tick()
                await asyncio.sleep(self.tick_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in simulation loop: {e}", exc_info=True)
                await asyncio.sleep(2.0)

    async def _tick(self):
        """Single tick step: processes a batch of agents, updates timers and director."""
        self.current_tick += 1
        
        # 1. Update shuttle timer
        shuttle = self.world.emergency_shuttle
        if shuttle["status"] == "InTransit":
            shuttle["eta_seconds"] = max(0, shuttle["eta_seconds"] - self.tick_interval)
            if shuttle["eta_seconds"] <= 0:
                shuttle["status"] = "Docked"
                self.world.broadcast_announcement(
                    "Emergency Shuttle Control",
                    "🚨 АВАРИЙНЫЙ ШАТТЛ ПРИСТЫКОВАЛСЯ В ШЛЮЗЕ ЭВАКУАЦИИ! У экипажа есть 2 минуты на посадку!",
                    alert_type="ShuttleDocked"
                )

        # 2. Update Director auto-events
        self.director.update_auto_director()

        # 3. Select a subset of active agents to make decisions this tick (to keep latency crisp)
        living_agents = [a for a in self.world.agents.values() if a["vitals"]["is_alive"]]
        if not living_agents:
            return

        # Pick 3 to 6 agents per tick for active reasoning
        batch_size = min(len(living_agents), random.randint(3, 6))
        active_batch = random.sample(living_agents, batch_size)

        tasks = [self._process_agent(agent) for agent in active_batch]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_agent(self, agent: Dict[str, Any]):
        """Runs the perception-decision-action cycle for a single agent."""
        try:
            action = await self.brain.decide_action(agent, self.world)
            result = self.world.resolve_action(agent["id"], action)
            
            # If RCON is connected, sync radio messages and announcements to the SS14 server!
            if self.rcon_bridge and action.get("type") == "speak_radio":
                msg = action.get("message", "")
                chan = action.get("channel", "Common")
                sender = f"{agent['name']} ({agent['role']})"
                # Bridge call to SS14 server console
                try:
                    await self.rcon_bridge.send_chat(sender, chan, msg)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error processing agent {agent.get('name')}: {e}")

    def get_state_snapshot(self) -> Dict[str, Any]:
        """Returns full serializable station and crew state for UI and API."""
        return {
            "round_id": self.world.round_id,
            "station_name": self.world.station_name,
            "uptime_seconds": int(time.time() - self.world.round_start_time),
            "alert_level": self.world.alert_level,
            "emergency_shuttle": self.world.emergency_shuttle,
            "metrics": self.world.station_metrics,
            "total_crew": len(self.world.agents),
            "living_crew": len([a for a in self.world.agents.values() if a["vitals"]["is_alive"]]),
            "agents": list(self.world.agents.values()),
            "rooms": self.world.rooms,
            "recent_radio": self.world.radio_logs[-25:],
            "recent_actions": self.world.action_history[-25:],
            "director_log": self.director.director_log[-15:],
            "events_catalog": self.director.get_events_catalog(),
            "llm_config": {
                "model": self.brain.model,
                "base_url": self.brain.base_url,
                "has_api_key": bool(self.brain.api_key)
            }
        }
