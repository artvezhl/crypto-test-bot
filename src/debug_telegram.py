from config import Config
import json
import requests
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_telegram_connection():
    """Тестируем подключение к Telegram API"""
    print("🧪 Тестируем Telegram уведомления...")

    token = Config.TELEGRAM_BOT_TOKEN
    chat_id = Config.TELEGRAM_CHAT_ID

    if not token or token == "your_telegram_token":
        print("❌ TELEGRAM_BOT_TOKEN не настроен в .env файле")
        return False

    if not chat_id or chat_id == "your_chat_id":
        print("❌ TELEGRAM_CHAT_ID не настроен в .env файле")
        return False

    print(f"🔑 Token: {token[:10]}...")
    print(f"💬 Chat ID: {chat_id}")

    # Тестируем получение информации о боте
    url = f"https://api.telegram.org/bot{token}/getMe"

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            bot_info = response.json()
            print(
                f"✅ Бот найден: {bot_info['result']['first_name']} (@{bot_info['result']['username']})")
        else:
            print(
                f"❌ Ошибка получения информации о боте: {response.status_code}")
            print(f"📄 Ответ: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Ошибка подключения к Telegram API: {e}")
        return False

    return True


def send_test_messages():
    """Отправляем тестовые сообщения"""
    token = Config.TELEGRAM_BOT_TOKEN
    chat_id = Config.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        return False

    test_messages = [
        "🔔 *ТЕСТОВОЕ УВЕДОМЛЕНИЕ* 🔔",
        "🤖 Торговый бот успешно запущен!",
        "📊 Статус: Работает в тестовом режиме",
        "💹 Сигнал: HOLD (тестовый)",
        "🔄 Итерация завершена успешно",
        "❌ Тестовое сообщение об ошибке"
    ]

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    successful_messages = 0

    for i, message in enumerate(test_messages, 1):
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                print(f"✅ Сообщение {i} отправлено: {message[:30]}...")
                successful_messages += 1
            else:
                print(
                    f"❌ Ошибка отправки сообщения {i}: {response.status_code}")
                print(f"📄 Ответ: {response.text}")
        except Exception as e:
            print(f"❌ Ошибка при отправке сообщения {i}: {e}")

    return successful_messages


def test_telegram_formats():
    """Тестируем разные форматы сообщений"""
    token = Config.TELEGRAM_BOT_TOKEN
    chat_id = Config.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # Тест с форматированием Markdown
    markdown_message = """
*📊 ТЕСТ ФОРМАТИРОВАНИЯ 📊*

*Жирный текст*
_Курсивный текст_
`Моноширинный текст`

*Список:*
• Пункт 1
• Пункт 2
• Пункт 3

[Ссылка](https://bybit.com)
"""

    payload = {
        'chat_id': chat_id,
        'text': markdown_message,
        'parse_mode': 'Markdown'
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("✅ Markdown сообщение отправлено")
        else:
            print(f"❌ Ошибка Markdown сообщения: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка отправки Markdown: {e}")


if __name__ == "__main__":
    print("🚀 Запуск теста Telegram уведомлений...\n")

    # Тестируем подключение
    if test_telegram_connection():
        print("\n" + "="*50)
        print("📨 Тестируем отправку сообщений...")
        print("="*50)

        # Отправляем тестовые сообщения
        success_count = send_test_messages()

        print("\n" + "="*50)
        print("🎨 Тестируем форматирование...")
        print("="*50)

        # Тестируем форматирование
        test_telegram_formats()

        print("\n" + "="*50)
        print(f"📊 ИТОГ: Отправлено {success_count} сообщений")
        print("="*50)
    else:
        print("\n❌ Тест не пройден: проверьте настройки Telegram")
