import streamlit as st
import yfinance as yf
import pandas as pd
from search_agent import run_smart_agent
import database as db

# --- 1. Page Config ---
st.set_page_config(page_title="Pro Financial Agent", page_icon="📈", layout="wide")

if "db_init" not in st.session_state:
    db.init_db()
    st.session_state.db_init = True

# --- 2. Sidebar ---
with st.sidebar:
    st.title("💰 Market Intelligence")
    if st.button("🗑️ Reset All Memory"):
        db.clear_db()
        st.rerun()

# --- 3. System Prompt ---
SYSTEM_PROMPT = """
You are a Wall Street Financial Analyst.
1. Identify the company the user is asking about and find its TICKER symbol (e.g., 'Sea Limited' -> 'SE').
2. Call 'get_financial_metrics' with that ticker.
3. Call 'web_search' to find "latest SEC 10-K risk factors" and "quarterly sentiment".
4. Output a clean Report with:
   - **Valuation Table** (Revenue, Gross Profit, Free Cash Flow).
   - **SEC Risks Summary**.
   - **Sentiment Rating** (Buy/Hold/Sell).
"""

# --- 4. Load History ---
stored_messages = db.load_messages()
if not stored_messages:
    db.save_message("system", SYSTEM_PROMPT)
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
else:
    st.session_state.messages = stored_messages

# --- 5. Helper: Cached Chart Drawing ---
@st.cache_data(ttl=3600)
def get_stock_history(ticker):
    """Fetches 1y history."""
    try:
        stock = yf.Ticker(ticker)
        # Check if valid by trying to get history
        df = stock.history(period="1y")
        if not df.empty:
            return df['Close']
    except:
        return None

def render_chart(ticker):
    """Draws the chart for a confirmed ticker."""
    with st.spinner(f"📉 Drawing chart for {ticker}..."):
        data = get_stock_history(ticker)
        if data is not None:
            st.line_chart(data, color="#00FF00")
        else:
            st.warning(f"Could not load chart data for {ticker}")

# --- 6. Display Chat History ---
for message in st.session_state.messages:
    if message["role"] != "system":
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            # If we saved a chart ticker in the message metadata, we could re-draw it here
            # (For simplicity, we draw new charts at the bottom of the active interaction)

# --- 7. Main Interaction Loop ---
if prompt := st.chat_input("Analyze a company (e.g. 'Sea Limited' or 'SE')"):
    
    # A. Show User Input
    st.chat_message("user").markdown(prompt)
    db.save_message("user", prompt)

    # B. Run Agent & Capture Tickers
    with st.chat_message("assistant"):
        with st.spinner("Identifying company & Fetching data..."):
            
            # Pass history to agent
            full_history = db.load_messages()
            response_text, found_tickers = run_smart_agent(full_history)
            
            # 1. DRAW CHARTS FIRST (If agent found tickers)
            if found_tickers:
                for ticker in found_tickers:
                    st.subheader(f"Price Trend: {ticker}")
                    render_chart(ticker)
            
            # 2. SHOW TEXT RESPONSE
            st.markdown(response_text)
    
    db.save_message("assistant", response_text)