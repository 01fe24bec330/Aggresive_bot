import requests
import pandas as pd
import numpy as np
import ta
import time
from datetime import datetime, date

# ==============================
# CONFIG
# ==============================

SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "BNB": "BNBUSDT",
    "XRP": "XRPUSDT",
    "AVAX": "AVAXUSDT",
    "DOGE": "DOGEUSDT",
    "LINK": "LINKUSDT",
    "MATIC": "MATICUSDT",
    "LTC": "LTCUSDT"
}

START_CAPITAL = 50
RISK_PERCENT = 0.015
MAX_TRADES_PER_DAY = 15
MAX_OPEN_TRADES = 3

TELEGRAM_TOKEN = "8679615295:AAFsFvOUk21PGvO49o4vaEB8VYBYRIl_xMw"
TELEGRAM_CHAT_ID = "7225721600"

capital = START_CAPITAL
daily_pnl = 0
open_positions = {}
trades_today = 0
current_day = date.today()
last_heartbeat = 0

# ==============================
# TELEGRAM
# ==============================

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        })
    except:
        pass


# ==============================
# DATA FETCH
# ==============================

def get_klines(symbol, interval):
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": 200}
        response = requests.get(url, params=params)
        data = response.json()

        if not data or isinstance(data, dict):
            return None

        df = pd.DataFrame(data)
        df = df.iloc[:, 0:6]
        df.columns = ["time","open","high","low","close","volume"]

        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["volume"] = df["volume"].astype(float)

        return df
    except:
        return None


# ==============================
# STRATEGY LOGIC
# ==============================

def check_signal(symbol):

    df_1h = get_klines(symbol, "1h")
    df_15m = get_klines(symbol, "15m")

    if df_1h is None or df_15m is None or len(df_1h) < 50 or len(df_15m) < 50:
        return None

    df_1h["atr"] = ta.volatility.average_true_range(
        df_1h["high"], df_1h["low"], df_1h["close"], 14
    )

    df_1h["atr_avg"] = df_1h["atr"].rolling(20).mean()

    df_15m["adx"] = ta.trend.adx(
        df_15m["high"], df_15m["low"], df_15m["close"], 14
    )

    df_15m["atr"] = ta.volatility.average_true_range(
        df_15m["high"], df_15m["low"], df_15m["close"], 14
    )

    df_15m["vol_avg"] = df_15m["volume"].rolling(20).mean()

    last_1h = df_1h.iloc[-1]
    prev_1h = df_1h.iloc[-2]
    last_15m = df_15m.iloc[-1]

    # ATR compression (volatility squeeze)
    compression = last_1h["atr"] < last_1h["atr_avg"]

    # LONG breakout
    if (
        compression and
        last_15m["close"] > prev_1h["high"] and
        last_15m["volume"] > last_15m["vol_avg"] and
        last_15m["adx"] > 20
    ):
        return ("LONG", last_15m["close"], last_15m["atr"])

    # SHORT breakout
    if (
        compression and
        last_15m["close"] < prev_1h["low"] and
        last_15m["volume"] > last_15m["vol_avg"] and
        last_15m["adx"] > 20
    ):
        return ("SHORT", last_15m["close"], last_15m["atr"])

    return None


# ==============================
# TRADE MANAGEMENT
# ==============================

def open_trade(coin, direction, entry, atr):
    global capital, trades_today

    risk_amount = capital * RISK_PERCENT
    stop_distance = atr * 1.2
    size = risk_amount / stop_distance

    if direction == "LONG":
        stop = entry - stop_distance
        target = entry + stop_distance * 2.8
    else:
        stop = entry + stop_distance
        target = entry - stop_distance * 2.8

    open_positions[coin] = {
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "target": target,
        "size": size
    }

    trades_today += 1

    send_telegram(
        f"🔥 AGGRESSIVE {coin} {direction}\n"
        f"Entry: {round(entry,4)}\n"
        f"Stop: {round(stop,4)}\n"
        f"Target: {round(target,4)}"
    )


def check_exit(coin):
    global capital, daily_pnl

    position = open_positions[coin]
    symbol = SYMBOLS[coin]

    df = get_klines(symbol, "15m")
    if df is None or len(df) < 5:
        return

    price = df.iloc[-1]["close"]

    if position["direction"] == "LONG":
        if price <= position["stop"] or price >= position["target"]:
            pnl = (price - position["entry"]) * position["size"]
        else:
            return
    else:
        if price >= position["stop"] or price <= position["target"]:
            pnl = (position["entry"] - price) * position["size"]
        else:
            return

    capital += pnl
    daily_pnl += pnl

    send_telegram(
        f"💰 AGGRESSIVE CLOSED {coin}\n"
        f"PnL: {round(pnl,2)} USDT\n"
        f"Capital: {round(capital,2)}"
    )

    del open_positions[coin]


# ==============================
# DAILY REPORT
# ==============================

def daily_report():
    global daily_pnl
    send_telegram(
        f"📊 DAILY REPORT\n"
        f"PnL: {round(daily_pnl,2)} USDT\n"
        f"Capital: {round(capital,2)}"
    )
    daily_pnl = 0


# ==============================
# MAIN LOOP
# ==============================

send_telegram("🚀 Aggressive Breakout Engine Online")

while True:
    try:

        if date.today() != current_day:
            daily_report()
            trades_today = 0

        for coin in SYMBOLS.keys():

            if coin in open_positions:
                check_exit(coin)

            else:
                if (
                    trades_today < MAX_TRADES_PER_DAY and
                    len(open_positions) < MAX_OPEN_TRADES
                ):
                    signal = check_signal(SYMBOLS[coin])
                    if signal:
                        direction, entry, atr = signal
                        open_trade(coin, direction, entry, atr)

        time.sleep(60)

    except Exception as e:
        print("Error:", e)
        time.sleep(10)
