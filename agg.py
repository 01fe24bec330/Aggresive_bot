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
last_heartbeat_hour = None

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
# DATA
# ==============================

def get_klines(symbol, interval):
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": 200}
        data = requests.get(url, params=params).json()

        if not data or isinstance(data, dict):
            return None

        df = pd.DataFrame(data)
        df = df.iloc[:, 0:6]
        df.columns = ["time","open","high","low","close","volume"]

        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)

        return df
    except:
        return None

# ==============================
# STRATEGY (High Frequency Momentum)
# ==============================

def check_signal(symbol):

    df = get_klines(symbol, "15m")
    if df is None or len(df) < 50:
        return None

    df["adx"] = ta.trend.adx(df["high"], df["low"], df["close"], 14)
    df["atr"] = ta.volatility.average_true_range(df["high"], df["low"], df["close"], 14)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    recent_high = df["high"].rolling(5).max().iloc[-2]
    recent_low = df["low"].rolling(5).min().iloc[-2]

    # LONG micro-breakout
    if (
        last["close"] > recent_high and
        last["adx"] > 14
    ):
        return ("LONG", last["close"], last["atr"])

    # SHORT micro-breakout
    if (
        last["close"] < recent_low and
        last["adx"] > 14
    ):
        return ("SHORT", last["close"], last["atr"])

    return None

# ==============================
# TRADE MANAGEMENT
# ==============================

def open_trade(coin, direction, entry, atr):
    global capital, trades_today

    stop_distance = atr * 1.2
    if stop_distance <= 0:
        return

    risk_amount = capital * RISK_PERCENT
    size = risk_amount / stop_distance

    if direction == "LONG":
        stop = entry - stop_distance
        target = entry + stop_distance * 2
    else:
        stop = entry + stop_distance
        target = entry - stop_distance * 2

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

    position = open_positions.get(coin)
    if not position:
        return

    df = get_klines(SYMBOLS[coin], "15m")
    if df is None:
        return

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
            f"💰 AGGRESSIVE CLOSED {coin}\n"
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
            f"🤖 Aggressive Alive\n"
            f"Capital: {round(capital,2)}\n"
            f"Open Trades: {len(open_positions)}\n"
            f"Trades Today: {trades_today}"
        )
        last_heartbeat_hour = hour

# ==============================
# DAILY RESET
# ==============================

def daily_reset():
    global trades_today, daily_pnl, current_day

    if date.today() != current_day:
        send_telegram(
            f"📊 DAILY REPORT\n"
            f"PnL: {round(daily_pnl,2)}\n"
            f"Capital: {round(capital,2)}"
        )
        trades_today = 0
        daily_pnl = 0
        current_day = date.today()

# ==============================
# MAIN LOOP
# ==============================

send_telegram("🚀 Aggressive High-Frequency Engine Online")

while True:
    try:

        heartbeat()
        daily_reset()

        for coin in list(open_positions.keys()):
            check_exit(coin)

        if trades_today < MAX_TRADES_PER_DAY and len(open_positions) < MAX_OPEN_TRADES:

            for coin in SYMBOLS.keys():

                if coin in open_positions:
                    continue

                signal = check_signal(SYMBOLS[coin])
                if signal:
                    direction, entry, atr = signal
                    open_trade(coin, direction, entry, atr)

                    if len(open_positions) >= MAX_OPEN_TRADES:
                        break

        time.sleep(60)

    except Exception as e:
        print("Error:", e)
        time.sleep(10)
