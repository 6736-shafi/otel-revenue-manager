---
name: otb-health
description: "otel-rm-v2 | Assess on-the-books health for a stay month. Judgment thresholds for occupancy pace, ADR benchmarks, and revenue concentration. Calls get_otb_summary."
---

# Skill: OTB Health Assessment

## Purpose
Evaluate whether on-the-books revenue and room nights are on track for a given stay month.

## Steps
1. Call `get_otb_summary(stay_month)` to retrieve OTB metrics
2. Calculate occupancy pace: `room_nights / (70 rooms × days_in_month)`
3. Benchmark ADR against £150 threshold
4. Flag concentration if top segment > 60% of room nights
5. Deliver verdict with recommended action

## Judgment Thresholds

### Occupancy Pace
- **Strong**: ≥ 80% of capacity → protect rate, resist discounting
- **On track**: 60–79% → monitor; consider targeted promotions
- **At risk**: < 60% with < 60 days to arrival → open lower rate tiers, push OTA

### ADR
- **Healthy**: ADR ≥ £150 → maintain; push upsell and packages
- **Watch**: £120–£149 → review rate strategy; check segment mix
- **Low**: < £120 → investigate; may be over-reliant on discounted segments

### Revenue Concentration
- Top segment > 60% of room nights → concentration risk; diversify channels

## Answer Style
Lead with occupancy pace and ADR headline. Flag risks immediately.
"We have X room nights on the books for [month], representing Y% occupancy pace at £Z ADR..."
