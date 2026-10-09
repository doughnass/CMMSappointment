from django import template

register = template.Library()


@register.filter
def abs_value(value):
    try:
        return abs(int(value))
    except (TypeError, ValueError):
        return value
