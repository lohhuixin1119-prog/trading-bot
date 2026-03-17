import requests
import time
import hmac
import hashlib

BASE_URL = 'https://mock-api.roostoo.com'
API_KEY = 'l5zxW7pvWVSsyIOwu6rgovXKgcDGZDpr8RMfKTazfUnKsMthXhfMPEJHk5Q7IKjW'
SECRET_KEY = 'Mck1HErBvHXzZqt5QQY0iQHj7US8qka4ZQC5NCVWOI7eqnjTQEa1lO806dG24erX'

# 先拿服务器时间
server_time = requests.get(f'{BASE_URL}/v3/serverTime').json()['ServerTime']
print('Server time:', server_time)
print('Local time: ', int(time.time() * 1000))

payload = {
    'pair': 'BNB/USD',
    'side': 'BUY',
    'type': 'MARKET',
    'quantity': '0.1',
    'timestamp': str(server_time)
}

sorted_keys = sorted(payload.keys())
total = '&'.join(f'{k}={payload[k]}' for k in sorted_keys)
print('Total params:', total)

sig = hmac.new(
    SECRET_KEY.encode('utf-8'),
    total.encode('utf-8'),
    hashlib.sha256
).hexdigest()
print('Signature:', sig)

headers = {
    'RST-API-KEY': API_KEY,
    'MSG-SIGNATURE': sig,
    'Content-Type': 'application/x-www-form-urlencoded'
}

r = requests.post(f'{BASE_URL}/v3/place_order', headers=headers, data=total)
print(r.status_code)
print(r.text)