import requests, time, hmac, hashlib, os, logging
from collections import deque

BASE_URL   = "https://mock-api.roostoo.com"
API_KEY    = os.environ.get("ROOSTOO_API_KEY", "l5zxW7pvWVSsyIOwu6rgovXKgcDGZDpr8RMfKTazfUnKsMthXhfMPEJHk5Q7IKjW")
SECRET_KEY = os.environ.get("ROOSTOO_SECRET_KEY", "Mck1HErBvHXzZqt5QQY0iQHj7US8qka4ZQC5NCVWOI7eqnjTQEa1lO806dG24erX")

PAIRS     = ["BTC/USD", "ETH/USD", "BNB/USD"]
SHORT_WIN = 5
LONG_WIN  = 20
INTERVAL  = 300
TRADE_PCT = 0.2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

price_history = {pair: deque(maxlen=LONG_WIN) for pair in PAIRS}
last_signal   = {pair: None for pair in PAIRS}

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
    return r.json().get("Wallet", {})

def place_order(pair, side, quantity):
    payload = {"pair": pair, "side": side, "type": "MARKET",
               "quantity": str(round(quantity, 6))}
    headers, body = sign(payload)
    r = requests.post(f"{BASE_URL}/v3/place_order", headers=headers, data=body)
    return r.json()

def ma(prices, n):
    data = list(prices)
    if len(data) < n:
        return None
    return sum(data[-n:]) / n

def check_signal(pair):
    hist = price_history[pair]
    if len(hist) < LONG_WIN:
        return None
    short_now  = ma(hist, SHORT_WIN)
    long_now   = ma(hist, LONG_WIN)
    prev       = deque(list(hist)[:-1])
    short_prev = ma(prev, SHORT_WIN)
    long_prev  = ma(prev, LONG_WIN)
    if short_prev is None or long_prev is None:
        return None
    if short_now is None or long_now is None:
        return None
    if short_prev <= long_prev and short_now > long_now:
        return "BUY"
    if short_prev >= long_prev and short_now < long_now:
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
        log.info(f"BUY  {pair} qty={qty:.6f} @ ~{price}")
        log.info(place_order(pair, "BUY", qty))
    elif signal == "SELL" and coin_free > 0:
        qty = coin_free * TRADE_PCT
        log.info(f"SELL {pair} qty={qty:.6f} @ ~{price}")
        log.info(place_order(pair, "SELL", qty))

def run():
    log.info("=== Bot started ===")
    while True:
        for pair in PAIRS:
            price = get_ticker(pair)
            if price is None:
                log.warning(f"No ticker for {pair}")
                continue
            price_history[pair].append(price)
            signal = check_signal(pair)
            log.info(f"{pair} price={price:.2f} "
                     f"bars={len(price_history[pair])}/{LONG_WIN} signal={signal}")
            if signal in ("BUY", "SELL") and signal != last_signal[pair]:
                execute(pair, signal)
                last_signal[pair] = signal
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
 
