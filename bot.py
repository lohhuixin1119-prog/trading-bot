import requests, time, hmac, hashlib, logging
from collections import deque

BASE_URL   = "https://mock-api.roostoo.com"
API_KEY    = "YTtq1D8FlNv4grUh4zhg9J5S1KqPd1c3bwEkNAwKLEkIQCi6dsEY6Pdpc6HZp08P"
SECRET_KEY = "Mck1HErBvHXzZqt5QQY0iQHj7US8qka4ZQC5NCVWOI7eqnjTQEa1lO806dG24erX"

PAIRS      = ["BTC/USD", "ETH/USD", "BNB/USD"]
INTERVAL   = 60

EMA_FAST   = 2
EMA_SLOW   = 3
EMA_SIGNAL = 2
RSI_PERIOD = 3
RSI_BUY    = 65
RSI_SELL   = 35
TRADE_PCT  = 0.1

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

price_history = {pair: deque(maxlen=100) for pair in PAIRS}

def timestamp():
    return str(int(time.time() * 1000))

def sign(payload):
    payload["timestamp"] = timestamp()
    total = "&".join(f"{k}={payload[k]}" for k in sorted(payload))
    sig = hmac.new(SECRET_KEY.encode(), total.encode(), hashlib.sha256).hexdigest()
    return {"RST-API-KEY": API_KEY, "MSG-SIGNATURE": sig,
            "Content-Type": "application/x-www-form-urlencoded"}, total

def get_ticker(pair):
    r = requests.get(f"{BASE_URL}/v3/ticker",
                     params={"pair": pair, "timestamp": timestamp()})
    d = r.json()
    if d.get("Success"):
        return float(d["Data"][pair]["LastPrice"])
    return None

def get_balance():
    headers, params = sign({})
    r = requests.get(f"{BASE_URL}/v3/balance", headers=headers, params=params)
    return r.json().get("SpotWallet", {})

PRECISION = {
    "BTC": 6,
    "ETH": 4,
    "BNB": 2
}

def place_order(pair, side, quantity):
    coin = pair.split("/")[0]
    precision = PRECISION.get(coin, 4)
    quantity = round(quantity, precision)
    if quantity <= 0:
        log.warning(f"Quantity too small for {pair}")
        return None
    payload = {"pair": pair, "side": side, "type": "MARKET",
               "quantity": str(quantity)}
    headers, body = sign(payload)
    r = requests.post(f"{BASE_URL}/v3/place_order", headers=headers, data=body)
    return r.json()

def calc_ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(list(prices)[:period]) / period
    for price in list(prices)[period:]:
        ema = price * k + ema * (1 - k)
    return ema

def calc_macd(prices):
    if len(prices) < EMA_SLOW + EMA_SIGNAL:
        return None, None, None
    ema_fast = calc_ema(prices, EMA_FAST)
    ema_slow = calc_ema(prices, EMA_SLOW)
    if ema_fast is None or ema_slow is None:
        return None, None, None
    macd_line = ema_fast - ema_slow
    macd_values = []
    prices_list = list(prices)
    for i in range(EMA_SIGNAL):
        subset = deque(prices_list[:len(prices_list)-i])
        ef = calc_ema(subset, EMA_FAST)
        es = calc_ema(subset, EMA_SLOW)
        if ef and es:
            macd_values.insert(0, ef - es)
    if len(macd_values) < EMA_SIGNAL:
        return macd_line, None, None
    signal_line = sum(macd_values) / EMA_SIGNAL
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calc_rsi(prices):
    if len(prices) < RSI_PERIOD + 1:
        return None
    prices_list = list(prices)[-RSI_PERIOD-1:]
    gains, losses = [], []
    for i in range(1, len(prices_list)):
        diff = prices_list[i] - prices_list[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / RSI_PERIOD
    avg_loss = sum(losses) / RSI_PERIOD
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def check_signal(pair):
    hist = price_history[pair]
    needed = EMA_SLOW + EMA_SIGNAL
    if len(hist) < needed:
        return None

    macd_line, signal_line, histogram = calc_macd(hist)
    rsi = calc_rsi(hist)

    if macd_line is None or signal_line is None or rsi is None:
        return None

    log.info(f"{pair} MACD={macd_line:.2f} Signal={signal_line:.2f} RSI={rsi:.1f}")

    if macd_line > signal_line and rsi < RSI_BUY:
        return "BUY"
    elif macd_line < signal_line and rsi > RSI_SELL:
        return "SELL"
    return "HOLD"

def execute(pair, signal):
    wallet    = get_balance()
    coin      = pair.split("/")[0]
    usd_free  = float(wallet.get("USD",  {}).get("Free", 0))
    coin_free = float(wallet.get(coin,   {}).get("Free", 0))
    price     = price_history[pair][-1]

    if signal == "BUY" and usd_free > 1:
        qty = (usd_free * TRADE_PCT) / price
        log.info(f">>> BUY  {pair} qty={qty:.6f} @ ~{price}")
        log.info(place_order(pair, "BUY", qty))

    elif signal == "SELL" and coin_free > 0:
        qty = coin_free * TRADE_PCT
        log.info(f">>> SELL {pair} qty={qty:.6f} @ ~{price}")
        log.info(place_order(pair, "SELL", qty))

def run():
    needed = EMA_SLOW + EMA_SIGNAL
    log.info("=== Bot started (MACD + RSI 20-30x/day) ===")
    log.info(f"Need {needed} bars = ~{needed} minutes to start")
    while True:
        for pair in PAIRS:
            price = get_ticker(pair)
            if price is None:
                log.warning(f"No ticker for {pair}")
                continue

            price_history[pair].append(price)
            bars = len(price_history[pair])

            if bars < needed:
                log.info(f"{pair} price={price:.2f} collecting {bars}/{needed}")
                continue

            signal = check_signal(pair)
            log.info(f"{pair} price={price:.2f} signal={signal}")

            if signal in ("BUY", "SELL"):
                execute(pair, signal)

        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()