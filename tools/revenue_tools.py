"""
Revenue Manager Tools - Phase 2
5 required tools that query semantic views (never raw SQL to agent).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from langchain.tools import tool

from tools.db import query, query_one

logger = logging.getLogger(__name__)


@tool
def get_otb_summary(stay_month: str, exclude_cancelled: bool = True) -> dict[str, Any]:
    """
    Get on-the-books (OTB) summary for a stay month.

    Returns aggregate revenue and room night metrics for a given stay month
    using the default OTB universe (Posted + non-cancelled reservations).

    Args:
        stay_month: Month in YYYY-MM format (e.g. '2025-07')
        exclude_cancelled: If True (default), exclude cancelled reservations

    Returns:
        Dictionary with: stay_month, row_count, reservation_count, room_nights,
        room_revenue, total_revenue, exclude_cancelled
    """
    try:
        # Parse stay month
        year, month = stay_month.split("-")
        year, month = int(year), int(month)

        # Build date range
        from_date = f"{year:04d}-{month:02d}-01"
        if month == 12:
            to_date = f"{year + 1:04d}-01-01"
        else:
            to_date = f"{year:04d}-{month + 1:02d}-01"

        if exclude_cancelled:
            # Use the semantic view (already filters cancelled + provisional)
            result = query_one(
                """
                SELECT
                    %s AS stay_month,
                    COUNT(*) AS row_count,
                    COUNT(DISTINCT reservation_id) AS reservation_count,
                    COALESCE(SUM(number_of_spaces), 0) AS room_nights,
                    COALESCE(SUM(daily_room_revenue_before_tax), 0)::numeric(14,2) AS room_revenue,
                    COALESCE(SUM(daily_total_revenue_before_tax), 0)::numeric(14,2) AS total_revenue,
                    %s AS exclude_cancelled
                FROM public.vw_stay_night_base
                WHERE stay_date >= %s::date
                  AND stay_date < %s::date
                """,
                (stay_month, exclude_cancelled, from_date, to_date)
            )
        else:
            # Include all statuses (for explicit cancelled analysis)
            result = query_one(
                """
                SELECT
                    %s AS stay_month,
                    COUNT(*) AS row_count,
                    COUNT(DISTINCT reservation_id) AS reservation_count,
                    COALESCE(SUM(number_of_spaces), 0) AS room_nights,
                    COALESCE(SUM(daily_room_revenue_before_tax), 0)::numeric(14,2) AS room_revenue,
                    COALESCE(SUM(daily_total_revenue_before_tax), 0)::numeric(14,2) AS total_revenue,
                    %s AS exclude_cancelled
                FROM public.reservations_hackathon
                WHERE stay_date >= %s::date
                  AND stay_date < %s::date
                  AND financial_status = 'Posted'
                """,
                (stay_month, exclude_cancelled, from_date, to_date)
            )

        if result:
            return {
                "stay_month": stay_month,
                "row_count": int(result["row_count"] or 0),
                "reservation_count": int(result["reservation_count"] or 0),
                "room_nights": int(result["room_nights"] or 0),
                "room_revenue": float(result["room_revenue"] or 0),
                "total_revenue": float(result["total_revenue"] or 0),
                "exclude_cancelled": exclude_cancelled,
                "adr": round(float(result["room_revenue"] or 0) / max(int(result["room_nights"] or 1), 1), 2),
            }
        return {
            "stay_month": stay_month,
            "row_count": 0,
            "reservation_count": 0,
            "room_nights": 0,
            "room_revenue": 0.0,
            "total_revenue": 0.0,
            "exclude_cancelled": exclude_cancelled,
            "adr": 0.0,
        }
    except Exception as e:
        logger.error(f"get_otb_summary error: {e}")
        return {"error": str(e), "stay_month": stay_month}


@tool
def get_segment_mix(stay_month: str, macro_group: str | None = None) -> list[dict[str, Any]]:
    """
    Get segment/market mix for a stay month using the semantic view.

    Breaks down OTB by market segment, using effective macro groups
    from market_macro_group_history (time-effective classification).

    Args:
        stay_month: Month in YYYY-MM format (e.g. '2025-07')
        macro_group: Optional filter by macro group (e.g. 'Retail', 'Corporate', 'MICE', 'Leisure')

    Returns:
        List of segment rows with: market_code, market_name, macro_group,
        room_nights, total_revenue, share_of_room_nights, share_of_revenue
    """
    try:
        year, month = stay_month.split("-")
        year, month = int(year), int(month)
        from_date = f"{year:04d}-{month:02d}-01"
        to_date = f"{year:04d}-{month + 1:02d}-01" if month < 12 else f"{year + 1:04d}-01-01"

        macro_filter = "AND effective_macro_group = %(macro_group)s" if macro_group else ""

        rows = query(
            f"""
            WITH segment_data AS (
                SELECT
                    market_code,
                    market_name,
                    effective_macro_group,
                    SUM(number_of_spaces) AS room_nights,
                    SUM(daily_total_revenue_before_tax) AS total_revenue
                FROM public.vw_segment_stay_night
                WHERE stay_date >= %(from_date)s::date
                  AND stay_date < %(to_date)s::date
                  {macro_filter}
                GROUP BY market_code, market_name, effective_macro_group
            ),
            totals AS (
                SELECT
                    SUM(room_nights) AS total_room_nights,
                    SUM(total_revenue) AS total_revenue_all
                FROM segment_data
            )
            SELECT
                s.market_code,
                s.market_name,
                s.effective_macro_group AS macro_group,
                s.room_nights,
                ROUND(s.total_revenue::numeric, 2) AS total_revenue,
                ROUND(100.0 * s.room_nights / NULLIF(t.total_room_nights, 0), 2) AS share_of_room_nights,
                ROUND(100.0 * s.total_revenue / NULLIF(t.total_revenue_all, 0), 2) AS share_of_revenue
            FROM segment_data s
            CROSS JOIN totals t
            ORDER BY s.room_nights DESC
            """,
            {"from_date": from_date, "to_date": to_date, "macro_group": macro_group}
        )

        return [
            {
                "market_code": r["market_code"],
                "market_name": r["market_name"],
                "macro_group": r["macro_group"],
                "room_nights": int(r["room_nights"] or 0),
                "total_revenue": float(r["total_revenue"] or 0),
                "share_of_room_nights": float(r["share_of_room_nights"] or 0),
                "share_of_revenue": float(r["share_of_revenue"] or 0),
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"get_segment_mix error: {e}")
        return [{"error": str(e)}]


@tool
def get_pickup_delta(booking_window_days: int, future_stay_from: str) -> dict[str, Any]:
    """
    Get booking pace (pickup) for future stays within the booking window.

    Measures how many new reservations were created in the last N days
    for stays from a given date forward. Uses Europe/London midnight as
    window boundaries (stored as UTC in create_datetime).

    Args:
        booking_window_days: Number of days to look back (e.g. 7, 14, 30)
        future_stay_from: Start date for future stays in YYYY-MM-DD format

    Returns:
        Dictionary with: window_start, window_end, future_stay_from,
        new_reservations, new_room_nights, new_total_revenue, by_segment
    """
    try:
        booking_window_days = int(booking_window_days)  # coerce string "7" → 7
        result = query_one(
            """
            WITH window_bounds AS (
                SELECT
                    (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/London')::date - %(days)s * INTERVAL '1 day'
                        AS window_start_london,
                    (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/London')::date
                        AS window_end_london
            ),
            pickup_data AS (
                SELECT
                    r.reservation_id,
                    r.market_code,
                    m.market_name,
                    COALESCE(h.macro_group, m.macro_group) AS effective_macro_group,
                    SUM(r.number_of_spaces) AS room_nights,
                    SUM(r.daily_total_revenue_before_tax) AS total_revenue
                FROM public.reservations_hackathon r
                JOIN public.market_code_lookup m ON m.market_code = r.market_code
                LEFT JOIN LATERAL (
                    SELECT mh.macro_group
                    FROM public.market_macro_group_history mh
                    WHERE mh.market_code = r.market_code
                      AND r.stay_date >= mh.valid_from
                      AND (mh.valid_to IS NULL OR r.stay_date < mh.valid_to)
                    ORDER BY mh.valid_from DESC
                    LIMIT 1
                ) h ON TRUE
                CROSS JOIN window_bounds wb
                WHERE r.create_datetime AT TIME ZONE 'Europe/London' >=
                      wb.window_start_london::timestamptz
                  AND r.create_datetime AT TIME ZONE 'Europe/London' <
                      wb.window_end_london + INTERVAL '1 day'
                  AND r.stay_date >= %(future_stay_from)s::date
                  AND r.reservation_status <> 'Cancelled'
                  AND r.financial_status = 'Posted'
                GROUP BY r.reservation_id, r.market_code, m.market_name, h.macro_group, m.macro_group
            )
            SELECT
                (SELECT window_start_london FROM window_bounds) AS window_start,
                (SELECT window_end_london FROM window_bounds) AS window_end,
                %(future_stay_from)s AS future_stay_from,
                COUNT(DISTINCT reservation_id) AS new_reservations,
                COALESCE(SUM(room_nights), 0) AS new_room_nights,
                COALESCE(SUM(total_revenue), 0)::numeric(14,2) AS new_total_revenue
            FROM pickup_data
            """,
            {"days": booking_window_days, "future_stay_from": future_stay_from}
        )

        # Get by-segment breakdown
        by_segment = query(
            """
            WITH window_bounds AS (
                SELECT
                    (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/London')::date - %(days)s * INTERVAL '1 day'
                        AS window_start_london,
                    (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/London')::date
                        AS window_end_london
            )
            SELECT
                r.market_code,
                m.market_name,
                COALESCE(h.macro_group, m.macro_group) AS effective_macro_group,
                COUNT(DISTINCT r.reservation_id) AS new_reservations,
                COALESCE(SUM(r.number_of_spaces), 0) AS new_room_nights,
                COALESCE(SUM(r.daily_total_revenue_before_tax), 0)::numeric(14,2) AS new_total_revenue
            FROM public.reservations_hackathon r
            JOIN public.market_code_lookup m ON m.market_code = r.market_code
            LEFT JOIN LATERAL (
                SELECT mh.macro_group
                FROM public.market_macro_group_history mh
                WHERE mh.market_code = r.market_code
                  AND r.stay_date >= mh.valid_from
                  AND (mh.valid_to IS NULL OR r.stay_date < mh.valid_to)
                ORDER BY mh.valid_from DESC
                LIMIT 1
            ) h ON TRUE
            CROSS JOIN window_bounds wb
            WHERE r.create_datetime AT TIME ZONE 'Europe/London' >=
                  wb.window_start_london::timestamptz
              AND r.create_datetime AT TIME ZONE 'Europe/London' <
                  wb.window_end_london + INTERVAL '1 day'
              AND r.stay_date >= %(future_stay_from)s::date
              AND r.reservation_status <> 'Cancelled'
              AND r.financial_status = 'Posted'
            GROUP BY r.market_code, m.market_name, h.macro_group, m.macro_group
            ORDER BY new_room_nights DESC
            """,
            {"days": booking_window_days, "future_stay_from": future_stay_from}
        )

        return {
            "booking_window_days": booking_window_days,
            "future_stay_from": future_stay_from,
            "window_start": str(result["window_start"]) if result else None,
            "window_end": str(result["window_end"]) if result else None,
            "new_reservations": int(result["new_reservations"] or 0) if result else 0,
            "new_room_nights": int(result["new_room_nights"] or 0) if result else 0,
            "new_total_revenue": float(result["new_total_revenue"] or 0) if result else 0.0,
            "by_segment": [
                {
                    "market_code": r["market_code"],
                    "market_name": r["market_name"],
                    "macro_group": r["effective_macro_group"],
                    "new_reservations": int(r["new_reservations"] or 0),
                    "new_room_nights": int(r["new_room_nights"] or 0),
                    "new_total_revenue": float(r["new_total_revenue"] or 0),
                }
                for r in by_segment
            ],
        }
    except Exception as e:
        logger.error(f"get_pickup_delta error: {e}")
        return {"error": str(e)}


@tool
def get_as_of_otb(stay_month: str, as_of_utc: str) -> dict[str, Any]:
    """
    Get point-in-time OTB snapshot as of a specific UTC datetime.

    IMPORTANT: This tool requires human-in-the-loop approval before execution.
    It performs a point-in-time rebuild which can be expensive.

    Uses: create_datetime <= as_of_utc AND (status != 'Cancelled' OR cancellation_datetime > as_of_utc)

    Args:
        stay_month: Month in YYYY-MM format
        as_of_utc: UTC datetime string (e.g. '2025-06-01T00:00:00Z')

    Returns:
        Point-in-time OTB with: stay_month, as_of_utc, row_count,
        reservation_count, room_nights, room_revenue, total_revenue
    """
    # NOTE: This tool is gated behind human approval in the agent layer
    try:
        year, month = stay_month.split("-")
        year, month = int(year), int(month)
        from_date = f"{year:04d}-{month:02d}-01"
        to_date = f"{year:04d}-{month + 1:02d}-01" if month < 12 else f"{year + 1:04d}-01-01"

        result = query_one(
            """
            SELECT
                %(stay_month)s AS stay_month,
                %(as_of_utc)s AS as_of_utc,
                COUNT(*) AS row_count,
                COUNT(DISTINCT reservation_id) AS reservation_count,
                COALESCE(SUM(number_of_spaces), 0) AS room_nights,
                COALESCE(SUM(daily_room_revenue_before_tax), 0)::numeric(14,2) AS room_revenue,
                COALESCE(SUM(daily_total_revenue_before_tax), 0)::numeric(14,2) AS total_revenue
            FROM public.reservations_hackathon
            WHERE stay_date >= %(from_date)s::date
              AND stay_date < %(to_date)s::date
              AND financial_status = 'Posted'
              AND create_datetime <= %(as_of_utc)s::timestamptz
              AND (
                  reservation_status <> 'Cancelled'
                  OR cancellation_datetime > %(as_of_utc)s::timestamptz
              )
            """,
            {
                "stay_month": stay_month,
                "as_of_utc": as_of_utc,
                "from_date": from_date,
                "to_date": to_date,
            }
        )

        if result:
            rn = int(result["room_nights"] or 0)
            rr = float(result["room_revenue"] or 0)
            return {
                "stay_month": stay_month,
                "as_of_utc": as_of_utc,
                "row_count": int(result["row_count"] or 0),
                "reservation_count": int(result["reservation_count"] or 0),
                "room_nights": rn,
                "room_revenue": rr,
                "total_revenue": float(result["total_revenue"] or 0),
                "adr": round(rr / max(rn, 1), 2),
            }
        return {
            "stay_month": stay_month,
            "as_of_utc": as_of_utc,
            "row_count": 0,
            "reservation_count": 0,
            "room_nights": 0,
            "room_revenue": 0.0,
            "total_revenue": 0.0,
            "adr": 0.0,
        }
    except Exception as e:
        logger.error(f"get_as_of_otb error: {e}")
        return {"error": str(e)}


@tool
def get_block_vs_transient_mix(stay_month: str) -> dict[str, Any]:
    """
    Get group/block vs transient business breakdown for a stay month.

    Splits OTB into block (is_block=True, group bookings) and transient
    (is_block=False, individual bookings), with top company concentration.

    Args:
        stay_month: Month in YYYY-MM format (e.g. '2025-07')

    Returns:
        Dictionary with: block_room_nights, transient_room_nights,
        block_total_revenue, transient_total_revenue,
        block_share_of_room_nights, block_share_of_revenue,
        top_companies (top 3 by revenue), top3_company_revenue_share
    """
    try:
        year, month = stay_month.split("-")
        year, month = int(year), int(month)
        from_date = f"{year:04d}-{month:02d}-01"
        to_date = f"{year:04d}-{month + 1:02d}-01" if month < 12 else f"{year + 1:04d}-01-01"

        # Block vs transient summary
        result = query_one(
            """
            SELECT
                COALESCE(SUM(number_of_spaces) FILTER (WHERE is_block = TRUE), 0) AS block_room_nights,
                COALESCE(SUM(number_of_spaces) FILTER (WHERE is_block = FALSE), 0) AS transient_room_nights,
                COALESCE(SUM(daily_total_revenue_before_tax) FILTER (WHERE is_block = TRUE), 0)::numeric(14,2)
                    AS block_total_revenue,
                COALESCE(SUM(daily_total_revenue_before_tax) FILTER (WHERE is_block = FALSE), 0)::numeric(14,2)
                    AS transient_total_revenue,
                COALESCE(SUM(number_of_spaces), 0) AS total_room_nights,
                COALESCE(SUM(daily_total_revenue_before_tax), 0) AS total_revenue
            FROM public.vw_stay_night_base
            WHERE stay_date >= %(from_date)s::date
              AND stay_date < %(to_date)s::date
            """,
            {"from_date": from_date, "to_date": to_date}
        )

        # Top companies by revenue
        top_companies = query(
            """
            SELECT
                COALESCE(company_name, 'Individual/No Company') AS company_name,
                SUM(number_of_spaces) AS room_nights,
                SUM(daily_total_revenue_before_tax)::numeric(14,2) AS total_revenue
            FROM public.vw_stay_night_base
            WHERE stay_date >= %(from_date)s::date
              AND stay_date < %(to_date)s::date
              AND is_block = TRUE
              AND company_name IS NOT NULL
            GROUP BY company_name
            ORDER BY total_revenue DESC
            LIMIT 3
            """,
            {"from_date": from_date, "to_date": to_date}
        )

        if not result:
            return {"stay_month": stay_month, "error": "No data found"}

        block_rn = int(result["block_room_nights"] or 0)
        trans_rn = int(result["transient_room_nights"] or 0)
        total_rn = int(result["total_room_nights"] or 0)
        block_rev = float(result["block_total_revenue"] or 0)
        trans_rev = float(result["transient_total_revenue"] or 0)
        total_rev = float(result["total_revenue"] or 0)

        top3_rev = sum(float(c["total_revenue"] or 0) for c in top_companies)
        top3_share = round(100.0 * top3_rev / max(total_rev, 0.01), 2)

        return {
            "stay_month": stay_month,
            "block_room_nights": block_rn,
            "transient_room_nights": trans_rn,
            "block_total_revenue": block_rev,
            "transient_total_revenue": trans_rev,
            "block_share_of_room_nights": round(100.0 * block_rn / max(total_rn, 1), 2),
            "block_share_of_revenue": round(100.0 * block_rev / max(total_rev, 0.01), 2),
            "top_companies": [
                {
                    "company_name": c["company_name"],
                    "room_nights": int(c["room_nights"] or 0),
                    "total_revenue": float(c["total_revenue"] or 0),
                }
                for c in top_companies
            ],
            "top3_company_revenue_share": top3_share,
        }
    except Exception as e:
        logger.error(f"get_block_vs_transient_mix error: {e}")
        return {"error": str(e), "stay_month": stay_month}


# Export all tools
ALL_TOOLS = [
    get_otb_summary,
    get_segment_mix,
    get_pickup_delta,
    get_as_of_otb,
    get_block_vs_transient_mix,
]
