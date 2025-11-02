import json
from bybit_client import BybitClient
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_bybit_client():
    """Тестируем клиент Bybit изолированно"""
    print("🧪 Тестируем Bybit клиент...")

    client = BybitClient()

    try:
        # Тест получения баланса
        print("💰 Получаем баланс...")
        balance = client.get_balance()
        if balance:
            print("✅ Баланс получен:")
            print(json.dumps(balance, indent=2))
        else:
            print("❌ Не удалось получить баланс")

        # Тест получения рыночных данных
        print("\n📈 Получаем рыночные данные...")
        market_data = client.get_market_data("ETHUSDT")
        if market_data:
            print("✅ Рыночные данные получены:")
            print(json.dumps(market_data, indent=2))
        else:
            print("❌ Не удалось получить рыночные данные")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_bybit_client()
