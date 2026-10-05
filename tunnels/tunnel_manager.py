"""
Multi-Provider Tunneling & Network Exposure Manager for Google Colab
Provides rock-solid public access via:
1. Pinggy (SSH Zero-Config TCP/HTTP Tunnel - No account needed)
2. Bore (Lightweight Zero-Auth TCP Tunnel - No account needed)
3. Cloudflared (HTTPS Quick Tunnel - Works with ss14s:// and Web UI)
4. Ngrok (TCP/HTTP Tunnel with AuthToken)
5. Playit.gg (UDP/TCP Game Tunnel)
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
from typing import Dict, Any, Optional, List

logger = logging.getLogger("SS14_TunnelManager")

class TunnelManager:
    def __init__(self, game_port: int = 1212, dashboard_port: int = 8000):
        self.game_port = game_port
        self.dashboard_port = dashboard_port
        
        self.processes: List[subprocess.Popen] = []
        self.game_public_url = f"127.0.0.1:{game_port}"
        self.dashboard_public_url = f"http://127.0.0.1:{dashboard_port}"
        self.playit_claim_url: Optional[str] = None
        self.active_tunnels: Dict[str, str] = {}
        self.available_game_links: List[str] = []

    def start_cloudflared(self, port: Optional[int] = None) -> Optional[str]:
        """
        Starts Cloudflared quick tunnel for HTTPS Web Dashboard and ss14s:// launcher queries.
        """
        port = port or self.dashboard_port
        cf_bin = "cloudflared"
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

        try:
            cmd = [cf_bin, "tunnel", "--url", f"http://127.0.0.1:{port}"]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            self.processes.append(proc)

            start_time = time.time()
            while time.time() - start_time < 20:
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if match:
                    url = match.group(0)
                    self.dashboard_public_url = url
                    self.active_tunnels["cloudflared_dashboard"] = url
                    clean_domain = url.replace("https://", "")
                    self.available_game_links.append(f"ss14s://{clean_domain}")
                    logger.info(f"🚀 Cloudflared Tunnel Active: {url}")
                    return url

            return None
        except Exception as e:
            logger.error(f"Error starting cloudflared: {e}")
            return None

    def start_pinggy_tcp(self, port: Optional[int] = None) -> Optional[str]:
        """
        Starts Pinggy TCP tunnel over SSH (Zero setup, no account needed).
        """
        port = port or self.game_port
        if not shutil.which("ssh"):
            return None

        logger.info(f"Starting Pinggy TCP tunnel for port {port}...")
        try:
            cmd = [
                "ssh",
                "-p", "443",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ServerAliveInterval=30",
                "-o", "ExitOnForwardFailure=yes",
                f"-R0:127.0.0.1:{port}",
                "tcp@a.pinggy.io"
            ]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            self.processes.append(proc)

            start_time = time.time()
            while time.time() - start_time < 15:
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                # Search for tcp:// or host:port output
                match = re.search(r"(?:tcp://)?([a-zA-Z0-9.-]+\.pinggy\.io:[0-9]+)", line) or re.search(r"(a\.pinggy\.io:[0-9]+)", line)
                if match:
                    addr = match.group(1).replace("tcp://", "")
                    self.game_public_url = addr
                    self.active_tunnels["pinggy_tcp"] = addr
                    self.available_game_links.append(f"ss14://{addr}")
                    logger.info(f"🚀 Pinggy TCP Tunnel Active: {addr}")
                    return addr

            return None
        except Exception as e:
            logger.warning(f"Pinggy tunnel failed: {e}")
            return None

    def start_bore_tcp(self, port: Optional[int] = None) -> Optional[str]:
        """
        Starts Bore TCP tunnel (Lightweight, zero account needed).
        """
        port = port or self.game_port
        bore_bin = "bore"
        if not shutil.which("bore"):
            logger.info("Downloading bore binary...")
            try:
                bore_url = "https://github.com/ekzhang/bore/releases/download/v0.5.2/bore-v0.5.2-x86_64-unknown-linux-musl.tar.gz"
                urllib.request.urlretrieve(bore_url, "/tmp/bore.tar.gz")
                import tarfile
                with tarfile.open("/tmp/bore.tar.gz", "r:gz") as tar:
                    tar.extractall("/tmp")
                os.chmod("/tmp/bore", 0o755)
                bore_bin = "/tmp/bore"
            except Exception as e:
                logger.warning(f"Could not download bore: {e}")
                return None

        try:
            cmd = [bore_bin, "local", str(port), "--to", "bore.pub"]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            self.processes.append(proc)

            start_time = time.time()
            while time.time() - start_time < 15:
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                match = re.search(r"listening at bore\.pub:([0-9]+)", line) or re.search(r"(bore\.pub:[0-9]+)", line)
                if match:
                    port_assigned = match.group(1)
                    addr = f"bore.pub:{port_assigned}" if not ":" in port_assigned else port_assigned
                    self.game_public_url = addr
                    self.active_tunnels["bore_tcp"] = addr
                    self.available_game_links.append(f"ss14://{addr}")
                    logger.info(f"🚀 Bore TCP Tunnel Active: {addr}")
                    return addr

            return None
        except Exception as e:
            logger.warning(f"Bore tunnel failed: {e}")
            return None

    def start_playit(self) -> Optional[str]:
        """
        Sets up Playit.gg for SS14 UDP/TCP game traffic.
        """
        playit_bin = "playit"
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

        try:
            cmd = [playit_bin, "run"]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            self.processes.append(proc)

            def _monitor():
                for line in iter(proc.stdout.readline, ''):
                    if not line:
                        break
                    claim_match = re.search(r"https://playit\.gg/claim/[a-zA-Z0-9]+", line)
                    if claim_match:
                        self.playit_claim_url = claim_match.group(0)
                        self.active_tunnels["playit_claim"] = self.playit_claim_url
                        print(f"\n⚡ [PLAYIT.GG АВТОРИЗАЦИЯ]: Привяжите туннель: {self.playit_claim_url}\n")
                    
                    tunnel_match = re.search(r"([a-zA-Z0-9.-]+\.playit\.gg:[0-9]+)", line) or re.search(r"([a-zA-Z0-9.-]+\.gl\.joinmc\.link:[0-9]+)", line)
                    if tunnel_match:
                        addr = tunnel_match.group(1)
                        self.game_public_url = addr
                        self.active_tunnels["playit_game"] = addr
                        self.available_game_links.append(f"ss14://{addr}")
                        logger.info(f"🚀 Playit.gg Game Address: {addr}")

            threading.Thread(target=_monitor, daemon=True).start()
            self.active_tunnels["playit"] = "Running (Playit Agent active)"
            return "playit_active"
        except Exception as e:
            logger.error(f"Error starting playit: {e}")
            return None

    def start_ngrok(self, auth_token: str, tunnel_type: str = "tcp", port: Optional[int] = None) -> Optional[str]:
        """
        Starts Ngrok TCP/HTTP tunnel if auth_token is provided.
        """
        if not auth_token:
            return None
        try:
            from pyngrok import ngrok, conf
            conf.get_default().auth_token = auth_token
            target_port = port or (self.game_port if tunnel_type == "tcp" else self.dashboard_port)
            bind_addr = f"127.0.0.1:{target_port}"
            tunnel = ngrok.connect(bind_addr, proto=tunnel_type)
            public_url = tunnel.public_url
            if tunnel_type == "tcp":
                clean_addr = public_url.replace("tcp://", "")
                self.game_public_url = clean_addr
                self.active_tunnels["ngrok_game"] = clean_addr
                self.available_game_links.append(f"ss14://{clean_addr}")
                logger.info(f"🚀 Ngrok Game Tunnel Active: {clean_addr}")
            else:
                self.dashboard_public_url = public_url
                self.active_tunnels["ngrok_dashboard"] = public_url
            return public_url
        except Exception as e:
            logger.warning(f"Ngrok connection failed: {e}")
            return None

    def start_all_best_tunnels(self, ngrok_token: Optional[str] = None):
        """
        Launches best combination of tunnels to guarantee immediate connectivity in Google Colab.
        """
        logger.info("Initializing multi-provider tunneling suite...")
        # 1. Cloudflared for Dashboard & HTTPS launcher query
        self.start_cloudflared(self.dashboard_port)
        
        # 2. Ngrok if token provided
        if ngrok_token and len(ngrok_token.strip()) > 5:
            self.start_ngrok(ngrok_token, tunnel_type="tcp", port=self.game_port)
        
        # 3. Pinggy TCP tunnel (No auth needed)
        self.start_pinggy_tcp(self.game_port)

        # 4. Bore TCP tunnel (No auth needed)
        self.start_bore_tcp(self.game_port)

        # 5. Playit.gg agent (Native UDP/TCP)
        self.start_playit()

    def stop_all(self):
        """Stops all active tunnel background processes."""
        for proc in self.processes:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()
        self.processes.clear()
        self.active_tunnels.clear()
        logger.info("All tunnels stopped.")

    def get_tunnel_status(self) -> Dict[str, Any]:
        return {
            "game_public_url": self.game_public_url,
            "ss14_connect_link": f"ss14://{self.game_public_url}",
            "dashboard_public_url": self.dashboard_public_url,
            "available_game_links": self.available_game_links,
            "playit_claim_url": self.playit_claim_url,
            "active_tunnels": self.active_tunnels
        }
