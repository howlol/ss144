"""
Public Tunneling & Network Exposure Manager for Google Colab
Manages Playit.gg (UDP/TCP game traffic), Cloudflared, Ngrok, and Localtunnel
allowing anyone anywhere to connect to the Space Station 14 Server & Web Dashboard.
"""

import os
import re
import sys
import time
import shutil
import urllib.request
import subprocess
import threading
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("SS14_TunnelManager")

class TunnelManager:
    def __init__(self, game_port: int = 1212, dashboard_port: int = 8000):
        self.game_port = game_port
        self.dashboard_port = dashboard_port
        self.playit_process: Optional[subprocess.Popen] = None
        self.cloudflared_process: Optional[subprocess.Popen] = None
        self.ngrok_process: Optional[subprocess.Popen] = None
        
        self.game_public_url = f"127.0.0.1:{game_port}"
        self.dashboard_public_url = f"http://127.0.0.1:{dashboard_port}"
        self.playit_claim_url: Optional[str] = None
        self.active_tunnels: Dict[str, str] = {}

    def start_cloudflared(self, port: Optional[int] = None) -> Optional[str]:
        """
        Starts Cloudflared quick tunnel for the Web Dashboard (Zero configuration HTTPS).
        """
        port = port or self.dashboard_port
        if not shutil.which("cloudflared"):
            logger.info("Downloading cloudflared binary...")
            try:
                cf_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
                urllib.request.urlretrieve(cf_url, "/tmp/cloudflared")
                os.chmod("/tmp/cloudflared", 0o755)
                cf_bin = "/tmp/cloudflared"
            except Exception as e:
                logger.warning(f"Could not download cloudflared: {e}")
                return None
        else:
            cf_bin = "cloudflared"

        try:
            cmd = [cf_bin, "tunnel", "--url", f"http://127.0.0.1:{port}"]
            self.cloudflared_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            start_time = time.time()
            while time.time() - start_time < 20:
                line = self.cloudflared_process.stdout.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if match:
                    url = match.group(0)
                    self.dashboard_public_url = url
                    self.active_tunnels["cloudflared_dashboard"] = url
                    logger.info(f"🚀 Cloudflared Dashboard Tunnel Active: {url}")
                    return url

            logger.warning("Cloudflared tunnel startup timed out.")
            return None
        except Exception as e:
            logger.error(f"Error starting cloudflared: {e}")
            return None

    def start_playit(self) -> Optional[str]:
        """
        Sets up Playit.gg for SS14 UDP/TCP game traffic.
        Playit maps UDP ports cleanly for game clients in Google Colab.
        """
        if not shutil.which("playit"):
            logger.info("Downloading playit.gg CLI...")
            try:
                playit_url = "https://github.com/playit-cloud/playit-agent/releases/download/v0.15.26/playit-linux-amd64"
                urllib.request.urlretrieve(playit_url, "/tmp/playit")
                os.chmod("/tmp/playit", 0o755)
                playit_bin = "/tmp/playit"
            except Exception as e:
                logger.warning(f"Could not download playit: {e}")
                return None
        else:
            playit_bin = "playit"

        try:
            cmd = [playit_bin, "run"]
            self.playit_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            def _monitor_playit_output():
                for line in iter(self.playit_process.stdout.readline, ''):
                    if not line:
                        break
                    # Check for claim URL
                    claim_match = re.search(r"https://playit\.gg/claim/[a-zA-Z0-9]+", line)
                    if claim_match:
                        self.playit_claim_url = claim_match.group(0)
                        self.active_tunnels["playit_claim"] = self.playit_claim_url
                        print(f"\n⚡ [PLAYIT.GG АВТОРИЗАЦИЯ ТУННЕЛЯ]: Перейдите по ссылке для привязки: {self.playit_claim_url}\n")
                    
                    # Check for assigned tunnel address
                    tunnel_match = re.search(r"([a-zA-Z0-9.-]+\.playit\.gg:[0-9]+)", line) or re.search(r"([a-zA-Z0-9.-]+\.gl\.joinmc\.link:[0-9]+)", line)
                    if tunnel_match:
                        addr = tunnel_match.group(1)
                        self.game_public_url = addr
                        self.active_tunnels["playit_game"] = addr
                        logger.info(f"🚀 Playit.gg Game Address Assigned: {addr}")

            t = threading.Thread(target=_monitor_playit_output, daemon=True)
            t.start()
            
            # Brief wait to catch early claim URL
            time.sleep(2.0)
            self.active_tunnels["playit"] = "Running (Playit Agent active)"
            return "playit_active"
        except Exception as e:
            logger.error(f"Error starting playit: {e}")
            return None

    def start_ngrok(self, auth_token: str, tunnel_type: str = "tcp", port: Optional[int] = None) -> Optional[str]:
        """
        Starts Ngrok TCP (for game) or HTTP (for dashboard) if auth_token is provided.
        """
        if not auth_token:
            return None
        try:
            from pyngrok import ngrok, conf
            conf.get_default().auth_token = auth_token
            target_port = port or (self.game_port if tunnel_type == "tcp" else self.dashboard_port)
            # Use explicit 127.0.0.1 IPv4 address to prevent [::1] IPv6 connection refused
            bind_addr = f"127.0.0.1:{target_port}"
            tunnel = ngrok.connect(bind_addr, proto=tunnel_type)
            public_url = tunnel.public_url
            if tunnel_type == "tcp":
                clean_addr = public_url.replace("tcp://", "")
                self.game_public_url = clean_addr
                self.active_tunnels["ngrok_game"] = clean_addr
                logger.info(f"🚀 Ngrok Game Tunnel Active: {clean_addr}")
            else:
                self.dashboard_public_url = public_url
                self.active_tunnels["ngrok_dashboard"] = public_url
                logger.info(f"🚀 Ngrok Dashboard Tunnel Active: {public_url}")
            return public_url
        except Exception as e:
            logger.warning(f"Ngrok connection failed: {e}")
            return None

    def stop_all(self):
        """Stops all active tunnel background processes."""
        for proc in [self.cloudflared_process, self.playit_process, self.ngrok_process]:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except Exception:
                    proc.kill()
        self.active_tunnels.clear()
        logger.info("All tunnels stopped.")

    def get_tunnel_status(self) -> Dict[str, Any]:
        return {
            "game_public_url": self.game_public_url,
            "ss14_connect_link": f"ss14://{self.game_public_url}",
            "dashboard_public_url": self.dashboard_public_url,
            "playit_claim_url": self.playit_claim_url,
            "active_tunnels": self.active_tunnels
        }
