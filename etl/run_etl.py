"""
Main ETL runner - orchestrates scrape → transform → load pipeline.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from etl.scraper import run_scraper
from etl.transform import transform_raw_data
from etl.load import run_load

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main():
    logger.info("=== Starting ETL Pipeline ===")

    # Phase 1: Extract (Scrape)
    logger.info("Phase 1: Scraping data...")
    raw_data = await run_scraper()

    # Save raw data
    os.makedirs("etl", exist_ok=True)
    with open("etl/raw_data.json", "w") as f:
        json.dump(raw_data, f, indent=2, default=str)

    # Save scrape manifest
    with open("etl/SCRAPE_MANIFEST.json", "w") as f:
        json.dump(raw_data["scrape_manifest"], f, indent=2)

    logger.info(f"Scraped {len(raw_data.get('reservations', []))} reservations")
    logger.info(f"Scrape manifest saved: {raw_data['scrape_manifest']}")

    # Phase 2: Transform
    logger.info("Phase 2: Transforming data...")
    transformed = transform_raw_data(raw_data)
    logger.info(f"Transformed into {len(transformed.get('reservation_rows', []))} stay-date rows")

    # Phase 3: Load
    logger.info("Phase 3: Loading into PostgreSQL...")
    result = run_load(transformed, raw_data["scrape_manifest"])
    logger.info(f"Load result: {result}")

    logger.info("=== ETL Pipeline Complete ===")
    logger.info(f"  Rows loaded: {result['rows_loaded']}")
    logger.info(f"  Dataset revision: {result['dataset_revision']}")
    logger.info(f"  Row hash: {result['row_hash']}")

    return result


if __name__ == "__main__":
    result = asyncio.run(main())
    print(json.dumps(result, indent=2))
