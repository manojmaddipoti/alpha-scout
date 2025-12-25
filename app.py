import streamlit as st
import yfinance as yf
import pandas as pd
from search_agent import run_smart_agent
import database as db
from fpdf import FPDF
import re

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Market Intelligence Agent", page_icon="🤖", layout="wide")

# --- 2. PASSWORD PROTECTION ---
SECRET_PASSWORD = "Laxmi@2026" 

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    # Login UI
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

# --- 3. DATABASE INIT ---
if "db_init" not in st.session_state:
    db.init_db()
    st.session_state.db_init = True

# --- 4. PDF GENERATOR HELPER ---
def create_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Simple clean up of Markdown for the PDF (Removing **bold** markers)
    clean_text = text.replace("**", "").replace("##", "").replace("###", "")
    
    # Split text into lines to avoid overflow
    # encoding='latin-1' deals with special characters often found in finance text
    pdf.multi_cell(0, 10, clean_text.encode('latin-1', 'replace').decode('latin-1'))
    
    return pdf.output(dest='S').encode('latin-1')

# --- 5. SIDEBAR (The Gemini Look) ---
with st.sidebar:
    st.title("🤖 Market Agent")
    
    # The "New Chat" Button (Like the Pencil Icon)
    if st.button("➕ New Chat", use_container_width=True):
        db.clear_db()
        st.rerun()
    
    st.divider()
    
    # Collapsible Criteria (Cleaner Look)
    with st.expander("✅ Investment Criteria (View Only)"):
        st.markdown("""
        - Rev Growth > 25%
        - PEG < 2.0
        - NRR > 115%
        - Gross Margin > 70%
        - Rule of 40 > 40%
        - SBC < 20% of Rev
        """)
        
    st.caption("v1.0.2 - Public Build")

# --- 6. SYSTEM PROMPT ---
SYSTEM_PROMPT = """
You are a Senior Investment Analyst.
When asked about a stock, you MUST follow this structure:

1. **Company Mission:** Summarize the 'mission' from the tool output in 2 sentences.
2. **Financial Health Check:**
   - Present a Markdown Table with: Price, P/E, PEG Ratio, Rev Growth, Gross Margin.
   - If PEG > 2.0, flag it as "Expensive".
   - If PEG < 1.0, flag it as "Undervalued".
3. **Bull & Bear Analysis:**
   - **🐂 Bull Case:** List 3 reasons the stock could go UP.
   - **🐻 Bear Case:** List 3 reasons the stock could go DOWN.
   - **🐻 Competition:** List 3 competitors and their growth rates.
4. **NRR Search:** If NRR is missing, search specifically for "[Company] Net Revenue Retention latest quarter".
5. **Verdict:** Buy, Hold, or Sell.
"""

# Load History Logic
stored_messages = db.load_messages()
if not stored_messages:
    db.save_message("system", SYSTEM_PROMPT)
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
else:
    # Auto-update system prompt if code changed
    if stored_messages[0]["role"] == "system" and stored_messages[0]["content"] != SYSTEM_PROMPT:
        stored_messages[0]["content"] = SYSTEM_PROMPT
    st.session_state.messages = stored_messages

# --- 7. HELPER: CHARTS ---
@st.cache_data(ttl=3600)
def get_stock_history(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        return df['Close'] if not df.empty else None
    except:
        return None

# --- 8. MAIN CHAT INTERFACE ---
# Display historical messages
for message in st.session_state.messages:
    if message["role"] != "system":
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# Input Area
if prompt := st.chat_input("Ask about a stock (e.g. 'Analyze Datadog')"):
    
    # User Message
    st.chat_message("user").markdown(prompt)
    db.save_message("user", prompt)

    # Assistant Response
    with st.chat_message("assistant"):
        with st.spinner("Analyzing market data..."):
            
            # Run the Agent
            full_history = db.load_messages()
            response_text, found_tickers = run_smart_agent(full_history)
            
            # Show Charts if tickers found
            if found_tickers:
                for ticker in found_tickers:
                    st.subheader(f"📉 Price Trend: {ticker}")
                    data = get_stock_history(ticker)
                    if data is not None:
                        st.line_chart(data, color="#00FF00")
            
            # Show Text Analysis
            st.markdown(response_text)
            
            # --- NEW: PDF DOWNLOAD BUTTON ---
            pdf_bytes = create_pdf(response_text)
            st.download_button(
                label="📄 Download Investment Memo (PDF)",
                data=pdf_bytes,
                file_name=f"investment_memo.pdf",
                mime="application/pdf"
            )
    
    # Save Assistant Message
    db.save_message("assistant", response_text)