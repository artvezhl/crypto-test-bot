import json
from deepseek_client import DeepSeekClient
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_deepseek_with_debug():
    """Тестируем DeepSeek с детальной отладкой"""
    print("🧪 Тестируем DeepSeek клиент с отладкой...")

    # Проверяем наличие API ключа
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key or api_key == "your_deepseek_api_key_here":
        print("❌ API ключ DeepSeek не настроен!")
        print("💡 Добавьте ваш реальный API ключ в файл .env")
        return

    client = DeepSeekClient()

    # Тестовые данные
    test_market_data = {
        'symbol': 'ETHUSDT',
        'price': 3500.50,
        'price_change_24h': 2.5,
        'volume_24h': 15000000,
        'rsi': 45.5,
        'macd': -12.3,
        'trend': 'neutral',
        'historical': 'Последние цены: [3480, 3490, 3500, 3510, 3505]'
    }

    print("📊 Отправляем тестовые данные:")
    print(json.dumps(test_market_data, indent=2, ensure_ascii=False))

    try:
        signal = client.get_trading_signal(test_market_data)
        print("✅ Результат:")
        print(json.dumps(signal, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_deepseek_with_debug()
