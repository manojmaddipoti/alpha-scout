"""Exercise the signed-in workflow without external API calls or native PDF libraries."""
import sys
from pathlib import Path
from types import SimpleNamespace

import database
import research_workspace
import streamlit
from streamlit.testing.v1 import AppTest


def test_authenticated_research_and_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-not-used')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    monkeypatch.setattr(database, 'DB_NAME', str(tmp_path/'ui.sqlite'))
    monkeypatch.setitem(sys.modules, 'weasyprint', None)
    monkeypatch.setattr(streamlit, 'user', SimpleNamespace(is_logged_in=True, to_dict=lambda:{'sub':'ui-user'}))
    from config import Config
    monkeypatch.setattr(Config, 'ALLOWED_EMAILS', set())
    calls = []
    def fake_run(messages, model):
        calls.append(messages)
        return 'Completed research memo', []
    monkeypatch.setattr(research_workspace, 'run_smart_agent', fake_run)
    app = AppTest.from_file(str(Path(__file__).parents[1]/'app.py')).run(timeout=20)
    assert not app.exception
    app.text_area[0].set_value('Cash and accounts need confirmation')
    next(b for b in app.button if b.label == 'Save and confirm current notes').click().run()
    assert database.load_workspace('ui-user')['context'] == 'Cash and accounts need confirmation'
    app.chat_input[0].set_value('Analyze TEST').run(timeout=20)
    assert not app.exception
    assert any('Completed research memo' in item.value for item in app.markdown)
    assert any('Cash and accounts need confirmation' in m['content'] for m in calls[0])
    session_id = database.get_all_sessions('ui-user')[0][0]
    assert 'Completed research memo' in database.load_messages('ui-user',session_id)[-1]['content']
