# AudioXApp/templatetags/audio_filters.py
from django import template
import math

register = template.Library()

@register.filter(name='format_duration')
def format_duration(seconds):
    """
    Formats a duration given in seconds into MM:SS or HH:MM:SS string.
    """
    if seconds is None: # Allow 0 seconds, but not None
        return "--:--"
    try:
        num_seconds = float(seconds) # Allow for float seconds initially
        if num_seconds < 0:
             return "--:--" # Or handle as error, e.g., raise ValueError
        
        num_seconds = int(round(num_seconds)) # Round to nearest whole second and convert to int

        hours = num_seconds // 3600
        minutes = (num_seconds % 3600) // 60
        remaining_seconds = num_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{remaining_seconds:02d}"
        else:
            return f"{minutes}:{remaining_seconds:02d}"
    except (ValueError, TypeError):
        return "--:--" # Return default if conversion fails