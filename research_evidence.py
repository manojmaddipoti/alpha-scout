"""Request-local provenance. Records retrieval, not the truth of model claims."""
from contextvars import ContextVar
from datetime import datetime, timezone
from urllib.parse import urlsplit
import ipaddress
import json

ACTIVE_EVIDENCE = ContextVar('alpha_scout_evidence', default=None)


def public_url(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower()
        if parsed.scheme not in ('https', 'http') or not host or parsed.username or parsed.password:
            return False
        if host == 'localhost' or host.endswith(('.local', '.internal', '.localhost')) or '.' not in host:
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return True
    except ValueError:
        return False


def source_urls(value):
    urls = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ('url', 'source_url', 'document_url') and public_url(item):
                urls.add(item)
            else:
                urls.update(source_urls(item))
    elif isinstance(value, list):
        for item in value:
            urls.update(source_urls(item))
    return urls


class EvidenceLog:
    def __init__(self):
        self.records = []
        self.id_offset = 0

    @property
    def urls(self):
        return set().union(*(source_urls(r['data']) for r in self.records if r['tool'] in {'web_search', 'read_source', 'get_sec_filing', 'get_financial_metrics', 'get_competitor_metrics'}))

    def record(self, tool, arguments, output):
        try:
            data = json.loads(output)
        except (ValueError, TypeError):
            data = {'text': str(output)}
        record = {'id': f'E{self.id_offset+len(self.records)+1}', 'tool': tool, 'arguments': arguments,
                  'retrieved_at': datetime.now(timezone.utc).isoformat(), 'data': data}
        self.records.append(record)
        return json.dumps(record, ensure_ascii=False, default=str, allow_nan=False)
