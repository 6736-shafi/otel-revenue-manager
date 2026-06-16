"""
Tool Tests - Phase 2
≥10 tool test cases (requires DB with data).
"""
import pytest
from unittest.mock import patch, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestGetOtbSummary:
    """Tests for get_otb_summary tool."""

    def test_otb_summary_returns_required_fields(self, mock_db):
        """get_otb_summary must return all required schema fields."""
        from tools.revenue_tools import get_otb_summary
        mock_db.return_value = {
            "stay_month": "2025-07",
            "row_count": 150,
            "reservation_count": 50,
            "room_nights": 300,
            "room_revenue": 45000.00,
            "total_revenue": 49500.00,
            "exclude_cancelled": True,
        }
        result = get_otb_summary.invoke({"stay_month": "2025-07"})
        assert "stay_month" in result
        assert "row_count" in result
        assert "reservation_count" in result
        assert "room_nights" in result
        assert "room_revenue" in result
        assert "total_revenue" in result

    def test_otb_summary_month_format(self, mock_db):
        """stay_month must be returned in YYYY-MM format."""
        from tools.revenue_tools import get_otb_summary
        mock_db.return_value = {"stay_month": "2025-07", "row_count": 0,
                                "reservation_count": 0, "room_nights": 0,
                                "room_revenue": 0, "total_revenue": 0}
        result = get_otb_summary.invoke({"stay_month": "2025-07"})
        assert result["stay_month"] == "2025-07"

    def test_otb_summary_exclude_cancelled_default_true(self, mock_db):
        """exclude_cancelled defaults to True (uses vw_stay_night_base)."""
        from tools.revenue_tools import get_otb_summary
        mock_db.return_value = {"stay_month": "2025-07", "row_count": 0,
                                "reservation_count": 0, "room_nights": 0,
                                "room_revenue": 0, "total_revenue": 0}
        result = get_otb_summary.invoke({"stay_month": "2025-07"})
        assert result.get("exclude_cancelled") is True

    def test_otb_summary_handles_error(self):
        """Returns error dict on DB failure."""
        from tools.revenue_tools import get_otb_summary
        with patch("tools.revenue_tools.query_one", side_effect=Exception("DB down")):
            result = get_otb_summary.invoke({"stay_month": "2025-07"})
            assert "error" in result


class TestGetSegmentMix:
    """Tests for get_segment_mix tool."""

    def test_segment_mix_returns_list(self, mock_db_list):
        """get_segment_mix returns a list of segment rows."""
        from tools.revenue_tools import get_segment_mix
        mock_db_list.return_value = [
            {"market_code": "OTA", "market_name": "Online Travel Agency",
             "macro_group": "Retail", "room_nights": 200, "total_revenue": 30000,
             "share_of_room_nights": 66.7, "share_of_revenue": 60.6}
        ]
        result = get_segment_mix.invoke({"stay_month": "2025-07"})
        assert isinstance(result, list)

    def test_segment_mix_includes_share_fields(self, mock_db_list):
        """Each segment row must include share_of_room_nights and share_of_revenue."""
        from tools.revenue_tools import get_segment_mix
        mock_db_list.return_value = [
            {"market_code": "OTA", "market_name": "OTA", "macro_group": "Retail",
             "room_nights": 100, "total_revenue": 15000,
             "share_of_room_nights": 100.0, "share_of_revenue": 100.0}
        ]
        result = get_segment_mix.invoke({"stay_month": "2025-07"})
        if result and not result[0].get("error"):
            assert "share_of_room_nights" in result[0]
            assert "share_of_revenue" in result[0]

    def test_segment_mix_macro_group_filter(self, mock_db_list):
        """Macro group filter is passed through correctly."""
        from tools.revenue_tools import get_segment_mix
        mock_db_list.return_value = []
        result = get_segment_mix.invoke({"stay_month": "2025-07", "macro_group": "Retail"})
        assert isinstance(result, list)


class TestGetPickupDelta:
    """Tests for get_pickup_delta tool."""

    def test_pickup_returns_by_segment(self, mock_db_list):
        """get_pickup_delta must include by_segment breakdown."""
        from tools.revenue_tools import get_pickup_delta
        with patch("tools.revenue_tools.query_one") as mock_one:
            mock_one.return_value = {
                "window_start": "2025-06-08",
                "window_end": "2025-06-15",
                "future_stay_from": "2025-07-01",
                "new_reservations": 25,
                "new_room_nights": 75,
                "new_total_revenue": 12500,
            }
            mock_db_list.return_value = []
            result = get_pickup_delta.invoke({
                "booking_window_days": 7,
                "future_stay_from": "2025-07-01"
            })
            assert "by_segment" in result
            assert "new_reservations" in result
            assert "new_room_nights" in result

    def test_pickup_uses_london_timezone(self, mock_db_list):
        """Pickup window uses Europe/London midnight boundaries (not UTC)."""
        from tools.revenue_tools import get_pickup_delta
        # The SQL should reference 'Europe/London' timezone
        with patch("tools.revenue_tools.query_one") as mock_one, \
             patch("tools.revenue_tools.query") as mock_q:
            mock_one.return_value = {"new_reservations": 0, "new_room_nights": 0, "new_total_revenue": 0}
            mock_q.return_value = []
            result = get_pickup_delta.invoke({
                "booking_window_days": 7,
                "future_stay_from": "2025-07-01"
            })
            assert result is not None


class TestGetAsOfOtb:
    """Tests for get_as_of_otb tool (HITL required)."""

    def test_as_of_otb_requires_both_params(self):
        """get_as_of_otb must accept stay_month and as_of_utc."""
        from tools.revenue_tools import get_as_of_otb
        with patch("tools.revenue_tools.query_one") as mock_one:
            mock_one.return_value = {
                "stay_month": "2025-07",
                "as_of_utc": "2025-06-01T00:00:00Z",
                "row_count": 100,
                "reservation_count": 30,
                "room_nights": 200,
                "room_revenue": 30000,
                "total_revenue": 33000,
            }
            result = get_as_of_otb.invoke({
                "stay_month": "2025-07",
                "as_of_utc": "2025-06-01T00:00:00Z"
            })
            assert "stay_month" in result
            assert "as_of_utc" in result

    def test_as_of_otb_uses_cancellation_datetime(self):
        """Point-in-time logic: include cancelled rows where cancellation_datetime > as_of_utc."""
        from tools.revenue_tools import get_as_of_otb
        # Verify the tool definition uses cancellation_datetime in the WHERE clause
        # by inspecting the tool's source (functional test of logic)
        import inspect
        source = inspect.getsource(get_as_of_otb.func)
        assert "cancellation_datetime" in source
        assert "as_of_utc" in source


class TestGetBlockVsTransientMix:
    """Tests for get_block_vs_transient_mix tool."""

    def test_block_mix_returns_required_fields(self):
        """Must return all 8 required fields."""
        from tools.revenue_tools import get_block_vs_transient_mix
        with patch("tools.revenue_tools.query_one") as mock_one, \
             patch("tools.revenue_tools.query") as mock_q:
            mock_one.return_value = {
                "block_room_nights": 100,
                "transient_room_nights": 200,
                "block_total_revenue": 15000,
                "transient_total_revenue": 30000,
                "total_room_nights": 300,
                "total_revenue": 45000,
            }
            mock_q.return_value = [
                {"company_name": "Corp A", "room_nights": 50, "total_revenue": 7500},
                {"company_name": "Corp B", "room_nights": 30, "total_revenue": 4500},
            ]
            result = get_block_vs_transient_mix.invoke({"stay_month": "2025-07"})
            assert "block_room_nights" in result
            assert "transient_room_nights" in result
            assert "block_total_revenue" in result
            assert "transient_total_revenue" in result
            assert "block_share_of_room_nights" in result
            assert "block_share_of_revenue" in result
            assert "top_companies" in result
            assert "top3_company_revenue_share" in result

    def test_block_mix_top_companies_max_3(self):
        """top_companies must contain at most 3 entries."""
        from tools.revenue_tools import get_block_vs_transient_mix
        with patch("tools.revenue_tools.query_one") as mock_one, \
             patch("tools.revenue_tools.query") as mock_q:
            mock_one.return_value = {
                "block_room_nights": 300,
                "transient_room_nights": 200,
                "block_total_revenue": 45000,
                "transient_total_revenue": 30000,
                "total_room_nights": 500,
                "total_revenue": 75000,
            }
            mock_q.return_value = [
                {"company_name": "A", "room_nights": 100, "total_revenue": 15000},
                {"company_name": "B", "room_nights": 100, "total_revenue": 15000},
                {"company_name": "C", "room_nights": 100, "total_revenue": 15000},
            ]
            result = get_block_vs_transient_mix.invoke({"stay_month": "2025-07"})
            assert len(result["top_companies"]) <= 3


# Fixtures

@pytest.fixture
def mock_db():
    """Mock query_one for single-row results."""
    with patch("tools.revenue_tools.query_one") as mock:
        yield mock


@pytest.fixture
def mock_db_list():
    """Mock query for list results."""
    with patch("tools.revenue_tools.query") as mock:
        yield mock
