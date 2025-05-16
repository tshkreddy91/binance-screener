import streamlit as st
import pandas as pd
import asyncio
import websockets
import json
import requests
from datetime import datetime, timedelta
import time

# Global constants
BINANCE_WS_URL = "wss://fstream.binance.com/stream?streams="
BINANCE_API_URL = "https://fapi.binance.com"
SYMBOLS_ENDPOINT = "/fapi/v1/exchangeInfo"
KLINES_ENDPOINT = "/fapi/v1/klines"
INR_CONVERSION_API = "https://api.exchangerate.host/latest?base=USD&symbols=INR"

# Helper functions
def get_inr_rate():
    try:
        res = requests.get(INR_CONVERSION_API).json()
        return res["rates"]["INR"]
    except:
        return 82  # fallback

def fetch_perpetual_futures_symbols():
    try:
        res = requests.get(BINANCE_API_URL + SYMBOLS_ENDPOINT).json()
        if "symbols" not in res:
            st.error(f"API error {res.get('code')}: {res.get('msg')}")
            return []
        symbols = [s["symbol"] for s in res["symbols"] if s["contractType"] == "PERPETUAL"]
        return symbols
    except Exception as e:
        st.error(f"Exception fetching symbols: {e}")
        return []



def fetch_5day_1min_avg_vol(symbol, days=5):
    try:
        end_time = int(time.time() * 1000)
        start_time = end_time - days * 24 * 60 * 60 * 1000
        params = {
            "symbol": symbol,
            "interval": "1m",
            "startTime": start_time,
            "endTime": end_time,
            "limit": 1000
        }
        res = requests.get(BINANCE_API_URL + KLINES_ENDPOINT, params=params).json()
        if isinstance(res, dict) and "code" in res:
            return None
        volumes = [float(k[5]) for k in res]  # volume is 6th item
        avg_vol = sum(volumes) / len(volumes) if volumes else 0
        return avg_vol
    except Exception as e:
        return None

async def listen_binance_ws(symbols, queue):
    streams = "/".join([f"{s.lower()}@trade" for s in symbols])
    url = BINANCE_WS_URL + streams
    async with websockets.connect(url) as ws:
        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)
                await queue.put(data)
            except Exception as e:
                st.error(f"WebSocket error: {e}")
                break

def process_trade_data(trade, inr_rate):
    symbol = trade['s']
    qty = float(trade['q'])
    price = float(trade['p'])
    volume = qty
    value_in_usd = qty * price
    value_in_inr = value_in_usd * inr_rate
    timestamp = datetime.fromtimestamp(trade['T'] / 1000)
    return {
        "symbol": symbol,
        "volume": volume,
        "value_in_inr": value_in_inr,
        "timestamp": timestamp,
    }

# Streamlit UI and logic

st.set_page_config(page_title="Binance Futures Screener", layout="wide")
st.title("Binance Perpetual Futures Screener")

# Sidebar - API key input (optional)
api_key = st.sidebar.text_input("Binance API Key (optional)")

# Filter conditions toggle
filter_toggle = st.sidebar.checkbox("Show Filter Criteria", value=True)

# Filter condition options
condition = st.sidebar.radio("Filter Condition", ["Volume-based", "Value-based"])

if condition == "Volume-based":
    vol_multiplier = st.sidebar.number_input("Volume Multiplier (x avg vol)", min_value=1.0, value=10.0, step=0.5)
    days = st.sidebar.number_input("No of days for average volume", min_value=1, max_value=30, value=5, step=1)
else:
    min_value_inr = st.sidebar.number_input("Minimum 1 min trade value (INR Crore)", min_value=0.1, value=4.0, step=0.1)

# Search bar for symbols
search_symbol = st.text_input("Search Symbol")

# Pagination variables
page_size = 20
page_num_current = st.session_state.get("page_num_current", 1)
page_num_history = st.session_state.get("page_num_history", 1)

if "filtered_current" not in st.session_state:
    st.session_state.filtered_current = pd.DataFrame(columns=["symbol", "volume", "value_in_inr", "timestamp"])

if "filtered_history" not in st.session_state:
    st.session_state.filtered_history = pd.DataFrame(columns=["symbol", "volume", "value_in_inr", "timestamp"])

if "page_num_current" not in st.session_state:
    st.session_state.page_num_current = 1

if "page_num_history" not in st.session_state:
    st.session_state.page_num_history = 1

def filter_and_search(df, search):
    if search.strip():
        df = df[df['symbol'].str.contains(search.strip().upper())]
    return df

def paginate(df, page_num):
    start = (page_num - 1) * page_size
    end = start + page_size
    return df.iloc[start:end]

def next_page_current():
    if (st.session_state.page_num_current * page_size) < len(st.session_state.filtered_current):
        st.session_state.page_num_current += 1

def prev_page_current():
    if st.session_state.page_num_current > 1:
        st.session_state.page_num_current -= 1

def next_page_history():
    if (st.session_state.page_num_history * page_size) < len(st.session_state.filtered_history):
        st.session_state.page_num_history += 1

def prev_page_history():
    if st.session_state.page_num_history > 1:
        st.session_state.page_num_history -= 1

# Buttons to paginate
col1, col2, col3, col4 = st.columns(4)
with col1:
    if st.button("⬅️ Prev (Current)"):
        prev_page_current()
with col2:
    if st.button("Next ➡️ (Current)"):
        next_page_current()
with col3:
    if st.button("⬅️ Prev (History)"):
        prev_page_history()
with col4:
    if st.button("Next ➡️ (History)"):
        next_page_history()

# Start screener button
if st.button("▶️ Start Screener"):

    inr_rate = get_inr_rate()
    symbols = fetch_perpetual_futures_symbols()

    if not symbols:
        st.warning("No symbols found, please try again later.")
    else:
        st.success(f"Fetched {len(symbols)} symbols")

        # For simplicity, limit number of symbols to 50 to reduce load (you can increase)
        symbols = symbols[:50]

        avg_vol_dict = {}
        if condition == "Volume-based":
            with st.spinner("Fetching 5-day average volumes..."):
                for sym in symbols:
                    avg_vol = fetch_5day_1min_avg_vol(sym, int(days))
                    if avg_vol is not None:
                        avg_vol_dict[sym] = avg_vol
                    else:
                        avg_vol_dict[sym] = 0

        st.info("Listening to real-time trades. Please wait for updates...")

        # Prepare to run async websocket listener
        import threading
        import queue

        q = queue.Queue()

        async def run_ws():
            await listen_binance_ws(symbols, q)

        def start_loop(loop):
            asyncio.set_event_loop(loop)
            loop.run_until_complete(run_ws())

        loop = asyncio.new_event_loop()
        t = threading.Thread(target=start_loop, args=(loop,), daemon=True)
        t.start()

        # Process incoming trade messages for 1 minute intervals
        df_current_min = pd.DataFrame(columns=["symbol", "volume", "value_in_inr", "timestamp"])

        start_time = datetime.utcnow()
        last_minute = start_time.minute

        while True:
            try:
                while not q.empty():
                    msg = q.get_nowait()
                    data = msg.get("data", {})
                    if data.get("e") == "trade":
                        trade = data
                        trade_info = process_trade_data(trade, inr_rate)

                        # Filtering logic
                        sym = trade_info["symbol"]
                        vol = trade_info["volume"]
                        val = trade_info["value_in_inr"]

                        passes_filter = False
                        if condition == "Volume-based":
                            avg_vol = avg_vol_dict.get(sym, 0)
                            if avg_vol > 0 and vol > vol_multiplier * avg_vol:
                                passes_filter = True
                        else:
                            if val > min_value_inr * 1e7:
                                passes_filter = True

                        if passes_filter:
                            # Add or update row in df_current_min
                            df_current_min = df_current_min[df_current_min["symbol"] != sym]
                            new_row = pd.DataFrame([trade_info])
                            df_current_min = pd.concat([df_current_min, new_row], ignore_index=True)

                # Check if minute changed
                now = datetime.utcnow()
                if now.minute != last_minute:
                    last_minute = now.minute
                    # Update session state filtered current
                    st.session_state.filtered_current = df_current_min.sort_values(by="timestamp", ascending=False)
                    # Append current to history
                    st.session_state.filtered_history = pd.concat([df_current_min, st.session_state.filtered_history], ignore_index=True).drop_duplicates(subset=["symbol", "timestamp"]).sort_values(by="timestamp", ascending=False)

                    df_current_min = pd.DataFrame(columns=["symbol", "volume", "value_in_inr", "timestamp"])
                    # Show updated data
                    st.experimental_rerun()
                time.sleep(1)
            except Exception as e:
                st.error(f"Error in main loop: {e}")
                break

# Show current filtered pairs
st.subheader("Current 1-Minute Filtered Pairs")
df_filtered_current = filter_and_search(st.session_state.filtered_current, search_symbol)
df_filtered_current_paginated = paginate(df_filtered_current, st.session_state.page_num_current)
st.dataframe(df_filtered_current_paginated.style.applymap(lambda v: "background-color: lightgreen", subset=pd.IndexSlice[:, ["symbol"]]))

# Show history filtered pairs
st.subheader("Previous Minutes Filtered Pairs (History)")
df_filtered_history = filter_and_search(st.session_state.filtered_history, search_symbol)
df_filtered_history_paginated = paginate(df_filtered_history, st.session_state.page_num_history)
st.dataframe(df_filtered_history_paginated)
