import requests
import os
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

API_KEY    = os.getenv("OANDA_API_KEY")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
BASE_URL   = os.getenv("OANDA_BASE_URL")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type":  "application/json"
}

url = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/instruments"
response = requests.get(url, headers=HEADERS)
instruments = response.json().get("instruments", [])

print("All available instruments on your account:")
print("=" * 52)
for i in instruments:
    print(f"{i['name']:<20} {i['displayName']}")
