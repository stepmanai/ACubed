{{ config(
    materialized = "table",
    schema = "features",
    unique_key = "note_id"
) }}

{% set concentration = var("concentration_multiplier") %}

with steps as (
    select * from {{ ref("stg_steps") }}
),

final as (
    select
        note_id,
        song_id,
        index,
        timestamp,
        ({{ concentration }} * index) / ({{ concentration }} * index + 1.0) as density
    from steps
)

select * from final
