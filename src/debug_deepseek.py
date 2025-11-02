import json
from deepseek_client import DeepSeekClient
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_deepseek_client():
    """Тестируем клиент DeepSeek изолированно"""
    print("🧪 Тестируем DeepSeek клиент...")

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
    print(json.dumps(test_market_data, indent=2))

    try:
        signal = client.get_trading_signal(test_market_data)
        print("✅ Получен сигнал от DeepSeek:")
        print(json.dumps(signal, indent=2))
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_deepseek_client()
