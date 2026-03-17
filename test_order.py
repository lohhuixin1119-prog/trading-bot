import requests
import time
import hmac
import hashlib

BASE_URL = 'https://mock-api.roostoo.com'
API_KEY = 'YTtq1D8FlNv4grUh4zhg9J5S1KqPd1c3bwEkNAwKLEkIQCi6dsEY6Pdpc6HZp08P'
SECRET_KEY = 'Mck1HErBvHXzZqt5QQY0iQHj7US8qka4ZQC5NCVWOI7eqnjTQEa1lO806dG24erX'

timestamp = str(int(time.time() * 1000))

payload = {'timestamp': timestamp}
total = f'timestamp={timestamp}'

sig = hmac.new(
    SECRET_KEY.encode('utf-8'),
    total.encode('utf-8'),
    hashlib.sha256
).hexdigest()

headers = {
    'RST-API-KEY': API_KEY,
    'MSG-SIGNATURE': sig
}

r = requests.get(f'{BASE_URL}/v3/balance', headers=headers, params=payload)
print(r.status_code)
print(r.text)