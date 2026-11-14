{#- First day of the panel week containing `d` (a DATE). var('week_start'):
    'sunday' -> Sunday-start weeks, aligned with the policy date 2025-01-05 (a Sunday);
    'monday' -> ISO weeks. See DECISIONS.md (Phase 1). -#}
{% macro week_start(d) %}
  {%- if var('week_start') == 'sunday' and target.type == 'snowflake' -%}
    cast(dateadd(day, -(dayofweekiso({{ d }}) % 7), {{ d }}) as date)
  {%- elif var('week_start') == 'monday' and target.type == 'snowflake' -%}
    cast(dateadd(day, 1 - dayofweekiso({{ d }}), {{ d }}) as date)
  {%- elif var('week_start') == 'sunday' -%}
    cast({{ d }} - cast(dayofweek({{ d }}) as integer) as date)
  {%- elif var('week_start') == 'monday' -%}
    cast(date_trunc('week', {{ d }}) as date)
  {%- else -%}
    {{ exceptions.raise_compiler_error("week_start must be 'sunday' or 'monday', got " ~ var('week_start')) }}
  {%- endif -%}
{% endmacro %}
