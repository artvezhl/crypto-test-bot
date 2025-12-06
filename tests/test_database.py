"""
Unit-тесты для Database класса.

Запуск:
    pytest tests/test_database.py -v
    pytest tests/test_database.py -v -k "test_add"  # только тесты добавления
"""
import sys
import os
import pytest
import tempfile
from unittest.mock import patch

# Добавляем src в путь для импорта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestDatabaseVirtualPositions:
    """Тесты для работы с виртуальными позициями"""

    @pytest.fixture
    def db(self):
        """Создаёт временную SQLite БД для тестов"""
        # Создаём временный файл для БД
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db_path = f.name
        
        # Патчим DATABASE_URL чтобы использовать временную БД
        with patch.dict(os.environ, {'DATABASE_URL': ''}, clear=False):
            from database import Database
            
            # Создаём Database с временным файлом
            db = Database.__new__(Database)
            db.logger = __import__('logging').getLogger(__name__)
            db.max_retries = 3
            db.retry_delay = 1
            db.db_config = temp_db_path
            db.db_type = 'sqlite'
            db._init_db()
            
            yield db
        
        # Удаляем временный файл после теста
        try:
            os.unlink(temp_db_path)
        except:
            pass

    def test_add_virtual_position_buy(self, db):
        """Тест добавления BUY позиции"""
        position_id = db.add_virtual_position(
            symbol='BTCUSDT',
            side='BUY',
            size=0.001,
            entry_price=50000.0,
            leverage=10,
            stop_loss=49000.0,
            take_profit=52000.0
        )
        
        assert position_id > 0
        
        # Проверяем, что позиция сохранилась
        position = db.get_virtual_position(position_id)
        assert position is not None
        assert position['symbol'] == 'BTCUSDT'
        assert position['side'] == 'BUY'
        assert position['size'] == 0.001
        assert position['entry_price'] == 50000.0
        assert position['leverage'] == 10
        assert position['status'] == 'open'

    def test_add_virtual_position_sell(self, db):
        """Тест добавления SELL позиции"""
        position_id = db.add_virtual_position(
            symbol='ETHUSDT',
            side='SELL',
            size=0.1,
            entry_price=3000.0,
            leverage=5,
            stop_loss=3100.0,
            take_profit=2800.0
        )
        
        assert position_id > 0
        
        position = db.get_virtual_position(position_id)
        assert position is not None
        assert position['side'] == 'SELL'
        assert position['stop_loss'] == 3100.0
        assert position['take_profit'] == 2800.0

    def test_close_virtual_position(self, db):
        """Тест закрытия позиции"""
        # Создаём позицию
        position_id = db.add_virtual_position(
            symbol='BTCUSDT',
            side='BUY',
            size=0.001,
            entry_price=50000.0,
            leverage=10
        )
        
        # Закрываем с прибылью
        db.close_virtual_position(position_id, exit_price=51000.0, close_reason='take_profit')
        
        # Проверяем
        position = db.get_virtual_position(position_id)
        assert position['status'] == 'closed'
        assert position['exit_price'] == 51000.0
        assert position['close_reason'] == 'take_profit'
        # PnL = (51000 - 50000) * 0.001 = 1.0
        assert position['realized_pnl'] == 1.0

    def test_close_virtual_position_with_loss(self, db):
        """Тест закрытия позиции с убытком"""
        position_id = db.add_virtual_position(
            symbol='BTCUSDT',
            side='BUY',
            size=0.001,
            entry_price=50000.0
        )
        
        # Закрываем с убытком
        db.close_virtual_position(position_id, exit_price=49000.0, close_reason='stop_loss')
        
        position = db.get_virtual_position(position_id)
        assert position['status'] == 'closed'
        # PnL = (49000 - 50000) * 0.001 = -1.0
        assert position['realized_pnl'] == -1.0

    def test_update_virtual_position_price(self, db):
        """Тест обновления цены позиции"""
        position_id = db.add_virtual_position(
            symbol='BTCUSDT',
            side='BUY',
            size=0.001,
            entry_price=50000.0
        )
        
        # Обновляем цену
        db.update_virtual_position_price(position_id, current_price=51000.0)
        
        position = db.get_virtual_position(position_id)
        assert position['current_price'] == 51000.0
        # Unrealized PnL = (51000 - 50000) * 0.001 = 1.0
        assert position['unrealized_pnl'] == 1.0

    def test_get_virtual_open_positions(self, db):
        """Тест получения открытых позиций"""
        # Создаём несколько позиций
        db.add_virtual_position('BTCUSDT', 'BUY', 0.001, 50000.0)
        db.add_virtual_position('ETHUSDT', 'SELL', 0.1, 3000.0)
        pos3_id = db.add_virtual_position('BTCUSDT', 'SELL', 0.002, 51000.0)
        
        # Закрываем одну
        db.close_virtual_position(pos3_id, 50000.0, 'manual')
        
        # Получаем все открытые
        open_positions = db.get_virtual_open_positions()
        assert len(open_positions) == 2
        
        # Получаем только по BTCUSDT
        btc_positions = db.get_virtual_open_positions('BTCUSDT')
        assert len(btc_positions) == 1
        assert btc_positions[0]['symbol'] == 'BTCUSDT'

    def test_get_virtual_trade_stats(self, db):
        """Тест получения статистики торговли"""
        # Создаём и закрываем позиции
        pos1 = db.add_virtual_position('BTCUSDT', 'BUY', 0.001, 50000.0)
        db.close_virtual_position(pos1, 51000.0, 'take_profit')  # +1.0
        
        pos2 = db.add_virtual_position('BTCUSDT', 'BUY', 0.001, 50000.0)
        db.close_virtual_position(pos2, 49000.0, 'stop_loss')  # -1.0
        
        pos3 = db.add_virtual_position('ETHUSDT', 'SELL', 0.1, 3000.0)
        db.close_virtual_position(pos3, 2900.0, 'take_profit')  # +10.0
        
        # Одна открытая позиция
        db.add_virtual_position('BTCUSDT', 'BUY', 0.001, 50000.0)
        
        stats = db.get_virtual_trade_stats(days=30)
        
        assert stats['total_trades'] == 4
        assert stats['closed_trades'] == 3
        assert stats['open_trades'] == 1
        assert stats['winning_trades'] == 2
        assert stats['losing_trades'] == 1
        # Total realized PnL = 1.0 - 1.0 + 10.0 = 10.0
        assert stats['total_realized_pnl'] == 10.0


class TestDatabaseValidation:
    """Тесты валидации параметров"""

    @pytest.fixture
    def db(self):
        """Создаёт временную SQLite БД для тестов"""
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

    def test_invalid_side(self, db):
        """Тест: невалидный side вызывает ошибку"""
        with pytest.raises(ValueError, match="Невалидный side"):
            db.add_virtual_position(
                symbol='BTCUSDT',
                side='INVALID',
                size=0.001,
                entry_price=50000.0
            )

    def test_invalid_size_zero(self, db):
        """Тест: size = 0 вызывает ошибку"""
        with pytest.raises(ValueError, match="Невалидный size"):
            db.add_virtual_position(
                symbol='BTCUSDT',
                side='BUY',
                size=0,
                entry_price=50000.0
            )

    def test_invalid_size_negative(self, db):
        """Тест: отрицательный size вызывает ошибку"""
        with pytest.raises(ValueError, match="Невалидный size"):
            db.add_virtual_position(
                symbol='BTCUSDT',
                side='BUY',
                size=-0.001,
                entry_price=50000.0
            )

    def test_invalid_entry_price(self, db):
        """Тест: невалидная entry_price вызывает ошибку"""
        with pytest.raises(ValueError, match="Невалидный entry_price"):
            db.add_virtual_position(
                symbol='BTCUSDT',
                side='BUY',
                size=0.001,
                entry_price=0
            )

    def test_invalid_leverage_too_low(self, db):
        """Тест: leverage < 1 вызывает ошибку"""
        with pytest.raises(ValueError, match="Невалидный leverage"):
            db.add_virtual_position(
                symbol='BTCUSDT',
                side='BUY',
                size=0.001,
                entry_price=50000.0,
                leverage=0
            )

    def test_invalid_leverage_too_high(self, db):
        """Тест: leverage > 125 вызывает ошибку"""
        with pytest.raises(ValueError, match="Невалидный leverage"):
            db.add_virtual_position(
                symbol='BTCUSDT',
                side='BUY',
                size=0.001,
                entry_price=50000.0,
                leverage=200
            )

    def test_invalid_symbol_empty(self, db):
        """Тест: пустой symbol вызывает ошибку"""
        with pytest.raises(ValueError, match="Невалидный symbol"):
            db.add_virtual_position(
                symbol='',
                side='BUY',
                size=0.001,
                entry_price=50000.0
            )

    def test_invalid_symbol_too_short(self, db):
        """Тест: слишком короткий symbol вызывает ошибку"""
        with pytest.raises(ValueError, match="Невалидный symbol"):
            db.add_virtual_position(
                symbol='BT',
                side='BUY',
                size=0.001,
                entry_price=50000.0
            )

    def test_invalid_stop_loss_buy(self, db):
        """Тест: stop_loss >= entry_price для BUY вызывает ошибку"""
        with pytest.raises(ValueError, match="Stop-loss.*должен быть ниже"):
            db.add_virtual_position(
                symbol='BTCUSDT',
                side='BUY',
                size=0.001,
                entry_price=50000.0,
                stop_loss=51000.0  # выше entry_price
            )

    def test_invalid_take_profit_buy(self, db):
        """Тест: take_profit <= entry_price для BUY вызывает ошибку"""
        with pytest.raises(ValueError, match="Take-profit.*должен быть выше"):
            db.add_virtual_position(
                symbol='BTCUSDT',
                side='BUY',
                size=0.001,
                entry_price=50000.0,
                take_profit=49000.0  # ниже entry_price
            )

    def test_invalid_stop_loss_sell(self, db):
        """Тест: stop_loss <= entry_price для SELL вызывает ошибку"""
        with pytest.raises(ValueError, match="Stop-loss.*должен быть выше"):
            db.add_virtual_position(
                symbol='BTCUSDT',
                side='SELL',
                size=0.001,
                entry_price=50000.0,
                stop_loss=49000.0  # ниже entry_price
            )

    def test_invalid_take_profit_sell(self, db):
        """Тест: take_profit >= entry_price для SELL вызывает ошибку"""
        with pytest.raises(ValueError, match="Take-profit.*должен быть ниже"):
            db.add_virtual_position(
                symbol='BTCUSDT',
                side='SELL',
                size=0.001,
                entry_price=50000.0,
                take_profit=51000.0  # выше entry_price
            )


class TestDatabaseSettings:
    """Тесты для работы с настройками"""

    @pytest.fixture
    def db(self):
        """Создаёт временную SQLite БД для тестов"""
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

    def test_set_and_get_setting(self, db):
        """Тест установки и получения настройки"""
        db.set_setting('test_key', 'test_value')
        
        value = db.get_setting('test_key')
        assert value == 'test_value'

    def test_get_setting_default(self, db):
        """Тест получения настройки с дефолтным значением"""
        value = db.get_setting('non_existent_key', 'default_value')
        assert value == 'default_value'

    def test_update_setting(self, db):
        """Тест обновления настройки"""
        db.set_setting('test_key', 'value1')
        db.set_setting('test_key', 'value2')
        
        value = db.get_setting('test_key')
        assert value == 'value2'


class TestDatabaseDecimalConversion:
    """Тесты конвертации Decimal в float"""

    @pytest.fixture
    def db(self):
        """Создаёт временную SQLite БД для тестов"""
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

    def test_convert_row_with_decimal(self, db):
        """Тест конвертации Decimal в float"""
        from decimal import Decimal
        
        row = {
            'id': 1,
            'price': Decimal('50000.12345678'),
            'size': Decimal('0.001'),
            'name': 'test'
        }
        
        converted = db._convert_row(row)
        
        assert converted['id'] == 1
        assert isinstance(converted['price'], float)
        assert converted['price'] == 50000.12345678
        assert isinstance(converted['size'], float)
        assert converted['name'] == 'test'

    def test_convert_rows(self, db):
        """Тест конвертации списка словарей"""
        from decimal import Decimal
        
        rows = [
            {'id': 1, 'price': Decimal('100.0')},
            {'id': 2, 'price': Decimal('200.0')}
        ]
        
        converted = db._convert_rows(rows)
        
        assert len(converted) == 2
        assert isinstance(converted[0]['price'], float)
        assert isinstance(converted[1]['price'], float)

    def test_position_values_are_float(self, db):
        """Тест: значения позиции возвращаются как float"""
        position_id = db.add_virtual_position(
            symbol='BTCUSDT',
            side='BUY',
            size=0.001,
            entry_price=50000.12345678
        )
        
        position = db.get_virtual_position(position_id)
        
        # Проверяем, что числовые значения - float
        assert isinstance(position['size'], float)
        assert isinstance(position['entry_price'], float)
        assert isinstance(position['current_price'], float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

