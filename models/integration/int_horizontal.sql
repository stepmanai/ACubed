{{ config(
    materialized='table',
    schema='features',
    unique_key='note_id'
) }}

{% set density_thresholds = var("density_thresholds") %}

WITH steps AS (
    SELECT
        note_id,
        song_id,
        index,
        timestamp
    FROM {{ ref('stg_steps') }}
),

paired_steps AS (
    SELECT
        base.note_id,
        base.song_id,
        base.index,
        base.timestamp,
        neighbor.timestamp - base.timestamp AS time_diff
    FROM steps AS base
    JOIN steps AS neighbor
        ON base.song_id = neighbor.song_id
        AND neighbor.timestamp BETWEEN base.timestamp - 117 AND base.timestamp + 118
),

scored AS (
    SELECT
        ps.note_id,
        ps.song_id,
        ps.index,
        ps.timestamp,
        CASE
        {% for lower, upper, weight in density_thresholds %}
            {% set operator = '<=' if loop.last else '<' %}
            WHEN ps.time_diff >= {{ lower }} AND ps.time_diff {{ operator }} {{ upper }} THEN {{ weight }}
        {% endfor %}
            ELSE 0.0
        END AS weight
    FROM paired_steps AS ps
),

final AS (
    SELECT
        note_id,
        ANY_VALUE(song_id) AS song_id,
        ANY_VALUE(index) AS index,
        ANY_VALUE(timestamp) AS timestamp,
        SUM(weight) AS density
    FROM scored
    GROUP BY note_id
)

SELECT * FROM final
