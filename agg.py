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

        return df
    except:
        return None


# ==============================
# STRATEGY (Relaxed Breakout)
# ==============================

def check_signal(symbol):

    df_1h = get_klines(symbol, "1h")
    df_15m = get_klines(symbol, "15m")

    if df_1h is None or df_15m is None or len(df_1h) < 30 or len(df_15m) < 30:
        return None

    df_15m["adx"] = ta.trend.adx(
        df_15m["high"], df_15m["low"], df_15m["close"], 14
    )

    df_15m["atr"] = ta.volatility.average_true_range(
        df_15m["high"], df_15m["low"], df_15m["close"], 14
    )

    prev_1h = df_1h.iloc[-2]
    last_15m = df_15m.iloc[-1]

    # LONG breakout
    if (
        last_15m["close"] > prev_1h["high"] and
        last_15m["adx"] > 15
    ):
        return ("LONG", last_15m["close"], last_15m["atr"])

    # SHORT breakout
    if (
        last_15m["close"] < prev_1h["low"] and
        last_15m["adx"] > 15
    ):
        return ("SHORT", last_15m["close"], last_15m["atr"])

    return None


# ==============================
# TRADE MANAGEMENT
# ==============================

def open_trade(coin, direction, entry, atr):
    global capital, trades_today

    stop_distance = atr * 1.3
    if stop_distance <= 0:
        return

    risk_amount = capital * RISK_PERCENT
    size = risk_amount / stop_distance

    if direction == "LONG":
        stop = entry - stop_distance
        target = entry + stop_distance * 2.5
    else:
        stop = entry + stop_distance
        target = entry - stop_distance * 2.5

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
        f"Target: {round(target,4)}\n"
        f"Capital: {round(capital,2)}"
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
            f"PnL: {round(pnl,2)} USDT\n"
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
            f"PnL: {round(daily_pnl,2)} USDT\n"
            f"Capital: {round(capital,2)}"
        )
        trades_today = 0
        daily_pnl = 0
        current_day = date.today()


# ==============================
# MAIN LOOP
# ==============================

send_telegram("🚀 Aggressive Breakout (More Active) Online")

while True:
    try:

        heartbeat()
        daily_reset()

        # Check exits first
        for coin in list(open_positions.keys()):
            check_exit(coin)

        # New trades
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
