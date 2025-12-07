"""
Integration тесты для торгового бота.

Тестируют полный цикл работы виртуальной торговли:
- Полный торговый цикл
- Срабатывание stop-loss и take-profit
- Position reversal

Запуск:
    pytest tests/test_integration.py -v
"""
import sys
import os
import pytest
import tempfile
from unittest.mock import Mock, patch, MagicMock

# Добавляем src в путь для импорта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestFullTradingCycle:
    """Интеграционные тесты полного торгового цикла"""

    @pytest.fixture
    def mock_env(self):
        """Мокает переменные окружения"""
        env_vars = {
            'DATABASE_URL': '',
            'BYBIT_API_KEY': 'test_key',
            'BYBIT_API_SECRET': 'test_secret',
            'DEEPSEEK_API_KEY': 'test_deepseek_key',
            'TELEGRAM_BOT_TOKEN': 'test_telegram_token',
        }
        with patch.dict(os.environ, env_vars, clear=False):
            yield

    @pytest.fixture
    def temp_db_path(self):
        """Создаёт временный путь для БД"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            yield f.name
        try:
            os.unlink(f.name)
        except:
            pass

    @pytest.fixture
    def db(self, temp_db_path, mock_env):
        """Создаёт временную БД для тестов"""
        from database import Database
        
        db = Database.__new__(Database)
        db.logger = __import__('logging').getLogger(__name__)
        db.max_retries = 3
        db.retry_delay = 1
        db.db_config = temp_db_path
        db.db_type = 'sqlite'
        db._init_db()
        
        return db

    def test_full_trading_cycle_buy_then_close(self, db):
        """Тест: открытие BUY позиции → обновление цены → закрытие по take-profit"""
        # 1. Открываем позицию
        position_id = db.add_virtual_position(
            symbol='BTCUSDT',
            side='BUY',
            size=0.01,
            entry_price=50000.0,
            leverage=10,
            stop_loss=49000.0,
            take_profit=52000.0
        )
        
        assert position_id > 0
        
        # 2. Проверяем, что позиция открыта
        open_positions = db.get_virtual_open_positions('BTCUSDT')
        assert len(open_positions) == 1
        assert open_positions[0]['status'] == 'open'
        
        # 3. Обновляем цену (рост)
        db.update_virtual_position_price(position_id, 51000.0)
        
        position = db.get_virtual_position(position_id)
        assert position['current_price'] == 51000.0
        assert position['unrealized_pnl'] == 10.0  # (51000 - 50000) * 0.01
        
        # 4. Цена достигает take-profit
        db.close_virtual_position(position_id, 52000.0, 'take_profit')
        
        position = db.get_virtual_position(position_id)
        assert position['status'] == 'closed'
        assert position['close_reason'] == 'take_profit'
        assert position['realized_pnl'] == 20.0  # (52000 - 50000) * 0.01
        
        # 5. Проверяем статистику
        stats = db.get_virtual_trade_stats(30)
        assert stats['closed_trades'] == 1
        assert stats['winning_trades'] == 1
        assert stats['total_realized_pnl'] == 20.0

    def test_full_trading_cycle_sell_then_close(self, db):
        """Тест: открытие SELL позиции → закрытие с прибылью"""
        # 1. Открываем SHORT позицию
        position_id = db.add_virtual_position(
            symbol='ETHUSDT',
            side='SELL',
            size=1.0,
            entry_price=3000.0,
            leverage=5,
            stop_loss=3100.0,
            take_profit=2800.0
        )
        
        # 2. Цена падает - прибыль для SHORT
        db.update_virtual_position_price(position_id, 2900.0)
        
        position = db.get_virtual_position(position_id)
        # Unrealized PnL = (3000 - 2900) * 1.0 = 100.0
        assert position['unrealized_pnl'] == 100.0
        
        # 3. Закрываем по take-profit
        db.close_virtual_position(position_id, 2800.0, 'take_profit')
        
        position = db.get_virtual_position(position_id)
        # Realized PnL = (3000 - 2800) * 1.0 = 200.0
        assert position['realized_pnl'] == 200.0
        assert position['status'] == 'closed'


class TestStopLossTriggers:
    """Тесты срабатывания stop-loss"""

    @pytest.fixture
    def db(self):
        """Создаёт временную БД"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db_path = f.name
        
        with patch.dict(os.environ, {'DATABASE_URL': ''}, clear=False):
            from database import Database
            
            db = Database.__new__(Database)
            db.logger = __import__('logging').getLogger(__name__)
            db.max_retries = 3
            db.retry_delay = 1
            db.db_config = temp_db_path
            db.db_type = 'sqlite'
            db._init_db()
            
            yield db
        
        try:
            os.unlink(temp_db_path)
        except:
            pass

    def test_stop_loss_triggers_buy(self, db):
        """Тест: stop-loss срабатывает для BUY позиции"""
        position_id = db.add_virtual_position(
            symbol='BTCUSDT',
            side='BUY',
            size=0.01,
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0
        )
        
        # Цена падает ниже stop-loss
        current_price = 48500.0
        position = db.get_virtual_position(position_id)
        
        # Симулируем логику бота
        if current_price <= position['stop_loss']:
            db.close_virtual_position(position_id, current_price, 'stop_loss')
        
        position = db.get_virtual_position(position_id)
        assert position['status'] == 'closed'
        assert position['close_reason'] == 'stop_loss'
        # PnL = (48500 - 50000) * 0.01 = -15.0
        assert position['realized_pnl'] == -15.0

    def test_stop_loss_triggers_sell(self, db):
        """Тест: stop-loss срабатывает для SELL позиции"""
        position_id = db.add_virtual_position(
            symbol='ETHUSDT',
            side='SELL',
            size=1.0,
            entry_price=3000.0,
            stop_loss=3100.0,
            take_profit=2800.0
        )
        
        # Цена растёт выше stop-loss (убыток для SHORT)
        current_price = 3150.0
        position = db.get_virtual_position(position_id)
        
        if current_price >= position['stop_loss']:
            db.close_virtual_position(position_id, current_price, 'stop_loss')
        
        position = db.get_virtual_position(position_id)
        assert position['status'] == 'closed'
        assert position['close_reason'] == 'stop_loss'
        # PnL = (3000 - 3150) * 1.0 = -150.0
        assert position['realized_pnl'] == -150.0


class TestTakeProfitTriggers:
    """Тесты срабатывания take-profit"""

    @pytest.fixture
    def db(self):
        """Создаёт временную БД"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db_path = f.name
        
        with patch.dict(os.environ, {'DATABASE_URL': ''}, clear=False):
            from database import Database
            
            db = Database.__new__(Database)
            db.logger = __import__('logging').getLogger(__name__)
            db.max_retries = 3
            db.retry_delay = 1
            db.db_config = temp_db_path
            db.db_type = 'sqlite'
            db._init_db()
            
            yield db
        
        try:
            os.unlink(temp_db_path)
        except:
            pass

    def test_take_profit_triggers_buy(self, db):
        """Тест: take-profit срабатывает для BUY позиции"""
        position_id = db.add_virtual_position(
            symbol='BTCUSDT',
            side='BUY',
            size=0.01,
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0
        )
        
        # Цена достигает take-profit
        current_price = 52500.0
        position = db.get_virtual_position(position_id)
        
        if current_price >= position['take_profit']:
            db.close_virtual_position(position_id, current_price, 'take_profit')
        
        position = db.get_virtual_position(position_id)
        assert position['status'] == 'closed'
        assert position['close_reason'] == 'take_profit'
        # PnL = (52500 - 50000) * 0.01 = 25.0
        assert position['realized_pnl'] == 25.0

    def test_take_profit_triggers_sell(self, db):
        """Тест: take-profit срабатывает для SELL позиции"""
        position_id = db.add_virtual_position(
            symbol='ETHUSDT',
            side='SELL',
            size=1.0,
            entry_price=3000.0,
            stop_loss=3100.0,
            take_profit=2800.0
        )
        
        # Цена падает до take-profit
        current_price = 2750.0
        position = db.get_virtual_position(position_id)
        
        if current_price <= position['take_profit']:
            db.close_virtual_position(position_id, current_price, 'take_profit')
        
        position = db.get_virtual_position(position_id)
        assert position['status'] == 'closed'
        assert position['close_reason'] == 'take_profit'
        # PnL = (3000 - 2750) * 1.0 = 250.0
        assert position['realized_pnl'] == 250.0


class TestPositionReversal:
    """Тесты переворота позиции (position reversal)"""

    @pytest.fixture
    def db(self):
        """Создаёт временную БД"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db_path = f.name
        
        with patch.dict(os.environ, {'DATABASE_URL': ''}, clear=False):
            from database import Database
            
            db = Database.__new__(Database)
            db.logger = __import__('logging').getLogger(__name__)
            db.max_retries = 3
            db.retry_delay = 1
            db.db_config = temp_db_path
            db.db_type = 'sqlite'
            db._init_db()
            
            yield db
        
        try:
            os.unlink(temp_db_path)
        except:
            pass

    def test_position_reversal_buy_to_sell(self, db):
        """Тест: переворот с BUY на SELL"""
        # 1. Открываем BUY
        buy_id = db.add_virtual_position(
            symbol='BTCUSDT',
            side='BUY',
            size=0.01,
            entry_price=50000.0
        )
        
        # 2. Получаем сигнал на SELL - закрываем BUY
        current_price = 50500.0
        db.close_virtual_position(buy_id, current_price, 'reversal')
        
        # 3. Открываем SELL
        sell_id = db.add_virtual_position(
            symbol='BTCUSDT',
            side='SELL',
            size=0.01,
            entry_price=current_price,
            stop_loss=51500.0,
            take_profit=49000.0
        )
        
        # 4. Проверяем результат
        buy_position = db.get_virtual_position(buy_id)
        assert buy_position['status'] == 'closed'
        assert buy_position['close_reason'] == 'reversal'
        assert buy_position['realized_pnl'] == 5.0  # (50500 - 50000) * 0.01
        
        sell_position = db.get_virtual_position(sell_id)
        assert sell_position['status'] == 'open'
        assert sell_position['side'] == 'SELL'
        
        # 5. Проверяем, что только одна позиция открыта
        open_positions = db.get_virtual_open_positions('BTCUSDT')
        assert len(open_positions) == 1
        assert open_positions[0]['id'] == sell_id

    def test_position_reversal_sell_to_buy(self, db):
        """Тест: переворот с SELL на BUY"""
        # 1. Открываем SELL
        sell_id = db.add_virtual_position(
            symbol='ETHUSDT',
            side='SELL',
            size=1.0,
            entry_price=3000.0
        )
        
        # 2. Получаем сигнал на BUY - закрываем SELL
        current_price = 2900.0  # С прибылью
        db.close_virtual_position(sell_id, current_price, 'reversal')
        
        # 3. Открываем BUY
        buy_id = db.add_virtual_position(
            symbol='ETHUSDT',
            side='BUY',
            size=1.0,
            entry_price=current_price,
            stop_loss=2800.0,
            take_profit=3100.0
        )
        
        # 4. Проверяем
        sell_position = db.get_virtual_position(sell_id)
        assert sell_position['status'] == 'closed'
        assert sell_position['realized_pnl'] == 100.0  # (3000 - 2900) * 1.0
        
        buy_position = db.get_virtual_position(buy_id)
        assert buy_position['status'] == 'open'
        assert buy_position['side'] == 'BUY'


class TestMultipleSymbols:
    """Тесты работы с несколькими символами одновременно"""

    @pytest.fixture
    def db(self):
        """Создаёт временную БД"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db_path = f.name
        
        with patch.dict(os.environ, {'DATABASE_URL': ''}, clear=False):
            from database import Database
            
            db = Database.__new__(Database)
            db.logger = __import__('logging').getLogger(__name__)
            db.max_retries = 3
            db.retry_delay = 1
            db.db_config = temp_db_path
            db.db_type = 'sqlite'
            db._init_db()
            
            yield db
        
        try:
            os.unlink(temp_db_path)
        except:
            pass

    def test_multiple_symbols_positions(self, db):
        """Тест: позиции по разным символам работают независимо"""
        # Открываем позиции по разным символам
        btc_id = db.add_virtual_position('BTCUSDT', 'BUY', 0.01, 50000.0)
        eth_id = db.add_virtual_position('ETHUSDT', 'SELL', 1.0, 3000.0)
        sol_id = db.add_virtual_position('SOLUSDT', 'BUY', 10.0, 100.0)
        
        # Закрываем только ETH
        db.close_virtual_position(eth_id, 2900.0, 'take_profit')
        
        # Проверяем
        all_open = db.get_virtual_open_positions()
        assert len(all_open) == 2
        
        btc_open = db.get_virtual_open_positions('BTCUSDT')
        assert len(btc_open) == 1
        
        eth_open = db.get_virtual_open_positions('ETHUSDT')
        assert len(eth_open) == 0
        
        sol_open = db.get_virtual_open_positions('SOLUSDT')
        assert len(sol_open) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


