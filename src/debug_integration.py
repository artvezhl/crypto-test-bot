import json
from deepseek_client import DeepSeekClient
from bybit_client import BybitClient
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_full_integration():
    """Тестируем полную интеграцию всех компонентов"""
    print("🔄 Тестируем полную интеграцию...")

    # 1. Тестируем Bybit
    print("\n1. 🔗 Тестируем Bybit клиент...")
    bybit = BybitClient()

    try:
        market_data = bybit.get_market_data("ETHUSDT")
        if market_data:
            print(f"✅ Bybit данные получены:")
            print(f"   Символ: {market_data['symbol']}")
            print(f"   Цена: {market_data['price']}")
            print(f"   Изменение 24h: {market_data['price_change_24h']}%")
        else:
            print("❌ Не удалось получить данные Bybit")
            return False
    except Exception as e:
        print(f"❌ Ошибка Bybit: {e}")
        return False

    # 2. Тестируем DeepSeek
    print("\n2. 🧠 Тестируем DeepSeek клиент...")
    deepseek = DeepSeekClient()

    try:
        signal = deepseek.get_trading_signal(market_data)
        print(f"✅ DeepSeek сигнал получен:")
        print(f"   Действие: {signal['action']}")
        print(f"   Уверенность: {signal['confidence']}")
        print(f"   Причина: {signal['reason']}")
    except Exception as e:
        print(f"❌ Ошибка DeepSeek: {e}")
        return False

    # 3. Тестируем Telegram (опционально)
    print("\n3. 📱 Тестируем Telegram уведомление...")
    try:
        import requests
        from config import Config

        token = Config.TELEGRAM_BOT_TOKEN
        chat_id = Config.TELEGRAM_CHAT_ID

        if token and token != "your_telegram_token" and chat_id and chat_id != "your_chat_id":
            message = f"""
🤖 *ИНТЕГРАЦИОННЫЙ ТЕСТ*

📊 *Данные рынка:*
• Символ: {market_data['symbol']}
• Цена: ${market_data['price']}
• Изменение: {market_data['price_change_24h']}%

🎯 *Сигнал AI:*
• Действие: {signal['action']}
• Уверенность: {signal['confidence']}
• Причина: {signal['reason']}

✅ Все системы работают!
"""

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }

            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                print("✅ Telegram уведомление отправлено")
            else:
                print(f"⚠️ Telegram ошибка: {response.status_code}")
        else:
            print("⚠️ Telegram не настроен, пропускаем")

    except Exception as e:
        print(f"⚠️ Ошибка Telegram: {e}")

    print("\n" + "="*50)
    print("🎉 ИНТЕГРАЦИОННЫЙ ТЕСТ ЗАВЕРШЕН УСПЕШНО!")
    print("="*50)

    return True


if __name__ == "__main__":
    test_full_integration()
