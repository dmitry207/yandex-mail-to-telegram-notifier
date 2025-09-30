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

def load_processed_state():
    """Загружает ID последнего обработанного письма"""
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
            print(f"📁 Загружено состояние: ID {state.get('last_processed_id')}")
            return state.get('last_processed_id', None)
    except FileNotFoundError:
        print("📁 Файл состояния не найден, начинаем с начала")
        return None

def save_processed_state(email_id):
    """Сохраняет ID обработанного письма"""
    with open(STATE_FILE, 'w') as f:
        json.dump({'last_processed_id': email_id}, f)
    print(f"💾 Сохранено состояние: ID {email_id}")

def send_telegram_message(subject, sender, body_preview, email_id):
    """Отправляет сообщение в Telegram"""
    print("🟡 Отправка уведомления в Telegram...")
    
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
        response = requests.post(url, json=payload, timeout=30)
        print(f"📡 Статус Telegram: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Уведомление успешно отправлено в Telegram!")
            return True
        else:
            print(f"❌ Ошибка Telegram: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")
        return False

def check_email():
    """Основная функция проверки почты"""
    print("🔍 Начинаем проверку почты...")
    print(f"🕒 Время: {email.utils.formatdate()}")
    
    try:
        # Подключаемся к серверу Яндекс.Почты
        print("🔐 Подключаемся к Яндекс.Почте...")
        mail = imaplib.IMAP4_SSL('imap.yandex.ru', 993)
        mail.login(YANDEX_EMAIL, YANDEX_APP_PASSWORD)
        mail.select('inbox')
        print("✅ Успешное подключение к Яндекс.Почте")
        
        # Ищем непрочитанные письма
        print("🔎 Поиск непрочитанных писем...")
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
        
        # Обрабатываем письма в порядке от старых к новым
        for email_id in email_ids:
            email_id_str = email_id.decode()
            print(f"\n--- Обработка письма ID: {email_id_str} ---")
            
            # Пропускаем письма, которые уже обрабатывались
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
            
            # Декодируем тему
            subject = "Без темы"
            if msg['Subject']:
                subject_raw, encoding = decode_header(msg['Subject'])[0]
                if isinstance(subject_raw, bytes):
                    subject = subject_raw.decode(encoding if encoding else 'utf-8')
                else:
                    subject = subject_raw
            
            # Получаем отправителя
            sender = msg.get('From', 'Неизвестный отправитель')
            
            print(f"📧 Тема: {subject}")
            print(f"📩 Отправитель: {sender}")
            
            # Проверяем критерии фильтрации
            is_target_sender = TARGET_SENDER in sender
            is_target_subject = any(keyword.lower() in subject.lower() for keyword in TARGET_SUBJECT_KEYWORDS)
            
            print(f"🔍 Критерии: отправитель={is_target_sender}, тема={is_target_subject}")
            
            if is_target_sender and is_target_subject:
                print("🎯 Письмо подходит под критерии! Обрабатываем...")
                
                # Извлекаем текст письма
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
                                print(f"⚠️ Ошибка декодирования тела письма: {e}")
                                body = "Не удалось прочитать текст письма"
                else:
                    try:
                        body_bytes = msg.get_payload(decode=True)
                        if body_bytes:
                            body = body_bytes.decode('utf-8', errors='ignore')
                    except Exception as e:
                        print(f"⚠️ Ошибка декодирования тела письма: {e}")
                        body = "Не удалось прочитать текст письма"
                
                print(f"📝 Длина текста письма: {len(body)} символов")
                
                # Отправляем уведомление в Telegram
                if send_telegram_message(subject, sender, body, email_id_str):
                    notifications_sent += 1
                    print("✅ Уведомление обработано успешно")
                else:
                    print("❌ Ошибка отправки уведомления")
                
                # Помечаем письмо как прочитанное
                mail.store(email_id, '+FLAGS', '\\Seen')
                print("📭 Письмо помечено как прочитанное")
                
                # Обновляем ID последнего обработанного письма
                new_last_processed_id = email_id_str
            else:
                print("❌ Письмо не подходит под критерии фильтрации")
        
        # Сохраняем состояние, если были обработаны новые письма
        if new_last_processed_id != last_processed_id:
            save_processed_state(new_last_processed_id)
        else:
            print("💾 Состояние не изменилось")
        
        print(f"\n=== РЕЗУЛЬТАТ ===")
        print(f"📊 Отправлено уведомлений: {notifications_sent}")
        print(f"📁 Текущее состояние: ID {new_last_processed_id}")
        
        # Закрываем соединение
        mail.close()
        mail.logout()
        print("🔒 Соединение с почтой закрыто")
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        print(f"🔧 Детали ошибки:\n{traceback.format_exc()}")

if __name__ == '__main__':
    check_email()
    print("\n🎯 Проверка почты завершена")
