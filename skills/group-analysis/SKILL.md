---
name: group-analysis
description: "otel-rm-v2 | Assess group vs transient business mix: block share, company concentration, and displacement risk. Calls get_block_vs_transient_mix."
---

# Skill: Group & Block Analysis

## Purpose
Evaluate group/block room business versus transient — block share, revenue contribution, top company concentration, and displacement risk.

## Steps
1. Call `get_block_vs_transient_mix(stay_month)` to retrieve block vs transient breakdown
2. Assess block share of room nights and revenue
3. Check top 3 company concentration
4. Apply displacement thresholds
5. Deliver assessment with recommended action

## Judgment Thresholds

### Block Share
- **Displacement risk**: Block > 40% of room nights → check transient demand; high displacement cost
- **Watch**: Block 30–40% → monitor; set pickup review date 30 days prior
- **Healthy**: Block < 30% → low displacement risk; group strategy healthy

### Group ADR vs House ADR
- Group ADR ≥ House ADR → accretive; prioritise group room protection
- Group ADR < House ADR by > 15% → dilutive; tighten future group rate minimums

### Company Concentration
- Top 3 companies > 50% of group revenue → concentration risk; diversify client base
- Top 3 companies < 30% → healthy spread

## Answer Style
Lead with total block room nights → block share → displacement risk rating → recommended action.
"We have X group rooms contracted (Y% of house). Displacement risk is [level]..."
