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
