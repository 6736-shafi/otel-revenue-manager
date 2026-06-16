# ATTESTATION.md (Phase 0)

## Candidate

- Name: Shafi Uddin
- Repository URL: https://github.com/shafiuddin/otel-revenue-manager
- Date: 2026-06-15

---

## Comprehension prompts

### 1. Fact-table grain

In one sentence, what is the grain of `reservations_hackathon`?

> One row per **reservation × stay_date**: a 3-night stay with 2 rooms generates 3 rows, each with `number_of_spaces = 2`.

### 2. Revenue columns

Name the two revenue columns and when to use each.

> **`daily_room_revenue_before_tax`**: room-only revenue for that stay_date; use when analyzing room ADR or pure accommodation revenue. **`daily_total_revenue_before_tax`**: room + packages/F&B for that stay_date; use when measuring total hotel revenue or RevPAR.

### 3. Row vs reservation

Give one example question where counting rows would be wrong.

> "How many reservations do we have in July?" — counting rows gives stay_date rows (e.g., 300 rows for 100 reservations × average 3 nights), not reservation count; should use `COUNT(DISTINCT reservation_id)`.

### 4. Schema fields

Is there an `otel_challenge_token` column in the official schema? If so, what is it used for?

> No — `otel_challenge_token` does not exist in the schema. The official schema has no such column; this appears to be a comprehension trap to verify candidates read the actual `schema.sql`.

### 5. Default OTB filters

Which `reservation_status` and `financial_status` values are excluded from default OTB?

> Excluded: `reservation_status = 'Cancelled'` and `financial_status = 'Provisional'`. Default OTB universe is **Posted + non-cancelled** rows only (implemented in `vw_stay_night_base`).

### 6. Stay date vs property date

When can `property_date` differ from `stay_date`, and which field drives monthly OTB?

> `property_date` differs from `stay_date` when the hotel's business date (local midnight rollover) doesn't align with the calendar date — e.g., a check-in at 11 PM might attribute revenue to the prior business date. Monthly OTB is driven by **`stay_date`** (the night being stayed), not `property_date`.

### 7. Point-in-time OTB

How does `as_of_utc` change which cancelled rows are included in `get_as_of_otb`?

> Without `as_of_utc`, cancelled rows are excluded. With `as_of_utc`, a cancelled reservation is **included** if `create_datetime ≤ as_of_utc AND cancellation_datetime > as_of_utc` — meaning it was on-the-books at that point in time (cancelled afterward). This lets us rebuild what OTB looked like on a past date.

### 8. Block vs transient

How does `is_block` affect a "group vs transient mix" question?

> `is_block = TRUE` identifies group/block bookings (multi-room corporate or event blocks). A "group vs transient" question splits room nights and revenue by `is_block`: block = group; non-block = transient individual bookings. Using `is_block` is more reliable than using market_code alone (some corporate codes can be either).

### 9. List pagination

How many reservations does the data site show per list page?

> 100 reservations per list page.

### 10. Pagination completeness

How will you prove you did not miss the last list page during ETL?

> I will: (1) store all scraped `reservation_id` values in `SCRAPE_MANIFEST.json` with `reservation_ids_sha256` and `reservation_ids_count`; (2) run `scripts/compute_load_fingerprint.py` to generate a `db_reservation_ids_sha256` from the database; (3) reconcile both hashes against the `/verify` page expected counts. If they match, pagination is complete.

### 11. Tool grain

For `get_otb_summary`, what is the difference between `row_count` and `reservation_count`?

> **`row_count`**: number of stay-date rows (reservation × stay_date) matching the filter — a 3-night stay = 3 rows. **`reservation_count`**: `COUNT(DISTINCT reservation_id)` — unique bookings. A GM asking "how many bookings do we have?" wants `reservation_count`; computing RevPAR or room nights uses `row_count` × `number_of_spaces`.

### 12. Human-in-the-loop

Why must `get_as_of_otb` be gated behind approval, and what goes wrong if it is not?

> `get_as_of_otb` performs a full point-in-time DB scan with complex `cancellation_datetime` logic — it's expensive (30+ seconds on large datasets) and potentially confusing: the GM might not realize they're looking at a **historical** OTB snapshot, not current. Without the gate, the agent could silently return stale data in response to what the GM thought was a current-OTB question, leading to bad commercial decisions.

### 13. Skill vs tool

Name one revenue-manager question that should load a **skill** but call **`get_segment_mix`**, not raw SQL.

> "Are we too dependent on OTA for August?" — this loads `SKILL_SEGMENT_ANALYSIS` (which applies the OTA dependency judgment threshold: > 50% = high risk) and then calls `get_segment_mix("2025-08")` to get the data. The skill provides the threshold + recommended action; the tool provides the numbers. No raw SQL is exposed.

---

## ETL design (one line)

Playwright scrapes paginated list (100/page) until no next-page, then fetches each reservation detail; idempotent via `ON CONFLICT (reservation_id, stay_date) DO UPDATE`; anchor date = scrape day ISO date stored in `load_manifest.dataset_revision`.
