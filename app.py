"""Ticker-first independent equity research, isolated from portfolio workflows."""
import json
from datetime import datetime
import streamlit as st
from config import Config
from model_config import MODEL_CHOICES, provider_for_model
from report_safety import safe_report_html, deny_resource_fetch
from stock_research import normalize_ticker, run_stock_research, run_followup
import database as db

st.set_page_config(page_title="Alpha Scout Independent Research", page_icon="📊", layout="wide")

# Authentication
try:
    is_logged_in = st.user.is_logged_in
except AttributeError:
    st.error(
        "OIDC authentication is not configured. Add an [auth] section to "
        ".streamlit/secrets.toml or the deployment secrets."
    )
    st.stop()

if not is_logged_in:
    st.title("Alpha Scout")
    st.caption("Sign in with the configured identity provider to continue.")
    st.button("Log in", on_click=st.login, type="primary")
    st.stop()

user_claims = st.user.to_dict()
user_id = user_claims.get("sub") or user_claims.get("email")
user_email = str(user_claims.get("email", "")).lower()
if not user_id:
    st.error("The identity provider did not return a stable user identifier.")
    st.button("Log out", on_click=st.logout)
    st.stop()
if Config.ALLOWED_EMAILS and user_email not in Config.ALLOWED_EMAILS:
    st.error("Your account is authenticated but is not authorized for this app.")
    st.button("Log out", on_click=st.logout)
    st.stop()

# Clear widget/session data when an authenticated identity changes.
if st.session_state.get("authenticated_owner") != user_id:
    st.session_state.clear()
    st.session_state.authenticated_owner = user_id

# Session and Database Initialization
if "db_init" not in st.session_state:
    try:
        db.init_db()
        st.session_state.db_init = True
    except Exception as e:
        st.error(f"Database initialization failed: {e}")
        st.info("The app will continue but chat history won't be saved.")
        st.session_state.db_init = False

if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None

# Sidebar Navigation
with st.sidebar:
    st.title("Alpha Scout Analyst")
    st.caption(user_claims.get("email") or user_claims.get("name") or "Signed in")
    st.button("Log out", on_click=st.logout, use_container_width=True)

    model_choice = st.selectbox(
        "AI Model",
        Config.available_models() or MODEL_CHOICES,
        index=0
    )

    alternatives = [m for m in Config.available_models() if provider_for_model(m) != provider_for_model(model_choice)]
    challenger = st.selectbox("Independent challenge", ["None", *alternatives], index=1 if alternatives else 0)
    st.caption("A second provider checks the thesis. Each review uses additional API credits.")

    if st.button("New Chat", use_container_width=True, type="primary"):
        st.session_state.current_session_id = None
        st.session_state.messages = []
        st.session_state.pop("transient_report", None)
        st.rerun()

    st.subheader("Research history")

    if st.session_state.db_init:
        try:
            sessions = db.get_all_sessions(user_id)
            for s_id, s_title in sessions:
                indicator = "▶ " if s_id == st.session_state.current_session_id else ""
                if st.button(f"{indicator}{s_title}", key=s_id, use_container_width=True):
                    if s_id != st.session_state.current_session_id:
                        st.session_state.current_session_id = s_id
                        st.rerun()
        except Exception as e:
            st.error(f"Error loading chat history: {e}")

    if st.session_state.current_session_id:
        st.divider()
        if st.button("Delete Current Chat", type="secondary", use_container_width=True):
            try:
                db.delete_session(user_id, st.session_state.current_session_id)
                st.session_state.current_session_id = None
                st.rerun()
            except Exception as e:
                st.error(f"Error deleting chat: {e}")

PDF_CSS = """
@page {
    size: Letter;
    margin: 0.75in 0.75in 1in 0.75in;
    @bottom-center {
        content: "Alpha Scout — Confidential Research  |  Page " counter(page) " of " counter(pages);
        font-family: 'Helvetica Neue', Arial, sans-serif;
        font-size: 9pt;
        color: #888;
    }
}
body {
    font-family: 'Georgia', 'Times New Roman', serif;
    font-size: 10.5pt;
    line-height: 1.55;
    color: #1a1a1a;
}
.cover {
    border-bottom: 2px solid #0a3d62;
    padding-bottom: 12px;
    margin-bottom: 24px;
}
.cover h1 {
    color: #0a3d62;
    font-size: 22pt;
    margin: 0;
    letter-spacing: -0.5px;
}
.cover .meta {
    color: #555;
    font-size: 9.5pt;
    margin-top: 6px;
    font-family: 'Helvetica Neue', Arial, sans-serif;
}
h1, h2, h3 {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    color: #0a3d62;
    page-break-after: avoid;
}
h1 { font-size: 16pt; border-bottom: 1px solid #ccc; padding-bottom: 4px; margin-top: 22px; }
h2 { font-size: 13pt; margin-top: 18px; }
h3 { font-size: 11.5pt; margin-top: 14px; color: #1f5582; }
p { margin: 8px 0; }
strong { color: #0a3d62; }
ul, ol { margin: 8px 0; padding-left: 22px; }
li { margin: 3px 0; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0;
    font-size: 9.5pt;
    font-family: 'Helvetica Neue', Arial, sans-serif;
}
th {
    background: #0a3d62;
    color: white;
    padding: 6px 10px;
    text-align: left;
    border: 1px solid #0a3d62;
}
td {
    padding: 6px 10px;
    border: 1px solid #ddd;
}
tr:nth-child(even) td { background: #f7f9fb; }
code {
    font-family: 'SF Mono', Monaco, Consolas, monospace;
    font-size: 9pt;
    background: #f4f4f4;
    padding: 1px 4px;
    border-radius: 3px;
}
pre {
    background: #f7f9fb;
    border-left: 3px solid #0a3d62;
    padding: 10px 14px;
    font-family: 'SF Mono', Monaco, Consolas, monospace;
    font-size: 9pt;
    overflow-x: auto;
}
blockquote {
    border-left: 3px solid #0a3d62;
    margin: 12px 0;
    padding: 6px 14px;
    color: #444;
    font-style: italic;
    background: #f9fafc;
}
"""

def create_pdf(text):
    try:
        from weasyprint import HTML, CSS
        html_body = safe_report_html(text)
        date_str = datetime.now().strftime("%B %d, %Y")
        full_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head><body>
  <div class="cover">
    <h1>Alpha Scout — Equity Research Memo</h1>
    <div class="meta">Generated {date_str} &nbsp;·&nbsp; Confidential &nbsp;·&nbsp; Not investment advice</div>
  </div>
  {html_body}
</body></html>"""
        return HTML(string=full_html, url_fetcher=deny_resource_fetch).write_pdf(stylesheets=[CSS(string=PDF_CSS)])
    except Exception:
        return None


st.title("Independent stock research")
st.caption("Enter one ticker for a detailed assessment of its business, financials, valuation and competitors. No portfolio information is needed.")

with st.form("ticker_research"):
    ticker_input = st.text_input("Stock ticker", placeholder="MSFT, NVDA, TSM or BRK-B", max_chars=15)
    submitted = st.form_submit_button("Research stock", type="primary")

if submitted:
    try:
        ticker = normalize_ticker(ticker_input)
        with st.spinner(f"Researching {ticker}: disclosures, financials, competitors and valuation..."):
            result = run_stock_research(ticker, model_choice, None if challenger == "None" else challenger)
        st.session_state.transient_report = json.loads(result.to_json())
        st.session_state.current_session_id = None
        if st.session_state.db_init:
            try:
                st.session_state.current_session_id = db.save_research_report(user_id, result.to_json())
                st.session_state.pop("transient_report", None)
            except Exception:
                st.warning("Research completed but could not be saved. Download this report before leaving.")
        st.rerun()
    except Exception as exc:
        st.error(str(exc))
        st.stop()

session_id = st.session_state.current_session_id
report = st.session_state.get("transient_report") if session_id is None else None
messages = []
if session_id and st.session_state.db_init:
    try:
        report = db.load_research_report(user_id, session_id)
        messages = db.load_messages(user_id, session_id)
    except Exception:
        st.warning("Saved research could not be loaded. Check database availability.")
if report and not messages:
    messages = [{"role": "assistant", "content": report["report"]}]

if report:
    st.subheader(f"{report['ticker']} research")
    st.caption(f"Generated {report['created_at']} · {report['review_status']}")
    if report['flags']:
        st.warning("Evidence or completeness gaps remain. Read the report's gap list before relying on its conclusions.")
    st.download_button("Download research and source data", json.dumps(report, indent=2),
                       f"{report['ticker']}_research.json", "application/json")
elif session_id:
    st.info("Archived conversation. Start a ticker report above for independent research; archived portfolio context is not reused.")
else:
    st.markdown("The report covers business economics, financial history, earnings quality, competitors, valuation scenarios, catalysts and the bear case. A separate model can challenge the findings.")

for i, message in enumerate(messages):
    if message['role'] not in ('assistant', 'user'):
        continue
    with st.chat_message(message['role']):
        st.markdown(message['content'])
        if message['role'] == 'assistant':
            st.download_button("Download Markdown", message['content'], f"research_{i}.md", "text/markdown", key=f"md_{i}")
            pdf = create_pdf(message['content'])
            if pdf:
                st.download_button("Download PDF", pdf, f"research_{i}.pdf", "application/pdf", key=f"pdf_{i}")

if report:
    question = st.chat_input("Ask a follow-up about this stock or its competitors")
    if question:
        try:
            with st.spinner("Investigating your follow-up..."):
                response = run_followup(report['ticker'], messages, question, model_choice, report.get('evidence', []))
            if session_id and st.session_state.db_init:
                db.save_message(user_id, session_id, 'user', question)
                db.save_message(user_id, session_id, 'assistant', response)
                st.rerun()
            else:
                st.chat_message('user').markdown(question)
                st.chat_message('assistant').markdown(response)
                st.download_button("Download follow-up", response, "followup.md", "text/markdown")
                st.warning("This conversation is not saved because durable storage is unavailable.")
        except Exception as exc:
            st.error(str(exc))
