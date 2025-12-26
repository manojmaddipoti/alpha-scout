import streamlit as st
import yfinance as yf
# CORRECTED IMPORT: Added SYSTEM_PROMPT
from search_agent import run_smart_agent, get_valid_gemini_models, SYSTEM_PROMPT 
import database as db
from fpdf import FPDF
import time

# --- 1. CONFIGURATION & CSS (The "Gemini" Look) ---
st.set_page_config(page_title="Market Intelligence", page_icon="✨", layout="wide")

# Custom CSS to hide Streamlit branding and tighten the UI
st.markdown("""
<style>
    /* Hide the huge top header */
    .stAppHeader {display: none;}
    
    /* Hide the footer (Made with Streamlit) */
    footer {visibility: hidden;}
    
    /* Adjust sidebar padding */
    [data-testid="stSidebar"] {
        padding-top: 2rem;
    }
    
    /* Make the chat input sticky at the bottom with a glow */
    .stChatInputContainer {
        padding-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. AUTHENTICATION ---
SECRET_PASSWORD = "Laxmi@2026" 

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if st.session_state.password_correct:
        return True
    
    # Login Screen
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

# --- 3. SESSION MANAGEMENT (Lazy Creation) ---
if "db_init" not in st.session_state:
    db.init_db()
    st.session_state.db_init = True

# Initialize session_id as None (Waiting for first message)
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None

# --- 4. SIDEBAR NAVIGATION ---
with st.sidebar:
    st.title("✨ Market Agent")
    
    # --- MODEL SELECTOR ---
    model_choice = st.selectbox(
        "🧠 AI Model",
        [
            "gpt-4o",              # Best OpenAI Model for Agents
            "gemini-1.5-pro",      # Best Google Model for Deep Analysis
            "gemini-2.0-flash-exp" # (Optional) The latest experimental fast model
        ],
        index=0
    )
    
    # NEW CHAT BUTTON
    if st.button("➕ New Chat", use_container_width=True, type="primary"):
        st.session_state.current_session_id = None
        st.session_state.messages = [] 
        st.rerun()

    st.subheader("Recent Chats")
    
    # Load history from DB
    sessions = db.get_all_sessions()
    
    for s_id, s_title in sessions:
        if s_id == st.session_state.current_session_id:
            if st.button(f"🟢 {s_title}", key=s_id, use_container_width=True):
                pass # Already active
        else:
            if st.button(f"📄 {s_title}", key=s_id, use_container_width=True):
                st.session_state.current_session_id = s_id
                st.rerun()
    
    if st.session_state.current_session_id:
        st.divider()
        if st.button("🗑️ Delete Chat", type="secondary", use_container_width=True):
            db.delete_session(st.session_state.current_session_id)
            st.session_state.current_session_id = None
            st.rerun()

# --- 5. SYSTEM PROMPT LOGIC ---
# Load Messages Logic
if st.session_state.current_session_id is None:
    # New Chat: Use the imported SYSTEM_PROMPT from search_agent.py
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
else:
    # Existing Chat: Load history from DB
    st.session_state.messages = db.load_messages(st.session_state.current_session_id)

# --- 6. HELPERS (Charts & PDF) ---
@st.cache_data(ttl=3600)
def get_stock_history(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        return df['Close'] if not df.empty else None
    except:
        return None

def create_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    clean_text = text.replace("**", "").replace("##", "").replace("###", "")
    pdf.multi_cell(0, 10, clean_text.encode('latin-1', 'replace').decode('latin-1'))
    return pdf.output(dest='S').encode('latin-1')

# --- 7. MAIN CHAT INTERFACE ---
# Render history
for i, message in enumerate(st.session_state.messages):
    if message["role"] != "system":
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            # PDF BUTTON
            if message["role"] == "assistant":
                pdf_data = create_pdf(message["content"])
                st.download_button(
                    label="⬇️ Download PDF",
                    data=pdf_data,
                    file_name=f"report_{i}.pdf",
                    mime="application/pdf",
                    key=f"pdf_{i}"
                )

# --- 8. INPUT HANDLER ---
if prompt := st.chat_input("Ask about a stock (e.g., 'Analyze Nvidia')"):
    
    # A. LAZY CREATION: Create DB entry on first message
    if st.session_state.current_session_id is None:
        short_title = (prompt[:20] + "..") if len(prompt) > 20 else prompt
        st.session_state.current_session_id = db.create_session(short_title)
        db.save_message(st.session_state.current_session_id, "system", SYSTEM_PROMPT)

    # B. Render User Message
    st.chat_message("user").markdown(prompt)
    db.save_message(st.session_state.current_session_id, "user", prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # C. Generate Response
    with st.chat_message("assistant"):
        with st.spinner("Analyzing market data..."):
            
            # Run Agent
            response_text, found_tickers = run_smart_agent(st.session_state.messages, model_choice)
            
            # Charts
            if found_tickers:
                for ticker in found_tickers:
                    st.subheader(f"📉 {ticker} Price Trend")
                    data = get_stock_history(ticker)
                    if data is not None:
                        st.line_chart(data, color="#00FF00")
            
            # Text Response
            st.markdown(response_text)
            
            # PDF Button (Immediate)
            pdf_data = create_pdf(response_text)
            st.download_button(
                label="⬇️ Download PDF",
                data=pdf_data,
                file_name="latest_report.pdf",
                mime="application/pdf",
                key="pdf_latest"
            )

    # D. Save & Refresh
    db.save_message(st.session_state.current_session_id, "assistant", response_text)
    time.sleep(0.5) 
    st.rerun()