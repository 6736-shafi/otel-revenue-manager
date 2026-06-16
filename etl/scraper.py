"""
ETL Phase 1 - Scraper
Scrapes reservation data from https://otel-hackathon-data-site.vercel.app
using Playwright for client-rendered HTML pages.

Key observations from site inspection:
- Reservation list uses JS button pagination (not URL params)
- Reference data uses tab-based navigation
- Detail pages show both reservation fields AND pre-computed stay rows
- Stay rows table has: stay_date, property_date, financial_status,
  daily_room_revenue_before_tax, daily_total_revenue_before_tax
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from playwright.async_api import async_playwright, Page

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = os.environ.get("DATA_SITE_URL", "https://otel-hackathon-data-site.vercel.app")


async def scrape_reference_tab(page: Page, tab_name: str) -> list[dict]:
    """Scrape a single reference tab by clicking it."""
    tabs = await page.query_selector_all("button")
    for tab in tabs:
        text = await tab.inner_text()
        if tab_name.lower() in text.strip().lower():
            await tab.click()
            await asyncio.sleep(1)
            break

    rows = []
    tables = await page.query_selector_all("table")
    for table in tables:
        headers = await table.query_selector_all("thead th")
        if not headers:
            headers = await table.query_selector_all("tr:first-child th, tr:first-child td")
        header_texts = [(await h.inner_text()).strip().lower() for h in headers]
        if not header_texts:
            continue

        body_rows = await table.query_selector_all("tbody tr")
        if not body_rows:
            all_rows = await table.query_selector_all("tr")
            body_rows = all_rows[1:] if all_rows else []

        for row in body_rows:
            cells = await row.query_selector_all("td")
            cell_texts = [(await c.inner_text()).strip() for c in cells]
            if cell_texts and len(cell_texts) >= len(header_texts):
                row_data = {}
                for i, header in enumerate(header_texts):
                    row_data[header] = cell_texts[i] if i < len(cell_texts) else ""
                rows.append(row_data)
    return rows


async def scrape_reference_data(page: Page) -> dict[str, Any]:
    """Scrape all reference lookup tables."""
    logger.info("Scraping reference data...")
    await page.goto(f"{BASE_URL}/reference", wait_until="networkidle")
    await asyncio.sleep(2)

    reference = {
        "room_types": [],
        "market_codes": [],
        "channel_codes": [],
        "rate_plans": [],
        "macro_group_history": [],
    }

    reference["room_types"] = await scrape_reference_tab(page, "Room types")
    reference["market_codes"] = await scrape_reference_tab(page, "Markets")
    reference["channel_codes"] = await scrape_reference_tab(page, "Channels")
    reference["rate_plans"] = await scrape_reference_tab(page, "Rate plans")
    reference["macro_group_history"] = await scrape_reference_tab(page, "Macro history")

    logger.info(f"Reference: {len(reference['room_types'])} room types, "
                f"{len(reference['market_codes'])} markets, "
                f"{len(reference['channel_codes'])} channels, "
                f"{len(reference['rate_plans'])} rate plans, "
                f"{len(reference['macro_group_history'])} macro history rows")
    return reference


async def scrape_verify_page(page: Page) -> dict[str, Any]:
    """Scrape the /verify page to get expected counts."""
    logger.info("Scraping verify page...")
    await page.goto(f"{BASE_URL}/verify", wait_until="networkidle")
    await asyncio.sleep(2)

    body = await page.inner_text("body")
    verify_data = {}

    import re
    patterns = {
        "total_reservations": r'(\d+)\s+reservations',
        "total_rows": r'(\d+)\s+(?:total\s+)?rows',
        "dataset_revision": r'(?:dataset\s+revision|revision)\s+([\w\.\-]+)',
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            val = match.group(1)
            try:
                verify_data[key] = int(val)
            except ValueError:
                verify_data[key] = val

    logger.info(f"Verify data: {verify_data}")
    return verify_data


async def get_reservation_ids_from_page(page: Page) -> list[str]:
    """Extract reservation IDs from current list page."""
    links = await page.query_selector_all("a[href^='/reservations/R']")
    ids = []
    seen = set()
    for link in links:
        href = await link.get_attribute("href")
        if href:
            import re
            m = re.search(r'/reservations/(R\w+)$', href)
            if m:
                res_id = m.group(1)
                if res_id not in seen:
                    seen.add(res_id)
                    ids.append(res_id)
    return ids


async def scrape_all_reservation_ids(page: Page) -> tuple[list[str], int]:
    """Navigate through all pages and collect reservation IDs."""
    logger.info("Scraping reservation list pages...")
    await page.goto(f"{BASE_URL}/reservations", wait_until="networkidle")
    await asyncio.sleep(2)

    all_ids = []
    seen = set()
    page_num = 1

    while True:
        ids = await get_reservation_ids_from_page(page)
        new_ids = [i for i in ids if i not in seen]
        all_ids.extend(new_ids)
        seen.update(new_ids)

        # Get page info
        body_text = await page.inner_text("body")
        import re
        page_match = re.search(r'Page\s+(\d+)\s+of\s+(\d+)', body_text)
        if page_match:
            current = int(page_match.group(1))
            total = int(page_match.group(2))
            logger.info(f"  Page {current}/{total}: {len(new_ids)} new IDs (total: {len(all_ids)})")
            if current >= total:
                break
        else:
            logger.info(f"  Page {page_num}: {len(new_ids)} new IDs (total: {len(all_ids)})")

        # Try to click Next
        next_btn = await page.query_selector("button:has-text('Next')")
        if not next_btn:
            logger.info("No Next button found, stopping")
            break

        disabled = await next_btn.get_attribute("disabled")
        aria_disabled = await next_btn.get_attribute("aria-disabled")
        if disabled is not None or aria_disabled == "true":
            logger.info("Next button is disabled, stopping")
            break

        await next_btn.click()
        await asyncio.sleep(1.5)
        page_num += 1

        if page_num > 20:
            logger.warning("Hit safety page limit")
            break

    pages_scraped = page_num
    return all_ids, pages_scraped


async def scrape_reservation_detail(page: Page, reservation_id: str) -> dict[str, Any] | None:
    """Scrape a single reservation detail page.

    Extracts both reservation-level fields AND the pre-computed stay rows table.
    """
    url = f"{BASE_URL}/reservations/{reservation_id}"
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(0.5)

        body_text = await page.inner_text("body")
        lines = [l.strip() for l in body_text.split("\n") if l.strip()]

        # Parse key-value pairs (field name on one line, value on next)
        reservation_fields = {"reservation_id": reservation_id}
        known_fields = {
            "arrival_date", "departure_date", "nights", "reservation_status",
            "create_datetime", "cancellation_datetime", "guest_country",
            "is_block", "is_walk_in", "number_of_spaces", "space_type",
            "market_code", "channel_code", "source_name", "rate_plan_code",
            "adr_room", "lead_time", "company_name", "travel_agent_name",
        }

        i = 0
        while i < len(lines) - 1:
            key = lines[i].lower().replace(" ", "_")
            val = lines[i + 1]
            if key in known_fields:
                # Skip "—" as null
                reservation_fields[key] = None if val == "—" else val
            i += 1

        # Extract stay rows from table
        stay_rows = []
        tables = await page.query_selector_all("table")
        for table in tables:
            headers = await table.query_selector_all("thead th")
            if not headers:
                continue
            header_texts = [(await h.inner_text()).strip().lower() for h in headers]

            # Only process the stay rows table
            if "stay_date" not in header_texts:
                continue

            body_rows = await table.query_selector_all("tbody tr")
            for row in body_rows:
                cells = await row.query_selector_all("td")
                cell_texts = [(await c.inner_text()).strip() for c in cells]
                if len(cell_texts) >= len(header_texts):
                    row_data = {}
                    for j, header in enumerate(header_texts):
                        row_data[header] = cell_texts[j] if j < len(cell_texts) else ""
                    stay_rows.append(row_data)

        return {
            "reservation": reservation_fields,
            "stay_rows": stay_rows,
        }
    except Exception as e:
        logger.error(f"Failed to scrape {reservation_id}: {e}")
        return None


async def run_scraper() -> dict[str, Any]:
    """Main scraper function. Returns all scraped data."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()

        scraped_at = datetime.now(timezone.utc).isoformat()

        # Scrape reference data
        reference = await scrape_reference_data(page)

        # Scrape verify page
        verify = await scrape_verify_page(page)

        # Scrape all reservation IDs
        all_reservation_ids, pages_scraped = await scrape_all_reservation_ids(page)
        logger.info(f"Total unique reservation IDs: {len(all_reservation_ids)}")

        # Build scrape manifest
        ids_sorted = sorted(all_reservation_ids)
        ids_hash = hashlib.sha256("\n".join(ids_sorted).encode()).hexdigest()
        scrape_manifest = {
            "anchor_date": datetime.now(timezone.utc).date().isoformat(),
            "pages_scraped": pages_scraped,
            "reservation_ids_count": len(all_reservation_ids),
            "reservation_ids_sha256": ids_hash,
            "source_url": BASE_URL,
            "scraped_at": scraped_at,
        }

        # Scrape individual reservation details
        logger.info(f"Scraping {len(all_reservation_ids)} reservation details...")
        reservations = []

        for i, res_id in enumerate(all_reservation_ids):
            if i % 25 == 0:
                logger.info(f"  Progress: {i}/{len(all_reservation_ids)}")
            detail = await scrape_reservation_detail(page, res_id)
            if detail:
                reservations.append(detail)

        await browser.close()

        return {
            "scraped_at": scraped_at,
            "source_url": BASE_URL,
            "reference": reference,
            "verify": verify,
            "reservations": reservations,
            "scrape_manifest": scrape_manifest,
        }


if __name__ == "__main__":
    import sys
    data = asyncio.run(run_scraper())

    os.makedirs("etl", exist_ok=True)
    with open("etl/raw_data.json", "w") as f:
        json.dump(data, f, indent=2, default=str)
    with open("etl/SCRAPE_MANIFEST.json", "w") as f:
        json.dump(data["scrape_manifest"], f, indent=2)

    logger.info(f"Scraping complete. {len(data['reservations'])} reservations scraped.")
    logger.info(f"Scrape manifest: {data['scrape_manifest']}")
