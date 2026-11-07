{#- Return `col` cast to `dtype` if the relation/expression exposes it, else a typed NULL.
    Used for columns that exist only in some TLC years (e.g. cbd_congestion_fee from 2025). -#}
{% macro column_or_null(from_expr, col, dtype) %}
  {%- if execute -%}
    {%- set res = run_query("select column_name from (describe select * from " ~ from_expr ~ ")") -%}
    {%- set names = res.columns[0].values() | map('lower') | list -%}
    {%- if col | lower in names -%}
      try_cast({{ col }} as {{ dtype }})
    {%- else -%}
      cast(null as {{ dtype }})
    {%- endif -%}
  {%- else -%}
    cast(null as {{ dtype }})
  {%- endif -%}
{% endmacro %}
