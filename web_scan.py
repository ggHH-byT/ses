from __future__ import annotations
import re
from pathlib import Path
from io import BytesIO
from typing import Any

from loguru import logger
from PIL import Image
from playwright.async_api import async_playwright, Page, BrowserContext

from detectors import phash_from_image, has_outline

BURGER_SELECTORS = [
    '[aria-label="Open menu"]',
    'button:has(svg[class*="icon-menu"])',
    'button >> text=/^Menu$/i'
]

PROFILE_SELECTORS = [
    '[data-testid="AppSideBarProfile"]',
    'a[href*="settings"]',
    'div:has-text(/^Settings$/i)'
]

SEND_GIFT_SELECTORS = [
    'text=/^Отправить подарок$/',
    'text=/^Send a Gift$/i',
    'button:has-text("Gift")'
]

SEARCH_INPUT_SELECTORS = [
    '[placeholder="Search"]',
    '[placeholder="Поиск"]',
    '[data-testid="searchInput"]',
    'input[type="text"]'
]

GIFTS_GRID_SELECTORS = [
    '[data-testid="gift-catalog"]',
    'div:has([data-testid="gift-card"])',
]

CARD_SELECTORS = [
    '[data-testid="gift-card"]',
    'div[class*="gift"]',
]

BUY_OPEN_SELECTORS = [
    'button:has-text("Подарить")',
    'button:has-text("Send")',
    'button:has-text("Gift")',
    'text=/^Подарить$/',
    'text=/^Send$/i',
]

CONFIRM_SELECTORS = [
    'button:has-text("Отправить")',
    'button:has-text("Confirm")',
    'button:has-text("Pay")',
    '[data-testid="gift-send-button"]'
]

SUCCESS_TOAST = [
    'text=/Подарок отправлен/i',
    'text=/Gift sent/i'
]

def parse_price_stars(dom_html: str) -> int | None:
    m = re.search(r'[\u2B50⭐]\s*([\d\s]+)', dom_html)
    if not m:
        nums = re.findall(r'(\d[\d\s]{2,})', dom_html)
        if not nums:
            return None
        value = max(nums, key=lambda s: len(s))
        return int(value.replace(" ", ""))
    return int(m.group(1).replace(" ", ""))

async def _click_any(page: Page, selectors: list[str], timeout_ms: int) -> bool:
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=timeout_ms)
            await page.click(sel)
            logger.info(f"Clicked: {sel}")
            return True
        except Exception:
            continue
    return False

class WebGiftScanner:
    def __init__(self, url: str, state_file: str, screenshots_dir: str, headless: bool, timeout_sec: int, screenshot_every_step: bool):
        self.url = url
        self.state_file = state_file
        self.screenshots_dir = screenshots_dir
        self.headless = headless
        self.timeout = timeout_sec * 1000
        self.screenshot_every_step = screenshot_every_step
        Path(screenshots_dir).mkdir(parents=True, exist_ok=True)

    async def _screenshot(self, page: Page, name: str):
        path = Path(self.screenshots_dir) / f"{name}.png"
        await page.screenshot(path=str(path), full_page=True)
        logger.info(f"[screenshot] {path}")
        return str(path)

    async def _click_first_available(self, page: Page, selectors: list[str], name: str):
        last_error = None
        for sel in selectors:
            try:
                await page.wait_for_selector(sel, timeout=self.timeout)
                await page.click(sel)
                logger.info(f"Clicked '{name}' via selector: {sel}")
                return True
            except Exception as e:
                last_error = e
        if last_error:
            raise last_error
        return False

    async def _type_and_select_contact(self, page: Page, username: str):
        for sel in SEARCH_INPUT_SELECTORS:
            try:
                inp = await page.wait_for_selector(sel, timeout=self.timeout)
                await inp.fill(username)
                await page.wait_for_timeout(600)
                await page.keyboard.press("Enter")
                logger.info(f"Selected contact {username}")
                return
            except Exception:
                continue
        raise RuntimeError("Search input not found")

    async def run_scan(self, recipient_username: str, buy_policy: dict[str, Any] | None = None) -> dict:
        result: dict[str, Any] = {"new_border_cards": [], "screens": [], "bought": []}

        async with async_playwright() as pw:
            state_path = Path(self.state_file)
            storage_state = str(state_path) if state_path.exists() else None

            browser = await pw.chromium.launch(headless=self.headless, args=["--disable-dev-shm-usage", "--no-sandbox"])
            context: BrowserContext = await browser.new_context(storage_state=storage_state, viewport={"width":1280, "height":800})
            page: Page = await context.new_page()

            try:
                await page.goto(self.url, wait_until="networkidle", timeout=self.timeout)
                if self.screenshot_every_step:
                    result["screens"].append(await self._screenshot(page, "step_1_open_web"))

                if any(k in page.url for k in ("login", "auth", "qr")):
                    logger.warning("Not authenticated in Telegram Web. Please login once; state will be saved.")
                    await page.wait_for_timeout(120_000)

                await self._click_first_available(page, BURGER_SELECTORS, "burger")
                if self.screenshot_every_step:
                    result["screens"].append(await self._screenshot(page, "step_2_burger_open"))

                await self._click_first_available(page, PROFILE_SELECTORS, "profile")
                if self.screenshot_every_step:
                    result["screens"].append(await self._screenshot(page, "step_3_profile_open"))

                await self._click_first_available(page, SEND_GIFT_SELECTORS, "send_gift")
                if self.screenshot_every_step:
                    result["screens"].append(await self._screenshot(page, "step_4_send_gift"))

                await self._type_and_select_contact(page, recipient_username)
                if self.screenshot_every_step:
                    result["screens"].append(await self._screenshot(page, "step_5_contact_selected"))

                grid = None
                for sel in GIFTS_GRID_SELECTORS:
                    try:
                        grid = await page.wait_for_selector(sel, timeout=self.timeout)
                        break
                    except Exception:
                        continue
                if grid is None:
                    raise RuntimeError("Gift grid not found")

                grid_shot_path = Path(self.screenshots_dir) / "step_6_gift_grid.png"
                await grid.screenshot(path=str(grid_shot_path))
                result["screens"].append(str(grid_shot_path))

                cards = []
                for csel in CARD_SELECTORS:
                    try:
                        cards = await grid.query_selector_all(csel)
                        if cards:
                            break
                    except Exception:
                        continue
                if not cards:
                    logger.warning("No gift cards found by selectors")
                    return result

                detected = []
                for idx, card in enumerate(cards, start=1):
                    dom_html = await card.inner_html()
                    price = parse_price_stars(dom_html)
                    card_png = await card.screenshot()
                    img = Image.open(BytesIO(card_png))

                    if img.width < 120 or img.height < 120:
                        continue

                    border_flag = has_outline(img)
                    dom_flag = bool(re.search(r"(new|badge|outline|highlight|premium)", dom_html, re.I))

                    if dom_flag or border_flag:
                        h = phash_from_image(img)
                        card_path = Path(self.screenshots_dir) / f"gift_card_{idx}_{h}.png"
                        img.save(card_path)
                        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", dom_html)).strip()[:120]
                        detected.append({"idx": idx, "phash": h, "path": str(card_path),
                                         "dom_new": dom_flag, "border": border_flag,
                                         "price": price, "title": title})

                result["new_border_cards"] = detected

                # === Покупка ===
                if buy_policy and detected:
                    bought = []
                    cap = int(buy_policy.get("daily_cap_left", 10**9))
                    max_price = int(buy_policy.get("max_price_stars", 10**9))
                    wait_ms = int(buy_policy.get("wait_success_ms", 6000))
                    insufficient = [s.lower() for s in buy_policy.get("insufficient_text", [])]

                    for d in detected:
                        price = d.get("price") or 0
                        if price <= 0 or price > max_price or price > cap:
                            continue
                        try:
                            await cards[d["idx"]-1].click()
                            result["screens"].append(await self._screenshot(page, f"buy_{d['idx']}_opened"))

                            await _click_any(page, BUY_OPEN_SELECTORS, self.timeout)
                            await _click_any(page, CONFIRM_SELECTORS, self.timeout)

                            await page.wait_for_timeout(wait_ms)

                            toast_ok = False
                            for sel in SUCCESS_TOAST:
                                try:
                                    await page.wait_for_selector(sel, timeout=1000)
                                    toast_ok = True
                                    break
                                except Exception:
                                    continue

                            page_html = (await page.content()).lower()
                            if any(t in page_html for t in insufficient):
                                result["screens"].append(await self._screenshot(page, f"buy_{d['idx']}_insufficient"))
                                continue

                            shot = await self._screenshot(page, f"buy_{d['idx']}_done" if toast_ok else f"buy_{d['idx']}_maybe")
                            d["bought"] = bool(toast_ok)
                            d["buy_screen"] = shot
                            if toast_ok:
                                cap -= price
                                bought.append(d)
                        except Exception as e:
                            logger.exception(f"Buy flow failed for idx={d['idx']}: {e}")
                            result["screens"].append(await self._screenshot(page, f"buy_{d['idx']}_error"))

                    result["bought"] = bought

                await context.storage_state(path=str(state_path))

            finally:
                await context.close()
                await browser.close()

        return result
