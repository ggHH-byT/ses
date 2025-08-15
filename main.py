from __future__ import annotations
import os
import asyncio
import yaml
from dotenv import load_dotenv
from loguru import logger

from utils import ensure_dirs, setup_logging
from db import GiftDB
from notifier import Notifier
from web_scan import WebGiftScanner

async def main():
    load_dotenv()
    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    setup_logging(cfg["paths"]["logs_dir"])
    ensure_dirs(cfg["paths"]["logs_dir"], cfg["paths"]["screenshots_dir"], "data")

    api_id = int(os.environ["API_ID"])
    api_hash = os.environ["API_HASH"]
    session_string = os.environ.get("SESSION_STRING", "").strip()
    admin_chat_id = int(os.environ["ADMIN_CHAT_ID"])

    db = GiftDB(cfg["paths"]["db_file"])
    await db.init()

    notifier = Notifier(session_string=session_string, api_id=api_id, api_hash=api_hash, admin_chat_id=admin_chat_id)
    await notifier.start()

    try:
        scanner = WebGiftScanner(
            url=cfg["telegram_web_url"],
            state_file=cfg["paths"]["state_file"],
            screenshots_dir=cfg["paths"]["screenshots_dir"],
            headless=bool(cfg.get("headless", True)),
            timeout_sec=int(cfg.get("timeout_sec", 25)),
            screenshot_every_step=bool(cfg.get("screenshot_every_step", True))
        )

        spent = await db.spent_today()
        daily_cap = int(cfg.get("buy", {}).get("daily_cap_stars", 0))
        daily_left = max(0, daily_cap - spent) if daily_cap else 10**9

        buy_policy = None
        if bool(cfg.get("auto_buy", False)):
            b = cfg.get("buy", {})
            buy_policy = {
                "max_price_stars": int(b.get("max_price_stars", 10**9)),
                "daily_cap_left": daily_left,
                "wait_success_ms": int(b.get("wait_success_ms", 6000)),
                "insufficient_text": b.get("insufficient_text", ["Недостаточно", "Insufficient"]),
            }

        res = await scanner.run_scan(cfg["recipient_username"], buy_policy=buy_policy)
        detected = res["new_border_cards"] or []

        if detected:
            known = await db.known_hashes()
            really_new = [d for d in detected if d["phash"] not in known]
            if really_new:
                await db.add_hashes([d["phash"] for d in really_new])

        bought = res.get("bought", []) or []
        if bought:
            total = sum(d.get("price") or 0 for d in bought)
            await notifier.send_text(f"🛒 Куплено подарков: {len(bought)} на {total}⭐")
            for d in bought:
                await db.add_purchase(d["phash"], d.get("title"), d.get("price"), d.get("buy_screen"))
                await notifier.send_photo_with_caption(d["buy_screen"], f"✅ Куплен подарок idx={d['idx']} price={d.get('price')}⭐")
        else:
            if detected:
                await notifier.send_text("ℹ️ Новинки найдены, но покупок нет (лимит/цена/баланс/ошибка).")
            else:
                await notifier.send_text("🔍 Новых подарков с обводкой не найдено.")

    except Exception as e:
        logger.exception("Scan failed")
        err_note = f"❌ Ошибка сканирования: {e}"
        await notifier.send_text(err_note)
        try:
            from pathlib import Path
            shots = sorted(Path("screenshots").glob("*.png"))
            if shots:
                await notifier.send_photo_with_caption(str(shots[-1]), err_note)
        except Exception:
            pass
    finally:
        await notifier.stop()

if __name__ == "__main__":
    asyncio.run(main())
