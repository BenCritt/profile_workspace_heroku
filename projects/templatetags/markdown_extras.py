from django import template
import markdown
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter(name='render_markdown')
def render_markdown(text):
    if not text:
        return ""
    # Convert markdown to HTML. 
    # The 'fenced_code' and 'tables' extensions help format AI output properly.
    html = markdown.markdown(text, extensions=['fenced_code', 'tables'])
    return mark_safe(html)