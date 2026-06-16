#!/usr/bin/env python3
"""
Railway startup: ensure schema, views, and ETL data exist in hosted Postgres.
Runs once on deploy — idempotent (safe to re-run).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)


def run_sql_file(conn, filepath: Path):
    """Execute a SQL file against the connection."""
    sql = filepath.read_text()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    print(f"  ✅ {filepath.name}")


def check_data_exists(conn) -> bool:
    """Check if reservations data already exists."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM public.reservations_hackathon")
        count = cur.fetchone()[0]
    return count > 0


def main():
    print("🚀 Railway startup — setting up database...")
    conn = psycopg2.connect(DATABASE_URL)

    # 1. Create schema (idempotent — CREATE IF NOT EXISTS)
    print("\n📋 Step 1: Creating schema...")
    run_sql_file(conn, ROOT / "schema.sql")

    # 2. Create views (idempotent — CREATE OR REPLACE)
    print("\n📋 Step 2: Creating views...")
    run_sql_file(conn, ROOT / "sql" / "views.sql")

    # 3. Check if data needs loading
    print("\n📋 Step 3: Checking data...")
    if check_data_exists(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.reservations_hackathon")
            count = cur.fetchone()[0]
        print(f"  ✅ Data already loaded ({count} rows)")
    else:
        print("  ⚠️  No data found — automatically running ETL...")
        conn.close()
        # Run ETL inline
        import asyncio
        from etl.run_etl import main as etl_main
        asyncio.run(etl_main())
        return

    conn.close()
    print("\n✅ Database setup complete!")


if __name__ == "__main__":
    main()
