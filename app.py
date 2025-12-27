#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os

# ============================================================
# EMERGENCY STARTUP DIAGNOSTICS
# ============================================================
print("=" * 80, flush=True)
print("🚨 APP.PY EXECUTION STARTED", flush=True)
print(f"Python: {sys.version}", flush=True)
print(f"CWD: {os.getcwd()}", flush=True)
print("=" * 80, flush=True)
sys.stdout.flush()

# ============================================================
# STEP 1: Check Environment Variables
# ============================================================
print("🔍 Checking environment variables...", flush=True)

env_vars = {
    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
    "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY"),
    "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY"),
    "SEC_IDENTITY": os.getenv("SEC_IDENTITY"),
}

for key, value in env_vars.items():
    if value:
        print(f"  ✅ {key}: {'*' * 10}{value[-4:]}", flush=True)
    else:
        print(f"  ❌ {key}: MISSING", flush=True)

sys.stdout.flush()

# ============================================================
# STEP 2: Import Streamlit FIRST (to initialize runtime)
# ============================================================
print("📦 Importing streamlit...", flush=True)
try:
    import streamlit as st
    print("✅ Streamlit imported", flush=True)
except Exception as e:
    print(f"❌ Streamlit import FAILED: {e}", flush=True)
    sys.exit(1)

# ============================================================
# STEP 3: Import other dependencies
# ============================================================
print("📦 Importing yfinance...", flush=True)
try:
    import yfinance as yf
    print("✅ yfinance imported", flush=True)
except Exception as e:
    print(f"❌ yfinance import FAILED: {e}", flush=True)
    st.error(f"Failed to import yfinance: {e}")
    sys.exit(1)

print("📦 Importing search_agent...", flush=True)
try:
    from search_agent import run_smart_agent, get_valid_gemini_models, SYSTEM_PROMPT
    print("✅ search_agent imported", flush=True)
except Exception as e:
    print(f"❌ search_agent import FAILED: {e}", flush=True)
    import traceback
    traceback.print_exc()
    st.error(f"Failed to import search_agent: {e}")
    sys.exit(1)

print("📦 Importing database...", flush=True)
try:
    import database as db
    print("✅ database imported", flush=True)
except Exception as e:
    print(f"❌ database import FAILED: {e}", flush=True)
    st.error(f"Failed to import database: {e}")
    sys.exit(1)

print("📦 Importing FPDF...", flush=True)
try:
    from fpdf import FPDF
    print("✅ FPDF imported", flush=True)
except Exception as e:
    print(f"❌ FPDF import FAILED: {e}", flush=True)
    st.error(f"Failed to import FPDF: {e}")
    sys.exit(1)

import time

print("=" * 80, flush=True)
print("✅ ALL IMPORTS COMPLETED SUCCESSFULLY", flush=True)
print("=" * 80, flush=True)
sys.stdout.flush()

# --- 1. CONFIGURATION & CSS ---
st.set_page_config(page_title="Market Intelligence", page_icon="✨", layout="wide")

st.markdown("""
<style>
    .stAppHeader {display: none;}
    footer {visibility: hidden;}
    [data-testid="stSidebar"] {padding-top: 2rem;}
    .stChatInputContainer {padding-bottom: 20px;}
</style>
""", unsafe_allow_html=True)

# --- 2. AUTHENTICATION ---
SECRET_PASSWORD = os.getenv("APP_PASSWORD", "Laxmi@2026")

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if st.session_state.password_correct:
        return True
    
    col1, col2, col3 = st.columns([1,2,1])
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

# --- 3. SESSION MANAGEMENT (Safe DB Init) ---
if "db_init" not in st.session_state:
    try:
        print("🗄️ Initializing database...", flush=True)
        db.init_db()
        st.session_state.db_init = True
        print("✅ Database initialized", flush=True)
    except Exception as e:
        print(f"❌ Database init failed: {e}", flush=True)
        st.error(f"Database initialization failed: {e}")
        st.info("The app will continue but chat history won't be saved.")
        st.session_state.db_init = False

if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None

# --- 4. SIDEBAR NAVIGATION ---
with st.sidebar:
    st.title("✨ Market Agent")
    
    model_choice = st.selectbox(
        "🧠 AI Model",
        [
            "gpt-4o",
            "gemini-3-pro-preview",
            "deep-research-pro-preview-12-2025"
        ],
        index=1
    )
    
    if st.button("➕ New Chat", use_container_width=True, type="primary"):
        st.session_state.current_session_id = None
        st.session_state.messages = []
        st.rerun()

    st.subheader("Recent Chats")
    
    if st.session_state.db_init:
        try:
            sessions = db.get_all_sessions()
            for s_id, s_title in sessions:
                if s_id == st.session_state.current_session_id:
                    if st.button(f"🟢 {s_title}", key=s_id, use_container_width=True):
                        pass
                else:
                    if st.button(f"📄 {s_title}", key=s_id, use_container_width=True):
                        st.session_state.current_session_id = s_id
                        st.rerun()
        except Exception as e:
            st.error(f"Error loading chat history: {e}")
    
    if st.session_state.current_session_id:
        st.divider()
        if st.button("🗑️ Delete Chat", type="secondary", use_container_width=True):
            try:
                db.delete_session(st.session_state.current_session_id)
                st.session_state.current_session_id = None
                st.rerun()
            except Exception as e:
                st.error(f"Error deleting chat: {e}")

# --- 5. SYSTEM PROMPT LOGIC ---
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

# --- 6. HELPERS ---
@st.cache_data(ttl=3600)
def get_stock_history(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        return df['Close'] if not df.empty else None
    except Exception as e:
        print(f"Error fetching {ticker}: {e}", flush=True)
        return None

def create_pdf(text):
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        clean_text = text.replace("**", "").replace("##", "").replace("###", "")
        pdf.multi_cell(0, 10, clean_text.encode('latin-1', 'replace').decode('latin-1'))
        return bytes(pdf.output())
    except Exception as e:
        print(f"PDF creation error: {e}", flush=True)
        return None

# --- 7. MAIN CHAT INTERFACE ---
for i, message in enumerate(st.session_state.messages):
    if message["role"] != "system":
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            if message["role"] == "assistant":
                pdf_data = create_pdf(message["content"])
                if pdf_data:
                    st.download_button(
                        label="⬇️ Download PDF",
                        data=pdf_data,
                        file_name=f"report_{i}.pdf",
                        mime="application/pdf",
                        key=f"pdf_{i}"
                    )

# --- 8. INPUT HANDLER ---
if prompt := st.chat_input("Ask about a stock (e.g., 'Analyze Nvidia')"):
    
    if st.session_state.current_session_id is None and st.session_state.db_init:
        try:
            short_title = (prompt[:20] + "..") if len(prompt) > 20 else prompt
            st.session_state.current_session_id = db.create_session(short_title)
            db.save_message(st.session_state.current_session_id, "system", SYSTEM_PROMPT)
        except Exception as e:
            print(f"Session creation error: {e}", flush=True)
            st.warning("Chat history won't be saved for this session")

    st.chat_message("user").markdown(prompt)
    if st.session_state.db_init and st.session_state.current_session_id:
        try:
            db.save_message(st.session_state.current_session_id, "user", prompt)
        except Exception as e:
            print(f"Message save error: {e}", flush=True)
    
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("Analyzing market data..."):
            try:
                response_text, found_tickers = run_smart_agent(st.session_state.messages, model_choice)
                
                if found_tickers:
                    for ticker in found_tickers:
                        st.subheader(f"📉 {ticker} Price Trend")
                        data = get_stock_history(ticker)
                        if data is not None:
                            st.line_chart(data, color="#00FF00")
                
                st.markdown(response_text)
                
                pdf_data = create_pdf(response_text)
                if pdf_data:
                    st.download_button(
                        label="⬇️ Download PDF",
                        data=pdf_data,
                        file_name="latest_report.pdf",
                        mime="application/pdf",
                        key="pdf_latest"
                    )
            except Exception as e:
                error_msg = f"Error generating response: {str(e)}"
                print(f"❌ Agent error: {e}", flush=True)
                st.error(error_msg)
                response_text = error_msg

    if st.session_state.db_init and st.session_state.current_session_id:
        try:
            db.save_message(st.session_state.current_session_id, "assistant", response_text)
        except Exception as e:
            print(f"Message save error: {e}", flush=True)
    
    time.sleep(0.5)
    st.rerun()

print("✅ App fully loaded and ready!", flush=True)
sys.stdout.flush()