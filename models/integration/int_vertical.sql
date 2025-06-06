{{ config(
    materialized = "table",
    schema = "features",
    unique_key = "note_id"
) }}

with steps as (
    select * from {{ ref("stg_steps") }}
),

step_deltas as (
    select
        note_id,
        song_id,
        orientation,
        index,
        timestamp,
        lead(timestamp) over (
            partition by song_id, orientation
            order by timestamp
        ) as next_timestamp
    from steps
),

min_nonzero_delta as (
    select
        min((next_timestamp - timestamp) / 1000.0) as min_delta
    from step_deltas
    where next_timestamp is not null
      and (next_timestamp - timestamp) / 1000.0 > 0
),

final as (
    select
        sd.note_id,
        sd.song_id,
        sd.index,
        sd.timestamp,
        coalesce(
            1.0 / (
                case
                    when sd.next_timestamp is null then null
                    when sd.next_timestamp = sd.timestamp then m.min_delta
                    else (sd.next_timestamp - sd.timestamp) / 1000.0
                end
            ),
            0
        ) as density
    from step_deltas sd
    cross join min_nonzero_delta m
)

select * from final
