---
name: room-type-mix
description: "otel-rm-v2 | Review room type distribution on the books to identify upgrade opportunities, upsell potential, and inventory imbalances. Calls get_otb_summary."
---

# Skill: Room Type Mix Analysis

## Purpose
Assess how room inventory is being consumed across room types to surface upsell and upgrade opportunities.

## Steps
1. Call `get_otb_summary(stay_month)` for overall OTB context
2. Cross-reference against `room_type_lookup` (3 room types, ~70 rooms total)
3. Identify room type concentration and availability gaps
4. Apply upsell thresholds
5. Recommend inventory or pricing action

## Judgment Thresholds

### Superior/Suite Utilisation
- Superior/Suite > 80% booked → close lower room types to drive upsells at check-in
- Superior/Suite 50–80% → normal; offer paid upgrades at booking
- Superior/Suite < 30% → under-utilised; push upgrade offers via OTA or direct

### Standard Room Pressure
- Standard rooms > 90% booked with Superiors available → active upsell opportunity
- Standard rooms < 60% booked → consider rate positioning vs Superiors

### ADR by Room Type
- If Superior ADR < 115% of Standard ADR → room type pricing too compressed; widen gap
- Healthy spread: Superior 20–30% premium over Standard

## Answer Style
Lead with highest-demand room type and fill rate. Flag upsell opportunity clearly.
"Standard rooms are X% sold for [month]. With Y Superiors still available, we have an upsell opportunity worth £Z if converted at check-in..."
