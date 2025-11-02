from order_helper import OrderHelper
from config import Config
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def final_check():
    """Финальная проверка всех типов данных"""
    print("🔍 ФИНАЛЬНАЯ ПРОВЕРКА ТИПОВ ДАННЫХ")
    print("=" * 50)

    # Проверка Config
    print("📋 Config проверка:")
    print(
        f"  POSITION_SIZE: {Config.POSITION_SIZE} (тип: {type(Config.POSITION_SIZE)})")
    print(
        f"  MIN_CONFIDENCE: {Config.MIN_CONFIDENCE} (тип: {type(Config.MIN_CONFIDENCE)})")

    # Проверка OrderHelper
    print("\n🔧 OrderHelper проверка:")
    test_size = OrderHelper.get_validated_size('ETHUSDT', 0.01, 3950)
    print(f"  Тестовый размер: {test_size} (тип: {type(test_size)})")

    # Проверка преобразований
    print("\n🔄 Проверка преобразований:")
    position_size_float = float(Config.POSITION_SIZE)
    print(
        f"  float(Config.POSITION_SIZE): {position_size_float} (тип: {type(position_size_float)})")

    print("\n✅ ВСЕ ПРОВЕРКИ ЗАВЕРШЕНЫ")


if __name__ == "__main__":
    final_check()
