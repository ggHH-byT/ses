from __future__ import annotations
import aiosqlite
from pathlib import Path
from typing import Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS gifts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phash TEXT NOT NULL,
  detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS gifts_phash_uq ON gifts(phash);

CREATE TABLE IF NOT EXISTS purchases(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phash TEXT NOT NULL,
  title TEXT,
  price_stars INTEGER,
  bought_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  screenshot TEXT
);
CREATE INDEX IF NOT EXISTS purchases_dt_idx ON purchases(bought_at);
"""

class GiftDB:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def known_hashes(self) -> set[str]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT phash FROM gifts") as cur:
                rows = await cur.fetchall()
        return {r[0] for r in rows}

    async def add_hashes(self, hashes: Iterable[str]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany("INSERT OR IGNORE INTO gifts(phash) VALUES (?)", [(h,) for h in hashes])
            await db.commit()

    async def add_purchase(self, phash: str, title: str | None, price_stars: int | None, screenshot: str | None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO purchases(phash, title, price_stars, screenshot) VALUES (?,?,?,?)",
                (phash, title, price_stars, screenshot),
            )
            await db.commit()

    async def spent_today(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COALESCE(SUM(price_stars),0) FROM purchases WHERE date(bought_at)=date('now','localtime')"
            ) as cur:
                row = await cur.fetchone()
                return int(row[0] or 0)
