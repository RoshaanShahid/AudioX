from django import template

register = template.Library()

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
