import os
import requests

print("=== DEBUG: CHECKING SECRETS ===")

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

print(f"TELEGRAM_BOT_TOKEN: {TELEGRAM_BOT_TOKEN}")
print(f"TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")

# Test Telegram
print("Testing Telegram API...")
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
payload = {
    'chat_id': TELEGRAM_CHAT_ID,
    'text': "Test from mail_notifier.py",
}

response = requests.post(url, json=payload)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")

if response.status_code == 200:
    print("✅ TELEGRAM WORKS!")
else:
    print("❌ TELEGRAM FAILED!")

# Exit after test
exit(0)
