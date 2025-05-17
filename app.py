
import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh

# Constants
BINANCE_API_URL = "https://fapi.binance.com"
SYMBOLS_ENDPOINT = "/fapi/v1/exchangeInfo"
INR_CONVERSION_RATE = 83.0  # You can update this to match live rates

# State setup
if "volume_history" not in st.session_state:
    st.session_state.volume_history = []
if "value_history" not in st.session_state:
    st.session_state.value_history = []

# Auto refresh every 60 seconds
st_autorefresh(interval=60 * 1000, key="refresh")

st.set_page_config(layout="wide")
st.title("📈 Real-Time Crypto Screener")

# --- Functions ---
def fetch_symbols():
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(BINANCE_API_URL + SYMBOLS_ENDPOINT, headers=headers).json()
    if "symbols" not in res:
        st.error(f"API error {res.get('code')}: {res.get('msg')}")
        return []
    return [s["symbol"] for s in res["symbols"] if s["contractType"] == "PERPETUAL"]

def fetch_1min_volume(symbol):
    end_time = int(time.time() * 1000)
    start_time = end_time - 60_000
    url = f"{BINANCE_API_URL}/fapi/v1/aggTrades?symbol={symbol}&startTime={start_time}&endTime={end_time}"
    try:
        res = requests.get(url).json()
        volume = sum(float(t['q']) for t in res)
        value_inr = sum(float(t['p']) * float(t['q']) * INR_CONVERSION_RATE for t in res)
        return volume, value_inr
    except:
        return 0, 0

def calculate_average_volume(symbol, days=5):
    end_time = int(time.time() * 1000)
    start_time = end_time - (days * 24 * 60 * 60 * 1000)
    url = f"{BINANCE_API_URL}/fapi/v1/aggTrades?symbol={symbol}&startTime={start_time}&endTime={end_time}&limit=1000"
    try:
        res = requests.get(url).json()
        total_volume = sum(float(t['q']) for t in res)
        avg_per_min = total_volume / (days * 1440)
        return avg_per_min
    except:
        return 0

def highlight_green_rows(row):
    return ['background-color: lightgreen'] * len(row)

def screen_pairs(symbols, avg_days, vol_multiplier, value_threshold):
    current_minute = datetime.now(pytz.utc).strftime("%Y-%m-%d %H:%M")

    volume_results = []
    value_results = []

    for sym in symbols:
        vol, val = fetch_1min_volume(sym)
        avg_vol = calculate_average_volume(sym, avg_days)

        if avg_vol > 0 and vol > vol_multiplier * avg_vol:
            volume_results.append({"Symbol": sym, "Volume": round(vol, 2), "Avg Volume": round(avg_vol, 2), "Time": current_minute})

        if val > value_threshold:
            value_results.append({"Symbol": sym, "Value (INR)": int(val), "Time": current_minute})

    return pd.DataFrame(volume_results), pd.DataFrame(value_results)

# --- Filters ---
st.subheader("📊 Volume Condition")
col1, col2 = st.columns(2)
with col1:
    avg_days = st.slider("Average over days", 1, 10, 5)
with col2:
    vol_multiplier = st.slider("Volume Multiplier", 1, 20, 10)

st.subheader("💰 Value Condition")
value_threshold = st.number_input("Min 1-minute trade value (INR)", value=4_00_00_000)

# --- Screening Logic ---
symbols = fetch_symbols()
if not symbols:
    st.error("No symbols found.")
else:
    with st.spinner("Screening..."):
        vol_df, val_df = screen_pairs(symbols, avg_days, vol_multiplier, value_threshold)

    timestamp = datetime.now(pytz.utc).strftime("%Y-%m-%d %H:%M")
    vol_df["Time"] = timestamp
    val_df["Time"] = timestamp

    # Get previous results
    prev_vol = st.session_state.volume_history[-1] if st.session_state.volume_history else pd.DataFrame(columns=vol_df.columns)
    prev_val = st.session_state.value_history[-1] if st.session_state.value_history else pd.DataFrame(columns=val_df.columns)

    # Save history
    st.session_state.volume_history.append(vol_df)
    st.session_state.value_history.append(val_df)

    # --- Output ---
    st.markdown("### ✅ Volume Condition Matches")
    st.markdown("**🟢 Current Minute**")
    st.dataframe(vol_df.style.apply(highlight_green_rows, axis=1), use_container_width=True)
    st.markdown("**🕘 Previous Minute**")
    st.dataframe(prev_vol, use_container_width=True)

    st.markdown("---")

    st.markdown("### ✅ Value Condition Matches")
    st.markdown("**🟢 Current Minute**")
    st.dataframe(val_df.style.apply(highlight_green_rows, axis=1), use_container_width=True)
    st.markdown("**🕘 Previous Minute**")
    st.dataframe(prev_val, use_container_width=True)

    st.success("Auto-refreshed at: " + timestamp)
