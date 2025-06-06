{% macro apply_judge_window(thresholds, step_alias='a', window_alias='b') %}
    {% set offset_expr = window_alias ~ '.timestamp - ' ~ step_alias ~ '.timestamp' %}
    case
        {% for lower, upper, weight in thresholds %}
            when (
                {# Determine inclusive/exclusive boundaries based on threshold range #}
                {% if lower == -17 and upper == 17 %}
                    {{ offset_expr }} >= {{ lower }} and {{ offset_expr }} <= {{ upper }}
                {% elif lower > 0 %}
                    {{ offset_expr }} > {{ lower }} and {{ offset_expr }} <= {{ upper }}
                {% else %}
                    {{ offset_expr }} >= {{ lower }} and {{ offset_expr }} < {{ upper }}
                {% endif %}
            ) then {{ weight }}
        {% endfor %}
        else 0.0
    end
{% endmacro %}
