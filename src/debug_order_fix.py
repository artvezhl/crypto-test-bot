from order_helper import OrderHelper
from config import Config
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_order_fix():
    """Тестируем исправление ордеров"""
    print("🧪 Тестируем исправление проблемы с ордерами...")

    # Проверяем, что POSITION_SIZE - это число
    print(
        f"📏 POSITION_SIZE: {Config.POSITION_SIZE} (тип: {type(Config.POSITION_SIZE)})")

    # Тестируем OrderHelper
    test_cases = [
        ('ETHUSDT', 0.001, 3950),  # Должен скорректировать до 0.01
        ('ETHUSDT', 0.01, 3950),   # Должен остаться 0.01
        ('ETHUSDT', 0.02, 3950),   # Должен остаться 0.02
    ]

    for symbol, size, price in test_cases:
        validated = OrderHelper.get_validated_size(symbol, size, price)
        value = validated * price
        print(f"{symbol}: {size} -> {validated} (${value:.2f})")


if __name__ == "__main__":
    test_order_fix()
