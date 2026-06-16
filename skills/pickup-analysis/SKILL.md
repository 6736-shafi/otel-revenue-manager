---
name: pickup-analysis
description: "otel-rm-v2 | Analyse booking pickup velocity over a window of days for a future stay period. Identifies pace acceleration or deceleration. Calls get_pickup_delta."
---

# Skill: Pickup Analysis

## Purpose
Measure recent booking pace to detect acceleration or deceleration in demand.

## Steps
1. Call `get_pickup_delta(booking_window_days=7, future_stay_from)` for recent pace
2. Benchmark new room nights against 20 RN/week threshold
3. Check OTA share of pickup for rate sensitivity signal
4. Deliver pace assessment with recommended action

## Judgment Thresholds

### Weekly Pickup Pace
- **Strong**: ≥ 30 new room nights in 7 days → demand healthy; hold or nudge rate up
- **On track**: 20–29 new room nights → pace acceptable; maintain strategy
- **Slow**: < 20 new room nights → slow demand; consider promotion or OTA rate push

### OTA Share of Pickup
- OTA > 70% of new pickup room nights → heavy rate sensitivity; test BAR increase
- OTA 40–70% → normal; watch trend
- OTA < 40% → strong direct/corporate mix; healthy

### Pickup Momentum
- Compare this 7-day window vs prior 7-day for trend direction
- Accelerating → tighten rate
- Decelerating with > 60 days to arrival → investigate and act

## Answer Style
Lead with total pickup in the window. Flag pace vs threshold immediately.
"In the last 7 days, we picked up X room nights for stays from [date]. Pace is [SLOW/ON TRACK/STRONG]..."
