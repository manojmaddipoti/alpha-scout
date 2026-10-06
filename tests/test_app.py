"""Ticker-only UI must not read or send legacy portfolio context."""
import sys
from pathlib import Path
from types import SimpleNamespace
import database
import stock_research
import streamlit
from streamlit.testing.v1 import AppTest


def test_ticker_starts_independent_research_and_preserves_private_history(tmp_path, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-not-used')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    monkeypatch.setattr(database, 'DB_NAME', str(tmp_path/'ui.sqlite'))
    database.init_db()
    database.save_workspace('ui-user', 'PRIVATE PORTFOLIO CASH MUST NOT BE SENT', [])
    monkeypatch.setattr(database, 'load_workspace', lambda *a: (_ for _ in ()).throw(AssertionError('No portfolio read allowed')))
    monkeypatch.setitem(sys.modules, 'weasyprint', None)
    monkeypatch.setattr(streamlit, 'user', SimpleNamespace(is_logged_in=True, to_dict=lambda:{'sub':'ui-user'}))
    from config import Config
    monkeypatch.setattr(Config, 'ALLOWED_EMAILS', set())
    calls=[]
    def fake_run(ticker, proposer, challenger):
        calls.append((ticker,proposer,challenger))
        return stock_research.ResearchResult(ticker,'2026-10-05T00:00:00+00:00','Independent stock memo',[],[],proposer,challenger,'Unchallenged')
    monkeypatch.setattr(stock_research,'run_stock_research',fake_run)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'app.py')).run(timeout=20)
    assert not app.exception
    assert not app.text_area
    app.text_input[0].set_value('msft')
    next(b for b in app.button if b.label=='Research stock').click().run(timeout=20)
    assert not app.exception
    assert calls[0][0]=='MSFT'
    assert any('Independent stock memo' in m.value for m in app.markdown)
    sid=database.get_all_sessions('ui-user')[0][0]
    assert database.load_research_report('ui-user',sid)['ticker']=='MSFT'
    assert database.load_research_report('intruder',sid) is None
    # A second ticker gets a new investigation, without the first conversation.
    app.text_input[0].set_value('TSM')
    next(b for b in app.button if b.label=='Research stock').click().run(timeout=20)
    assert calls[-1][0]=='TSM'
    assert len(database.get_all_sessions('ui-user'))==2
