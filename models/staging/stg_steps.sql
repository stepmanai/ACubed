{{ config(
    materialized = 'view',
    schema = 'features'
) }}

with source as (

    select *
    from {{ source('features', 'steps') }}

),

renamed as (

    select
        note_id,
        song_id,
        index,
        framers,
        orientation,
        color,
        timestamp,
        _dlt_load_id
    from source

)

select *
from renamed
