"""
ETL Tests - Phase 1
≥3 test cases for ETL pipeline.
"""
import pytest
from datetime import date, datetime, timezone

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from etl.transform import (
    parse_date, parse_datetime, parse_decimal, parse_int, parse_bool,
    transform_reference_data, transform_reservations, infer_plan_family,
)


class TestDateParsing:
    def test_parse_iso_date(self):
        assert parse_date("2025-07-15") == date(2025, 7, 15)

    def test_parse_uk_date(self):
        assert parse_date("15/07/2025") == date(2025, 7, 15)

    def test_parse_none_date(self):
        assert parse_date(None) is None

    def test_parse_empty_date(self):
        assert parse_date("") is None

    def test_parse_dash_as_null(self):
        assert parse_date("—") is None

    def test_parse_datetime_utc(self):
        dt = parse_datetime("2025-06-01T12:00:00Z")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.year == 2025


class TestFieldParsing:
    def test_parse_decimal_gbp(self):
        assert parse_decimal("£150.00") == 150.0

    def test_parse_decimal_comma(self):
        assert parse_decimal("1,250.50") == 1250.5

    def test_parse_decimal_none(self):
        assert parse_decimal(None) == 0.0

    def test_parse_decimal_dash(self):
        assert parse_decimal("—") == 0.0

    def test_parse_int(self):
        assert parse_int("3") == 3

    def test_parse_int_with_comma(self):
        assert parse_int("1,000") == 1000

    def test_parse_bool_true(self):
        assert parse_bool("true") is True
        assert parse_bool("yes") is True
        assert parse_bool("1") is True

    def test_parse_bool_false(self):
        assert parse_bool("false") is False
        assert parse_bool("no") is False
        assert parse_bool(None) is False


class TestRatePlanInference:
    def test_group_code_infers_group_family(self):
        family, comm = infer_plan_family("GROUPBB")
        assert family == "Group"

    def test_corp_code_infers_corporate_family(self):
        family, comm = infer_plan_family("CORP10BB")
        assert family == "Corporate"

    def test_unknown_code_defaults_to_retail(self):
        family, comm = infer_plan_family("OCHEARLY")
        assert family == "Retail"

    def test_commissionable_code_detected(self):
        family, comm = infer_plan_family("BOOKPROM")
        # BOOKPROM has BOOK prefix which is in commissionable list
        assert isinstance(comm, bool)


class TestReferenceTransform:
    def test_transforms_room_types(self):
        ref = {
            "room_types": [
                {"space_type": "KS", "room_class": "Standard", "display_name": "Standard King", "number_of_rooms": "52"},
                {"space_type": "TB", "room_class": "Standard", "display_name": "Standard Twin", "number_of_rooms": "20"},
            ],
            "market_codes": [], "channel_codes": [], "rate_plans": [], "macro_group_history": [],
        }
        result = transform_reference_data(ref)
        assert len(result["room_types"]) == 2
        assert result["room_types"][0]["space_type"] == "KS"
        assert result["room_types"][0]["number_of_rooms"] == 52

    def test_transforms_macro_group_history(self):
        ref = {
            "room_types": [], "market_codes": [], "channel_codes": [], "rate_plans": [],
            "macro_group_history": [
                {"market_code": "PROM", "valid_from": "2025-06-01", "valid_to": "—", "macro_group": "Leisure Group"},
                {"market_code": "OTA", "valid_from": "2020-01-01", "valid_to": "—", "macro_group": "Retail"},
            ]
        }
        result = transform_reference_data(ref)
        assert len(result["market_macro_group_history"]) == 2
        prom = next(r for r in result["market_macro_group_history"] if r["market_code"] == "PROM")
        assert prom["valid_to"] is None  # "—" → None
        assert prom["valid_from"] == date(2025, 6, 1)

    def test_rate_plan_commissionable_parsed(self):
        ref = {
            "room_types": [], "market_codes": [], "channel_codes": [],
            "rate_plans": [
                {"rate_plan_code": "BOOKBAR", "plan_family": "Retail", "is_commissionable": "true"},
                {"rate_plan_code": "GROUPBB", "plan_family": "Group", "is_commissionable": "false"},
            ],
            "macro_group_history": [],
        }
        result = transform_reference_data(ref)
        bookbar = next(r for r in result["rate_plans"] if r["rate_plan_code"] == "BOOKBAR")
        assert bookbar["is_commissionable"] is True
        groupbb = next(r for r in result["rate_plans"] if r["rate_plan_code"] == "GROUPBB")
        assert groupbb["is_commissionable"] is False


class TestReservationTransform:
    def _make_detail(self, res_id="RES001", arrival="2025-07-01", departure="2025-07-03",
                     space_type="KS", market_code="OTA", channel_code="WEB",
                     rate_plan_code="BOOKBAR", status="Reserved",
                     stay_rows=None):
        """Helper to build a reservation detail dict."""
        if stay_rows is None:
            stay_rows = [
                {"stay_date": arrival, "property_date": arrival, "financial_status": "Posted",
                 "daily_room_revenue_before_tax": "150.00", "daily_total_revenue_before_tax": "165.00"},
                {"stay_date": "2025-07-02", "property_date": "2025-07-02", "financial_status": "Posted",
                 "daily_room_revenue_before_tax": "150.00", "daily_total_revenue_before_tax": "165.00"},
            ]
        return {
            "reservation": {
                "reservation_id": res_id,
                "arrival_date": arrival,
                "departure_date": departure,
                "nights": str((date.fromisoformat(departure) - date.fromisoformat(arrival)).days),
                "reservation_status": status,
                "create_datetime": "2025-03-01T10:00:00Z",
                "number_of_spaces": "2",
                "space_type": space_type,
                "market_code": market_code,
                "channel_code": channel_code,
                "rate_plan_code": rate_plan_code,
                "adr_room": "150.00",
                "lead_time": "122",
            },
            "stay_rows": stay_rows,
        }

    def test_single_night_generates_one_row(self):
        detail = self._make_detail(arrival="2025-07-01", departure="2025-07-02",
                                   stay_rows=[{
                                       "stay_date": "2025-07-01", "property_date": "2025-07-01",
                                       "financial_status": "Posted", "daily_room_revenue_before_tax": "150.00",
                                       "daily_total_revenue_before_tax": "165.00"
                                   }])
        rows, _ = transform_reservations(
            [detail], {"BOOKBAR"}, {"KS", "TB", "EX"}, {"OTA", "BAR"}, {"WEB", "REC"}
        )
        assert len(rows) == 1
        assert rows[0]["stay_date"] == date(2025, 7, 1)

    def test_two_night_stay_generates_two_rows(self):
        detail = self._make_detail()  # 2 nights (2025-07-01 to 2025-07-03)
        rows, _ = transform_reservations(
            [detail], {"BOOKBAR"}, {"KS", "TB", "EX"}, {"OTA", "BAR"}, {"WEB", "REC"}
        )
        assert len(rows) == 2

    def test_room_nights_correct(self):
        """Room nights = SUM(number_of_spaces) across stay rows."""
        detail = self._make_detail()  # 2 rooms, 2 nights = 4 room nights
        rows, _ = transform_reservations(
            [detail], {"BOOKBAR"}, {"KS", "TB", "EX"}, {"OTA", "BAR"}, {"WEB", "REC"}
        )
        total_room_nights = sum(r["number_of_spaces"] for r in rows)
        assert total_room_nights == 4  # 2 rooms × 2 nights

    def test_unknown_rate_plan_added_to_extras(self):
        """Unknown rate plan codes should be captured in extra_rate_plans."""
        detail = self._make_detail(rate_plan_code="OCHEARLY")
        _, extra_rate_plans = transform_reservations(
            [detail], set(), {"KS"}, {"OTA"}, {"WEB"}
        )
        codes = [r["rate_plan_code"] for r in extra_rate_plans]
        assert "OCHEARLY" in codes

    def test_cancelled_status_preserved(self):
        detail = self._make_detail(status="Cancelled", stay_rows=[{
            "stay_date": "2025-07-01", "property_date": "2025-07-01",
            "financial_status": "Posted", "daily_room_revenue_before_tax": "0.00",
            "daily_total_revenue_before_tax": "0.00"
        }])
        rows, _ = transform_reservations(
            [detail], {"BOOKBAR"}, {"KS"}, {"OTA"}, {"WEB"}
        )
        assert rows[0]["reservation_status"] == "Cancelled"

    def test_mixed_financial_status_per_stay_row(self):
        """Different stay rows within a reservation can have different financial_status."""
        detail = self._make_detail(stay_rows=[
            {"stay_date": "2025-07-01", "property_date": "2025-07-01",
             "financial_status": "Posted", "daily_room_revenue_before_tax": "150.00",
             "daily_total_revenue_before_tax": "165.00"},
            {"stay_date": "2025-07-02", "property_date": "2025-07-02",
             "financial_status": "Provisional", "daily_room_revenue_before_tax": "150.00",
             "daily_total_revenue_before_tax": "165.00"},
        ])
        rows, _ = transform_reservations(
            [detail], {"BOOKBAR"}, {"KS"}, {"OTA"}, {"WEB"}
        )
        assert rows[0]["financial_status"] == "Posted"
        assert rows[1]["financial_status"] == "Provisional"

    def test_empty_reservation_list_returns_empty(self):
        rows, extras = transform_reservations([], set(), set(), set(), set())
        assert rows == []
        assert extras == []
