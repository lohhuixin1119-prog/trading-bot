import requests, time, hmac, hashlib, logging, json, os
from collections import deque

BASE_URL   = "https://mock-api.roostoo.com"
API_KEY    = "YTtq1D8FlNv4grUh4zhg9J5S1KqPd1c3bwEkNAwKLEkIQCi6dsEY6Pdpc6HZp08P"
SECRET_KEY = "Mck1HErBvHXzZqt5QQY0iQHj7US8qka4ZQC5NCVWOI7eqnjTQEa1lO806dG24erX"

PAIRS         = ["BTC/USD", "ETH/USD", "BNB/USD"]
INTERVAL      = 120
TRADE_PCT     = 0.15
BB_PERIOD     = 5
BB_STD        = 1.8
RSI_PERIOD    = 4
RSI_BUY       = 40
RSI_SELL      = 60
MIN_TRADE_GAP = 600
PRECISION     = {"BTC": 3, "ETH": 4, "BNB": 2}
DATA_FILE     = "price_data.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

price_history   = {pair: deque(maxlen=50) for pair in PAIRS}
last_trade_time = {pair: 0 for pair in PAIRS}

def save_prices():
    data = {pair: list(price_history[pair]) for pair in PAIRS}
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

def load_prices():
    if not os.path.exists(DATA_FILE):
        log.info("No saved data, starting fresh")
        return
    with open(DATA_FILE, "r") as f:
        data = json.load(f)
    for pair in PAIRS:
        if pair in data:
            for p in data[pair]:
                price_history[pair].append(p)
    log.info("Loaded: " + ", ".join(f"{p}={len(price_history[p])}" for p in PAIRS))

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

def calc_rsi(prices):
    if len(prices) < RSI_PERIOD + 1:
        return None
    prices_list = list(prices)[-(RSI_PERIOD+1):]
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

def calc_bollinger(prices):
    if len(prices) < BB_PERIOD:
        return None, None, None
    data = list(prices)[-BB_PERIOD:]
    mid = sum(data) / BB_PERIOD
    std = (sum((x - mid) ** 2 for x in data) / BB_PERIOD) ** 0.5
    upper = mid + BB_STD * std
    lower = mid - BB_STD * std
    return upper, mid, lower

def check_signal(pair):
    hist = price_history[pair]
    needed = max(BB_PERIOD, RSI_PERIOD + 1)
    if len(hist) < needed:
        return None
    price = list(hist)[-1]
    rsi = calc_rsi(hist)
    upper, mid, lower = calc_bollinger(hist)
    if rsi is None or upper is None:
        return None
    log.info(f"{pair} price={price:.2f} RSI={rsi:.1f} "
             f"BB_upper={upper:.2f} BB_lower={lower:.2f}")
    if price <= lower and rsi < RSI_BUY:
        return "BUY"
    elif price >= upper and rsi > RSI_SELL:
        return "SELL"
    return "HOLD"

def execute(pair, signal):
    now = time.time()
    if now - last_trade_time[pair] < MIN_TRADE_GAP:
        remaining = int(MIN_TRADE_GAP - (now - last_trade_time[pair]))
        log.info(f"{pair} cooldown {remaining}s remaining")
        return
    wallet    = get_balance()
    coin      = pair.split("/")[0]
    usd_free  = float(wallet.get("USD",  {}).get("Free", 0))
    coin_free = float(wallet.get(coin,   {}).get("Free", 0))
    price     = price_history[pair][-1]
    if signal == "BUY" and usd_free > 1:
        qty = (usd_free * TRADE_PCT) / price
        log.info(f">>> BUY  {pair} qty={qty:.6f} @ ~{price}")
        result = place_order(pair, "BUY", qty)
        log.info(result)
        if result and result.get("Success"):
            last_trade_time[pair] = now
            save_prices()
    elif signal == "SELL" and coin_free > 0:
        qty = coin_free * TRADE_PCT
        log.info(f">>> SELL {pair} qty={qty:.6f} @ ~{price}")
        result = place_order(pair, "SELL", qty)
        log.info(result)
        if result and result.get("Success"):
            last_trade_time[pair] = now
            save_prices()

def run():
    needed = max(BB_PERIOD, RSI_PERIOD + 1)
    load_prices()
    log.info("=== Bot started (RSI + Bollinger Bands) ===")
    log.info(f"Need {needed} bars = ~{needed * INTERVAL // 60} mins to start")
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
            log.info(f"{pair} signal={signal}")
            if signal in ("BUY", "SELL"):
                execute(pair, signal)
        save_prices()
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()