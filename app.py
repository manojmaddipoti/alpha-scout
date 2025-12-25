import streamlit as st
import yfinance as yf
import pandas as pd
from search_agent import run_smart_agent
import database as db

# --- 1. Page Config ---
st.set_page_config(page_title="Investment AI Analyst", page_icon="🦄", layout="wide")

# --- 2. PASSWORD LOCK (The Gatekeeper) ---
# Change this string to whatever password you want!
SECRET_PASSWORD = "Laxmi@2026" 

def check_password():
    """Returns `True` if the user had the correct password."""
    
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    # Show input for password
    st.title("🔒 Locked App")
    pwd = st.text_input("Enter Password to Access Agent", type="password")
    
    if st.button("Unlock"):
        if pwd == SECRET_PASSWORD:
            st.session_state.password_correct = True
            st.rerun() # Reload page to show the app
        else:
            st.error("Incorrect password.")
    return False

# STOP HERE if password is wrong
if not check_password():
    st.stop()

# --- 3. THE APP (Only runs if unlocked) ---
if "db_init" not in st.session_state:
    db.init_db()
    st.session_state.db_init = True

with st.sidebar:
    st.title("🦄 SaaS Inspector")
    if st.button("🗑️ Reset All Memory"):
        db.clear_db()
        st.rerun()
    st.markdown("""
    **Strict Investment Criteria:**
    - [ ] Rev Growth > 25%
    - [ ] PEG < 2.0
    - [ ] NRR > 115%
    - [ ] Gross Margin > 70%
    - [ ] Rule of 40 > 40%
    - [ ] SBC < 20% of Rev
    """)

# --- 4. System Prompt (The Strict Judge) ---
SYSTEM_PROMPT = """You are a Senior Investment Analyst.
When asked about a stock, you MUST follow this structure:

1. **Company Mission:** Summarize the 'mission' from the tool output in 2 sentences.
2. **Financial Health Check:**
   - Present a Markdown Table with: Price, P/E, PEG Ratio, Rev Growth, Gross Margin.
   - If PEG > 2.0, flag it as "Expensive".
   - If PEG < 1.0, flag it as "Undervalued".
3. **Bull & Bear Analysis:**
   - Use 'web_search' to find expert opinions.
   - **🐂 Bull Case:** List 3 reasons the stock could go UP.
   - **🐻 Bear Case:** List 3 reasons the stock could go DOWN.
   - **🐻 Competition:** List 3 competitors and their growth rates.
4. If NRR is missing, call `web_search` for "[Company] Net Revenue Retention latest quarter".
5. **Output a Markdown Table** comparing ACTUAL data vs TARGET data. Add a "✅" or "❌" column.
6. **Verdict:** Buy, Hold, or Sell (based on the data).
"""

# --- 5. Load & Sync History ---
stored_messages = db.load_messages()

if not stored_messages:
    # Scenario A: Brand new database
    db.save_message("system", SYSTEM_PROMPT)
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
else:
    # Scenario B: History exists, but we want to check if the Prompt changed!
    if stored_messages[0]["role"] == "system" and stored_messages[0]["content"] != SYSTEM_PROMPT:
        # Detected a code update! Overwrite the old system prompt in memory
        stored_messages[0]["content"] = SYSTEM_PROMPT
        # (Optional: You could strictly update the DB here too, but updating session_state is usually enough for the current run)
    
    st.session_state.messages = stored_messages

# --- 6. Helper: Chart ---
@st.cache_data(ttl=3600)
def get_stock_history(ticker):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        if not df.empty:
            return df['Close']
    except:
        return None

def render_chart(ticker):
    with st.spinner(f"📉 Drawing chart for {ticker}..."):
        data = get_stock_history(ticker)
        if data is not None:
            st.line_chart(data, color="#00FF00")
        else:
            st.warning(f"Could not load chart data for {ticker}")

# --- 7. Display Chat ---
for message in st.session_state.messages:
    if message["role"] != "system":
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# --- 8. Input Loop ---
if prompt := st.chat_input("Screen a stock (e.g. 'Analyze Datadog')"):
    
    st.chat_message("user").markdown(prompt)
    db.save_message("user", prompt)

    with st.chat_message("assistant"):
        with st.spinner("Calculating Rule of 40 & Searching NRR..."):
            
            full_history = db.load_messages()
            response_text, found_tickers = run_smart_agent(full_history)
            
            if found_tickers:
                for ticker in found_tickers:
                    st.subheader(f"Price Trend: {ticker}")
                    render_chart(ticker)
            
            st.markdown(response_text)
    
    db.save_message("assistant", response_text)