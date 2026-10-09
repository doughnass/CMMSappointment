import os
from functools import lru_cache

from django import template
from django.contrib.staticfiles import finders
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def abs_value(value):
    try:
        return abs(int(value))
    except (TypeError, ValueError):
        return value


@lru_cache(maxsize=64)
def _read_asset(absolute_path, mtime):
    with open(absolute_path, encoding='utf-8') as handle:
        content = handle.read()
    # Keep the inlined file from closing the surrounding <style>/<script> element
    return content.replace('</script', '<\\/script').replace('</style', '<\\/style')


@register.simple_tag
def inline_static(path):
    """Inline a static CSS/JS file into the page.

    The source stays in static/, but pages no longer depend on the web host being
    configured to serve /static/ (shared hosts, DEBUG=False, no collectstatic).
    The cache is keyed on the file's mtime so edits are picked up.
    """
    absolute = finders.find(path)
    if not absolute:
        return mark_safe(f'/* static file not found: {path} */')
    return mark_safe(_read_asset(absolute, os.path.getmtime(absolute)))
