"""
Fast Multi-Provider Tunneling Manager for Google Colab
Launches tunnels concurrently in parallel background threads for instant 3-second startup:
1. Cloudflared (HTTPS Quick Tunnel for Dashboard & ss14s:// queries)
2. Pinggy (SSH TCP Tunnel - 0 setup, no account)
3. Bore (Lightweight TCP proxy - 0 setup)
4. Playit.gg (UDP/TCP Game Tunnel)
5. Ngrok (TCP/HTTP Tunnel with AuthToken)
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
        self.udp_game_url: Optional[str] = None
        self.dashboard_public_url = f"http://127.0.0.1:{dashboard_port}"
        self.playit_claim_url: Optional[str] = None
        self.active_tunnels: Dict[str, str] = {}
        self.available_game_links: List[str] = []

    def start_cloudflared(self, port: Optional[int] = None) -> Optional[str]:
        """Starts Cloudflared quick tunnel for HTTPS Web Dashboard."""
        port = port or self.dashboard_port
        cf_bin = "cloudflared"
        if not shutil.which("cloudflared"):
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
            while time.time() - start_time < 8:
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.3)
                    continue
                match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if match:
                    url = match.group(0)
                    self.dashboard_public_url = url
                    self.active_tunnels["cloudflared_dashboard"] = url
                    clean_domain = url.replace("https://", "")
                    self.available_game_links.append(f"ss14s://{clean_domain}")
                    logger.info(f"🚀 Cloudflared: {url}")
                    return url

            return None
        except Exception as e:
            logger.error(f"Error starting cloudflared: {e}")
            return None

    def start_pinggy_udp(self, port: Optional[int] = None) -> Optional[str]:
        """Starts Pinggy UDP tunnel over SSH (Zero setup, no account needed)."""
        port = port or self.game_port
        if not shutil.which("ssh"):
            return None

        try:
            cmd = [
                "ssh",
                "-p", "443",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ServerAliveInterval=30",
                "-o", "ExitOnForwardFailure=yes",
                f"-R0:127.0.0.1:{port}",
                "udp@a.pinggy.io"
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
            while time.time() - start_time < 8:
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.3)
                    continue
                clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
                match = re.search(r"(?:udp://)?([a-zA-Z0-9.-]+\.pinggy\.io:[0-9]+)", clean_line) or re.search(r"(a\.pinggy\.io:[0-9]+)", clean_line)
                if match:
                    addr = match.group(1).replace("udp://", "")
                    self.udp_game_url = addr
                    self.active_tunnels["pinggy_udp"] = addr
                    print(f"⚡ [PINGGY UDP ИГРОВОЙ ТУННЕЛЬ]: udp://{addr}", flush=True)
                    return addr

            return None
        except Exception as e:
            logger.warning(f"Pinggy UDP error: {e}")
            return None

    def start_pinggy_tcp(self, port: Optional[int] = None) -> Optional[str]:
        """Starts Pinggy TCP tunnel over SSH (Zero setup, no account needed)."""
        """Starts Pinggy TCP tunnel over SSH (Zero setup, no account needed)."""
        port = port or self.game_port
        if not shutil.which("ssh"):
            return None

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
            while time.time() - start_time < 6:
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.3)
                    continue
                match = re.search(r"(?:tcp://)?([a-zA-Z0-9.-]+\.pinggy\.io:[0-9]+)", line) or re.search(r"(a\.pinggy\.io:[0-9]+)", line)
                if match:
                    addr = match.group(1).replace("tcp://", "")
                    self.game_public_url = addr
                    self.active_tunnels["pinggy_tcp"] = addr
                    self.available_game_links.append(f"ss14://{addr}")
                    logger.info(f"🚀 Pinggy TCP: {addr}")
                    return addr

            return None
        except Exception as e:
            return None

    def start_bore_tcp(self, port: Optional[int] = None) -> Optional[str]:
        """Starts Bore TCP tunnel (Lightweight, zero account needed)."""
        port = port or self.game_port
        bore_bin = "/tmp/bore"
        if not os.path.exists(bore_bin) and not shutil.which("bore"):
            try:
                bore_url = "https://github.com/ekzhang/bore/releases/download/v0.5.2/bore-v0.5.2-x86_64-unknown-linux-musl.tar.gz"
                urllib.request.urlretrieve(bore_url, "/tmp/bore.tar.gz")
                import tarfile
                with tarfile.open("/tmp/bore.tar.gz", "r:gz") as tar:
                    tar.extractall("/tmp")
                os.chmod("/tmp/bore", 0o755)
            except Exception:
                return None

        try:
            cmd = [bore_bin if os.path.exists(bore_bin) else "bore", "local", str(port), "--to", "bore.pub"]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            self.processes.append(proc)

            start_time = time.time()
            while time.time() - start_time < 6:
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.3)
                    continue
                match = re.search(r"listening at bore\.pub:([0-9]+)", line) or re.search(r"(bore\.pub:[0-9]+)", line)
                if match:
                    port_assigned = match.group(1)
                    addr = f"bore.pub:{port_assigned}" if not ":" in port_assigned else port_assigned
                    self.game_public_url = addr
                    self.active_tunnels["bore_tcp"] = addr
                    self.available_game_links.append(f"ss14://{addr}")
                    logger.info(f"🚀 Bore TCP: {addr}")
                    return addr

            return None
        except Exception:
            return None

    def start_playit(self) -> Optional[str]:
        """Sets up Playit.gg for SS14 UDP/TCP game traffic using a PTY for instant unbuffered logs."""
        if hasattr(self, "_playit_started") and self._playit_started:
            return self.playit_claim_url or "playit_active"
        self._playit_started = True

        playit_bin = shutil.which("playit") or "/usr/local/bin/playit" or "/tmp/playit"
        if not shutil.which("playit") and not os.path.exists(playit_bin):
            try:
                subprocess.run("wget -q https://github.com/playit-cloud/playit-agent/releases/download/v0.15.26/playit-linux-amd64 -O /tmp/playit && chmod +x /tmp/playit", shell=True, timeout=30)
                if os.path.exists("/tmp/playit"):
                    playit_bin = "/tmp/playit"
            except Exception as e:
                logger.error(f"Failed to fetch playit: {e}")
                return None

        secret_path = "/tmp/playit_secret.toml"
        os.makedirs(os.path.expanduser("~/.config/playit"), exist_ok=True)
        os.makedirs("/etc/playit", exist_ok=True)

        try:
            import pty
            import select
            master, slave = pty.openpty()
            proc = subprocess.Popen(
                [playit_bin, "--secret_path", secret_path, "run"],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                close_fds=True
            )
            os.close(slave)
            self.processes.append(proc)

            def _pty_reader():
                buf = ""
                while proc.poll() is None:
                    r, _, _ = select.select([master], [], [], 0.5)
                    if not r:
                        continue
                    try:
                        data = os.read(master, 1024).decode("utf-8", errors="ignore")
                    except Exception:
                        break
                    if not data:
                        break
                    buf += data
                    while "\n" in buf:
                        raw_line, buf = buf.split("\n", 1)
                        c_line = re.sub(r'\x1b\[[0-9;]*m', '', raw_line).strip()
                        if not c_line:
                            continue

                        # Check for claim URL
                        claim_match = re.search(r"https?://playit\.gg/claim/[a-zA-Z0-9]+", c_line)
                        if claim_match and not self.playit_claim_url:
                            self.playit_claim_url = claim_match.group(0)
                            if not self.playit_claim_url.startswith("http"):
                                self.playit_claim_url = "https://" + self.playit_claim_url
                            self.active_tunnels["playit_claim"] = self.playit_claim_url
                            print("\n" + "="*72, flush=True)
                            print("⚡ [PLAYIT.GG — АКТИВАЦИЯ ИГРОВОГО ТУННЕЛЯ (UDP+TCP)]:", flush=True)
                            print(f"👉 ССЫЛКА ДЛЯ ПРИВЯЗКИ: {self.playit_claim_url}", flush=True)
                            print("1. Перейдите по ссылке (вход без пароля / в 1 клик).", flush=True)
                            print("2. Нажмите «Add Tunnel» ➔ выберите «Custom (TCP+UDP)».", flush=True)
                            print(f"3. Укажите Local Port: {self.game_port}", flush=True)
                            print("4. Нажмите «Create Tunnel» ➔ скопируйте выданный адрес (например: xxx.gl.at.ply.gg:12345).", flush=True)
                            print("="*72 + "\n", flush=True)

                        # Check for assigned tunnel address
                        tunnel_match = re.search(r"([a-zA-Z0-9.-]+\.(?:ply\.gg|playit\.gg|joinmc\.link):[0-9]+)", c_line)
                        if tunnel_match:
                            addr = tunnel_match.group(1)
                            self.game_public_url = addr
                            self.active_tunnels["playit_game"] = addr
                            if f"ss14://{addr}" not in self.available_game_links:
                                self.available_game_links.append(f"ss14://{addr}")
                            print(f"\n🎮 [PLAYIT.GG АДРЕС ДЛЯ DIRECT CONNECT В ЛАУНЧЕРЕ]: {addr}\n", flush=True)

            t = threading.Thread(target=_pty_reader, daemon=True)
            t.start()

            # Synchronously wait up to 4 seconds for claim URL to print immediately
            t_wait = time.time()
            while time.time() - t_wait < 4:
                if self.playit_claim_url:
                    break
                time.sleep(0.2)

            self.active_tunnels["playit"] = "Running"
            return self.playit_claim_url or "playit_active"
        except Exception as e:
            logger.error(f"Error starting playit with pty: {e}")
            return None

    def start_tailscale(self, auth_key: Optional[str] = None) -> Optional[str]:
        """Sets up Tailscale mesh network for 100% native zero-lag UDP/TCP gameplay."""
        if not shutil.which("tailscale"):
            try:
                subprocess.run("curl -fsSL https://tailscale.com/install.sh | sh", shell=True, check=True)
            except Exception as e:
                logger.warning(f"Could not install Tailscale: {e}")
                return None

        try:
            # Start tailscaled daemon in background if not running
            subprocess.Popen(["tailscaled", "--tun=userspace-networking", "--socks5-server=localhost:1055"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2)

            cmd = ["tailscale", "up", "--hostname=colab-ss14-server"]
            if auth_key:
                cmd.extend(["--authkey", auth_key])
            else:
                cmd.append("--qr")

            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            self.processes.append(proc)
            return "tailscale_started"
        except Exception as e:
            logger.warning(f"Tailscale error: {e}")
            return None

    def start_ngrok(self, auth_token: str, tunnel_type: str = "tcp", port: Optional[int] = None) -> Optional[str]:
        """Starts Ngrok tunnel if auth_token is provided."""
        """Starts Ngrok tunnel if auth_token is provided."""
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
                logger.info(f"🚀 Ngrok TCP: {clean_addr}")
            else:
                self.dashboard_public_url = public_url
                self.active_tunnels["ngrok_dashboard"] = public_url
            return public_url
        except Exception as e:
            logger.warning(f"Ngrok connection notice: {e}")
            return None

    def start_all_best_tunnels(self, ngrok_token: Optional[str] = None):
        """
        Launches all tunnels concurrently in parallel threads.
        Completes in ~3-4 seconds total instead of waiting sequentially.
        """
        print("🌐 Запуск параллельных туннелей (Cloudflared, Pinggy, Bore, Playit)...")
        threads = []
        
        # 1. Cloudflared (Dashboard & HTTPS query)
        t_cf = threading.Thread(target=lambda: self.start_cloudflared(self.dashboard_port))
        threads.append(t_cf)
        
        # 2. Pinggy TCP
        t_pg = threading.Thread(target=lambda: self.start_pinggy_tcp(self.game_port))
        threads.append(t_pg)

        # 3. Pinggy UDP (Zero setup UDP Game Tunnel)
        t_pg_udp = threading.Thread(target=lambda: self.start_pinggy_udp(self.game_port))
        threads.append(t_pg_udp)

        # 4. Bore TCP
        t_bore = threading.Thread(target=lambda: self.start_bore_tcp(self.game_port))
        threads.append(t_bore)

        # 5. Playit.gg
        t_playit = threading.Thread(target=self.start_playit)
        threads.append(t_playit)

        # 6. Ngrok (if token)
        if ngrok_token and len(ngrok_token.strip()) > 5:
            t_ng = threading.Thread(target=lambda: self.start_ngrok(ngrok_token, "tcp", self.game_port))
            threads.append(t_ng)

        # Start all concurrently
        for t in threads:
            t.start()

        # Wait max 4 seconds for all to spin up
        for t in threads:
            t.join(timeout=4.0)

        print("⚡ Все доступные туннели успешно инициализированы!")

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
            "udp_game_url": self.udp_game_url,
            "ss14_connect_link": f"ss14://{self.game_public_url}",
            "dashboard_public_url": self.dashboard_public_url,
            "available_game_links": self.available_game_links,
            "playit_claim_url": self.playit_claim_url,
            "active_tunnels": self.active_tunnels
        }
