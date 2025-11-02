from trading_strategy import TradingBot
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_final():
    """Финальный тест"""
    print("🧪 ФИНАЛЬНЫЙ ТЕСТ")
    print("=" * 50)

    bot = TradingBot()

    print(
        f"✅ position_size: {bot.position_size} (тип: {type(bot.position_size)})")
    print(
        f"✅ min_confidence: {bot.min_confidence} (тип: {type(bot.min_confidence)})")

    # Проверяем, что это действительно числа
    if isinstance(bot.position_size, (int, float)) and isinstance(bot.min_confidence, (int, float)):
        print("🎉 ВСЕ ПРАВИЛЬНО - это числа!")
        return True
    else:
        print("❌ ОШИБКА - это не числа!")
        return False


if __name__ == "__main__":
    test_final()
