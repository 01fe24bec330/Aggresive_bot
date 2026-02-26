import requests
import pandas as pd
import ta
import time
from datetime import datetime, date

# ==============================
# CONFIG
# ==============================

SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "BNB": "BNBUSDT",
    "SOL": "SOLUSDT",
    "XRP": "XRPUSDT"
}

START_CAPITAL = 100
RISK_PERCENT = 0.01
MAX_OPEN_TRADES = 5

TELEGRAM_TOKEN = "8679615295:AAFsFvOUk21PGvO49o4vaEB8VYBYRIl_xMw"
TELEGRAM_CHAT_ID = "7225721600"

capital = START_CAPITAL
open_positions = {}
last_trade_hour = {}
daily_pnl = 0
current_day = date.today()
last_heartbeat_hour = None

# ==============================
# TELEGRAM
# ==============================

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg
        })
    except:
        pass

# ==============================
# DATA
# ==============================

def get_klines(symbol):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": "15m", "limit": 100}
    data = requests.get(url, params=params).json()

    df = pd.DataFrame(data)
    df = df.iloc[:, 0:6]
    df.columns = ["time","open","high","low","close","volume"]

    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)

    return df

# ==============================
# ENTRY (FORCED HOURLY)
# ==============================

def forced_hourly_signal(symbol):

    df = get_klines(symbol)

    df["atr"] = ta.volatility.average_true_range(
        df["high"], df["low"], df["close"], 14
    )

    last_closed = df.iloc[-2]  # use last closed candle
    atr = last_closed["atr"]

    if last_closed["close"] > last_closed["open"]:
        direction = "LONG"
    else:
        direction = "SHORT"

    return direction, last_closed["close"], atr

# ==============================
# TRADE MANAGEMENT
# ==============================

def open_trade(coin, direction, entry, atr):
    global capital

    stop_distance = atr
    if stop_distance <= 0:
        return

    risk_amount = capital * RISK_PERCENT
    size = risk_amount / stop_distance

    if direction == "LONG":
        stop = entry - stop_distance
        target = entry + stop_distance * 1.5
    else:
        stop = entry + stop_distance
        target = entry - stop_distance * 1.5

    open_positions[coin] = {
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "target": target,
        "size": size
    }

    send_telegram(
        f"⏱ FORCED {coin} {direction}\n"
        f"Entry: {round(entry,4)}\n"
        f"Stop: {round(stop,4)}\n"
        f"Target: {round(target,4)}"
    )

def check_exit(coin):
    global capital, daily_pnl

    position = open_positions.get(coin)
    if not position:
        return

    df = get_klines(SYMBOLS[coin])
    price = df.iloc[-1]["close"]

    direction = position["direction"]
    entry = position["entry"]
    stop = position["stop"]
    target = position["target"]
    size = position["size"]

    closed = False

    if direction == "LONG":
        if price <= stop:
            pnl = (stop - entry) * size
            closed = True
        elif price >= target:
            pnl = (target - entry) * size
            closed = True
    else:
        if price >= stop:
            pnl = (entry - stop) * size
            closed = True
        elif price <= target:
            pnl = (entry - target) * size
            closed = True

    if closed:
        capital += pnl
        daily_pnl += pnl

        send_telegram(
            f"💰 CLOSED {coin}\n"
            f"PnL: {round(pnl,2)}\n"
            f"Capital: {round(capital,2)}"
        )

        del open_positions[coin]

# ==============================
# HEARTBEAT
# ==============================

def heartbeat():
    global last_heartbeat_hour
    hour = datetime.utcnow().hour

    if last_heartbeat_hour != hour:
        send_telegram(
            f"🤖 Forced Hourly Alive\n"
            f"Capital: {round(capital,2)}\n"
            f"Open Trades: {len(open_positions)}"
        )
        last_heartbeat_hour = hour

# ==============================
# DAILY RESET
# ==============================

def daily_reset():
    global daily_pnl, current_day

    if date.today() != current_day:
        send_telegram(
            f"📊 DAILY REPORT\n"
            f"PnL: {round(daily_pnl,2)}\n"
            f"Capital: {round(capital,2)}"
        )
        daily_pnl = 0
        current_day = date.today()

# ==============================
# MAIN LOOP
# ==============================

send_telegram("🚀 Forced Hourly Bot Online")

while True:
    try:

        now = datetime.utcnow()

        heartbeat()
        daily_reset()

        # Check exits first
        for coin in list(open_positions.keys()):
            check_exit(coin)

        # Forced hourly entries
        for coin in SYMBOLS.keys():

            if len(open_positions) >= MAX_OPEN_TRADES:
                break

            if coin in open_positions:
                continue

            if last_trade_hour.get(coin) == now.hour:
                continue

            direction, entry, atr = forced_hourly_signal(SYMBOLS[coin])
            open_trade(coin, direction, entry, atr)
            last_trade_hour[coin] = now.hour

        time.sleep(60)

    except Exception as e:
        print("Error:", e)
        time.sleep(10)
