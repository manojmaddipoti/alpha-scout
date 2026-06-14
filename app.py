import time
import streamlit as st
import yfinance as yf
import markdown as md_lib
from weasyprint import HTML, CSS
from datetime import datetime
from search_agent import run_smart_agent, SYSTEM_PROMPT
from config import Config
from model_config import MODEL_CHOICES
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
SECRET_PASSWORD = Config.APP_PASSWORD

if not SECRET_PASSWORD:
    st.error("APP_PASSWORD is not configured. Set it in your local .env file or deployment secrets.")
    st.stop()

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if st.session_state.password_correct:
        return True

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 Login")
        pwd = st.text_input("Access Code", type="password")
        if st.button("Enter"):
            if pwd == SECRET_PASSWORD:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    return False

if not check_password():
    st.stop()

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

    model_choice = st.selectbox(
        "AI Model",
        MODEL_CHOICES,
        index=0
    )

    if st.button("New Chat", use_container_width=True, type="primary"):
        st.session_state.current_session_id = None
        st.session_state.messages = []
        st.rerun()

    st.subheader("Recent Chats")

    if st.session_state.db_init:
        try:
            sessions = db.get_all_sessions()
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
                db.delete_session(st.session_state.current_session_id)
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
            st.session_state.messages = db.load_messages(st.session_state.current_session_id)
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
        html_body = md_lib.markdown(
            text,
            extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
        )
        date_str = datetime.now().strftime("%B %d, %Y")
        full_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head><body>
  <div class="cover">
    <h1>Alpha Scout — Equity Research Memo</h1>
    <div class="meta">Generated {date_str} &nbsp;·&nbsp; Confidential &nbsp;·&nbsp; Not investment advice</div>
  </div>
  {html_body}
</body></html>"""
        return HTML(string=full_html).write_pdf(stylesheets=[CSS(string=PDF_CSS)])
    except Exception:
        return None

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
            st.session_state.current_session_id = db.create_session(short_title)
            db.save_message(st.session_state.current_session_id, "system", SYSTEM_PROMPT)
        except Exception:
            st.warning("Chat history won't be saved for this session")

    st.chat_message("user").markdown(prompt)
    if st.session_state.db_init and st.session_state.current_session_id:
        try:
            db.save_message(st.session_state.current_session_id, "user", prompt)
        except Exception:
            pass

    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("Analyzing market data..."):
            try:
                response_text, found_tickers = run_smart_agent(st.session_state.messages, model_choice)

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
                response_text = error_msg

    if st.session_state.db_init and st.session_state.current_session_id:
        try:
            db.save_message(st.session_state.current_session_id, "assistant", response_text)
        except Exception:
            pass

    time.sleep(0.5)
    st.rerun()