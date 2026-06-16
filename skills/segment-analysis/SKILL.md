---
name: segment-analysis
description: "otel-rm-v2 | Analyse booking segment mix for a stay month. Identify dominant segments, concentration risk, and ADR by segment. Calls get_segment_mix."
---

# Skill: Segment Analysis

## Purpose
Understand which market segments are driving business and identify concentration or dependency risks.

## Steps
1. Call `get_segment_mix(stay_month)` to retrieve segment breakdown
2. Rank segments by room nights and revenue share
3. Apply OTA dependency check
4. Flag concentration if any single segment > 60%
5. Recommend diversification or protection action

## Judgment Thresholds

### OTA Dependency
- **High risk**: OTA > 50% of room nights → commission drain; push direct channels
- **Watch**: OTA 30–50% → monitor; incentivise direct bookings
- **Healthy**: OTA < 30% → good channel mix

### Corporate Share
- **Strong**: Corporate (CNR + CNI + CSR) > 30% → stable base; protect corporate rates
- **Weak**: Corporate < 15% → vulnerability to leisure demand swings

### Segment Concentration
- Any single segment > 60% room nights → flag concentration risk
- Ideal: no segment > 40% → balanced mix

## Answer Style
Lead with top 2–3 segments by room nights. Flag any OTA dependency immediately.
"Our mix for [month]: X% OTA (🔴 HIGH RISK / 🟡 WATCH / 🟢), Y% Corporate, Z% Leisure..."
