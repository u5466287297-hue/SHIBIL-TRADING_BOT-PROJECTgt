from flask import Flask, render_template, jsonify, request
import yfinance as yf
import pandas as pd
import datetime

app = Flask(__name__)

# ===================== Индикатори =====================
def compute_indicators(data):
    data["EMA5"] = data["Close"].ewm(span=5, adjust=False).mean()
    data["EMA20"] = data["Close"].ewm(span=20, adjust=False).mean()
    # RSI
    delta = data["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    data["RSI"] = 100 - (100 / (1 + rs))
    # MACD
    ema12 = data["Close"].ewm(span=12, adjust=False).mean()
    ema26 = data["Close"].ewm(span=26, adjust=False).mean()
    data["MACD"] = ema12 - ema26
    data["MACD_Signal"] = data["MACD"].ewm(span=9, adjust=False).mean()
    # ATR
    high_low = data["High"] - data["Low"]
    high_close = (data["High"] - data["Close"].shift()).abs()
    low_close = (data["Low"] - data["Close"].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    tr = ranges.max(axis=1)
    data["ATR"] = tr.rolling(14).mean()
    return data

# ===================== Настройки =====================
ASSETS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "GBP/JPY": "GBPJPY=X",
    "AUD/USD": "AUDUSD=X"
}

current_asset = "EUR/USD"
last_signal = None
signal_history = []
win_count = 0
loss_count = 0

# ===================== Логика =====================
def get_signal(symbol):
    global win_count, loss_count, last_signal
    data = yf.download(symbol, interval="1m", period="1d")
    if len(data) < 30:
        return None, data
    data = compute_indicators(data)

    ema5 = data["EMA5"].iloc[-1]
    ema20 = data["EMA20"].iloc[-1]
    rsi = data["RSI"].iloc[-1]
    macd = data["MACD"].iloc[-1]
    signal_line = data["MACD_Signal"].iloc[-1]
    atr = data["ATR"].iloc[-1]

    signal = None
    if ema5 > ema20 and rsi > 50 and macd > signal_line and atr > 0:
        signal = "BUY"
    elif ema5 < ema20 and rsi < 50 and macd < signal_line and atr > 0:
        signal = "SELL"

    return signal, data

# ===================== API =====================
@app.route("/api/signal")
def api_signal():
    global last_signal, signal_history, win_count, loss_count, current_asset
    asset = request.args.get("asset", current_asset)
    current_asset = asset

    signal, data = get_signal(ASSETS[asset])

    if signal and signal != last_signal:
        if last_signal is not None:
            last_close = data["Close"].iloc[-2]
            new_close = data["Close"].iloc[-1]
            if last_signal == "BUY" and new_close > last_close:
                win_count += 1
            elif last_signal == "SELL" and new_close < last_close:
                win_count += 1
            else:
                loss_count += 1
        last_signal = signal
        signal_history.insert(0, f"{datetime.datetime.now().strftime('%H:%M:%S')} - {signal}")

    total = win_count + loss_count
    accuracy = (win_count / total * 100) if total > 0 else 0

    return jsonify({
        "asset": asset,
        "signal": signal if signal else "NONE",
        "history": signal_history[:10],
        "stats": {
            "win": win_count,
            "loss": loss_count,
            "accuracy": f"{accuracy:.2f}%"
        },
        "chart": {
            "labels": [str(i) for i in data.index[-50:]],
            "close": list(data["Close"].iloc[-50:]),
            "ema5": list(data["EMA5"].iloc[-50:]),
            "ema20": list(data["EMA20"].iloc[-50:]),
            "rsi": list(data["RSI"].iloc[-50:]),
            "macd": list(data["MACD"].iloc[-50:]),
            "macd_signal": list(data["MACD_Signal"].iloc[-50:]),
            "atr": list(data["ATR"].iloc[-50:])
        }
    })

# ===================== UI =====================
@app.route("/")
def dashboard():
    return render_template("index.html", assets=list(ASSETS.keys()))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
