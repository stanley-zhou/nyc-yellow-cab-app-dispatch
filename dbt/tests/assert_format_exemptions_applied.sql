-- Fails if a row covered by a record-format exemption is dropped by the exempted rule
-- (DECISIONS.md, Phase 1: the 2025 Flex Fare and vendor-7 surprises).
select source_month, drop_reason, count(*) as n
from {{ ref('int_trips_flagged') }}
where (drop_reason = 'fare' and payment_type = {{ var('flex_fare_payment_type') }})
   or (drop_reason = 'distance' and payment_type = {{ var('flex_fare_payment_type') }}
       and coalesce(trip_distance, 0) <= 0)
   or (drop_reason = 'duration' and dropoff_ts = pickup_ts and trip_distance > 0
       and trip_distance <= {{ var('max_trip_distance_miles') }})
group by 1, 2
