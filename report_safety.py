"""Keep exported model text from loading local files or network resources."""
import bleach
import markdown


def safe_report_html(text):
    html = markdown.markdown(text, extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists'])
    return bleach.clean(html, tags=['p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li',
                        'table', 'thead', 'tbody', 'tr', 'th', 'td', 'strong', 'em', 'blockquote',
                        'code', 'pre', 'a', 'hr'], attributes={'a': ['href', 'title']},
                        protocols=['https', 'http'], strip=True)


def deny_resource_fetch(url, *args, **kwargs):
    raise ValueError('External and local resources are disabled in research exports')
