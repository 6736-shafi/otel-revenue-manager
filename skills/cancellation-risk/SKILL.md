---
name: cancellation-risk
description: "otel-rm-v2 | Assess cancellation risk for a stay month by reviewing cancellable reservations, booking window, and segment vulnerability. Calls get_otb_summary and get_segment_mix."
---

# Skill: Cancellation Risk Assessment

## Purpose
Identify how much of the on-books revenue is at risk of cancellation and which segments carry the highest vulnerability.

## Steps
1. Call `get_otb_summary(stay_month)` for total OTB and reservation count
2. Call `get_segment_mix(stay_month)` to identify high-cancel segments (OTA, PROM)
3. Calculate cancellable exposure by segment
4. Apply risk thresholds
5. Recommend mitigation action

## Judgment Thresholds

### OTA Cancellation Exposure
- OTA > 50% of room nights → HIGH cancellation risk (OTA bookings typically free-cancel)
- OTA 30–50% → WATCH; non-refundable incentives recommended
- OTA < 30% → lower inherent cancellation risk

### Promotional Rate Exposure
- PROM segment > 20% of room nights → moderate risk (often flexible rates)
- Consider closing flexible rate tiers if < 45 days to arrival

### Point-in-Time Snapshot (HITL Gate)
- `get_as_of_otb` requires **human approval** before execution — it rebuilds the full OTB state as of a past date and is resource-intensive
- Only invoke if the user explicitly asks for a historical comparison; otherwise use `get_otb_summary`

### Historical Cancel Rate Benchmark
- Cancel rate > 25% of all reservations created → flag as high-risk month
- Cancel rate 15–25% → watch; standard for leisure-heavy periods
- Cancel rate < 15% → healthy for this hotel type

## Answer Style
Lead with OTA share and estimated cancellable room nights.
"Of X room nights on the books, approximately Y are at cancellation risk (Z% OTA + PROM). I'd recommend..."
