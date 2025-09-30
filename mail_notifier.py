import imaplib
import email
from email.header import decode_header
import requests
import os
import json

# Конфигурация из переменных окружения
YANDEX_EMAIL = os.getenv('YANDEX_EMAIL')
YANDEX_APP_PASSWORD = os.getenv('YANDEX_APP_PASSWORD')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TARGET_SENDER = os.getenv('TARGET_SENDER', 'guard@arbitr.ru')
TARGET_SUBJECT_KEYWORDS = os.getenv('TARGET_SUBJECT_KEYWORDS', 'Предоставлен доступ к материалам дела').split(',')

STATE_FILE = 'email_state.json'

print("=== НАСТРОЙКИ СКРИПТА ===")
print(f"YANDEX_EMAIL: {YANDEX_EMAIL}")
print(f"TARGET_SENDER: {TARGET_SENDER}")
print(f"TARGET_SUBJECT_KEYWORDS: {TARGET_SUBJECT_KEYWORDS}")

def load_processed_state():
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            return state.get('last_processed_id', None)
    except FileNotFoundError:
        return None

def save_processed_state(email_id):
    with open(STATE_FILE, 'w') as f:
        json.dump({'last_processed_id': email_id}, f)

def send_telegram_message(subject, sender, body_preview, email_id):
    print("🟡 ОТПРАВКА В TELEGRAM...")
    
    message = f"⚖️ **Новое уведомление от арбитражного суда**\n\n" \
              f"📩 **От:** {sender}\n" \
              f"📋 **Тема:** {subject}\n" \
              f"🔔 **Статус:** Предоставлен доступ к материалам дела\n" \
              f"📖 **Отрывок:** {body_preview[:150]}...\n\n" \
              f"📧 **ID письма:** {email_id}"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"✅ УВЕДОМЛЕНИЕ ОТПРАВЛЕНО! Статус: {response.status_code}")
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")
        return False

def check_email():
    print("\n=== НАЧАЛО ПРОВЕРКИ ПОЧТЫ ===")
    
    try:
        # Подключаемся к почте
        mail = imaplib.IMAP4_SSL('imap.yandex.ru')
        mail.login(YANDEX_EMAIL, YANDEX_APP_PASSWORD)
        mail.select('inbox')
        print("✅ Подключение к почте успешно")
        
        # Ищем непрочитанные письма
        status, messages = mail.search(None, 'UNSEEN')
        
        if status != 'OK':
            print("ℹ️ Нет новых писем")
            return
        
        email_ids = messages[0].split()
        
        if not email_ids:
            print("ℹ️ Нет непрочитанных писем")
            return
        
        print(f"📨 Найдено непрочитанных писем: {len(email_ids)}")
        
        last_processed_id = load_processed_state()
        new_last_processed_id = last_processed_id
        notifications_sent = 0
        
        # Обрабатываем каждое письмо
        for email_id in email_ids:
            email_id_str = email_id.decode()
            print(f"\n--- ОБРАБОТКА ПИСЬМА ID: {email_id_str} ---")
            
            # Пропускаем уже обработанные
            if last_processed_id and int(email_id_str) <= int(last_processed_id):
                print("↪️ Письмо уже обработано, пропускаем")
                continue
            
            # Получаем письмо
            status, msg_data = mail.fetch(email_id, '(RFC822)')
            if status != 'OK':
                print("❌ Ошибка получения письма")
                continue
            
            # Парсим письмо
            msg = email.message_from_bytes(msg_data[0][1])
            
            # Извлекаем тему
            subject = "Без темы"
            if msg['Subject']:
                subject_raw, encoding = decode_header(msg['Subject'])[0]
                if isinstance(subject_raw, bytes):
                    subject = subject_raw.decode(encoding if encoding else 'utf-8')
                else:
                    subject = subject_raw
            
            # Извлекаем отправителя
            sender = msg['From'] or "Неизвестный отправитель"
            
            print(f"📧 Тема: {subject}")
            print(f"📩 Отправитель: {sender}")
            
            # ДЕТАЛЬНАЯ ПРОВЕРКА ФИЛЬТРАЦИИ
            print(f"\n🔍 ПРОВЕРКА ФИЛЬТРОВ:")
            print(f"   Ищем отправителя: '{TARGET_SENDER}'")
            print(f"   В отправителе: '{sender}'")
            
            is_target_sender = TARGET_SENDER in sender
            print(f"   Результат проверки отправителя: {is_target_sender}")
            
            print(f"   Ищем ключевые слова: {TARGET_SUBJECT_KEYWORDS}")
            print(f"   В теме: '{subject}'")
            
            is_target_subject = False
            for keyword in TARGET_SUBJECT_KEYWORDS:
                keyword_found = keyword.lower() in subject.lower()
                print(f"   Ключевое слово '{keyword}': {keyword_found}")
                if keyword_found:
                    is_target_subject = True
            
            print(f"   Результат проверки темы: {is_target_subject}")
            
            # ФИНАЛЬНОЕ РЕШЕНИЕ
            if is_target_sender and is_target_subject:
                print("🎯 ПИСЬМО ПОДХОДИТ! Отправляем уведомление...")
                
                # Извлекаем тело письма
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disposition = str(part.get('Content-Disposition'))
                        
                        if content_type == 'text/plain' and 'attachment' not in content_disposition:
                            try:
                                body_bytes = part.get_payload(decode=True)
                                if body_bytes:
                                    body = body_bytes.decode('utf-8', errors='ignore')
                                break
                            except Exception as e:
                                body = "Не удалось прочитать текст письма"
                else:
                    try:
                        body_bytes = msg.get_payload(decode=True)
                        if body_bytes:
                            body = body_bytes.decode('utf-8', errors='ignore')
                    except Exception as e:
                        body = "Не удалось прочитать текст письма"
                
                # Отправляем уведомление
                if send_telegram_message(subject, sender, body, email_id_str):
                    notifications_sent += 1
                    print("✅ УВЕДОМЛЕНИЕ УСПЕШНО ОТПРАВЛЕНО!")
                else:
                    print("❌ ОШИБКА ОТПРАВКИ УВЕДОМЛЕНИЯ")
                
                # Помечаем как прочитанное
                mail.store(email_id, '+FLAGS', '\\Seen')
                new_last_processed_id = email_id_str
            else:
                print("❌ Письмо НЕ ПОДХОДИТ под фильтры")
                if not is_target_sender:
                    print("   ⚠️ Причина: не подходит отправитель")
                if not is_target_subject:
                    print("   ⚠️ Причина: не подходит тема")
        
        # Сохраняем состояние
        if new_last_processed_id != last_processed_id:
            save_processed_state(new_last_processed_id)
            print(f"💾 Обновлен последний обработанный ID: {new_last_processed_id}")
        
        print(f"\n=== ИТОГ ===")
        print(f"📊 Отправлено уведомлений: {notifications_sent}")
        
        mail.close()
        mail.logout()
        
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        print(f"🔧 Детали ошибки:\n{traceback.format_exc()}")

if __name__ == '__main__':
    check_email()
