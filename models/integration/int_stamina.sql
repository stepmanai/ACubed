{{ config(
    materialized = "table",
    schema = "features",
    unique_key = "note_id"
) }}

{% set discount = var("stamina_discount_factor") %}
{% set window_size = var("stamina_window") %}

with horizontal as (
    select * from {{ ref('int_horizontal') }}
),

vertical as (
    select * from {{ ref('int_vertical') }}
),

work_base as (
    select 
        h.note_id,
        h.song_id,
        cast(h.index as integer) as idx,
        h.timestamp,
        h.density as horizontal,
        v.density as vertical,
        h.density * v.density as work
    from horizontal h
    join vertical v on h.note_id = v.note_id
),

-- Compute rolling weighted sum over the previous {{ window_size }} notes
weighted_base as (
    select
        *,
        sum(
            work * power({{ discount }}, idx - lag_idx)
        ) over (
            partition by song_id
            order by idx
            rows between {{ window_size }} preceding and 1 preceding
        ) as weighted_work,

        sum(
            power({{ discount }}, idx - lag_idx)
        ) over (
            partition by song_id
            order by idx
            rows between {{ window_size }} preceding and 1 preceding
        ) as total_weight
    from (
        select
            *,
            idx as lag_idx
        from work_base
    )
),

final as (
    select
        note_id,
        song_id,
        idx as index,
        timestamp,
        coalesce(weighted_work / nullif(total_weight, 0), 0) as density
    from weighted_base
)

select * from final
