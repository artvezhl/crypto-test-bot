import logging
from trading_strategy import TradingBot
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_strategy_simple():
    """Простой тест стратегии без моков (только если есть реальные API ключи)"""
    print("🎯 Простой тест стратегии...")

    # Включаем подробное логирование
    logging.basicConfig(level=logging.INFO)

    try:
        print("🔧 Создаем бота...")
        bot = TradingBot()

        print("🔄 Запускаем одну итерацию...")
        bot.run_iteration()

        print("✅ Итерация завершена успешно!")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_strategy_simple()
