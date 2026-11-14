{{ config(enabled=target.type != 'snowflake') }}  {#- E3: DuckDB only (raw-file cleaning) #}
-- Fails if any month removes more than var('max_monthly_removal_ratio') x the median monthly share
-- of rows (duplicates + every validity rule). This is the test that would have caught the 2025
-- Flex Fare surprise; a new failure is a data finding to investigate, not a threshold to raise.
with m as (
    select source_month, (raw_rows - valid_rows)::double / raw_rows as share_removed
    from {{ ref('fct_data_quality_monthly') }}
),
med as (select median(share_removed) as med from m)
select m.source_month, m.share_removed, med.med
from m, med
where m.share_removed > {{ var('max_monthly_removal_ratio') }} * med.med
