"""
FastAPI REST and WebSocket Endpoint Tests for Space Station 14 Director Deck
"""

import unittest
from fastapi.testclient import TestClient
import dashboard.app as app_module
from ai_engine.orchestrator import SimulationOrchestrator
from ss14_server.server_manager import SS14ServerManager
from tunnels.tunnel_manager import TunnelManager

class TestDashboardAPI(unittest.TestCase):

    def setUp(self):
        # Set up test singletons
        app_module.orchestrator = SimulationOrchestrator(crew_count=20)
        app_module.server_manager = SS14ServerManager()
        app_module.tunnel_manager = TunnelManager()
        self.client = TestClient(app_module.app)

    def test_status_endpoint(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("station_name", data)
        self.assertIn("agents", data)
        self.assertEqual(len(data["agents"]), 20)
        self.assertIn("server_status", data)
        self.assertIn("tunnel_status", data)

    def test_new_round_endpoint(self):
        response = self.client.post("/api/action/new_round", json={"crew_count": 25})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(app_module.orchestrator.world.agents), 25)

    def test_set_alert_endpoint(self):
        response = self.client.post("/api/action/set_alert", json={
            "level": "Red (Красный - Чрезвычайная ситуация)",
            "reason": "Тест аварии"
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(app_module.orchestrator.world.alert_level, "Red (Красный - Чрезвычайная ситуация)")

    def test_shuttle_endpoints(self):
        res_call = self.client.post("/api/action/shuttle/call")
        self.assertEqual(res_call.status_code, 200)
        self.assertTrue(res_call.json()["success"])

        res_recall = self.client.post("/api/action/shuttle/recall")
        self.assertEqual(res_recall.status_code, 200)
        self.assertTrue(res_recall.json()["success"])

    def test_trigger_event_endpoint(self):
        response = self.client.post("/api/action/trigger_event", json={"event_id": "meteor_shower"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_agent_perception_endpoint(self):
        first_agent = list(app_module.orchestrator.world.agents.values())[0]
        response = self.client.get(f"/api/agent/{first_agent['id']}/perception")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("document_json", data)
        self.assertIn("document_text", data)
        self.assertEqual(data["document_json"]["identity"]["name"], first_agent["name"])

    def test_whisper_endpoint(self):
        first_agent = list(app_module.orchestrator.world.agents.values())[0]
        response = self.client.post("/api/action/whisper", json={
            "agent_id": first_agent["id"],
            "whisper_text": "Проверьте гидропонику!"
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_llm_config_endpoint(self):
        response = self.client.post("/api/config/llm", json={
            "api_key": "sk-test123456",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o"
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(app_module.orchestrator.brain.model, "gpt-4o")
        self.assertEqual(app_module.orchestrator.brain.api_key, "sk-test123456")

if __name__ == "__main__":
    unittest.main()
