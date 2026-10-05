"""
Space Station 14 RCON Client & Bridge
Connects to SS14 Server RCON protocol to inject live chat messages,
station alerts, entity spawns, and round management commands.
"""

import asyncio
import struct
import logging
from typing import Optional, Tuple

logger = logging.getLogger("SS14_RconClient")

class SS14RconBridge:
    def __init__(self, host: str = "127.0.0.1", port: int = 1213, password: str = "SS14AdminSecret2026"):
        self.host = host
        self.port = port
        self.password = password
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.is_connected = False

    async def connect(self) -> bool:
        """Connects and authenticates to SS14 RCON server."""
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            # Send auth packet
            auth_success = await self._send_auth()
            self.is_connected = auth_success
            if auth_success:
                logger.info(f"Connected to SS14 RCON at {self.host}:{self.port}")
            return auth_success
        except Exception as e:
            # logger.debug(f"RCON connection not available (running in stand-alone simulation mode): {e}")
            self.is_connected = False
            return False

    async def _send_auth(self) -> bool:
        """Sends auth command."""
        try:
            cmd = f"auth {self.password}\n"
            self.writer.write(cmd.encode("utf-8"))
            await self.writer.drain()
            return True
        except Exception:
            return False

    async def send_command(self, command: str) -> str:
        """Sends a console command to SS14 server."""
        if not self.is_connected or not self.writer:
            return "RCON not connected (Simulated mode active)."

        try:
            cmd_payload = f"{command}\n"
            self.writer.write(cmd_payload.encode("utf-8"))
            await self.writer.drain()
            # Read response if available
            response = await asyncio.wait_for(self.reader.read(4096), timeout=2.0)
            return response.decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"Failed to execute RCON command '{command}': {e}")
            self.is_connected = False
            return f"Error: {e}"

    async def send_chat(self, sender: str, channel: str, message: str):
        """Injects a chat or radio message onto the SS14 server."""
        clean_msg = message.replace('"', '\\"')
        cmd = f'say "{sender} [{channel}]: {clean_msg}"'
        await self.send_command(cmd)

    async def send_announcement(self, message: str):
        """Sends station-wide announcement on SS14 server."""
        clean_msg = message.replace('"', '\\"')
        cmd = f'announce "{clean_msg}"'
        await self.send_command(cmd)

    async def close(self):
        """Closes RCON socket."""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        self.is_connected = False
