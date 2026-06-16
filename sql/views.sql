-- Semantic views for the Revenue Manager Agent
-- These views encode business logic so tools never expose raw SQL to the agent.

-- vw_stay_night_base: Default OTB universe
-- Filters: Posted financial status + non-cancelled reservations
create or replace view public.vw_stay_night_base as
select
  r.*
from public.reservations_hackathon r
where r.reservation_status <> 'Cancelled'
  and r.financial_status = 'Posted';

-- vw_segment_stay_night: Stay-night grain with effective macro group
-- Uses market_macro_group_history for time-effective segment classification
create or replace view public.vw_segment_stay_night as
select
  b.*,
  coalesce(h.macro_group, m.macro_group) as effective_macro_group,
  m.market_name
from public.vw_stay_night_base b
join public.market_code_lookup m on m.market_code = b.market_code
left join lateral (
  select h.macro_group
  from public.market_macro_group_history h
  where h.market_code = b.market_code
    and b.stay_date >= h.valid_from
    and (h.valid_to is null or b.stay_date < h.valid_to)
  order by h.valid_from desc
  limit 1
) h on true;
