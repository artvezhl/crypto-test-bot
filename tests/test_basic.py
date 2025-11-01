import sys
import os
import pytest
from unittest.mock import Mock, patch

# Добавляем src в путь для импорта
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestTradingBot:
    """Базовые тесты для торгового бота"""

    @patch('trading_strategy.DeepSeekClient')
    @patch('trading_strategy.BybitClient')
    def test_bot_initialization(self, mock_bybit, mock_deepseek):
        """Тест инициализации бота"""
        from trading_strategy import TradingBot

        bot = TradingBot()
        assert bot.symbol == "ETHUSDT"
        assert bot.position_size == 0.001
        assert mock_deepseek.called
        assert mock_bybit.called

    @patch('trading_strategy.DeepSeekClient')
    @patch('trading_strategy.BybitClient')
    def test_market_data_processing(self, mock_bybit, mock_deepseek):
        """Тест обработки рыночных данных"""
        from trading_strategy import TradingBot

        # Настраиваем моки
        mock_bybit_instance = mock_bybit.return_value
        mock_deepseek_instance = mock_deepseek.return_value

        mock_bybit_instance.get_market_data.return_value = {
            'symbol': 'ETHUSDT',
            'price': 3500.0,
            'price_change_24h': 2.5,
            'volume_24h': 10000000
        }

        mock_deepseek_instance.get_trading_signal.return_value = {
            'action': 'HOLD',
            'confidence': 0.5,
            'reason': 'Тестовый сигнал'
        }

        bot = TradingBot()
        bot.run_iteration()

        # Проверяем вызовы
        mock_bybit_instance.get_market_data.assert_called_once_with("ETHUSDT")
        mock_deepseek_instance.get_trading_signal.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
