# Metric Definitions

## Room Nights vs Stay Rows vs Reservations

- **Reservation**: One hotel booking (unique `reservation_id`). A guest booking 2 rooms for 3 nights = 1 reservation.
- **Stay rows**: Rows in `reservations_hackathon`. Grain is `reservation_id × stay_date`. 1 reservation × 3 nights = 3 rows.
- **Room nights**: `SUM(number_of_spaces)` at stay-date grain. 2 rooms × 3 nights = 6 room nights.

## Default OTB Filters

Default on-the-books universe for GM briefings:
- `reservation_status <> 'Cancelled'` — exclude cancelled bookings
- `financial_status = 'Posted'` — exclude provisional/unposted business

Both filters are pre-applied in `vw_stay_night_base`.

## Pickup Window Boundaries

`get_pickup_delta(booking_window_days, future_stay_from)` uses **Europe/London local midnight** as day boundaries. The `create_datetime` column stores UTC; comparison converts to London local time before applying the window. This matches how a London-based GM would count "bookings in the last 7 days."

## Effective Macro Group

`effective_macro_group` in `vw_segment_stay_night` is resolved via `market_macro_group_history` using `stay_date ∈ [valid_from, valid_to)`. If no history row applies, falls back to `market_code_lookup.macro_group`. This ensures segment reclassifications are applied historically-correctly.
