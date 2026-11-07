-- Fails if, for any source month, raw rows do not equal duplicates + dropped + valid rows, or if
-- valid rows do not equal in-grid pickups + pickups that missed the grid.
select *
from {{ ref('fct_data_quality_monthly') }}
where raw_rows <> duplicate_rows + drop_pickup_window + drop_duration + drop_distance
                 + drop_fare + drop_pu_zone + valid_rows
   or valid_rows <> pickups_in_grid + pu_miss_edge_straggler + pu_miss_spring_forward
