"""Legacy workspace validation for stored-data compatibility only. Not used by research."""
import json
import re
from datetime import date, datetime, timezone


STAGES = ('candidate', 'researching', 'watchlist', 'held', 'paused', 'rejected')


def validate_workspace(context, entries):
    if not isinstance(context, str) or len(context) > 20000:
        raise ValueError('Portfolio context must be text, at most 20,000 characters')
    if not isinstance(entries, list) or len(entries) > 30:
        raise ValueError('Keep at most 30 research entries')
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'ticker', 'stage', 'thesis', 'review_date'}:
            raise ValueError('Each entry needs ticker, stage, thesis and review_date')
        symbol = entry['ticker']
        if not isinstance(symbol, str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-^=]{0,14}', symbol) or symbol in seen:
            raise ValueError('Use unique uppercase ticker symbols')
        seen.add(symbol)
        if entry['stage'] not in STAGES or not isinstance(entry['thesis'], str) or len(entry['thesis']) > 4000:
            raise ValueError('Invalid research stage or thesis')
        if not isinstance(entry['review_date'], str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', entry['review_date']):
            raise ValueError('Review date must be YYYY-MM-DD')
        date.fromisoformat(entry['review_date'])
    return {'context': context, 'entries': entries, 'confirmed_at': datetime.now(timezone.utc).isoformat()}
