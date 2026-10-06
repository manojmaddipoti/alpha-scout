import json
from types import SimpleNamespace as N
import pandas as pd
import pytest
import stock_research as research
import search_agent as agent
from research_evidence import ACTIVE_EVIDENCE, EvidenceLog
from valuation import calculate_valuation
from metrics import statement_history, peer_comparability, INCOME_FIELDS


def full_memo():
    return '\n\n'.join('## '+s+'\nEvidence [E1]. Analysis with limitations.' for s in research.SECTIONS)


def seed(monkeypatch):
    monkeypatch.setattr(agent,'get_financial_metrics',lambda t:json.dumps({'ticker':t,'company_name':'Company '+t,'security_type':'EQUITY','latest_price':100,'trend_status':'current'}))
    monkeypatch.setattr(agent,'get_sec_filing',lambda t:json.dumps({'ticker':t,'documents':[{'url':'https://www.sec.gov/test','excerpts':{'mda':'primary evidence'}}]}))
    monkeypatch.setattr(agent,'web_search',lambda q:json.dumps({'results':[{'url':'https://issuer.example/earnings','content':'result'}]}))
    monkeypatch.setattr(agent,'get_competitor_metrics',lambda t,ps:json.dumps({'target':t,'rows':[{'ticker':x,'company_name':x} for x in [t,*ps]]}))


def test_ticker_research_requires_no_portfolio_and_collects_peers(monkeypatch):
    seed(monkeypatch)
    calls=[]
    def run(messages,model):
        calls.append(messages)
        agent._dispatch_tool('get_competitor_metrics',{'target_ticker':'MSFT','competitors':['ORCL','GOOG','AMZN']},[])
        return full_memo(),['MSFT']
    monkeypatch.setattr(research,'run_smart_agent',run)
    result=research.run_stock_research(' msft ','claude-test','gpt-test')
    assert result.ticker=='MSFT'
    assert result.review_status=='Independent challenge completed'
    assert len(calls)==2
    assert all('workspace' not in r['tool'] for r in result.evidence)
    assert 'target-plus-competitor' not in ' '.join(result.flags)
    assert ACTIVE_EVIDENCE.get() is None
    assert len(result.evidence)>=5


def test_missing_peer_data_gets_one_repair_and_visible_gap(monkeypatch):
    seed(monkeypatch)
    calls=[]
    monkeypatch.setattr(research,'run_smart_agent',lambda *args:(calls.append(args) or (full_memo(),[])))
    result=research.run_stock_research('MSFT','claude-test')
    assert len(calls)==2
    assert any('competitor dataset' in f for f in result.flags)
    assert 'Evidence and completeness gaps' in result.report


def test_failure_fallback_cannot_self_challenge(monkeypatch):
    seed(monkeypatch)
    def run(messages,model):
        if model.startswith('claude'): raise agent.ResearchFailure('unavailable')
        agent._dispatch_tool('get_competitor_metrics',{'target_ticker':'MSFT','competitors':['ORCL']},[])
        return full_memo(),[]
    monkeypatch.setattr(research,'run_smart_agent',run)
    result=research.run_stock_research('MSFT','claude-test','gpt-test')
    assert result.review_status=='Fallback research — unchallenged'
    assert '# Independent challenge' not in result.report
    assert ACTIVE_EVIDENCE.get() is None


def test_evidence_is_reset_after_total_failure(monkeypatch):
    seed(monkeypatch)
    monkeypatch.setattr(research,'run_smart_agent',lambda *a:(_ for _ in ()).throw(agent.ResearchFailure('failed')))
    with pytest.raises(agent.ResearchFailure): research.run_stock_research('MSFT','claude-test')
    assert ACTIVE_EVIDENCE.get() is None


def test_unknown_ids_and_missing_headings_are_exposed():
    log=EvidenceLog()
    flags=research.coverage_report(log,'MSFT','## Research verdict\nConfident answer [E999] https://made-up.example/source')
    assert any('Unknown evidence IDs' in f for f in flags)
    assert any('Missing report sections' in f for f in flags)
    assert any('URLs' in f for f in flags)


def test_source_read_requires_run_local_public_discovery(monkeypatch):
    log=EvidenceLog();token=ACTIVE_EVIDENCE.set(log)
    try:
        log.record('web_search',{},json.dumps({'results':[{'url':'https://issuer.example/earnings'}]}))
        called=[]
        monkeypatch.setattr(agent,'get_tavily_client',lambda:N(extract=lambda **kw:called.append(kw) or {'results':[{'url':kw['urls'][0],'raw_content':'primary text'}]}))
        assert 'error' in json.loads(agent.read_source('file:///etc/passwd'))
        assert 'error' in json.loads(agent.read_source('http://127.0.0.1/private'))
        assert 'error' in json.loads(agent.read_source('https://unknown.example/a'))
        assert json.loads(agent.read_source('https://issuer.example/earnings'))['documents'][0]['excerpt']=='primary text'
        assert len(called)==1
    finally: ACTIVE_EVIDENCE.reset(token)


def assumptions(method='equity_per_share'):
    return {'method':method,'currency':'USD','current_price':100,'years':3,
            'scenarios':[{'name':name,'terminal_metric':metric,'exit_multiple':10,'terminal_net_debt':100,
                          'terminal_shares':10,'cumulative_dividends_per_share':0}
                         for name,metric in [('bear',5),('base',10),('bull',20)]]}


def test_equity_multiple_does_not_subtract_debt_twice():
    result=calculate_valuation(assumptions())
    assert [r['target_price'] for r in result['results']]==[50,100,200]
    assert result['results'][2]['annualized_price_return_pct']==pytest.approx((2**(1/3)-1)*100)


def test_enterprise_bridge_and_equity_floor():
    result=calculate_valuation(assumptions('enterprise_multiple'))
    assert [r['target_price'] for r in result['results']]==[0,0,10]


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-1,True])
def test_bad_valuation_inputs_rejected(bad):
    args=assumptions();args['current_price']=bad
    with pytest.raises(ValueError):calculate_valuation(args)


def test_statement_history_keeps_nulls_and_dates():
    df=pd.DataFrame({'2025-12-31':[100,None],'2024-12-31':[80,4]},index=['Total Revenue','Diluted EPS'])
    rows=statement_history(df,INCOME_FIELDS,4)
    assert rows[0]['period_end']=='2025-12-31'
    assert rows[0]['diluted_eps'] is None
    assert rows[1]['revenue']==80


def test_peer_periods_and_currencies_are_not_silently_comparable():
    gaps=peer_comparability([{'ticker':'A','financial_period':'2025-12-31','financial_currency':'USD'},
                            {'ticker':'B','financial_period':'2025-06-30','financial_currency':'EUR'}])
    assert any('financial_period' in g for g in gaps)
    assert any('financial_currency' in g for g in gaps)


@pytest.mark.parametrize('symbol',['','NVDA AMD','../../secret','https://example.com'])
def test_ticker_validation(symbol):
    with pytest.raises(ValueError):research.normalize_ticker(symbol)


def test_calculator_arguments_cannot_create_discovered_urls():
    log=EvidenceLog()
    log.record('calculate_valuation',{},json.dumps({'assumptions':{'url':'https://attacker.example/injected'}}))
    assert not log.urls


def test_annual_margin_uses_matching_statement_not_vendor_ttm(monkeypatch):
    import metrics
    fake=N(info={'grossMargins':0.9,'operatingMargins':0.8},
           financials=pd.DataFrame({'2025-12-31':[100,40,20]},index=['Total Revenue','Gross Profit','Operating Income']),
           cashflow=pd.DataFrame(),balance_sheet=pd.DataFrame())
    monkeypatch.setattr(metrics.yf,'Ticker',lambda t:fake)
    result=metrics.get_equity_metrics('TEST')
    assert result['gross_margin_pct']==40
    assert result['operating_margin_pct']==20
    assert 'annual' in result['margin_basis']


def test_exhausted_credits_have_actionable_sanitized_message():
    class QuotaError(Exception):
        status_code=429
    result=agent.provider_error('OpenAI',QuotaError('credit_balance_exhausted no credits'))
    assert 'credits or quota are exhausted' in str(result)


def test_sec_metadata_survives_parser_failure_and_extraction_fallback(monkeypatch):
    import edgar
    monkeypatch.setenv('SEC_IDENTITY','Test test@example.com')
    monkeypatch.setattr(edgar,'set_identity',lambda v:None)
    f=N(form='10-K',filing_date='2026-07-29',document_url=None,primary_document='report.htm',
        accession_no='0000123456-26-000001',cik=12345,
        obj=lambda:(_ for _ in ()).throw(AttributeError('parser failure')),
        text=lambda:(_ for _ in ()).throw(AttributeError('parser failure')))
    monkeypatch.setattr(edgar,'Company',lambda t:N(get_filings=lambda **kw:N(latest=lambda:f)))
    calls=[]
    monkeypatch.setattr(agent,'get_tavily_client',lambda:N(extract=lambda **kw:calls.append(kw) or {'results':[{'raw_content':'Primary filing content'}]}))
    data=json.loads(agent.get_sec_filing('TEST'))
    assert data['documents'][0]['content_status']=='extracted'
    assert calls[0]['urls']==['https://www.sec.gov/Archives/edgar/data/12345/000012345626000001/report.htm']


def test_followup_does_not_reuse_prior_citation_ids(monkeypatch):
    def run(messages, model):
        record=json.loads(ACTIVE_EVIDENCE.get().record('web_search', {}, '{"results": []}'))
        return 'New evidence [' + record['id'] + ']', []
    monkeypatch.setattr(research, 'run_smart_agent', run)
    result=research.run_followup('MSFT', [{'role':'assistant','content':'Earlier follow-up [E25]'}], 'Why?', 'test', [])
    assert '[E26]' in result


def test_unavailable_gemini_model_is_actionable():
    class MissingModel(Exception):
        code=404
    assert 'configured model is unavailable' in str(agent.provider_error('Gemini', MissingModel()))
