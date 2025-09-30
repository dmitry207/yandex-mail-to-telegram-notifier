import os
import requests

print("=== DEBUG SECRETS ===")

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

print(f"TELEGRAM_BOT_TOKEN: {TELEGRAM_BOT_TOKEN}")
print(f"TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")

if not TELEGRAM_BOT_TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN not set!")
    
if not TELEGRAM_CHAT_ID:
    print("❌ TELEGRAM_CHAT_ID not set!")

if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    # Check bot
    print("\n1. Checking bot...")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
    response = requests.get(url)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print("   ✅ Bot is active")
    else:
        print(f"   ❌ Bot error: {response.text}")

    # Check sending with current Chat ID
    print(f"\n2. Testing send with Chat ID '{TELEGRAM_CHAT_ID}':")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': "Test message from GitHub Actions",
    }
    response = requests.post(url, json=payload)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text}")

    if response.status_code != 200:
        print(f"\n3. Checking available chats:")
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        response = requests.get(url)
        data = response.json()
        if data['ok'] and data['result']:
            print("   ✅ Available chats:")
            for update in data['result']:
                if 'message' in update:
                    chat = update['message']['chat']
                    print(f"      Chat ID: {chat['id']} | Type: {chat['type']} | Name: {chat.get('first_name', 'N/A')}")
        else:
            print("   ❌ No chats found")
