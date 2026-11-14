{#- Dialect macros for E3 (PLAN Amendment 4: "keep SQL portable with dbt macros where dialects
    differ"). Each `default__` body reproduces the DuckDB SQL the models used before E3, so the
    DuckDB warehouse is unchanged; the `snowflake__` body is the Snowflake equivalent. -#}

{#- count(*) of the rows where `cond` holds -#}
{% macro count_if(cond) %}{{ return(adapter.dispatch('count_if')(cond)) }}{% endmacro %}
{% macro default__count_if(cond) %}count(*) filter (where {{ cond }}){% endmacro %}
{% macro snowflake__count_if(cond) %}count_if({{ cond }}){% endmacro %}

{#- aggregate `fn(expr)` over the rows where `cond` holds -#}
{% macro agg_if(fn, expr, cond) %}{{ return(adapter.dispatch('agg_if')(fn, expr, cond)) }}{% endmacro %}
{% macro default__agg_if(fn, expr, cond) %}{{ fn }}({{ expr }}) filter (where {{ cond }}){% endmacro %}
{% macro snowflake__agg_if(fn, expr, cond) %}{{ fn }}(iff({{ cond }}, {{ expr }}, null)){% endmacro %}

{#- mean of an integer column: Snowflake's avg() of an integer returns a fixed-point NUMBER (3
    decimals in a window), DuckDB a double -#}
{% macro avg_double(expr) %}{{ return(adapter.dispatch('avg_double')(expr)) }}{% endmacro %}
{% macro default__avg_double(expr) %}avg({{ expr }}){% endmacro %}
{% macro snowflake__avg_double(expr) %}avg(cast({{ expr }} as double)){% endmacro %}

{#- continuous quantile at num / den (linear interpolation in both engines); Snowflake needs a
    constant, so the fraction is written as a 17-digit literal there -#}
{% macro quantile_cont(col, num, den) %}{{ return(adapter.dispatch('quantile_cont')(col, num, den)) }}{% endmacro %}
{% macro default__quantile_cont(col, num, den) %}quantile_cont({{ col }}, {{ num }} / {{ den }}){% endmacro %}
{% macro snowflake__quantile_cont(col, num, den) -%}
percentile_cont({{ '%.17g' % (num | float / den | float) }}) within group (order by {{ col }})
{%- endmacro %}

{#- `expr` plus `n` days / months -#}
{% macro plus_days(expr, n) %}{{ return(adapter.dispatch('plus_days')(expr, n)) }}{% endmacro %}
{% macro default__plus_days(expr, n) %}{{ expr }} + interval {{ n }} day{% endmacro %}
{% macro snowflake__plus_days(expr, n) %}dateadd(day, {{ n }}, {{ expr }}){% endmacro %}
{% macro plus_months(expr, n) %}{{ return(adapter.dispatch('plus_months')(expr, n)) }}{% endmacro %}
{% macro default__plus_months(expr, n) %}{{ expr }} + interval {{ n }} month{% endmacro %}
{% macro snowflake__plus_months(expr, n) %}dateadd(month, {{ n }}, {{ expr }}){% endmacro %}

{% macro minus_days(expr, n) %}{{ return(adapter.dispatch('minus_days')(expr, n)) }}{% endmacro %}
{% macro default__minus_days(expr, n) %}{{ expr }} - interval {{ n }} day{% endmacro %}
{% macro snowflake__minus_days(expr, n) %}dateadd(day, -{{ n }}, {{ expr }}){% endmacro %}

{#- whole days from DATE `a` to DATE `b` -#}
{% macro diff_days(a, b) %}{{ return(adapter.dispatch('diff_days')(a, b)) }}{% endmacro %}
{% macro default__diff_days(a, b) %}{{ b }} - {{ a }}{% endmacro %}
{% macro snowflake__diff_days(a, b) %}datediff(day, {{ a }}, {{ b }}){% endmacro %}

{#- whole seconds from `a` to `b` -#}
{% macro diff_seconds(a, b) %}{{ return(adapter.dispatch('diff_seconds')(a, b)) }}{% endmacro %}
{% macro default__diff_seconds(a, b) %}date_diff('second', {{ a }}, {{ b }}){% endmacro %}
{#- as double: Snowflake divides integers by a decimal literal in fixed point (rounded to 6
    decimals), DuckDB in floating point -#}
{% macro snowflake__diff_seconds(a, b) %}cast(datediff(second, {{ a }}, {{ b }}) as double){% endmacro %}

{#- weeks from the panel week of the policy date to `week_col` (a week start; exact multiple) -#}
{% macro event_week(week_col) %}{{ return(adapter.dispatch('event_week')(week_col)) }}{% endmacro %}
{% macro default__event_week(week_col) -%}
datediff('day', {{ week_start("date '" ~ var('policy_date') ~ "'") }}, {{ week_col }}) // 7
{%- endmacro %}
{% macro snowflake__event_week(week_col) -%}
cast(datediff(day, {{ week_start("date '" ~ var('policy_date') ~ "'") }}, {{ week_col }}) / 7 as integer)
{%- endmacro %}

{#- ISO day of week, 1 = Monday ... 7 = Sunday -#}
{% macro iso_dow(x) %}{{ return(adapter.dispatch('iso_dow')(x)) }}{% endmacro %}
{% macro default__iso_dow(x) %}isodow({{ x }}){% endmacro %}
{% macro snowflake__iso_dow(x) %}dayofweekiso({{ x }}){% endmacro %}

{#- local wall-clock timestamp (var timezone) of a GMT unix second; and its UTC date -#}
{% macro local_from_unix(col) %}{{ return(adapter.dispatch('local_from_unix')(col)) }}{% endmacro %}
{% macro default__local_from_unix(col) %}timezone('{{ var("timezone") }}', to_timestamp({{ col }})){% endmacro %}
{% macro snowflake__local_from_unix(col) %}convert_timezone('UTC', '{{ var("timezone") }}', to_timestamp_ntz({{ col }})){% endmacro %}
{% macro utc_date_from_unix(col) %}{{ return(adapter.dispatch('utc_date_from_unix')(col)) }}{% endmacro %}
{% macro default__utc_date_from_unix(col) %}cast(timezone('UTC', to_timestamp({{ col }})) as date){% endmacro %}
{% macro snowflake__utc_date_from_unix(col) %}cast(to_timestamp_ntz({{ col }}) as date){% endmacro %}

{#- first capture group of `pattern` in `expr` (pattern written with single backslashes) -#}
{% macro regex_group(expr, pattern) %}{{ return(adapter.dispatch('regex_group')(expr, pattern)) }}{% endmacro %}
{% macro default__regex_group(expr, pattern) %}regexp_extract({{ expr }}, '{{ pattern }}', 1){% endmacro %}
{% macro snowflake__regex_group(expr, pattern) -%}
regexp_substr({{ expr }}, '{{ pattern | replace("\\", "\\\\") }}', 1, 1, 'e', 1)
{%- endmacro %}

{#- window frame over a DATE order key: from `a` days back to `b` days back -#}
{% macro days_back(a, b) %}{{ return(adapter.dispatch('days_back')(a, b)) }}{% endmacro %}
{% macro default__days_back(a, b) %}range between interval {{ a }} day preceding and interval {{ b }} day preceding{% endmacro %}
{% macro snowflake__days_back(a, b) %}range between interval '{{ a }} day' preceding and interval '{{ b }} day' preceding{% endmacro %}

{#- the time is a Sunday -#}
{% macro is_sunday(x) %}{{ return(adapter.dispatch('is_sunday')(x)) }}{% endmacro %}
{% macro default__is_sunday(x) %}dayofweek({{ x }}) = 0{% endmacro %}
{% macro snowflake__is_sunday(x) %}dayofweekiso({{ x }}) = 7{% endmacro %}

{#- median -#}
{% macro median_of(x) %}{{ return(adapter.dispatch('median_of')(x)) }}{% endmacro %}
{% macro default__median_of(x) %}median({{ x }}){% endmacro %}
{% macro snowflake__median_of(x) %}median({{ x }}){% endmacro %}
