{{ config(
    materialized = 'view',
    schema = 'features'
) }}

with source as (

    select * 
    from {{ source('features', 'metadata') }}

),

renamed as (

    select
        id as metadata_id,
        name,
        author,
        author_url,
        stepauthor,
        genre,
        difficulty,
        length,
        note_count,
        min_nps,
        max_nps,
        timestamp,
        timestamp_format,
        swf_version
    from source

)

select *
from renamed
