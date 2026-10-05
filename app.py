import time
import json
import pandas as pd
from datetime import date
from market_sessions import completed_history
from research_workspace import reviewed_research, workspace_prompt
from report_safety import safe_report_html, deny_resource_fetch
import streamlit as st
import yfinance as yf
from datetime import datetime
from search_agent import SYSTEM_PROMPT
from config import Config
from model_config import MODEL_CHOICES, provider_for_model
import database as db

# Configuration
st.set_page_config(page_title="Market Intelligence", page_icon="📊", layout="wide")

st.markdown("""
<style>
    .stAppHeader {display: none;}
    footer {visibility: hidden;}
    [data-testid="stSidebar"] {padding-top: 2rem;}
    .stChatInputContainer {padding-bottom: 20px;}
</style>
""", unsafe_allow_html=True)

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
    st.title("Market Intelligence Agent")
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
        st.rerun()

    st.subheader("Recent Chats")

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

# Message History Management
if st.session_state.current_session_id is None:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
else:
    if st.session_state.db_init:
        try:
            st.session_state.messages = db.load_messages(
                user_id, st.session_state.current_session_id
            )
        except Exception as e:
            st.error(f"Error loading messages: {e}")
            st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    else:
        st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

# Helper Functions
@st.cache_data(ttl=3600)
def get_stock_history(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        return df['Close'] if not df.empty else None
    except Exception:
        return None

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

# Private workspace: manually maintained data, isolated by authenticated owner.
workspace = {"context": "", "entries": []}
if st.session_state.db_init:
    workspace = db.load_workspace(user_id)
    with st.expander("Portfolio context and research watchlist"):
        st.caption("Private to your sign-in. Enter account types, holdings/values, cash by account, goals, drawdown tolerance and restrictions. Do not enter credentials. Reconfirm after changes; notes expire for decision use after 35 days.")
        with st.form("workspace"):
            context = st.text_area("Portfolio context", value=workspace.get("context", ""), height=180, max_chars=20000)
            table = pd.DataFrame(workspace.get("entries", []), columns=["ticker", "stage", "thesis", "review_date"])
            table["review_date"] = pd.to_datetime(table["review_date"]).dt.date
            entries_table = st.data_editor(table, num_rows="dynamic", hide_index=True, column_config={
                "ticker": st.column_config.TextColumn("Ticker", required=True),
                "stage": st.column_config.SelectboxColumn("Research stage", options=["candidate", "researching", "watchlist", "held", "paused", "rejected"], required=True),
                "thesis": st.column_config.TextColumn("Thesis / what to verify", required=True),
                "review_date": st.column_config.DateColumn("Review by", required=True),
            })
            st.caption("Add a row to track a candidate. Research stages never authorize a trade.")
            if st.form_submit_button("Save and confirm current notes"):
                try:
                    entries = entries_table.to_dict("records")
                    for entry in entries:
                        entry["ticker"] = str(entry["ticker"]).strip().upper()
                        entry["review_date"] = str(entry["review_date"])
                    db.save_workspace(user_id, context, entries)
                    st.rerun()
                except (ValueError, TypeError) as exc:
                    st.error(str(exc))
        if workspace.get("entries"):
            due = [entry["ticker"] for entry in workspace["entries"] if entry["review_date"] <= date.today().isoformat() and entry["stage"] not in ("paused", "rejected")]
            if due:
                st.warning("Research review due: " + ", ".join(due))
        st.download_button("Export private research workspace", json.dumps(workspace, indent=2), "research_workspace.json", "application/json")
st.info("Research workspace: model outputs are proposals, not validated trade instructions. Check the independent challenge and unresolved data gaps.")

# Chat Interface
for i, message in enumerate(st.session_state.messages):
    if message["role"] != "system":
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            if message["role"] == "assistant":
                st.download_button(
                    label="Download Markdown",
                    data=message["content"],
                    file_name=f"report_{i}.md",
                    mime="text/markdown",
                    key=f"md_{i}"
                )
                pdf_data = create_pdf(message["content"])
                if pdf_data:
                    st.download_button(
                        label="Download PDF",
                        data=pdf_data,
                        file_name=f"report_{i}.pdf",
                        mime="application/pdf",
                        key=f"pdf_{i}"
                    )

# User Input Handler
if prompt := st.chat_input("Ask about a stock (e.g., 'Analyze NVDA')"):

    if st.session_state.current_session_id is None and st.session_state.db_init:
        try:
            short_title = (prompt[:20] + "..") if len(prompt) > 20 else prompt
            st.session_state.current_session_id = db.create_session(user_id, short_title)
            db.save_message(
                user_id,
                st.session_state.current_session_id,
                "system",
                SYSTEM_PROMPT,
            )
        except Exception:
            st.warning("Chat history won't be saved for this session")

    st.chat_message("user").markdown(prompt)
    if st.session_state.db_init and st.session_state.current_session_id:
        try:
            db.save_message(
                user_id, st.session_state.current_session_id, "user", prompt
            )
        except Exception:
            pass

    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("Analyzing market data..."):
            try:
                # Always use the current protocol, not a historical system prompt saved in SQLite.
                request = [{"role": "system", "content": SYSTEM_PROMPT},
                           {"role": "user", "content": workspace_prompt(workspace)},
                           *[m for m in st.session_state.messages if m["role"] != "system"]]
                response_text, found_tickers = reviewed_research(request, model_choice, None if challenger == "None" else challenger)

                if found_tickers:
                    for ticker in found_tickers:
                        st.subheader(f"{ticker} Price Trend")
                        data = get_stock_history(ticker)
                        if data is not None:
                            st.line_chart(data, color="#00FF00")

                st.markdown(response_text)

                st.download_button(
                    label="Download Markdown",
                    data=response_text,
                    file_name="analysis_report.md",
                    mime="text/markdown",
                    key="md_latest"
                )

                pdf_data = create_pdf(response_text)
                if pdf_data:
                    st.download_button(
                        label="Download PDF",
                        data=pdf_data,
                        file_name="analysis_report.pdf",
                        mime="application/pdf",
                        key="pdf_latest"
                    )
            except Exception as e:
                error_msg = f"Error generating response: {str(e)}"
                st.error(error_msg)
                st.stop()  # Failed provider output must never be persisted as completed research.

    if st.session_state.db_init and st.session_state.current_session_id:
        try:
            db.save_message(
                user_id,
                st.session_state.current_session_id,
                "assistant",
                response_text,
            )
        except Exception:
            pass

    time.sleep(0.5)
    st.rerun()
