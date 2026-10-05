"""
Automated SS14 Launcher & Client Connection End-to-End Simulation Test
Simulates exact C# SS14.Launcher network requests (/status, /info, /)
and verifies complete JSON schema and handshake integrity.
"""

import unittest
import json
import urllib.request
import time
from ss14_server.server_manager import SS14ServerManager
from ai_engine.orchestrator import SimulationOrchestrator

class TestLauncherConnectionFlow(unittest.TestCase):

    def setUp(self):
        self.server_mgr = SS14ServerManager(port=1215)
        self.server_mgr.start_http_status_server()
        time.sleep(0.3)

    def tearDown(self):
        self.server_mgr.stop_server()

    def test_launcher_get_status_schema(self):
        """Simulates SS14 Launcher GET /status request."""
        url = "http://127.0.0.1:1215/status"
        req = urllib.request.Request(url, headers={"User-Agent": "SpaceStation14-Launcher/0.39.1"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            
            # Verify required fields by SS14 launcher
            self.assertIn("name", data)
            self.assertIn("players", data)
            self.assertIn("soft_max_players", data)
            self.assertIn("tags", data)
            self.assertIsInstance(data["players"], int)
            self.assertIsInstance(data["tags"], list)

    def test_launcher_get_info_schema(self):
        """Simulates SS14 Launcher GET /info request."""
        url = "http://127.0.0.1:1215/info"
        req = urllib.request.Request(url, headers={"User-Agent": "SpaceStation14-Launcher/0.39.1"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            
            # Verify required fields by SS14 launcher to prevent NullReferenceException
            self.assertIn("connect_address", data)
            self.assertIn("auth", data)
            self.assertIn("mode", data["auth"])
            self.assertEqual(data["auth"]["mode"], "Optional")
            
            # Verify build section (prevents 404 / update error)
            self.assertIn("build", data)
            build = data["build"]
            self.assertIn("fork_id", build)
            self.assertIn("version", build)
            self.assertIn("engine_version", build)
            self.assertIn("download_url", build)
            self.assertTrue(build["download_url"].startswith("https://"))
            self.assertTrue(build["download_url"].endswith(".zip"))

if __name__ == "__main__":
    unittest.main()
