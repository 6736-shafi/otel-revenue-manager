"""
ETL Phase 3 - Load
Idempotent insert of transformed data into PostgreSQL.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import psycopg2
from psycopg2.extras import execute_values

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://hackathon:hackathon@localhost:5432/hotel_hackathon"
)


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def apply_schema(conn) -> None:
    """Apply schema.sql if tables don't exist."""
    schema_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "schema.sql")
    if os.path.exists(schema_path):
        with open(schema_path) as f:
            schema_sql = f.read()
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
        logger.info("Schema applied")


def apply_views(conn) -> None:
    """Apply semantic views."""
    views_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sql", "views.sql")
    if os.path.exists(views_path):
        with open(views_path) as f:
            views_sql = f.read()
        with conn.cursor() as cur:
            cur.execute(views_sql)
        conn.commit()
        logger.info("Views applied")


def load_room_types(conn, room_types: list[dict]) -> int:
    """Load room type lookup data."""
    if not room_types:
        return 0
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO public.room_type_lookup (space_type, room_class, display_name, number_of_rooms)
            VALUES %s
            ON CONFLICT (space_type) DO UPDATE SET
                room_class = EXCLUDED.room_class,
                display_name = EXCLUDED.display_name,
                number_of_rooms = EXCLUDED.number_of_rooms
            """,
            [(r["space_type"], r["room_class"], r["display_name"], r["number_of_rooms"])
             for r in room_types if r.get("space_type")]
        )
    conn.commit()
    logger.info(f"Loaded {len(room_types)} room types")
    return len(room_types)


def load_rate_plans(conn, rate_plans: list[dict]) -> int:
    """Load rate plan lookup data."""
    if not rate_plans:
        return 0
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO public.rate_plan_lookup (rate_plan_code, plan_family, is_commissionable)
            VALUES %s
            ON CONFLICT (rate_plan_code) DO UPDATE SET
                plan_family = EXCLUDED.plan_family,
                is_commissionable = EXCLUDED.is_commissionable
            """,
            [(r["rate_plan_code"], r["plan_family"], r.get("is_commissionable", False))
             for r in rate_plans if r.get("rate_plan_code")]
        )
    conn.commit()
    logger.info(f"Loaded {len(rate_plans)} rate plans")
    return len(rate_plans)


def load_market_codes(conn, market_codes: list[dict]) -> int:
    """Load market code lookup data."""
    if not market_codes:
        return 0
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO public.market_code_lookup (market_code, market_name, macro_group, description)
            VALUES %s
            ON CONFLICT (market_code) DO UPDATE SET
                market_name = EXCLUDED.market_name,
                macro_group = EXCLUDED.macro_group,
                description = EXCLUDED.description
            """,
            [(r["market_code"], r["market_name"], r["macro_group"], r.get("description"))
             for r in market_codes if r.get("market_code")]
        )
    conn.commit()
    logger.info(f"Loaded {len(market_codes)} market codes")
    return len(market_codes)


def load_channel_codes(conn, channel_codes: list[dict]) -> int:
    """Load channel code lookup data."""
    if not channel_codes:
        return 0
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO public.channel_code_lookup (channel_code, channel_name, channel_group)
            VALUES %s
            ON CONFLICT (channel_code) DO UPDATE SET
                channel_name = EXCLUDED.channel_name,
                channel_group = EXCLUDED.channel_group
            """,
            [(r["channel_code"], r["channel_name"], r["channel_group"])
             for r in channel_codes if r.get("channel_code")]
        )
    conn.commit()
    logger.info(f"Loaded {len(channel_codes)} channel codes")
    return len(channel_codes)


def load_macro_group_history(conn, history: list[dict]) -> int:
    """Load market macro group history."""
    if not history:
        return 0
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO public.market_macro_group_history (market_code, valid_from, valid_to, macro_group)
            VALUES %s
            ON CONFLICT (market_code, valid_from) DO UPDATE SET
                valid_to = EXCLUDED.valid_to,
                macro_group = EXCLUDED.macro_group
            """,
            [(r["market_code"], r["valid_from"], r.get("valid_to"), r["macro_group"])
             for r in history if r.get("market_code")]
        )
    conn.commit()
    logger.info(f"Loaded {len(history)} macro group history records")
    return len(history)


def load_reservations(conn, rows: list[dict]) -> int:
    """Load reservation stay-date rows (idempotent via upsert)."""
    if not rows:
        return 0

    # Filter to valid rows only
    valid_rows = [r for r in rows if r.get("reservation_id") and r.get("stay_date")]

    batch_size = 500
    total_loaded = 0

    for i in range(0, len(valid_rows), batch_size):
        batch = valid_rows[i:i + batch_size]
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO public.reservations_hackathon (
                    reservation_id, arrival_date, departure_date, stay_date, property_date,
                    reservation_status, financial_status, create_datetime, cancellation_datetime,
                    guest_country, is_block, is_walk_in, number_of_spaces, space_type,
                    market_code, channel_code, source_name, rate_plan_code,
                    daily_room_revenue_before_tax, daily_total_revenue_before_tax,
                    nights, adr_room, lead_time, company_name, travel_agent_name
                ) VALUES %s
                ON CONFLICT (reservation_id, stay_date) DO UPDATE SET
                    reservation_status = EXCLUDED.reservation_status,
                    financial_status = EXCLUDED.financial_status,
                    cancellation_datetime = EXCLUDED.cancellation_datetime,
                    daily_room_revenue_before_tax = EXCLUDED.daily_room_revenue_before_tax,
                    daily_total_revenue_before_tax = EXCLUDED.daily_total_revenue_before_tax,
                    number_of_spaces = EXCLUDED.number_of_spaces,
                    adr_room = EXCLUDED.adr_room,
                    company_name = EXCLUDED.company_name,
                    travel_agent_name = EXCLUDED.travel_agent_name
                """,
                [(
                    r["reservation_id"],
                    r["arrival_date"],
                    r["departure_date"],
                    r["stay_date"],
                    r["property_date"],
                    r["reservation_status"],
                    r["financial_status"],
                    r["create_datetime"],
                    r.get("cancellation_datetime"),
                    r.get("guest_country"),
                    r.get("is_block", False),
                    r.get("is_walk_in", False),
                    r.get("number_of_spaces", 1),
                    r.get("space_type", "STD"),
                    r.get("market_code", "OTA"),
                    r.get("channel_code", "WEB"),
                    r.get("source_name", "Unknown"),
                    r.get("rate_plan_code", "BAR"),
                    r.get("daily_room_revenue_before_tax", 0),
                    r.get("daily_total_revenue_before_tax", 0),
                    r.get("nights", 1),
                    r.get("adr_room", 0),
                    r.get("lead_time", 0),
                    r.get("company_name"),
                    r.get("travel_agent_name"),
                ) for r in batch]
            )
        conn.commit()
        total_loaded += len(batch)
        logger.info(f"Loaded reservation batch {i // batch_size + 1}: {total_loaded}/{len(valid_rows)}")

    return total_loaded


def compute_row_hash(rows: list[dict]) -> str:
    """Compute a deterministic hash of the reservation rows."""
    pairs = []
    for r in sorted(rows, key=lambda x: (x.get("reservation_id", ""), str(x.get("stay_date", "")))):
        pairs.append(f"{r.get('reservation_id', '')}|{r.get('stay_date', '')}|{r.get('financial_status', '')}")
    payload = "\n".join(pairs).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def insert_load_manifest(conn, dataset_revision: str, scraped_at: str, source_url: str, row_hash: str) -> None:
    """Insert a record into load_manifest."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.load_manifest (dataset_revision, scraped_at, source_url, row_hash)
            VALUES (%s, %s, %s, %s)
            """,
            (dataset_revision, scraped_at, source_url, row_hash)
        )
    conn.commit()
    logger.info(f"Inserted load manifest: revision={dataset_revision}")


def ensure_default_lookup_data(conn) -> None:
    """Ensure minimum lookup data exists for FK constraints."""
    with conn.cursor() as cur:
        # Check if lookup tables are empty
        cur.execute("SELECT COUNT(*) FROM public.room_type_lookup")
        if cur.fetchone()[0] == 0:
            logger.info("Inserting default room type lookup data...")
            execute_values(cur, """
                INSERT INTO public.room_type_lookup (space_type, room_class, display_name, number_of_rooms)
                VALUES %s ON CONFLICT DO NOTHING
            """, [
                ("STD", "Standard", "Standard Room", 40),
                ("DLX", "Deluxe", "Deluxe Room", 20),
                ("STE", "Suite", "Suite", 10),
            ])

        cur.execute("SELECT COUNT(*) FROM public.rate_plan_lookup")
        if cur.fetchone()[0] == 0:
            logger.info("Inserting default rate plan lookup data...")
            execute_values(cur, """
                INSERT INTO public.rate_plan_lookup (rate_plan_code, plan_family, is_commissionable)
                VALUES %s ON CONFLICT DO NOTHING
            """, [
                ("BAR", "Retail", False),
                ("PROM", "Retail", False),
                ("CSR", "Corporate", False),
                ("CNR", "Corporate", False),
                ("CGR", "Corporate", False),
                ("FIT", "Leisure", True),
                ("EVEN", "Group", False),
                ("SMERF", "Group", False),
            ])

        cur.execute("SELECT COUNT(*) FROM public.market_code_lookup")
        if cur.fetchone()[0] == 0:
            logger.info("Inserting default market code lookup data...")
            execute_values(cur, """
                INSERT INTO public.market_code_lookup (market_code, market_name, macro_group, description)
                VALUES %s ON CONFLICT DO NOTHING
            """, [
                ("OTA", "Online Travel Agency", "Retail", "Online booking platforms"),
                ("BAR", "Best Available Rate", "Retail", "Direct web bookings at best rate"),
                ("PROM", "Promotional", "Retail", "Promotional rate bookings"),
                ("FIT", "Free Independent Traveller", "Leisure", "Independent leisure travellers"),
                ("CSR", "Corporate Negotiated", "Corporate", "Negotiated corporate accounts"),
                ("CNR", "Corporate Room Nights", "Corporate", "Corporate room night agreements"),
                ("CNI", "Conference/Incentive", "MICE", "Conference and incentive bookings"),
                ("CGR", "Corporate Group", "Corporate", "Corporate group bookings"),
                ("EVEN", "Event", "MICE", "Event and conference bookings"),
                ("SMERF", "SMERF Group", "Leisure Group", "Social, Military, Educational, Religious, Fraternal groups"),
            ])

        cur.execute("SELECT COUNT(*) FROM public.channel_code_lookup")
        if cur.fetchone()[0] == 0:
            logger.info("Inserting default channel code lookup data...")
            execute_values(cur, """
                INSERT INTO public.channel_code_lookup (channel_code, channel_name, channel_group)
                VALUES %s ON CONFLICT DO NOTHING
            """, [
                ("WEB", "Brand Website", "Digital"),
                ("REC", "Reception/Walk-in", "Direct"),
                ("EMA", "Email/Fax", "Offline"),
                ("WAL", "Walk-in", "Direct"),
            ])

    conn.commit()


def run_load(transformed_data: dict[str, Any], scrape_manifest: dict[str, Any]) -> dict[str, Any]:
    """Run the full load pipeline."""
    conn = get_connection()

    try:
        # Apply schema and views
        apply_schema(conn)
        apply_views(conn)

        # Ensure default lookup data
        ensure_default_lookup_data(conn)

        # Load lookup tables (scraped data overrides defaults)
        if transformed_data.get("room_types"):
            load_room_types(conn, transformed_data["room_types"])
        if transformed_data.get("rate_plans"):
            load_rate_plans(conn, transformed_data["rate_plans"])
        if transformed_data.get("market_codes"):
            load_market_codes(conn, transformed_data["market_codes"])
        if transformed_data.get("channel_codes"):
            load_channel_codes(conn, transformed_data["channel_codes"])
        if transformed_data.get("market_macro_group_history"):
            load_macro_group_history(conn, transformed_data["market_macro_group_history"])

        # Load reservations
        rows = transformed_data.get("reservation_rows", [])
        n_loaded = load_reservations(conn, rows)

        # Insert load manifest
        row_hash = compute_row_hash(rows)
        dataset_revision = scrape_manifest.get("anchor_date", datetime.now(timezone.utc).date().isoformat())
        scraped_at = scrape_manifest.get("scraped_at", datetime.now(timezone.utc).isoformat())
        source_url = scrape_manifest.get("source_url", "https://otel-hackathon-data-site.vercel.app")

        insert_load_manifest(conn, dataset_revision, scraped_at, source_url, row_hash)

        return {
            "status": "success",
            "rows_loaded": n_loaded,
            "dataset_revision": dataset_revision,
            "row_hash": row_hash,
        }

    except Exception as e:
        conn.rollback()
        logger.error(f"Load failed: {e}")
        raise
    finally:
        conn.close()
