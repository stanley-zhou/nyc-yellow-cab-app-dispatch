Extracts for the Tableau Public dashboard (reports/dashboard_spec.md); regenerate with `make tableau-extract`.
channel_zone_week.csv: valid yellow pickups per pickup zone and complete panel week (Sunday start; a row only where the zone had pickups that week, so a missing zone-week means 0); app = any e-hail app (Flex Fare before 2026-06, request_source not NULL from 2026-06); street_hail excludes the CMT contracted block (VendorID 1 outer-borough trips, ended 2026-05), which is its own column.
zone_summary.csv: app_share_excl_block_<period> and mean_weekly_pickups_<period>; growth_log_2023_2025 only for zones with >= 20 pickups/week in 2023.
zones.geojson: TLC taxi zones, WGS84, simplified.
incrementality.csv: theta = 1 + d street / d app per zone-week; not identified (estimators disagree).
lyft_entry_daily.csv: CBD + Manhattan non-CBD daily pickups by vendor; preliminary.
Sources: dbt mart fct_weekly_zone_channel and results/ files named in scripts/18_tableau_extract.py.
