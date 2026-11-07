-- One row per distinct raw trip row of each monthly file, with the number of exact copies and the
-- first validity rule it fails (NULL = valid). Materialised as a table: it is the single heavy scan
-- of the raw files; every trip-level model downstream reads it instead of the Parquet files.
--
-- Exact duplicates: rows of the same file that are identical in EVERY raw column. The grouping
-- key is the projected columns plus a 64-bit hash of the full raw row, so two rows are merged only
-- if all projected values are equal AND the full-row hashes are equal (evidence and the measured
-- counts: results/duplicates_probe.json). Built file by file (macros/trips_flagged.sql).
--
-- Rules, applied in PLAN order; `drop_reason` names the FIRST failing rule, the `fails_*` flags
-- test each rule independently. A NULL in a tested column fails that rule.
--   pickup window : source_month - straggler_days  <=  pickup_ts  <  source_month + 1 month
--                   + straggler_days (half-open; DECISIONS.md)
--   duration      : min_duration_minutes <= dropoff_ts - pickup_ts <= max_duration_hours
--   distance      : 0 < trip_distance <= max_trip_distance_miles
--   fare          : fare_amount > 0
--   pickup zone   : zone_id_min <= pu_zone_id <= zone_id_max
{{ config(materialized='table', post_hook="{{ insert_remaining_files(this) }}") }}
{%- if execute %}
{{ trips_flagged_select(yellow_files()[0]) }}
{%- else %}
{{ trips_flagged_select('') }}
{%- endif %}
