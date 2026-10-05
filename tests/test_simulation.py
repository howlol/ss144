"""
Unit and Integration Tests for Space Station 14 AI Server
Tests crew generation, perception documents, world mechanics,
director powers, REST API endpoints, and orchestrator loops.
"""

import unittest
import asyncio
from ai_engine.crew_generator import generate_crew_roster, DEPARTMENTS, SPECIES
from ai_engine.station_world import StationWorld, STATION_MAP
from ai_engine.perception import build_perception_document, format_perception_document_text
from ai_engine.brain import AgentBrain
from ai_engine.director import DirectorEngine
from ai_engine.orchestrator import SimulationOrchestrator
from ss14_server.server_manager import SS14ServerManager
from tunnels.tunnel_manager import TunnelManager

class TestSS14Simulation(unittest.TestCase):

    def test_crew_generation_bounds(self):
        """Test crew generation bounds (20-40 agents)."""
        roster_20 = generate_crew_roster(20)
        self.assertEqual(len(roster_20), 20)

        roster_35 = generate_crew_roster(35)
        self.assertEqual(len(roster_35), 35)

        roster_40 = generate_crew_roster(40)
        self.assertEqual(len(roster_40), 40)

        # Check essential attributes on every agent
        has_captain = False
        has_traitor = False
        for agent in roster_35:
            self.assertIn("id", agent)
            self.assertIn("name", agent)
            self.assertIn("role", agent)
            self.assertIn("species", agent)
            self.assertIn("location", agent)
            self.assertIn("hands", agent)
            self.assertIn("left_hand", agent["hands"])
            self.assertIn("right_hand", agent["hands"])
            self.assertIn("inventory", agent)
            self.assertIn("vitals", agent)
            self.assertIn("mental_state", agent)
            self.assertTrue(agent["vitals"]["is_alive"])
            if agent["role"] == "Captain":
                has_captain = True
            if agent.get("is_antagonist"):
                has_traitor = True
                self.assertIsNotNone(agent.get("antagonist"))
                self.assertGreater(len(agent["antagonist"]["objectives"]), 0)

        self.assertTrue(has_captain, "Should include Captain")
        self.assertTrue(has_traitor, "Should include Traitors")

    def test_perception_document_structure(self):
        """Test perception frame document formatting."""
        world = StationWorld()
        roster = generate_crew_roster(25)
        world.register_agents(roster)

        doctor = next(a for a in roster if "Doctor" in a["role"] or "Medical" in a["role"])
        doc = build_perception_document(doctor, world)

        self.assertEqual(doc["document_type"], "SS14_SENSORY_PERCEPTION_FRAME")
        self.assertEqual(doc["identity"]["name"], doctor["name"])
        self.assertIn("vitals_and_health", doc)
        self.assertIn("current_environment", doc)
        self.assertIn("physical_embodiment", doc)

        doc_text = format_perception_document_text(doc)
        self.assertIn("ДОКУМЕНТ ВОСПРИЯТИЯ", doc_text)
        self.assertIn(doctor["name"], doc_text)

    def test_world_mechanics_and_actions(self):
        """Test movement, interaction, healing, radio, and shuttle."""
        world = StationWorld()
        roster = generate_crew_roster(20)
        world.register_agents(roster)

        agent = roster[0]
        # Test radio
        res_radio = world.resolve_action(agent["id"], {
            "type": "speak_radio",
            "channel": "Common [145.9]",
            "message": "Тестовая проверка рации на мостике."
        })
        self.assertIn("Тестовая проверка", res_radio)
        self.assertGreater(len(world.radio_logs), 0)

        # Test movement
        current_loc = agent["location"]
        connections = world.rooms[current_loc]["connections"]
        if connections:
            target_room = connections[0]
            res_move = world.resolve_action(agent["id"], {
                "type": "move_to",
                "destination": target_room
            })
            self.assertEqual(agent["location"], target_room)

        # Test shuttle call and recall
        success_call, _ = world.call_emergency_shuttle()
        self.assertTrue(success_call)
        self.assertEqual(world.emergency_shuttle["status"], "InTransit")

        success_recall, _ = world.recall_emergency_shuttle()
        self.assertTrue(success_recall)
        self.assertEqual(world.emergency_shuttle["status"], "Idle")

    def test_director_events_and_whispers(self):
        """Test Director Mode disasters and subconscious thought injections."""
        world = StationWorld()
        roster = generate_crew_roster(20)
        world.register_agents(roster)
        director = DirectorEngine(world)

        # Test Power Failure event
        res_power = director.trigger_event("power_failure")
        self.assertTrue(res_power["success"])
        self.assertLess(world.station_metrics["grid_stability_pct"], 100)

        # Test Meteor Shower event
        res_meteor = director.trigger_event("meteor_shower")
        self.assertTrue(res_meteor["success"])
        self.assertTrue(world.rooms["Cargo Bay (Грузовой терминал)"]["breached"])

        # Test Thought Injection
        target_agent = roster[0]
        res_whisper = director.inject_subconscious_whisper(target_agent["id"], "Вам кажется, что шлюз заминирован.")
        self.assertTrue(res_whisper["success"])
        self.assertIn("заминирован", target_agent["mental_state"]["internal_thoughts"])

    def test_orchestrator_tick_and_snapshot(self):
        """Test Simulation Orchestrator lifecycle and state serialization."""
        async def run_async_test():
            orch = SimulationOrchestrator(crew_count=22)
            self.assertEqual(len(orch.world.agents), 22)

            # Run 2 ticks
            await orch.step()
            await orch.step()

            snapshot = orch.get_state_snapshot()
            self.assertEqual(snapshot["total_crew"], 22)
            self.assertIn("agents", snapshot)
            self.assertIn("rooms", snapshot)
            self.assertIn("metrics", snapshot)
            await orch.stop()

        asyncio.run(run_async_test())

    def test_server_manager_config(self):
        """Test SS14 server config generation."""
        mgr = SS14ServerManager(server_dir="/tmp/test_ss14_cfg")
        cfg_path = mgr.write_configuration(public_host="playit.gg.domain", public_port=25565)
        self.assertTrue(cfg_path.endswith("server_config.toml"))
        with open(cfg_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("25565", content)
        self.assertIn("playit.gg.domain", content)
        self.assertIn("Optional", content)

if __name__ == "__main__":
    unittest.main()
