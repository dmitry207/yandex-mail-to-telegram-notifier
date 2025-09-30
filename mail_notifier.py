import imaplib
import email
from email.header import decode_header
import requests
import os
import json
import logging
from datetime import datetime
import re
import quopri
from email.encoders import decode_qprint

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Конфигурация из переменных окружения
YANDEX_EMAIL = os.getenv('YANDEX_EMAIL')
YANDEX_APP_PASSWORD = os.getenv('YANDEX_APP_PASSWORD')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TARGET_SENDER = os.getenv('TARGET_SENDER', 'guard@arbitr.ru')
TARGET_SUBJECT_KEYWORDS = os.getenv('TARGET_SUBJECT_KEYWORDS', 'Предоставлен доступ к материалам дела').split(',')

# Константы
IMAP_SERVER = 'imap.yandex.ru'
IMAP_PORT = 993
STATE_FILE = 'email_state.json'
REQUEST_TIMEOUT = 30

def log_info(message):
    """Логирование информационных сообщений"""
    logger.info(f"📝 {message}")

def log_error(message):
    """Логирование ошибок"""
    logger.error(f"❌ {message}")

def log_success(message):
    """Логирование успешных операций"""
    logger.info(f"✅ {message}")

def log_warning(message):
    """Логирование предупреждений"""
    logger.warning(f"⚠️ {message}")

def load_processed_state():
    """
    Загружает ID последнего обработанного письма из файла состояния
    
    Returns:
        str or None: ID последнего обработанного письма или None если файл не существует
    """
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
            last_id = state.get('last_processed_id')
            log_info(f"Загружено состояние: ID {last_id}")
            return last_id
    except FileNotFoundError:
        log_info("Файл состояния не найден, начинаем с начала")
        return None
    except json.JSONDecodeError as e:
        log_error(f"Ошибка чтения файла состояния: {e}")
        return None
    except Exception as e:
        log_error(f"Неожиданная ошибка при загрузке состояния: {e}")
        return None

def save_processed_state(email_id):
    """
    Сохраняет ID обработанного письма в файл состояния
    
    Args:
        email_id (str): ID обработанного письма
    """
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'last_processed_id': email_id}, f, ensure_ascii=False, indent=2)
        log_success(f"Сохранено состояние: ID {email_id}")
    except Exception as e:
        log_error(f"Ошибка сохранения состояния: {e}")

def decode_quoted_printable(text):
    """
    Декодирует quoted-printable строки
    """
    try:
        # Декодируем quoted-printable
        decoded_bytes = quopri.decodestring(text.encode('utf-8'))
        decoded_text = decoded_bytes.decode('utf-8', errors='ignore')
        return decoded_text
    except:
        return text

def extract_plain_text_from_html(html_text):
    """
    Извлекает чистый текст из HTML, убирая все теги
    """
    try:
        # Убираем HTML теги
        clean_text = re.sub(r'<[^>]+>', '', html_text)
        # Убираем множественные пробелы и переносы
        clean_text = re.sub(r'\s+', ' ', clean_text)
        # Убираем служебные HTML символы
        clean_text = re.sub(r'&nbsp;', ' ', clean_text)
        clean_text = re.sub(r'&amp;', '&', clean_text)
        clean_text = re.sub(r'&lt;', '<', clean_text)
        clean_text = re.sub(r'&gt;', '>', clean_text)
        clean_text = re.sub(r'&quot;', '"', clean_text)
        clean_text = clean_text.strip()
        return clean_text
    except:
        return html_text

def clean_telegram_text(text):
    """
    Очищает текст от символов, которые могут сломать разметку Telegram
    и декодирует quoted-printable строки
    
    Args:
        text (str): Исходный текст
        
    Returns:
        str: Очищенный текст
    """
    if not text:
        return ""
    
    # Декодируем quoted-printable строки (например, =D0=9C=D0=BE=D0=B9)
    cleaned_text = decode_quoted_printable(text)
    
    # Убираем HTML теги если они есть
    if '<' in cleaned_text and '>' in cleaned_text:
        cleaned_text = extract_plain_text_from_html(cleaned_text)
    
    # Заменяем проблемные символы Markdown на безопасные аналоги
    replacements = {
        '*': '•',
        '_': '—',
        '`': "'",
        '[': '(',
        ']': ')',
        '~': '≈',
        '#': '№',
        '=': '═',
        '|': '│',
        '{': '❴',
        '}': '❵',
        '>': '›',
        '<': '‹',
        '?': '？',
        '&': 'и',
        ';': ',',
        ':': 'ː',
        '!': '❗'
    }
    
    for old, new in replacements.items():
        cleaned_text = cleaned_text.replace(old, new)
    
    # Убираем множественные пробелы и переносы
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
    cleaned_text = cleaned_text.strip()
    
    return cleaned_text

def decode_email_header(header):
    """
    Декодирует email заголовок с учетом кодировки
    """
    if not header:
        return ""
    
    try:
        decoded_parts = decode_header(header)
        decoded_text = ""
        
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                if encoding:
                    decoded_text += part.decode(encoding, errors='ignore')
                else:
                    decoded_text += part.decode('utf-8', errors='ignore')
            else:
                decoded_text += str(part)
        
        return clean_telegram_text(decoded_text)
    except Exception as e:
        log_warning(f"Ошибка декодирования заголовка: {e}")
        return clean_telegram_text(str(header))

def send_telegram_message(subject, sender, body_preview, email_id):
    """
    Отправляет сообщение в Telegram
    
    Args:
        subject (str): Тема письма
        sender (str): Отправитель письма
        body_preview (str): Преview текста письма
        email_id (str): ID письма
        
    Returns:
        bool: True если отправка успешна, False в случае ошибки
    """
    log_info("Отправка уведомления в Telegram...")
    
    try:
        # Очищаем и декодируем текст
        subject_clean = decode_email_header(subject)
        sender_clean = decode_email_header(sender)
        body_clean = clean_telegram_text(body_preview)
        
        # Обрезаем слишком длинный текст
        if len(body_clean) > 150:
            body_clean = body_clean[:147] + "..."
        
        # Формируем сообщение
        message = (
            f"⚖️ НОВОЕ УВЕДОМЛЕНИЕ ОТ АРБИТРАЖНОГО СУДА\n\n"
            f"📩 ОТ: {sender_clean}\n"
            f"📋 ТЕМА: {subject_clean}\n"
            f"🔔 СТАТУС: Предоставлен доступ к материалам дела\n"
            f"📖 ОТРЫВОК: {body_clean}\n\n"
            f"📧 ID ПИСЬМА: {email_id}\n"
            f"🕒 ВРЕМЯ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message
            # Не используем parse_mode для избежания проблем с разметкой
        }
        
        response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        log_info(f"Статус Telegram: {response.status_code}")
        
        if response.status_code == 200:
            log_success("Уведомление успешно отправлено в Telegram!")
            return True
        else:
            log_error(f"Ошибка Telegram: {response.status_code} - {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        log_error("Таймаут при отправке в Telegram")
        return False
    except requests.exceptions.ConnectionError:
        log_error("Ошибка соединения с Telegram")
        return False
    except Exception as e:
        log_error(f"Неожиданная ошибка при отправке в Telegram: {e}")
        return False

def extract_email_body(msg):
    """
    Извлекает текстовое тело из email сообщения, убирая HTML теги
    
    Args:
        msg: Email сообщение
        
    Returns:
        str: Текст письма без HTML разметки
    """
    body = ""
    
    try:
        if msg.is_multipart():
            # Обрабатываем multipart сообщение
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get('Content-Disposition', ''))
                
                # Ищем текстовую часть без вложений
                if content_type == 'text/plain' and 'attachment' not in content_disposition:
                    try:
                        body_bytes = part.get_payload(decode=True)
                        if body_bytes:
                            body = body_bytes.decode('utf-8', errors='ignore')
                            break
                    except Exception as e:
                        log_warning(f"Ошибка декодирования части письма: {e}")
                        continue
                
                # Если текстовой версии нет, используем HTML но убираем теги
                if content_type == 'text/html' and not body and 'attachment' not in content_disposition:
                    try:
                        body_bytes = part.get_payload(decode=True)
                        if body_bytes:
                            html_body = body_bytes.decode('utf-8', errors='ignore')
                            # Убираем HTML теги и получаем чистый текст
                            body = extract_plain_text_from_html(html_body)
                            break
                    except Exception as e:
                        log_warning(f"Ошибка декодирования HTML части: {e}")
                        continue
        else:
            # Обрабатываем простое сообщение
            try:
                body_bytes = msg.get_payload(decode=True)
                if body_bytes:
                    body_content = body_bytes.decode('utf-8', errors='ignore')
                    # Если это HTML, убираем теги
                    if msg.get_content_type() == 'text/html':
                        body = extract_plain_text_from_html(body_content)
                    else:
                        body = body_content
            except Exception as e:
                log_warning(f"Ошибка декодирования письма: {e}")
        
        # Если тело пустое, возвращаем заглушку
        if not body:
            body = "Текст письма не доступен для чтения"
            
        return body.strip()
        
    except Exception as e:
        log_error(f"Ошибка извлечения тела письма: {e}")
        return "Ошибка чтения текста письма"

def check_email_criteria(subject, sender):
    """
    Проверяет письмо на соответствие критериям фильтрации
    
    Args:
        subject (str): Тема письма
        sender (str): Отправитель письма
        
    Returns:
        bool: True если письмо подходит под критерии
    """
    # Проверяем отправителя
    is_target_sender = TARGET_SENDER.lower() in sender.lower()
    
    # Проверяем тему на наличие ключевых слов
    is_target_subject = any(
        keyword.lower() in subject.lower() 
        for keyword in TARGET_SUBJECT_KEYWORDS 
        if keyword.strip()
    )
    
    log_info(f"Критерии проверки: отправитель={is_target_sender}, тема={is_target_subject}")
    return is_target_sender and is_target_subject

def process_email_message(mail, email_id, last_processed_id):
    """
    Обрабатывает одно email сообщение
    
    Args:
        mail: IMAP соединение
        email_id: ID письма
        last_processed_id: ID последнего обработанного письма
        
    Returns:
        tuple: (new_last_processed_id, notification_sent)
    """
    email_id_str = email_id.decode()
    log_info(f"Обработка письма ID: {email_id_str}")
    
    # Пропускаем уже обработанные письма
    if last_processed_id and int(email_id_str) <= int(last_processed_id):
        log_info("Письмо уже обработано, пропускаем")
        return last_processed_id, False
    
    # Получаем письмо
    try:
        status, msg_data = mail.fetch(email_id, '(RFC822)')
        if status != 'OK':
            log_error("Ошибка получения письма")
            return last_processed_id, False
    except Exception as e:
        log_error(f"Ошибка при получении письма: {e}")
        return last_processed_id, False
    
    # Парсим письмо
    try:
        msg = email.message_from_bytes(msg_data[0][1])
    except Exception as e:
        log_error(f"Ошибка парсинга письма: {e}")
        return last_processed_id, False
    
    # Извлекаем тему
    subject = msg.get('Subject', 'Без темы')
    subject = decode_email_header(subject)
    
    # Извлекаем отправителя
    sender = msg.get('From', 'Неизвестный отправитель')
    sender = decode_email_header(sender)
    
    log_info(f"Тема: {subject}")
    log_info(f"Отправитель: {sender}")
    
    # Проверяем критерии
    if not check_email_criteria(subject, sender):
        log_info("Письмо не подходит под критерии фильтрации")
        return last_processed_id, False
    
    log_success("Письмо подходит под критерии! Обрабатываем...")
    
    # Извлекаем текст письма
    body = extract_email_body(msg)
    log_info(f"Длина текста письма: {len(body)} символов")
    
    # Отправляем уведомление в Telegram
    notification_sent = False
    if send_telegram_message(subject, sender, body, email_id_str):
        notification_sent = True
        log_success("Уведомление обработано успешно")
    else:
        log_error("Ошибка отправки уведомления")
    
    # Помечаем письмо как прочитанное
    try:
        mail.store(email_id, '+FLAGS', '\\Seen')
        log_info("Письмо помечено как прочитанное")
    except Exception as e:
        log_warning(f"Ошибка при пометке письма как прочитанного: {e}")
    
    return email_id_str, notification_sent

def check_email():
    """
    Основная функция проверки почты
    """
    log_info("Начинаем проверку почты...")
    log_info(f"Время начала: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    mail = None
    try:
        # Подключаемся к серверу Яндекс.Почты
        log_info("Подключаемся к Яндекс.Почте...")
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(YANDEX_EMAIL, YANDEX_APP_PASSWORD)
        mail.select('inbox')
        log_success("Успешное подключение к Яндекс.Почте")
        
        # Ищем непрочитанные письма
        log_info("Поиск непрочитанных писем...")
        status, messages = mail.search(None, 'UNSEEN')
        
        if status != 'OK':
            log_info("Нет новых писем")
            return
        
        email_ids = messages[0].split()
        
        if not email_ids:
            log_info("Нет непрочитанных писем")
            return
        
        log_info(f"Найдено непрочитанных писем: {len(email_ids)}")
        
        # Загружаем состояние
        last_processed_id = load_processed_state()
        new_last_processed_id = last_processed_id
        notifications_sent = 0
        
        # Обрабатываем письма
        for email_id in email_ids:
            new_id, sent = process_email_message(mail, email_id, last_processed_id)
            if new_id != last_processed_id:
                new_last_processed_id = new_id
            if sent:
                notifications_sent += 1
        
        # Сохраняем состояние, если были обработаны новые письма
        if new_last_processed_id != last_processed_id:
            save_processed_state(new_last_processed_id)
        else:
            log_info("Состояние не изменилось")
        
        # Выводим итоги
        log_success(f"Проверка завершена. Отправлено уведомлений: {notifications_sent}")
        log_info(f"Текущее состояние: ID {new_last_processed_id}")
        
    except imaplib.IMAP4.error as e:
        log_error(f"Ошибка IMAP: {e}")
    except Exception as e:
        log_error(f"Критическая ошибка: {e}")
    finally:
        # Закрываем соединение
        if mail:
            try:
                mail.close()
                mail.logout()
                log_info("Соединение с почтой закрыто")
            except Exception as e:
                log_warning(f"Ошибка при закрытии соединения: {e}")

def main():
    """
    Главная функция
    """
    print("=" * 50)
    print("🎯 YANDEX MAIL TO TELEGRAM NOTIFIER")
    print("=" * 50)
    
    # Проверяем обязательные переменные окружения
    required_vars = {
        'YANDEX_EMAIL': YANDEX_EMAIL,
        'YANDEX_APP_PASSWORD': YANDEX_APP_PASSWORD,
        'TELEGRAM_BOT_TOKEN': TELEGRAM_BOT_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    
    missing_vars = [var for var, value in required_vars.items() if not value]
    if missing_vars:
        log_error(f"Отсутствуют обязательные переменные: {', '.join(missing_vars)}")
        return
    
    log_info("Конфигурация проверена успешно")
    log_info(f"Целевой отправитель: {TARGET_SENDER}")
    log_info(f"Ключевые слова в теме: {TARGET_SUBJECT_KEYWORDS}")
    
    # Запускаем проверку почты
    check_email()
    
    print("=" * 50)
    log_success("Работа скрипта завершена")
    print("=" * 50)

if __name__ == '__main__':
    main()
