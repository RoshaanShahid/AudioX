# AudioXApp/templatetags/audio_filters.py

from django import template
import math

register = template.Library()

# --- Custom Template Filters ---

@register.filter(name='format_duration')
def format_duration(seconds):
    """
    Formats a duration given in seconds into MM:SS or HH:MM:SS string.
    """
    if seconds is None:
        return "--:--"
    try:
        num_seconds = float(seconds)
        if num_seconds < 0:
            return "--:--"
        
        num_seconds = int(round(num_seconds))

        hours = num_seconds // 3600
        minutes = (num_seconds % 3600) // 60
        remaining_seconds = num_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{remaining_seconds:02d}"
        else:
            return f"{minutes}:{remaining_seconds:02d}"
    except (ValueError, TypeError):
        return "--:--"

@register.filter
def split(value, delimiter=','):
    """
    Split a string by delimiter and return a list
    Usage: {{ "a,b,c"|split:"," }}
    """
    if not value:
        return []
    return [item.strip() for item in str(value).split(delimiter)]

@register.filter
def join_with(value, delimiter=', '):
    """
    Join a list with a delimiter
    Usage: {{ my_list|join_with:", " }}
    """
    if not value:
        return ''
    return delimiter.join(str(item) for item in value)
