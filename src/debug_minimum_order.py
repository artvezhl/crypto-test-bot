from bybit_client import BybitClient
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_minimum_orders():
    """Тестируем различные размеры ордеров чтобы найти минимальный"""
    print("🧪 Тестируем минимальные размеры ордеров для Bybit...")
    print("=" * 60)

    client = BybitClient()

    # Тестируем разные размеры
    test_sizes = [0.01, 0.02, 0.03, 0.04, 0.05]

    for size in test_sizes:
        print(f"\n🔍 Тестируем размер: {size} ETH")

        # Получаем текущую цену
        market_data = client.get_market_data("ETHUSDT")
        if not market_data:
            print("❌ Не удалось получить данные рынка")
            continue

        price = market_data['price']
        order_value = size * price
        print(f"💵 Стоимость ордера: ${order_value:.2f}")

        # Пробуем разместить ордер
        order = client.place_order(
            symbol="ETHUSDT",
            side="Buy",
            qty=size
        )

        if order:
            print(
                f"✅ УСПЕХ! Минимальный рабочий размер: {size} ETH (${order_value:.2f})")
            break
        else:
            print(f"❌ Не удалось с размером {size} ETH")


if __name__ == "__main__":
    test_minimum_orders()
