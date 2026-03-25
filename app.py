import sys
import os
import time
import streamlit as st
import yfinance as yf
from fpdf import FPDF
from search_agent import run_smart_agent, SYSTEM_PROMPT
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
SECRET_PASSWORD = os.getenv("APP_PASSWORD", "Laxmi@2026")

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
        [
            "gemini-2.5-pro",
            "gpt-4o",
            "claude-sonnet-4-6",
        ],
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

def create_pdf(text):
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        clean_text = text.replace("**", "").replace("##", "").replace("###", "")
        pdf.multi_cell(0, 10, clean_text.encode('latin-1', 'replace').decode('latin-1'))
        return bytes(pdf.output())
    except Exception:
        return None

# Chat Interface
for i, message in enumerate(st.session_state.messages):
    if message["role"] != "system":
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            if message["role"] == "assistant":
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