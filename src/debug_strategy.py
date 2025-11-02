import logging
import json
from unittest.mock import Mock, patch
from trading_strategy import TradingBot
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_strategy_logic():
    """Тестируем логику торговой стратегии"""
    print("🎯 Тестируем логику торговой стратегии...")

    # Настраиваем логирование для отладки
    logging.basicConfig(level=logging.DEBUG)

    # Создаем моки для изоляции теста
    with patch('trading_strategy.DeepSeekClient') as mock_deepseek:
        with patch('trading_strategy.BybitClient') as mock_bybit:
            with patch('requests.post') as mock_requests:  # Мок для Telegram

                # Настраиваем моки
                mock_bybit_instance = mock_bybit.return_value
                mock_deepseek_instance = mock_deepseek.return_value

                # Мок для успешного Telegram запроса
                mock_telegram_response = Mock()
                mock_telegram_response.status_code = 200
                mock_telegram_response.json.return_value = {'ok': True}
                mock_requests.return_value = mock_telegram_response

                # Тестовые данные
                test_market_data = {
                    'symbol': 'ETHUSDT',
                    'price': 3500.0,
                    'price_change_24h': 2.5,
                    'volume_24h': 10000000,
                    'historical': 'Тестовые данные'
                }

                # Тестовые сигналы для разных сценариев
                test_scenarios = [
                    {
                        'name': '📈 Сильный BUY сигнал',
                        'signal': {'action': 'BUY', 'confidence': 0.85, 'reason': 'Сильный восходящий тренд'},
                        'should_trade': True
                    },
                    {
                        'name': '📉 Сильный SELL сигнал',
                        'signal': {'action': 'SELL', 'confidence': 0.82, 'reason': 'Сильный нисходящий тренд'},
                        'should_trade': True
                    },
                    {
                        'name': '⚖️ Слабый HOLD сигнал',
                        'signal': {'action': 'HOLD', 'confidence': 0.65, 'reason': 'Неопределенность на рынке'},
                        'should_trade': False
                    },
                    {
                        'name': '❌ Слишком низкая уверенность',
                        'signal': {'action': 'BUY', 'confidence': 0.65, 'reason': 'Слабый сигнал'},
                        'should_trade': False
                    }
                ]

                for scenario in test_scenarios:
                    print(f"\n{scenario['name']}")
                    print("-" * 40)

                    # Настраиваем моки для текущего сценария
                    mock_bybit_instance.get_market_data.return_value = test_market_data
                    mock_deepseek_instance.get_trading_signal.return_value = scenario['signal']
                    mock_bybit_instance.place_order.return_value = {
                        'result': {'orderId': 'test123'}}

                    # Создаем и запускаем бота
                    bot = TradingBot()
                    bot.run_iteration()

                    # Проверяем результаты
                    if scenario['should_trade']:
                        # Должен быть вызван place_order
                        if mock_bybit_instance.place_order.called:
                            print(
                                f"✅ Ордер размещен: {scenario['signal']['action']}")
                        else:
                            print(
                                f"❌ Ордер НЕ размещен, но должен был: {scenario['signal']['action']}")
                    else:
                        # Не должен быть вызван place_order
                        if not mock_bybit_instance.place_order.called:
                            print("✅ Ордер не размещен (низкая уверенность)")
                        else:
                            print("❌ Ордер размещен, но не должен был")

                    # Проверяем вызовы DeepSeek и Bybit
                    print(
                        f"📊 DeepSeek вызван: {mock_deepseek_instance.get_trading_signal.called}")
                    print(
                        f"📈 Bybit get_market_data вызван: {mock_bybit_instance.get_market_data.called}")

                    # Сбрасываем моки для следующего теста
                    mock_bybit_instance.reset_mock()
                    mock_deepseek_instance.reset_mock()
                    mock_requests.reset_mock()


def test_single_scenario():
    """Тестируем один конкретный сценарий с детальной отладкой"""
    print("\n🎯 Тестируем один сценарий с детальной отладкой...")

    with patch('trading_strategy.DeepSeekClient') as mock_deepseek:
        with patch('trading_strategy.BybitClient') as mock_bybit:
            with patch('requests.post') as mock_requests:

                # Настраиваем моки
                mock_bybit_instance = mock_bybit.return_value
                mock_deepseek_instance = mock_deepseek.return_value
                mock_requests.return_value.status_code = 200

                # Конкретный тестовый сценарий
                test_market_data = {
                    'symbol': 'ETHUSDT',
                    'price': 3500.0,
                    'price_change_24h': 2.5,
                    'volume_24h': 10000000,
                    'historical': 'Цены: [3480, 3490, 3500, 3510, 3505]'
                }

                test_signal = {
                    'action': 'BUY',
                    'confidence': 0.85,
                    'reason': 'Сильный восходящий тренд'
                }

                mock_bybit_instance.get_market_data.return_value = test_market_data
                mock_deepseek_instance.get_trading_signal.return_value = test_signal
                mock_bybit_instance.place_order.return_value = {
                    'result': {'orderId': 'test123'}}

                print("🔧 Создаем бота...")
                bot = TradingBot()

                print("🔄 Запускаем итерацию...")
                bot.run_iteration()

                # Детальная проверка
                print("\n📋 РЕЗУЛЬТАТЫ ТЕСТА:")
                print(
                    f"✅ Bybit.get_market_data вызван: {mock_bybit_instance.get_market_data.called}")
                print(
                    f"✅ DeepSeek.get_trading_signal вызван: {mock_deepseek_instance.get_trading_signal.called}")
                print(
                    f"✅ Bybit.place_order вызван: {mock_bybit_instance.place_order.called}")

                if mock_bybit_instance.place_order.called:
                    call_args = mock_bybit_instance.place_order.call_args
                    print(f"✅ Аргументы place_order: {call_args}")

                print(f"✅ Telegram запрос отправлен: {mock_requests.called}")


if __name__ == "__main__":
    print("🚀 Запуск тестов стратегии...")

    # Запускаем все сценарии
    test_strategy_logic()

    # Запускаем детальный тест одного сценария
    test_single_scenario()

    print("\n🎉 Все тесты завершены!")
