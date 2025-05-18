import streamlit as st
from binance.client import Client

api_key = st.secrets["BINANCE_API_KEY"]
secret_key = st.secrets["BINANCE_SECRET_KEY"]

client = Client(api_key, secret_key)

# Must be first Streamlit command
st.set_page_config(layout="wide")

import pandas as pd
import requests
import time
from datetime import datetime, timedelta
import pytz
from streamlit_autorefresh import st_autorefresh

# Auto-refresh every 60 seconds
st_autorefresh(interval=60000, key="refresh")

st.title("📈 Real-Time Crypto Screener (Binance Futures)")

# Filter panel toggle
with st.expander("🔧 Filter Settings", expanded=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        inr_threshold = st.number_input("Min 1-min trade value (INR)", value=4_00_00_000, step=10_00_000)
    with col2:
        volume_days = st.number_input("Days for volume avg", min_value=1, value=5)
    with col3:
        volume_multiplier = st.number_input("Volume multiplier", min_value=1.0, value=10.0)

# Initialize session state
if "history" not in st.session_state:
    st.session_state.history = []

if "previous_minute_data" not in st.session_state:
    st.session_state.previous_minute_data = {"value": [], "volume": []}

def fetch_symbols():
    try:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        data = requests.get(url).json()
        return [s['symbol'] for s in data['symbols'] if s['contractType'] == 'PERPETUAL' and s['symbol'].endswith('USDT')]
    except:
        return []

def fetch_1m_klines(symbol):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1m&limit={volume_days * 1440}"
    try:
        data = requests.get(url).json()
        return pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "num_trades",
            "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
        ])
    except:
        return pd.DataFrame()

symbols = fetch_symbols()

now_utc = datetime.utcnow()
now_ist = now_utc + timedelta(hours=5, minutes=30)
timestamp = now_ist.strftime('%Y-%m-%d %H:%M:%S')

value_results = []
volume_results = []

for symbol in symbols:
    df = fetch_1m_klines(symbol)
    if df.empty or len(df) < volume_days * 1440:
        continue

    df["volume"] = pd.to_numeric(df["volume"], errors='coerce')
    df["quote_asset_volume"] = pd.to_numeric(df["quote_asset_volume"], errors='coerce')

    last_volume = df.iloc[-1]["volume"]
    avg_volume = df["volume"][:-1].tail(volume_days * 1440).mean()

    last_value_in_usdt = df.iloc[-1]["quote_asset_volume"]
    inr_rate = 83  # approx
    last_value_in_inr = last_value_in_usdt * inr_rate

    if last_value_in_inr > inr_threshold:
        value_results.append({
            "Symbol": symbol,
            "1m Value (INR)": f"{last_value_in_inr:,.0f}",
            "Timestamp": timestamp
        })

    if last_volume > volume_multiplier * avg_volume:
        volume_results.append({
            "Symbol": symbol,
            "1m Vol": f"{last_volume:,.2f}",
            "Avg Vol": f"{avg_volume:,.2f}",
            "x Avg": f"{last_volume / avg_volume:.1f}x",
            "Timestamp": timestamp
        })

# Save current minute data as previous for next refresh
st.session_state.previous_minute_data = {
    "value": value_results.copy(),
    "volume": volume_results.copy()
}

st.subheader("📊 Value Condition (1-min Trade Value > ₹{:,})".format(inr_threshold))
if value_results:
    df_val = pd.DataFrame(value_results)
    st.dataframe(df_val, use_container_width=True)
else:
    st.info("No symbols met the value condition this minute.")

st.subheader("📊 Volume Condition (1-min Vol > {}x {}-day Avg)".format(volume_multiplier, volume_days))
if volume_results:
    df_vol = pd.DataFrame(volume_results)
    st.dataframe(df_vol, use_container_width=True)
else:
    st.info("No symbols met the volume condition this minute.")
