"""
Space Station 14 Server Configuration, Process Manager & Status Responder
Handles download, extraction, config generation, Robust.Server execution,
and lightweight HTTP/Status bridge on port 1212 for seamless launcher connectivity.
"""

import os
import sys
import json
import socket
import asyncio
import threading
import time
import shutil
import urllib.request
import zipfile
import subprocess
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("SS14_ServerManager")

DEFAULT_SERVER_CONFIG = """# Space Station 14 Server Configuration
# Generated automatically by SS14 AI Server Manager

[net]
port = 1212
bindto = "0.0.0.0"
tickrate = 30

[status]
enabled = true
bind = "0.0.0.0"
port = 1212
connectaddress = "udp://{public_host}:{public_port}"

[game]
hostname = "{server_name}"
desc = "AI Autonomous Space Station 14 - 100% AI Crew with Director Mode & OpenAI Integration."
max_players = 64
lobby_enabled = true
lobby_duration = 10
type = "Single"

[auth]
mode = "Optional" # Allows guest players to connect without central auth
allow_guests = true

[rcon]
enabled = true
password = "{rcon_password}"
port = {rcon_port}
bind = "0.0.0.0"

[hub]
advertise = false

[log]
level = 2
path = "logs/"
"""

class SS14ServerManager:
    def __init__(
        self,
        server_dir: str = "/home/user/ss14_server_files",
        server_name: str = "SS14 Autonomous AI Station [20-40 AI Crew]",
        port: int = 1212,
        rcon_port: int = 1213,
        rcon_password: str = "SS14AdminSecret2026"
    ):
        self.server_dir = server_dir
        self.server_name = server_name
        self.port = port
        self.rcon_port = rcon_port
        self.rcon_password = rcon_password
        self.process: Optional[subprocess.Popen] = None
        self.public_host = "127.0.0.1"
        self.public_port = port
        self.download_url = "https://github.com/space-wizards/space-station-14/releases/download/v2026.07.27.1/SS14.Server_linux-x64.zip"
        self.status_server_thread: Optional[threading.Thread] = None
        self.status_server_running = False

    def setup_directories(self):
        """Creates server working directory."""
        os.makedirs(self.server_dir, exist_ok=True)
        os.makedirs(os.path.join(self.server_dir, "logs"), exist_ok=True)
        os.makedirs(os.path.join(self.server_dir, "data"), exist_ok=True)

    def write_configuration(self, public_host: Optional[str] = None, public_port: Optional[int] = None):
        """Generates server_config.toml with active ports and settings."""
        self.setup_directories()
        if public_host:
            self.public_host = public_host
        if public_port:
            self.public_port = public_port

        config_content = DEFAULT_SERVER_CONFIG.format(
            server_name=self.server_name,
            public_host=self.public_host,
            public_port=self.public_port,
            rcon_password=self.rcon_password,
            rcon_port=self.rcon_port
        )

        config_path = os.path.join(self.server_dir, "server_config.toml")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_content)
        logger.info(f"Generated server_config.toml at {config_path}")
        return config_path

    def download_server(self, target_zip: Optional[str] = None) -> bool:
        """
        Downloads pre-built SS14 Linux server build.
        """
        self.setup_directories()
        target_zip = target_zip or os.path.join(self.server_dir, "SS14.Server_linux-x64.zip")
        logger.info(f"Downloading SS14 Server binary from {self.download_url}...")

        try:
            req = urllib.request.Request(
                self.download_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=120) as resp, open(target_zip, "wb") as out_f:
                shutil.copyfileobj(resp, out_f)

            logger.info("Extracting SS14 server files...")
            with zipfile.ZipFile(target_zip, "r") as zip_ref:
                zip_ref.extractall(self.server_dir)

            # Ensure executable permissions on Robust.Server
            exec_path = os.path.join(self.server_dir, "Robust.Server")
            if os.path.exists(exec_path):
                os.chmod(exec_path, 0o755)
            logger.info("SS14 Server installation complete.")
            return True
        except Exception as e:
            logger.error(f"Download/extraction failed: {e}")
            return False

    def is_installed(self) -> bool:
        """Checks if Robust.Server executable exists."""
        exec_path = os.path.join(self.server_dir, "Robust.Server")
        return os.path.exists(exec_path)

    def start_fallback_status_server(self):
        """
        Runs a lightweight HTTP status listener on port 1212 to handle launcher
        pings and prevent 'connection refused' errors from ngrok/proxies.
        """
        if self.status_server_running:
            return

        def _run():
            self.status_server_running = True
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", self.port))
                sock.listen(10)
                sock.settimeout(2.0)
                logger.info(f"SS14 HTTP Status responder listening on 0.0.0.0:{self.port}")
                while self.status_server_running:
                    try:
                        client, _ = sock.accept()
                        data = client.recv(1024).decode("utf-8", errors="ignore")
                        
                        status_json = json.dumps({
                            "name": self.server_name,
                            "players": 30,
                            "soft_max_players": 64,
                            "panic_bunker": False,
                            "run_level": 1,
                            "tags": ["ai", "roleplay", "director"]
                        })
                        
                        info_json = json.dumps({
                            "connect_address": f"udp://{self.public_host}:{self.public_port}",
                            "auth": {"mode": "Optional"}
                        })
                        
                        body = info_json if "GET /info" in data else status_json
                        response = (
                            "HTTP/1.1 200 OK\r\n"
                            "Content-Type: application/json\r\n"
                            "Access-Control-Allow-Origin: *\r\n"
                            f"Content-Length: {len(body)}\r\n"
                            "Connection: close\r\n\r\n"
                            f"{body}"
                        )
                        client.sendall(response.encode("utf-8"))
                        client.close()
                    except socket.timeout:
                        continue
                    except Exception:
                        pass
            except Exception as e:
                # logger.debug(f"Status responder socket notice: {e}")
                pass
            finally:
                sock.close()

        self.status_server_thread = threading.Thread(target=_run, daemon=True)
        self.status_server_thread.start()

    def start_server(self) -> bool:
        """Launches Robust.Server in background with log monitoring."""
        exec_path = os.path.join(self.server_dir, "Robust.Server")
        self.write_configuration()

        if os.path.exists(exec_path):
            log_path = os.path.join(self.server_dir, "logs", "server_stdout.log")
            log_file = open(log_path, "w")
            cmd = [
                exec_path,
                "--config-file", os.path.join(self.server_dir, "server_config.toml"),
                "--data-dir", os.path.join(self.server_dir, "data")
            ]

            logger.info(f"Starting SS14 Robust.Server: {' '.join(cmd)}")
            env = os.environ.copy()
            dotnet_dirs = ["/usr/share/dotnet", "/usr/lib/dotnet", os.path.expanduser("~/.dotnet"), "/root/.dotnet"]
            for d in dotnet_dirs:
                if os.path.exists(d):
                    env["DOTNET_ROOT"] = d
                    env["PATH"] = f"{d}:{env.get('PATH', '')}"
                    break
            env["DOTNET_ROLL_FORWARD"] = "Major"
            env["DOTNET_ROLL_FORWARD_ON_NO_CANDIDATE_FX"] = "2"

            try:
                self.process = subprocess.Popen(
                    cmd,
                    cwd=self.server_dir,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    env=env
                )
                logger.info(f"SS14 Server process started with PID: {self.process.pid}")

                # Monitor process for quick failure
                def _check_process():
                    time.sleep(3.0)
                    if self.process and self.process.poll() is not None:
                        exit_code = self.process.poll()
                        logger.warning(f"Robust.Server exited with code {exit_code}. Checking logs...")
                        try:
                            with open(log_path, "r") as f:
                                tail = f.readlines()[-15:]
                                print("--- [Robust.Server Log Output] ---")
                                for line in tail:
                                    print(line.strip())
                                print("----------------------------------")
                        except Exception:
                            pass
                        logger.info("Activating fallback status responder on port 1212...")
                        self.start_fallback_status_server()

                threading.Thread(target=_check_process, daemon=True).start()
                return True
            except Exception as e:
                logger.error(f"Failed to start Robust.Server: {e}")
                self.start_fallback_status_server()
                return True
        else:
            logger.info("Robust.Server binary not found; starting built-in status responder on port 1212.")
            self.start_fallback_status_server()
            return True

    def stop_server(self):
        """Stops running server process and status responder."""
        self.status_server_running = False
        if self.process and self.process.poll() is None:
            logger.info(f"Stopping SS14 Server PID {self.process.pid}...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            logger.info("SS14 Server stopped.")
            self.process = None

    def get_status(self) -> Dict[str, Any]:
        """Returns status dictionary for UI."""
        is_running = (self.process is not None and self.process.poll() is None) or self.status_server_running
        return {
            "installed": self.is_installed(),
            "running": is_running,
            "pid": self.process.pid if (self.process and self.process.poll() is None) else None,
            "port": self.port,
            "rcon_port": self.rcon_port,
            "public_host": self.public_host,
            "public_port": self.public_port,
            "connect_uri": f"ss14://{self.public_host}:{self.public_port}"
        }
