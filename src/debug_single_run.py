import logging
from trading_strategy import TradingBot
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_single_iteration():
    """Тестируем одну итерацию торгового бота"""
    print("🧪 Тестируем одну итерацию торгового бота...")

    # Настраиваем логирование для отладки
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    bot = TradingBot()

    try:
        print("🚀 Запускаем одну итерацию...")
        bot.run_iteration()
        print("✅ Итерация завершена успешно!")
    except Exception as e:
        print(f"❌ Ошибка во время итерации: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_single_iteration()
