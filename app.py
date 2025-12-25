import streamlit as st
import yfinance as yf
from search_agent import run_smart_agent
import database as db
from fpdf import FPDF

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Market Intelligence Agent", page_icon="🤖", layout="wide")

# --- 2. AUTHENTICATION ---
SECRET_PASSWORD = "Laxmi@2026" 

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if st.session_state.password_correct:
        return True
    
    st.title("🔒 Login Required")
    pwd = st.text_input("Enter Access Code", type="password")
    if st.button("Enter"):
        if pwd == SECRET_PASSWORD:
            st.session_state.password_correct = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False

if not check_password():
    st.stop()

# --- 3. SESSION STATE MANAGEMENT ---
if "db_init" not in st.session_state:
    db.init_db()
    st.session_state.db_init = True

# Ensure we have a current session_id
if "current_session_id" not in st.session_state:
    # Try to load the most recent session, or create a new one
    existing_sessions = db.get_all_sessions()
    if existing_sessions:
        st.session_state.current_session_id = existing_sessions[0][0]
    else:
        st.session_state.current_session_id = db.create_session("New Chat")

# --- 4. SIDEBAR HISTORY (GEMINI STYLE) ---
with st.sidebar:
    st.title("🤖 Market Agent")
    
    # "New Chat" Button
    if st.button("➕ New Chat", use_container_width=True):
        new_id = db.create_session("New Chat")
        st.session_state.current_session_id = new_id
        st.rerun()

    st.divider()
    st.subheader("Recent History")

    # List all previous sessions
    sessions = db.get_all_sessions()
    for s_id, s_title in sessions:
        # Style the active button differently (simulated by emoji)
        label = f"📂 {s_title}" if s_id != st.session_state.current_session_id else f"🟢 {s_title}"
        
        if st.button(label, key=s_id, use_container_width=True):
            st.session_state.current_session_id = s_id
            st.rerun()

    st.divider()
    if st.button("🗑️ Delete Current Chat", type="primary"):
        db.delete_session(st.session_state.current_session_id)
        del st.session_state.current_session_id
        st.rerun()

# --- 5. SYSTEM PROMPT ---
SYSTEM_PROMPT = """
You are a Senior Investment Analyst.
1. **Company Mission:** Summarize in 2 sentences.
2. **Financial Health:** Table with Price, P/E, PEG, Growth, Margin.
3. **Bull & Bear:** 3 reasons for each.
4. **Verdict:** Buy, Hold, or Sell.
"""

# Load messages for the *specific* session ID
current_messages = db.load_messages(st.session_state.current_session_id)

# Initialize System Prompt if empty chat
if not current_messages:
    db.save_message(st.session_state.current_session_id, "system", SYSTEM_PROMPT)
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
else:
    st.session_state.messages = current_messages

# --- 6. CHART & PDF HELPERS ---
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

# --- 7. MAIN CHAT LOOP ---
for message in st.session_state.messages:
    if message["role"] != "system":
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

if prompt := st.chat_input("Ask about a stock..."):
    
    # 1. Update Title if it's the first message
    if len(st.session_state.messages) <= 1:
        short_title = prompt[:25] + "..." if len(prompt) > 25 else prompt
        db.update_session_title(st.session_state.current_session_id, short_title)

    # 2. User Message
    st.chat_message("user").markdown(prompt)
    db.save_message(st.session_state.current_session_id, "user", prompt)
    st.session_state.messages.append({"role": "user", "content": prompt}) # Update local state immediately for speed

    # 3. Assistant Message
    with st.chat_message("assistant"):
        with st.spinner("Analyzing..."):
            
            # Run Agent
            response_text, found_tickers = run_smart_agent(st.session_state.messages)
            
            if found_tickers:
                for ticker in found_tickers:
                    st.subheader(f"📉 Price Trend: {ticker}")
                    data = get_stock_history(ticker)
                    if data is not None:
                        st.line_chart(data, color="#00FF00")
            
            st.markdown(response_text)
            
            # PDF
            pdf_bytes = create_pdf(response_text)
            st.download_button("📄 Download PDF", pdf_bytes, "report.pdf", "application/pdf")
    
    db.save_message(st.session_state.current_session_id, "assistant", response_text)
    # Force a rerun to update the sidebar title immediately
    st.rerun()