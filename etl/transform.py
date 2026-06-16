"""
ETL Phase 2 - Transform
Parses scraped reservation data into grain-correct records.
Grain: one row per reservation × stay_date

The scraper now provides stay_rows directly from the detail page,
so transformation is mostly about type conversion and validation.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def parse_date(value: str | None) -> date | None:
    """Parse date from various formats."""
    if not value or value == "—":
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def parse_datetime(value: str | None) -> datetime | None:
    """Parse datetime, returning UTC-aware datetime."""
    if not value or value == "—":
        return None
    value = value.strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            continue
    d = parse_date(value)
    if d:
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return None


def parse_bool(value: str | None) -> bool:
    """Parse boolean from string."""
    if not value:
        return False
    return str(value).strip().lower() in ("true", "yes", "1", "t")


def parse_decimal(value: str | None) -> float:
    """Parse monetary value."""
    if not value or value == "—":
        return 0.0
    import re
    cleaned = re.sub(r'[£$€,\s]', '', str(value))
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def parse_int(value: str | None) -> int:
    """Parse integer."""
    if not value or value == "—":
        return 0
    import re
    cleaned = re.sub(r'[,\s]', '', str(value))
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return 0


def infer_plan_family(rate_plan_code: str) -> tuple[str, bool]:
    """Infer plan_family and is_commissionable from rate plan code."""
    code = rate_plan_code.upper()
    # Group indicators
    if any(kw in code for kw in ["GRP", "GROUP", "BLOCK", "GBB", "GROUPBB"]):
        return "Group", False
    # Corporate indicators
    if any(kw in code for kw in ["CORP", "CSR", "CNR", "ZEPHYR"]):
        return "Corporate", False
    # Commissionable retail
    if any(kw in code for kw in ["FITBB", "BOOKBAR", "PROMO1", "BOOKPROM"]):
        return "Retail", True
    # Default retail
    return "Retail", False


def transform_reference_data(reference: dict[str, Any]) -> dict[str, Any]:
    """Transform reference lookup tables into DB-ready records."""
    result = {
        "room_types": [],
        "rate_plans": [],
        "market_codes": [],
        "channel_codes": [],
        "market_macro_group_history": [],
    }

    # Room types: KS, TB, EX
    for rt in reference.get("room_types", []):
        result["room_types"].append({
            "space_type": rt.get("space_type", ""),
            "room_class": rt.get("room_class", "Standard"),
            "display_name": rt.get("display_name", ""),
            "number_of_rooms": parse_int(rt.get("number_of_rooms", "10")),
        })

    # Rate plans
    for rp in reference.get("rate_plans", []):
        code = rp.get("rate_plan_code", "")
        is_comm_str = rp.get("is_commissionable", "false")
        result["rate_plans"].append({
            "rate_plan_code": code,
            "plan_family": rp.get("plan_family", "Retail"),
            "is_commissionable": is_comm_str.lower() in ("true", "yes", "1"),
        })

    # Market codes
    for mc in reference.get("market_codes", []):
        result["market_codes"].append({
            "market_code": mc.get("market_code", ""),
            "market_name": mc.get("market_name", ""),
            "macro_group": mc.get("macro_group", "Retail"),
            "description": mc.get("description"),
        })

    # Channel codes
    for cc in reference.get("channel_codes", []):
        result["channel_codes"].append({
            "channel_code": cc.get("channel_code", ""),
            "channel_name": cc.get("channel_name", ""),
            "channel_group": cc.get("channel_group", "Digital"),
        })

    # Macro group history
    for mgh in reference.get("macro_group_history", []):
        valid_from = parse_date(mgh.get("valid_from"))
        valid_to_raw = mgh.get("valid_to", "—")
        valid_to = None if valid_to_raw == "—" else parse_date(valid_to_raw)
        if valid_from and mgh.get("market_code") and mgh.get("macro_group"):
            result["market_macro_group_history"].append({
                "market_code": mgh.get("market_code", ""),
                "valid_from": valid_from,
                "valid_to": valid_to,
                "macro_group": mgh.get("macro_group", ""),
            })

    return result


def transform_reservations(
    reservations: list[dict],
    known_rate_plans: set[str],
    known_space_types: set[str],
    known_market_codes: set[str],
    known_channel_codes: set[str],
) -> tuple[list[dict], list[dict]]:
    """
    Transform reservation data into stay-date rows.

    Returns:
        (stay_rows, extra_rate_plans) - stay rows and any new rate plans to add
    """
    all_stay_rows = []
    extra_rate_plans = {}  # code → {plan_family, is_commissionable}

    for reservation_data in reservations:
        res = reservation_data.get("reservation", {})
        raw_stay_rows = reservation_data.get("stay_rows", [])

        res_id = res.get("reservation_id", "")
        if not res_id:
            continue

        # Parse reservation-level fields
        arrival = parse_date(res.get("arrival_date"))
        departure = parse_date(res.get("departure_date"))
        create_dt = parse_datetime(res.get("create_datetime")) or datetime.now(timezone.utc)
        cancel_dt = parse_datetime(res.get("cancellation_datetime"))

        status = res.get("reservation_status", "Reserved")
        if status.lower() in ("cancelled", "canceled"):
            status = "Cancelled"
        elif status.lower() in ("reserved", "active", "confirmed", "booked"):
            status = "Reserved"

        num_spaces = parse_int(res.get("number_of_spaces", "1")) or 1
        space_type = res.get("space_type", "KS")
        market_code = res.get("market_code", "OTA")
        channel_code = res.get("channel_code", "WEB")
        source_name = res.get("source_name", "Unknown")
        rate_plan_code = res.get("rate_plan_code", "BOOKBAR")
        adr_room = parse_decimal(res.get("adr_room", "0"))
        lead_time = parse_int(res.get("lead_time", "0"))
        guest_country = res.get("guest_country")
        is_block = parse_bool(res.get("is_block", "false"))
        is_walk_in = parse_bool(res.get("is_walk_in", "false"))
        company_name = res.get("company_name")
        travel_agent_name = res.get("travel_agent_name")
        nights = parse_int(res.get("nights", "1")) or 1

        # Track unknown rate plan codes
        if rate_plan_code and rate_plan_code not in known_rate_plans and rate_plan_code not in extra_rate_plans:
            family, commissionable = infer_plan_family(rate_plan_code)
            extra_rate_plans[rate_plan_code] = {
                "rate_plan_code": rate_plan_code,
                "plan_family": family,
                "is_commissionable": commissionable,
            }

        # Use defaults for unknown FK values
        if space_type not in known_space_types:
            logger.warning(f"Unknown space_type '{space_type}' for {res_id}, defaulting to KS")
            space_type = "KS" if "KS" in known_space_types else list(known_space_types)[0]
        if market_code not in known_market_codes:
            logger.warning(f"Unknown market_code '{market_code}' for {res_id}")
        if channel_code not in known_channel_codes:
            logger.warning(f"Unknown channel_code '{channel_code}' for {res_id}")

        if raw_stay_rows:
            # Use pre-computed stay rows from detail page
            for raw_row in raw_stay_rows:
                stay_date = parse_date(raw_row.get("stay_date", ""))
                property_date = parse_date(raw_row.get("property_date", "")) or stay_date
                financial_status = raw_row.get("financial_status", "Posted")
                if financial_status.lower() not in ("posted", "provisional"):
                    financial_status = "Posted"
                daily_room_rev = parse_decimal(raw_row.get("daily_room_revenue_before_tax", "0"))
                daily_total_rev = parse_decimal(raw_row.get("daily_total_revenue_before_tax", "0"))

                if not stay_date:
                    continue

                all_stay_rows.append({
                    "reservation_id": res_id,
                    "arrival_date": arrival,
                    "departure_date": departure,
                    "stay_date": stay_date,
                    "property_date": property_date,
                    "reservation_status": status,
                    "financial_status": financial_status,
                    "create_datetime": create_dt,
                    "cancellation_datetime": cancel_dt,
                    "guest_country": guest_country,
                    "is_block": is_block,
                    "is_walk_in": is_walk_in,
                    "number_of_spaces": num_spaces,
                    "space_type": space_type,
                    "market_code": market_code,
                    "channel_code": channel_code,
                    "source_name": source_name,
                    "rate_plan_code": rate_plan_code,
                    "daily_room_revenue_before_tax": round(daily_room_rev, 2),
                    "daily_total_revenue_before_tax": round(daily_total_rev, 2),
                    "nights": nights,
                    "adr_room": round(adr_room, 2),
                    "lead_time": lead_time,
                    "company_name": company_name,
                    "travel_agent_name": travel_agent_name,
                })
        else:
            # Fallback: expand from arrival/departure dates
            from datetime import timedelta
            if arrival and departure and departure > arrival:
                for offset in range((departure - arrival).days):
                    stay_date = arrival + timedelta(days=offset)
                    all_stay_rows.append({
                        "reservation_id": res_id,
                        "arrival_date": arrival,
                        "departure_date": departure,
                        "stay_date": stay_date,
                        "property_date": stay_date,
                        "reservation_status": status,
                        "financial_status": "Posted",
                        "create_datetime": create_dt,
                        "cancellation_datetime": cancel_dt,
                        "guest_country": guest_country,
                        "is_block": is_block,
                        "is_walk_in": is_walk_in,
                        "number_of_spaces": num_spaces,
                        "space_type": space_type,
                        "market_code": market_code,
                        "channel_code": channel_code,
                        "source_name": source_name,
                        "rate_plan_code": rate_plan_code,
                        "daily_room_revenue_before_tax": round(adr_room * num_spaces, 2),
                        "daily_total_revenue_before_tax": round(adr_room * num_spaces, 2),
                        "nights": nights,
                        "adr_room": round(adr_room, 2),
                        "lead_time": lead_time,
                        "company_name": company_name,
                        "travel_agent_name": travel_agent_name,
                    })

    logger.info(f"Transformed {len(reservations)} reservations into {len(all_stay_rows)} stay rows")
    logger.info(f"Found {len(extra_rate_plans)} unknown rate plan codes: {list(extra_rate_plans.keys())}")
    return all_stay_rows, list(extra_rate_plans.values())


def transform_raw_data(raw_data: dict[str, Any]) -> dict[str, Any]:
    """Transform raw scraped data into DB-ready records."""
    reference = raw_data.get("reference", {})
    ref_data = transform_reference_data(reference)

    # Build sets of known FK values
    known_rate_plans = {r["rate_plan_code"] for r in ref_data["rate_plans"]}
    known_space_types = {r["space_type"] for r in ref_data["room_types"]}
    known_market_codes = {r["market_code"] for r in ref_data["market_codes"]}
    known_channel_codes = {r["channel_code"] for r in ref_data["channel_codes"]}

    # Transform reservations
    stay_rows, extra_rate_plans = transform_reservations(
        raw_data.get("reservations", []),
        known_rate_plans,
        known_space_types,
        known_market_codes,
        known_channel_codes,
    )

    # Add extra rate plans to the list
    ref_data["rate_plans"].extend(extra_rate_plans)

    return {
        "room_types": ref_data["room_types"],
        "rate_plans": ref_data["rate_plans"],
        "market_codes": ref_data["market_codes"],
        "channel_codes": ref_data["channel_codes"],
        "market_macro_group_history": ref_data["market_macro_group_history"],
        "reservation_rows": stay_rows,
    }
