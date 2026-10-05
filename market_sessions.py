"""Completed US exchange sessions; intraday rows never count as closing signals."""
from datetime import datetime, timedelta, timezone
import pandas_market_calendars as mcal


def completed_history(history, now=None):
    now = now or datetime.now(timezone.utc)
    schedule = mcal.get_calendar('NYSE').schedule(start_date=(now-timedelta(days=550)).date(), end_date=now.date())
    completed = schedule[schedule.market_close <= now]
    if completed.empty:
        raise ValueError('No completed session available')
    expected = completed.index[-1].date()
    allowed = set(completed.index.date)
    clean = history[[stamp.date() in allowed for stamp in history.index]].sort_index()
    clean = clean[~clean.index.duplicated(keep='last')]
    return clean, expected
