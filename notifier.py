from __future__ import annotations
import os
from pyrogram import Client
from loguru import logger

class Notifier:
    def __init__(self, session_string: str, api_id: int, api_hash: str, admin_chat_id: int):
        self.session_string = session_string
        self.api_id = api_id
        self.api_hash = api_hash
        self.admin_chat_id = admin_chat_id
        self.app: Client | None = None

    async def start(self):
        self.app = Client(
            name="session-bot",
            api_id=self.api_id,
            api_hash=self.api_hash,
            session_string=self.session_string,
            workdir=os.getcwd(),
            no_updates=True
        )
        await self.app.start()
        logger.info("Pyrogram client started.")

    async def stop(self):
        if self.app:
            await self.app.stop()
            logger.info("Pyrogram client stopped.")

    async def send_text(self, text: str):
        if not self.app: return
        await self.app.send_message(self.admin_chat_id, text)

    async def send_photo_with_caption(self, photo_path: str, caption: str):
        if not self.app: return
        await self.app.send_photo(self.admin_chat_id, photo=photo_path, caption=caption)
