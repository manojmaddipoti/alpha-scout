from types import SimpleNamespace as N
from datetime import datetime, timezone
import json
import pandas as pd
import pytest
import search_agent as agent
import research_workspace as workspace
import database
from market_sessions import completed_history
from report_safety import safe_report_html, deny_resource_fetch
from metrics import _safe_float, _history_metrics, get_equity_metrics


def test_private_workspace_and_invalid_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_NAME', str(tmp_path/'db.sqlite'))
    database.init_db()
    entries = [{'ticker':'NVDA','stage':'candidate','thesis':'Check valuation','review_date':'2026-10-30'}]
    database.save_workspace('alice', 'Private Roth cash', entries)
    assert database.load_workspace('bob')['context'] == ''
    assert database.load_workspace('alice')['context'] == 'Private Roth cash'
    entries[0]['stage'] = 'approved'
    with pytest.raises(ValueError):
        database.save_workspace('alice', '', entries)
    assert database.load_workspace('alice')['context'] == 'Private Roth cash'


def test_stale_context_is_explicit():
    assert 'STALE OR MISSING' in workspace.workspace_prompt({'confirmed_at':'2020-01-01T00:00:00+00:00'})


def test_failure_fallback_is_not_independent_review(monkeypatch):
    def run(messages, model):
        if model.startswith('claude'):
            raise agent.ResearchFailure('billing')
        return 'draft', ['TEST']
    monkeypatch.setattr(workspace, 'run_smart_agent', run)
    text, _ = workspace.reviewed_research([], 'claude-test', 'gpt-test')
    assert 'fallback, unchallenged' in text
    text, _ = workspace.reviewed_research([], 'gpt-test', 'claude-test')
    assert 'challenge unavailable' in text
    with pytest.raises(ValueError):
        workspace.reviewed_research([], 'gpt-one', 'gpt-two')


def test_openai_preserves_reasoning_and_call_ids(monkeypatch):
    reasoning = N(type='reasoning', model_dump=lambda **kw: {'type':'reasoning','id':'r','summary':[], 'encrypted_content':'cipher'})
    call = N(type='function_call', name='get_financial_metrics', arguments='{"ticker":"NVDA"}', call_id='original',
             model_dump=lambda **kw: {'type':'function_call','name':'get_financial_metrics','arguments':'{"ticker":"NVDA"}','call_id':'original'})
    count = 0
    def create(**kw):
        nonlocal count
        count += 1
        assert kw['store'] is False
        if count == 1:
            return N(status='completed', output=[reasoning, call])
        assert kw['input'][-3]['encrypted_content'] == 'cipher'
        assert kw['input'][-1]['call_id'] == 'original'
        return N(status='completed', output=[], output_text='complete memo')
    monkeypatch.setattr(agent, 'get_openai_client', lambda: N(responses=N(create=create)))
    monkeypatch.setattr(agent, 'get_financial_metrics', lambda t: '{}')
    assert agent.run_openai_logic([]) == ('complete memo', ['NVDA'])


@pytest.mark.parametrize('status,text', [('incomplete','partial'), ('completed','')])
def test_openai_incomplete_is_failure(monkeypatch, status, text):
    monkeypatch.setattr(agent, 'get_openai_client', lambda: N(responses=N(create=lambda **kw: N(status=status, output=[], output_text=text))))
    with pytest.raises(agent.ResearchFailure):
        agent.run_openai_logic([])


@pytest.mark.parametrize('reason,text', [('max_tokens','partial'), ('end_turn','')])
def test_claude_incomplete_is_failure(monkeypatch, reason, text):
    class Stream:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get_final_message(self): return N(stop_reason=reason, content=[N(text=text)])
    monkeypatch.setattr(agent, 'get_claude_client', lambda: N(messages=N(stream=lambda **kw: Stream())))
    with pytest.raises(agent.ResearchFailure):
        agent.run_claude_logic([{'role':'user','content':'test'}])


def test_resource_injection_removed():
    html = safe_report_html('<img src="file:///etc/passwd"><style>@import "http://localhost";</style><a href="javascript:alert(1)">bad</a>')
    assert '<img' not in html and '<style' not in html and 'href=' not in html
    for url in ['file:///etc/passwd', 'http://127.0.0.1/', 'https://example.com/image.png']:
        with pytest.raises(ValueError): deny_resource_fetch(url)


def test_completed_session_excludes_intraday_and_holiday():
    history = pd.DataFrame({'Close':[1,2,3]}, index=pd.to_datetime(['2026-07-02','2026-07-03','2026-07-06']))
    clean, expected = completed_history(history, datetime(2026,7,6,15,tzinfo=timezone.utc))
    assert list(clean.Close) == [1]
    assert str(expected) == '2026-07-02'


def test_missing_capital_is_not_zero_and_negative_ocf_not_favorable(monkeypatch):
    import metrics
    df = lambda values: pd.DataFrame(values, index=[pd.Timestamp('2025-12-31')]).T
    fake = N(info={}, financials=df({'Operating Income':20,'Total Revenue':100}),
             balance_sheet=df({'Cash And Cash Equivalents':10}),
             cashflow=df({'Operating Cash Flow':-10,'Stock Based Compensation':5}), history=lambda **kw: pd.DataFrame())
    monkeypatch.setattr(metrics.yf,'Ticker',lambda t:fake)
    result = get_equity_metrics('TEST')
    assert result['invested_capital'] is None
    assert result['net_cash_or_debt'] is None
    assert result['sbc_to_ocf_pct'] is None
    assert _safe_float(float('inf')) is None


def test_malformed_tool_is_data_gap():
    assert json.loads(agent._dispatch_tool('get_financial_metrics',{},[]))['error'] == 'Tool failed'


def test_sec_returns_annual_and_newer_interim(monkeypatch):
    import edgar
    def filings(form):
        item = N(form=form[0], filing_date='2026-08-01', document_url='https://www.sec.gov/filing',
                 obj=lambda:N(management_discussion='Primary facts'), text=lambda:'text')
        return N(latest=lambda:item)
    monkeypatch.setenv('SEC_IDENTITY', 'Test test@example.com')
    monkeypatch.setattr(edgar, 'Company', lambda ticker: N(get_filings=filings))
    monkeypatch.setattr(edgar, 'set_identity', lambda identity:None)
    docs = json.loads(agent.get_sec_filing('TEST'))['documents']
    assert {d['form'] for d in docs} == {'10-K', '10-Q', '8-K'}
    assert all(d['url'] for d in docs)


def test_gemini_preserves_original_signed_content(monkeypatch):
    from google.genai import types
    content = types.Content(role='model', parts=[types.Part(function_call=types.FunctionCall(name='get_financial_metrics', args={'ticker':'TEST'}), thought_signature=b'signature')])
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return N(candidates=[N(content=content)])
        assert kwargs['contents'][-2] is content
        return N(candidates=[N(content=types.Content(parts=[types.Part(text='memo')]), finish_reason='STOP')],text='memo')
    monkeypatch.setattr(agent, 'get_gemini_client', lambda: N(models=N(generate_content=generate)))
    monkeypatch.setattr(agent, 'get_financial_metrics', lambda ticker:'{}')
    assert agent.run_gemini_logic([])[0] == 'memo'


def test_mismatched_statement_dates_do_not_produce_roic(monkeypatch):
    import metrics
    fake = N(info={}, financials=pd.DataFrame({'2025-12-31':[20,100]},index=['Operating Income','Total Revenue']),
             balance_sheet=pd.DataFrame({'2024-12-31':[10,30,100]},index=['Cash And Cash Equivalents','Total Debt','Stockholders Equity']),
             cashflow=pd.DataFrame(), history=lambda **kw:pd.DataFrame())
    monkeypatch.setattr(metrics.yf,'Ticker',lambda t:fake)
    assert get_equity_metrics('TEST')['roic_pct'] is None
