from contextlib import contextmanager
from decimal import Decimal
import json
import time
import urllib.parse
from psycopg2.extras import RealDictCursor
import psycopg2
from datetime import datetime
from typing import List, Dict, Optional, Any
import logging
import os


class Database:
    def __init__(self, db_url=None, max_retries=3, retry_delay=1):
        self.logger = logging.getLogger(__name__)
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        if db_url is None:
            db_url = os.getenv('DATABASE_URL')

        if db_url:
            self.db_config = self._parse_db_url(db_url)
            self.db_type = 'postgresql'
        else:
            self.db_config = self._get_sqlite_path()
            self.db_type = 'sqlite'

        self.logger.info(f"🔧 Используется БД: {self.db_type}")
        self._init_db()

    def _parse_db_url(self, db_url):
        """Парсинг URL базы данных для PostgreSQL"""
        try:
            result = urllib.parse.urlparse(db_url)
            return {
                'dbname': result.path[1:],
                'user': result.username,
                'password': result.password,
                'host': result.hostname,
                'port': result.port
            }
        except Exception as e:
            self.logger.error(f"❌ Ошибка парсинга DATABASE_URL: {e}")
            return None

    @contextmanager
    def _get_connection_with_retry(self):
        """Получение соединения с повторными попытками"""
        for attempt in range(self.max_retries):
            try:
                conn = self._get_connection()
                yield conn
                return
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                if attempt == self.max_retries - 1:
                    raise
                self.logger.warning(
                    f"⚠️ Попытка подключения {attempt + 1} не удалась: {e}. Повтор через {self.retry_delay}с...")
                time.sleep(self.retry_delay)

    def _execute_query_with_retry(self, query, params=None, fetch=True):
        """Выполнение запроса с повторными попытками"""
        for attempt in range(self.max_retries):
            try:
                return self._execute_query(query, params, fetch)
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                if attempt == self.max_retries - 1:
                    raise
                self.logger.warning(
                    f"⚠️ Попытка запроса {attempt + 1} не удалась: {e}. Повтор через {self.retry_delay}с...")
                time.sleep(self.retry_delay)

    def _get_postgresql_init_script(self):
        """Возвращает SQL-скрипт для инициализации PostgreSQL"""
        return """
        -- Создаем расширение для UUID если нужно
        CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

        -- Таблица позиций
        CREATE TABLE IF NOT EXISTS positions (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            side VARCHAR(10) NOT NULL,
            size DECIMAL(20, 8) NOT NULL,
            entry_price DECIMAL(20, 8) NOT NULL,
            current_price DECIMAL(20, 8) NOT NULL,
            stop_loss DECIMAL(20, 8),
            take_profit DECIMAL(20, 8),
            leverage INTEGER DEFAULT 10,
            status VARCHAR(20) DEFAULT 'open',
            pnl DECIMAL(20, 8) DEFAULT 0,
            pnl_percent DECIMAL(10, 4) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Таблица ордеров
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            position_id INTEGER REFERENCES positions(id),
            order_type VARCHAR(20) NOT NULL,
            side VARCHAR(10) NOT NULL,
            quantity DECIMAL(20, 8) NOT NULL,
            price DECIMAL(20, 8),
            status VARCHAR(20) DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Таблица настроек
        CREATE TABLE IF NOT EXISTS settings (
            key VARCHAR(100) PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Таблица разрешенных пользователей
        CREATE TABLE IF NOT EXISTS allowed_users (
            user_id BIGINT PRIMARY KEY,
            username VARCHAR(100),
            is_admin BOOLEAN DEFAULT FALSE,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Таблица истории баланса
        CREATE TABLE IF NOT EXISTS balance_history (
            id SERIAL PRIMARY KEY,
            total_equity DECIMAL(20, 8) NOT NULL,
            total_available DECIMAL(20, 8) NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Таблица логов торговли с расширенными полями
        CREATE TABLE IF NOT EXISTS trade_logs (
            id SERIAL PRIMARY KEY,
            level VARCHAR(20) NOT NULL,
            message TEXT NOT NULL,
            symbol VARCHAR(20),
            position_id INTEGER,
            signal_data JSONB,
            confidence DECIMAL(5,4),
            trade_action VARCHAR(50),
            response_time DECIMAL(10,4),
            error_details TEXT,
            pnl DECIMAL(20, 8),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Индексы для улучшения производительности
        CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
        CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
        CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
        CREATE INDEX IF NOT EXISTS idx_balance_history_timestamp ON balance_history(timestamp);
        CREATE INDEX IF NOT EXISTS idx_trade_logs_created_at ON trade_logs(created_at);
        CREATE INDEX IF NOT EXISTS idx_trade_logs_level ON trade_logs(level);
        CREATE INDEX IF NOT EXISTS idx_trade_logs_trade_action ON trade_logs(trade_action);

        -- Начальные настройки
        INSERT INTO settings (key, value) VALUES 
        ('symbol', 'ETHUSDT'),
        ('leverage', '10')
        ON CONFLICT (key) DO NOTHING;
        """

    def _execute_sql_script(self, sql_script):
        """Выполнение SQL скрипта"""
        try:
            # Разделяем скрипт на отдельные команды
            commands = []
            current_command = ""

            for line in sql_script.split('\n'):
                line = line.strip()
                # Пропускаем комментарии и пустые строки
                if line.startswith('--') or not line:
                    continue

                current_command += ' ' + line
                if line.endswith(';'):
                    commands.append(current_command.strip())
                    current_command = ""

            # Выполняем каждую команду отдельно
            for command in commands:
                if command:
                    self._execute_query(command, fetch=False)

            self.logger.info("✅ SQL-скрипт выполнен успешно")
        except Exception as e:
            self.logger.error(f"❌ Ошибка выполнения SQL-скрипта: {e}")
            raise

    def _init_postgresql(self):
        """Инициализация PostgreSQL - создание таблиц если их нет"""
        try:
            # Проверяем существование основной таблицы
            check_query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'positions'
            );
            """
            result = self._execute_query(check_query)

            if not result or not result[0]['exists']:
                self.logger.info(
                    "🔄 Таблицы не найдены, создаем структуру БД...")
                sql_script = self._get_postgresql_init_script()
                self._execute_sql_script(sql_script)
                self.logger.info("✅ Структура БД создана успешно")
            else:
                self.logger.info("✅ Таблицы PostgreSQL уже существуют")

            add_admin_query = """
            INSERT INTO allowed_users (user_id, username, is_admin) 
            VALUES (86157241, 'admin', TRUE)
            ON CONFLICT (user_id) DO UPDATE SET 
                username = EXCLUDED.username,
                is_admin = EXCLUDED.is_admin
            """
            self._execute_query(add_admin_query, fetch=False)
        except Exception as e:
            self.logger.error(f"❌ Ошибка инициализации PostgreSQL: {e}")
            raise

    def _init_sqlite(self):
        """Инициализация SQLite"""
        queries = [
            '''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                size REAL NOT NULL,
                entry_price REAL NOT NULL,
                current_price REAL NOT NULL,
                stop_loss REAL,
                take_profit REAL,
                leverage INTEGER DEFAULT 10,
                status TEXT DEFAULT 'open',
                pnl REAL DEFAULT 0,
                pnl_percent REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id INTEGER,
                order_type TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL,
                status TEXT DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (position_id) REFERENCES positions (id)
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS allowed_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS balance_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_equity REAL NOT NULL,
                total_available REAL NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS trade_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                symbol TEXT,
                position_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''',
            '''
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('symbol', 'ETHUSDT'), ('leverage', '10')
            '''
        ]

        for query in queries:
            self._execute_query(query, fetch=False)

    # Остальные методы остаются без изменений...
    def _init_db(self):
        """Инициализация базы данных"""
        try:
            if self.db_type == 'postgresql':
                self._init_postgresql()
            else:
                self._init_sqlite()
            self.logger.info("✅ База данных инициализирована")

            # Создаем таблицу для виртуальных позиций
            self._create_virtual_positions_table()
            
            # Создаем таблицу для исторических данных (кеш)
            self._create_historical_klines_table()
        except Exception as e:
            self.logger.error(f"❌ Ошибка инициализации БД: {e}")
            raise

    def get_trade_stats(self, days: int = 7) -> Dict:
        """Получение статистики торгов за период"""
        try:
            if self.db_type == 'postgresql':
                query = """
                SELECT
                    COUNT(*) as total_trades,
                    COUNT(CASE WHEN status = 'closed' THEN 1 END) as closed_trades,
                    COUNT(CASE WHEN status = 'open' THEN 1 END) as open_trades,
                    COALESCE(SUM(CASE WHEN status = 'closed' THEN pnl END), 0) as total_pnl,
                    AVG(CASE WHEN status = 'closed' THEN pnl_percent END) as avg_pnl_percent,
                    COUNT(CASE WHEN status = 'closed' AND pnl > 0 THEN 1 END) as winning_trades,
                    COUNT(CASE WHEN status = 'closed' AND pnl < 0 THEN 1 END) as losing_trades
                FROM positions
                WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '1 day' * %s
                """
            else:
                query = """
                SELECT
                    COUNT(*) as total_trades,
                    COUNT(CASE WHEN status = 'closed' THEN 1 END) as closed_trades,
                    COUNT(CASE WHEN status = 'open' THEN 1 END) as open_trades,
                    COALESCE(SUM(CASE WHEN status = 'closed' THEN pnl END), 0) as total_pnl,
                    AVG(CASE WHEN status = 'closed' THEN pnl_percent END) as avg_pnl_percent,
                    COUNT(CASE WHEN status = 'closed' AND pnl > 0 THEN 1 END) as winning_trades,
                    COUNT(CASE WHEN status = 'closed' AND pnl < 0 THEN 1 END) as losing_trades
                FROM positions
                WHERE created_at >= datetime('now', '-' || ? || ' days')
                """

            result = self._execute_query_with_retry(query, (days,))
            return self._convert_row(result[0]) if result else {}
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения статистики: {e}")
            return {}

    def log_trade_event(self, level: str, message: str, symbol: str | None = None,
                        position_id: int | None = None, signal_data: Dict | None = None,
                        confidence: float | None = None, trade_action: str | None = None,
                        response_time: float | None = None, error_details: str | None = None,
                        pnl: float | None = None):
        """Логирование торговых событий в БД с расширенной информацией"""
        try:
            if self.db_type == 'postgresql':
                query = """
                INSERT INTO trade_logs (level, message, symbol, position_id, signal_data, confidence, trade_action, response_time, error_details, pnl)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
            else:
                query = """
                INSERT INTO trade_logs (level, message, symbol, position_id, signal_data, confidence, trade_action, response_time, error_details, pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

            # Подготавливаем данные для вставки
            import json
            signal_data_json = json.dumps(signal_data) if signal_data else None

            params = (
                level, message, symbol, position_id, signal_data_json,
                confidence, trade_action, response_time, error_details, pnl
            )

            self._execute_query_with_retry(query, params, fetch=False)

        except Exception as e:
            self.logger.error(f"❌ Ошибка логирования в БД: {e}")

    def _get_sqlite_path(self):
        """Получение пути для SQLite"""
        possible_paths = [
            "/workspaces/crypto-trading-bot/data/trading_bot.db",
            "/app/data/trading_bot.db",
            "./data/trading_bot.db",
            "trading_bot.db"
        ]

        for path in possible_paths:
            db_dir = os.path.dirname(path)
            if os.path.exists(db_dir) or db_dir == '':
                if db_dir and not os.path.exists(db_dir):
                    os.makedirs(db_dir, exist_ok=True)
                return path
        return "trading_bot.db"

    def _get_connection(self):
        """Получение соединения с БД"""
        try:
            if self.db_type == 'postgresql':
                conn = psycopg2.connect(**self.db_config)
                conn.autocommit = False
                return conn
            else:
                import sqlite3
                return sqlite3.connect(self.db_config)
        except Exception as e:
            self.logger.error(f"❌ Ошибка подключения к БД: {e}")
            raise

    @contextmanager
    def transaction(self):
        """Context manager для атомарных транзакций.
        
        Использование:
            with self.db.transaction() as conn:
                # операции с БД
                # при ошибке - автоматический rollback
                # при успехе - автоматический commit
        """
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
            self.logger.debug("✅ Транзакция успешно завершена")
        except Exception as e:
            conn.rollback()
            self.logger.error(f"❌ Транзакция откачена: {e}")
            raise
        finally:
            conn.close()

    def _convert_decimal_to_float(self, value: Any) -> Any:
        """Конвертирует Decimal в float для удобства работы в Python"""
        if isinstance(value, Decimal):
            return float(value)
        return value

    def _convert_row(self, row: Dict) -> Dict:
        """Конвертирует все Decimal значения в словаре в float"""
        if not row:
            return row
        return {key: self._convert_decimal_to_float(value) for key, value in row.items()}

    def _convert_rows(self, rows: List[Dict]) -> List[Dict]:
        """Конвертирует все Decimal значения в списке словарей в float"""
        if not rows:
            return rows
        return [self._convert_row(row) for row in rows]

    def _execute_query(self, query, params=None, fetch=True):
        """Универсальный метод выполнения запросов"""
        conn = None
        try:
            conn = self._get_connection()

            if self.db_type == 'postgresql':
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query, params)
                    if fetch and query.strip().upper().startswith('SELECT'):
                        result = cursor.fetchall()
                        return [dict(row) for row in result]
                    elif fetch and query.strip().upper().startswith('INSERT'):
                        if 'RETURNING' in query.upper():
                            result = cursor.fetchone()
                            return dict(result) if result else None
                    conn.commit()
                    return None
            else:
                # SQLite
                cursor = conn.cursor()
                cursor.execute(query, params or [])
                if fetch and query.strip().upper().startswith('SELECT'):
                    columns = [col[0] for col in cursor.description]
                    return [dict(zip(columns, row)) for row in cursor.fetchall()]
                elif fetch and query.strip().upper().startswith('INSERT'):
                    if 'RETURNING' in query.upper():
                        # SQLite doesn't support RETURNING, use lastrowid
                        return {'id': cursor.lastrowid}
                conn.commit()
                return None

        except Exception as e:
            if conn:
                conn.rollback()
            self.logger.error(f"❌ Ошибка выполнения запроса: {e}")
            raise
        finally:
            if conn:
                conn.close()

    # Остальные методы работы с позициями и настройками...
    def add_position(self, symbol: str, side: str, size: float, entry_price: float,
                     leverage: int = 10, stop_loss: float | None = None, take_profit: float | None = None) -> int:
        """Добавление новой позиции"""
        if self.db_type == 'postgresql':
            query = """
            INSERT INTO positions (symbol, side, size, entry_price, current_price, leverage, stop_loss, take_profit)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """
        else:
            query = """
            INSERT INTO positions (symbol, side, size, entry_price, current_price, leverage, stop_loss, take_profit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """

        params = (symbol, side, size, entry_price, entry_price,
                  leverage, stop_loss, take_profit)
        result = self._execute_query(query, params, fetch=True)

        position_id = result['id'] if result else None
        if not position_id and self.db_type == 'sqlite':
            # Для SQLite получаем lastrowid
            position_id = self._execute_query(
                "SELECT last_insert_rowid() as id")[0]['id']

        self.logger.info(
            f"✅ Позиция #{position_id} добавлена: {side} {size} {symbol}")
        if not position_id:
            return 0
        return position_id

    def get_open_positions(self) -> List[Dict]:
        """Получение всех открытых позиций"""
        query = "SELECT * FROM positions WHERE status = 'open' ORDER BY created_at DESC"
        result = self._execute_query(query)
        return self._convert_rows(result) if result else []

    def update_position_price(self, position_id: int, current_price: float):
        """Обновление текущей цены позиции и расчет PnL"""
        # Сначала получаем данные позиции
        position = self.get_position(position_id)
        if not position:
            return

        side = position['side']
        size = position['size']
        entry_price = position['entry_price']

        # Расчет PnL
        if side == 'BUY':
            pnl = (current_price - entry_price) * size
            pnl_percent = ((current_price - entry_price) / entry_price) * 100
        else:  # SELL
            pnl = (entry_price - current_price) * size
            pnl_percent = ((entry_price - current_price) / entry_price) * 100

        # Обновляем позицию
        if self.db_type == 'postgresql':
            query = """
            UPDATE positions
            SET current_price = %s, pnl = %s, pnl_percent = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """
        else:
            query = """
            UPDATE positions
            SET current_price = ?, pnl = ?, pnl_percent = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """

        params = (current_price, pnl, pnl_percent, position_id)
        self._execute_query(query, params, fetch=False)

    def close_position(self, position_id: int, exit_price: float):
        """Закрытие позиции"""
        position = self.get_position(position_id)
        if not position:
            return

        side = position['side']
        size = position['size']
        entry_price = position['entry_price']

        # Расчет финального PnL
        if side == 'BUY':
            pnl = (exit_price - entry_price) * size
            pnl_percent = ((exit_price - entry_price) / entry_price) * 100
        else:  # SELL
            pnl = (entry_price - exit_price) * size
            pnl_percent = ((entry_price - exit_price) / entry_price) * 100

        if self.db_type == 'postgresql':
            query = """
            UPDATE positions
            SET status = 'closed', current_price = %s, pnl = %s, pnl_percent = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """
        else:
            query = """
            UPDATE positions
            SET status = 'closed', current_price = ?, pnl = ?, pnl_percent = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """

        params = (exit_price, pnl, pnl_percent, position_id)
        self._execute_query(query, params, fetch=False)
        self.logger.info(
            f"✅ Позиция #{position_id} закрыта. PnL: {pnl:.2f} USDT")

    def get_position(self, position_id: int) -> Optional[Dict]:
        """Получение позиции по ID"""
        if self.db_type == 'postgresql':
            query = "SELECT * FROM positions WHERE id = %s"
        else:
            query = "SELECT * FROM positions WHERE id = ?"

        result = self._execute_query(query, (position_id,))
        return self._convert_row(result[0]) if result else None

    def update_stop_loss(self, position_id: int, stop_loss: float):
        if self.db_type == 'postgresql':
            query = "UPDATE positions SET stop_loss = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s"
        else:
            query = "UPDATE positions SET stop_loss = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        self._execute_query(query, (stop_loss, position_id), fetch=False)

    def update_take_profit(self, position_id: int, take_profit: float):
        if self.db_type == 'postgresql':
            query = "UPDATE positions SET take_profit = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s"
        else:
            query = "UPDATE positions SET take_profit = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        self._execute_query(query, (take_profit, position_id), fetch=False)

    def get_setting(self, key: str, default: str | None = None) -> str:
        if self.db_type == 'postgresql':
            query = "SELECT value FROM settings WHERE key = %s"
        else:
            query = "SELECT value FROM settings WHERE key = ?"

        result = self._execute_query(query, (key,))
        res = result[0]['value'] if result else default
        if not res:
            if default:
                return default
        if res:
            return res
        return ''

    def set_setting(self, key: str, value: str):
        if self.db_type == 'postgresql':
            query = """
            INSERT INTO settings (key, value, updated_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = CURRENT_TIMESTAMP
            """
            params = (key, value, value)
        else:
            query = """
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """
            params = (key, value, value)

        self._execute_query(query, params, fetch=False)

    def add_allowed_user(self, user_id: int, username: str | None = None, is_admin: bool = False):
        """Добавляет пользователя в белый список"""
        params: tuple
        if self.db_type == 'postgresql':
            query = """
            INSERT INTO allowed_users (user_id, username, is_admin)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                username = %s,
                is_admin = %s
            """
            params = (user_id, username, is_admin, username, is_admin)
        else:
            query = """
            INSERT OR REPLACE INTO allowed_users (user_id, username, is_admin)
            VALUES (?, ?, ?)
            """
            params = (user_id, username, is_admin)

        self._execute_query(query, params, fetch=False)

    def is_user_allowed(self, user_id: int) -> bool:
        if self.db_type == 'postgresql':
            query = "SELECT 1 FROM allowed_users WHERE user_id = %s"
        else:
            query = "SELECT 1 FROM allowed_users WHERE user_id = ?"

        result = self._execute_query(query, (user_id,))
        return bool(result)

    def get_all_users(self):
        """Получить список всех пользователей"""
        try:
            if self.db_type == 'postgresql':
                query = "SELECT user_id, username, is_admin FROM allowed_users"
            else:
                query = "SELECT user_id, username, is_admin FROM allowed_users"

            result = self._execute_query(query, fetch=True)
            return result if result else []
        except Exception as e:
            self.logger.error(f"Ошибка получения списка пользователей: {e}")
            return []

    def is_user_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором"""
        try:
            if self.db_type == 'postgresql':
                query = "SELECT is_admin FROM allowed_users WHERE user_id = %s"
            else:
                query = "SELECT is_admin FROM allowed_users WHERE user_id = ?"

            result = self._execute_query(query, (user_id,), fetch=True)
            if result and len(result) > 0:
                return bool(result[0]['is_admin'])
            return False
        except Exception as e:
            self.logger.error(f"Ошибка проверки прав администратора: {e}")
            return False

    def set_user_admin(self, user_id: int, is_admin: bool):
        """Устанавливает права администратора для пользователя"""
        try:
            if self.db_type == 'postgresql':
                query = """
                UPDATE allowed_users
                SET is_admin = %s
                WHERE user_id = %s
                """
            else:
                query = """
                UPDATE allowed_users
                SET is_admin = ?
                WHERE user_id = ?
                """

            params = (is_admin, user_id)
            self._execute_query(query, params, fetch=False)
            return True
        except Exception as e:
            self.logger.error(f"Ошибка установки прав администратора: {e}")
            return False

    def remove_user(self, user_id: int) -> bool:
        """Удаляет пользователя из белого списка"""
        try:
            if self.db_type == 'postgresql':
                query = "DELETE FROM allowed_users WHERE user_id = %s"
            else:
                query = "DELETE FROM allowed_users WHERE user_id = ?"

            self._execute_query(query, (user_id,), fetch=False)
            return True
        except Exception as e:
            self.logger.error(f"Ошибка удаления пользователя: {e}")
            return False

    def _create_virtual_positions_table(self):
        """Создание таблицы для виртуальных позиций"""
        try:
            if self.db_type == 'postgresql':
                query = """
                CREATE TABLE IF NOT EXISTS virtual_positions (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    side VARCHAR(10) NOT NULL,
                    size DECIMAL(20, 8) NOT NULL,
                    entry_price DECIMAL(20, 8) NOT NULL,
                    current_price DECIMAL(20, 8) NOT NULL,
                    exit_price DECIMAL(20, 8),
                    stop_loss DECIMAL(20, 8),
                    take_profit DECIMAL(20, 8),
                    leverage INTEGER DEFAULT 1,
                    status VARCHAR(20) DEFAULT 'open',
                    unrealized_pnl DECIMAL(20, 8) DEFAULT 0,
                    realized_pnl DECIMAL(20, 8) DEFAULT 0,
                    pnl_percent DECIMAL(10, 4) DEFAULT 0,
                    close_reason VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP
                )
                """
            else:
                query = """
                CREATE TABLE IF NOT EXISTS virtual_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    size REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    current_price REAL NOT NULL,
                    exit_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    leverage INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'open',
                    unrealized_pnl REAL DEFAULT 0,
                    realized_pnl REAL DEFAULT 0,
                    pnl_percent REAL DEFAULT 0,
                    close_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP
                )
                """

            self._execute_query(query, fetch=False)
            
            # Создаём индексы для оптимизации запросов
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_virtual_positions_status ON virtual_positions(status)",
                "CREATE INDEX IF NOT EXISTS idx_virtual_positions_symbol ON virtual_positions(symbol)",
                "CREATE INDEX IF NOT EXISTS idx_virtual_positions_created_at ON virtual_positions(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_virtual_positions_symbol_status ON virtual_positions(symbol, status)"
            ]
            
            for index_query in indexes:
                try:
                    self._execute_query(index_query, fetch=False)
                except Exception as idx_err:
                    self.logger.warning(f"⚠️ Индекс уже существует или ошибка: {idx_err}")
            
            self.logger.info("✅ Таблица virtual_positions и индексы созданы/проверены")

        except Exception as e:
            self.logger.error(
                f"❌ Ошибка создания таблицы virtual_positions: {e}")

    def _validate_position_params(self, symbol: str, side: str, size: float, 
                                   entry_price: float, leverage: int = 1,
                                   stop_loss: float | None = None, 
                                   take_profit: float | None = None) -> None:
        """Валидация параметров позиции.
        
        Raises:
            ValueError: если параметры невалидны
        """
        # Валидация side
        if side not in ['BUY', 'SELL']:
            raise ValueError(f"Невалидный side: {side}. Должен быть 'BUY' или 'SELL'")
        
        # Валидация size
        if size <= 0:
            raise ValueError(f"Невалидный size: {size}. Должен быть > 0")
        
        # Валидация entry_price
        if entry_price <= 0:
            raise ValueError(f"Невалидный entry_price: {entry_price}. Должен быть > 0")
        
        # Валидация leverage
        if leverage < 1 or leverage > 125:
            raise ValueError(f"Невалидный leverage: {leverage}. Должен быть от 1 до 125")
        
        # Валидация symbol
        if not symbol or len(symbol) < 3:
            raise ValueError(f"Невалидный symbol: {symbol}. Минимум 3 символа")
        
        # Валидация stop-loss и take-profit относительно entry_price и side
        if side == 'BUY':
            if stop_loss is not None and stop_loss >= entry_price:
                raise ValueError(f"Stop-loss ({stop_loss}) должен быть ниже entry_price ({entry_price}) для BUY")
            if take_profit is not None and take_profit <= entry_price:
                raise ValueError(f"Take-profit ({take_profit}) должен быть выше entry_price ({entry_price}) для BUY")
        else:  # SELL
            if stop_loss is not None and stop_loss <= entry_price:
                raise ValueError(f"Stop-loss ({stop_loss}) должен быть выше entry_price ({entry_price}) для SELL")
            if take_profit is not None and take_profit >= entry_price:
                raise ValueError(f"Take-profit ({take_profit}) должен быть ниже entry_price ({entry_price}) для SELL")

    def add_virtual_position(self, symbol: str, side: str, size: float, entry_price: float,
                             leverage: int = 1, stop_loss: float | None = None,
                             take_profit: float | None = None) -> int:
        """Добавление новой виртуальной позиции с валидацией параметров"""
        try:
            # Валидация входных данных
            self._validate_position_params(symbol, side, size, entry_price, leverage, stop_loss, take_profit)
            if self.db_type == 'postgresql':
                query = """
                INSERT INTO virtual_positions (symbol, side, size, entry_price, current_price, leverage, stop_loss, take_profit)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """
            else:
                query = """
                INSERT INTO virtual_positions (symbol, side, size, entry_price, current_price, leverage, stop_loss, take_profit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """

            params = (symbol, side, size, entry_price, entry_price,
                      leverage, stop_loss, take_profit)
            result = self._execute_query(query, params, fetch=True)

            position_id = result['id'] if result else None
            if not position_id and self.db_type == 'sqlite':
                # Для SQLite получаем lastrowid
                position_id = self._execute_query(
                    "SELECT last_insert_rowid() as id")[0]['id']

            self.logger.info(
                f"✅ Виртуальная позиция #{position_id} добавлена: {side} {size} {symbol}")
            return position_id if position_id else 0

        except Exception as e:
            self.logger.error(f"❌ Ошибка добавления виртуальной позиции: {e}")
            return 0

    def get_virtual_open_positions(self, symbol: str | None = None) -> List[Dict]:
        """Получение всех открытых виртуальных позиций"""
        try:
            if symbol:
                if self.db_type == 'postgresql':
                    query = "SELECT * FROM virtual_positions WHERE status = 'open' AND symbol = %s ORDER BY created_at DESC"
                else:
                    query = "SELECT * FROM virtual_positions WHERE status = 'open' AND symbol = ? ORDER BY created_at DESC"
                result = self._execute_query(query, (symbol,))
            else:
                query = "SELECT * FROM virtual_positions WHERE status = 'open' ORDER BY created_at DESC"
                result = self._execute_query(query)

            return self._convert_rows(result) if result else []
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения виртуальных позиций: {e}")
            return []

    def get_virtual_position(self, position_id: int) -> Optional[Dict]:
        """Получение виртуальной позиции по ID"""
        try:
            if self.db_type == 'postgresql':
                query = "SELECT * FROM virtual_positions WHERE id = %s"
            else:
                query = "SELECT * FROM virtual_positions WHERE id = ?"

            result = self._execute_query(query, (position_id,))
            return self._convert_row(result[0]) if result else None
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения виртуальной позиции: {e}")
            return None

    def update_virtual_position_price(self, position_id: int, current_price: float):
        """Обновление текущей цены виртуальной позиции и расчет PnL"""
        try:
            # Сначала получаем данные позиции
            position = self.get_virtual_position(position_id)
            if not position:
                return

            side = position['side']
            size = position['size']
            entry_price = position['entry_price']

            # Расчет PnL
            if side == 'BUY':
                pnl = (current_price - entry_price) * size
                pnl_percent = ((current_price - entry_price) /
                               entry_price) * 100
            else:  # SELL
                pnl = (entry_price - current_price) * size
                pnl_percent = ((entry_price - current_price) /
                               entry_price) * 100

            # Обновляем позицию
            if self.db_type == 'postgresql':
                query = """
                UPDATE virtual_positions 
                SET current_price = %s, unrealized_pnl = %s, pnl_percent = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """
            else:
                query = """
                UPDATE virtual_positions 
                SET current_price = ?, unrealized_pnl = ?, pnl_percent = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """

            params = (current_price, pnl, pnl_percent, position_id)
            self._execute_query(query, params, fetch=False)

        except Exception as e:
            self.logger.error(f"❌ Ошибка обновления виртуальной позиции: {e}")

    def close_virtual_position(self, position_id: int, exit_price: float, close_reason: str = "manual"):
        """Закрытие виртуальной позиции"""
        try:
            position = self.get_virtual_position(position_id)
            if not position:
                return

            side = position['side']
            size = position['size']
            entry_price = position['entry_price']

            # Расчет финального PnL
            if side == 'BUY':
                pnl = (exit_price - entry_price) * size
                pnl_percent = ((exit_price - entry_price) / entry_price) * 100
            else:  # SELL
                pnl = (entry_price - exit_price) * size
                pnl_percent = ((entry_price - exit_price) / entry_price) * 100

            if self.db_type == 'postgresql':
                query = """
                UPDATE virtual_positions 
                SET status = 'closed', exit_price = %s, realized_pnl = %s, pnl_percent = %s, 
                    close_reason = %s, closed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """
            else:
                query = """
                UPDATE virtual_positions 
                SET status = 'closed', exit_price = ?, realized_pnl = ?, pnl_percent = ?, 
                    close_reason = ?, closed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """

            params = (exit_price, pnl, pnl_percent, close_reason, position_id)
            self._execute_query(query, params, fetch=False)
            self.logger.info(
                f"✅ Виртуальная позиция #{position_id} закрыта. PnL: {pnl:.2f} USDT")

        except Exception as e:
            self.logger.error(f"❌ Ошибка закрытия виртуальной позиции: {e}")

    def get_virtual_trade_stats(self, days: int = 30) -> Dict:
        """Получение статистики виртуальной торговли"""
        try:
            if self.db_type == 'postgresql':
                query = """
                SELECT 
                    COUNT(*) as total_trades,
                    COUNT(CASE WHEN status = 'closed' THEN 1 END) as closed_trades,
                    COUNT(CASE WHEN status = 'open' THEN 1 END) as open_trades,
                    COALESCE(SUM(realized_pnl), 0) as total_realized_pnl,
                    COALESCE(SUM(unrealized_pnl), 0) as total_unrealized_pnl,
                    AVG(CASE WHEN status = 'closed' THEN pnl_percent END) as avg_pnl_percent,
                    COUNT(CASE WHEN status = 'closed' AND realized_pnl > 0 THEN 1 END) as winning_trades,
                    COUNT(CASE WHEN status = 'closed' AND realized_pnl < 0 THEN 1 END) as losing_trades
                FROM virtual_positions 
                WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '1 day' * %s
                """
            else:
                query = """
                SELECT 
                    COUNT(*) as total_trades,
                    COUNT(CASE WHEN status = 'closed' THEN 1 END) as closed_trades,
                    COUNT(CASE WHEN status = 'open' THEN 1 END) as open_trades,
                    COALESCE(SUM(realized_pnl), 0) as total_realized_pnl,
                    COALESCE(SUM(unrealized_pnl), 0) as total_unrealized_pnl,
                    AVG(CASE WHEN status = 'closed' THEN pnl_percent END) as avg_pnl_percent,
                    COUNT(CASE WHEN status = 'closed' AND realized_pnl > 0 THEN 1 END) as winning_trades,
                    COUNT(CASE WHEN status = 'closed' AND realized_pnl < 0 THEN 1 END) as losing_trades
                FROM virtual_positions 
                WHERE created_at >= datetime('now', '-' || ? || ' days')
                """

            result = self._execute_query(query, (days,))
            return self._convert_row(result[0]) if result else {}
        except Exception as e:
            self.logger.error(
                f"❌ Ошибка получения статистики виртуальной торговли: {e}")
            return {}

    def _create_historical_klines_table(self):
        """Создание таблицы для кеширования исторических данных"""
        try:
            if self.db_type == 'postgresql':
                query = """
                CREATE TABLE IF NOT EXISTS historical_klines (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    interval VARCHAR(10) NOT NULL,
                    timestamp BIGINT NOT NULL,
                    open_price DECIMAL(20, 8) NOT NULL,
                    high_price DECIMAL(20, 8) NOT NULL,
                    low_price DECIMAL(20, 8) NOT NULL,
                    close_price DECIMAL(20, 8) NOT NULL,
                    volume DECIMAL(30, 8) NOT NULL,
                    turnover DECIMAL(30, 8) DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, interval, timestamp)
                )
                """
            else:
                query = """
                CREATE TABLE IF NOT EXISTS historical_klines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    open_price REAL NOT NULL,
                    high_price REAL NOT NULL,
                    low_price REAL NOT NULL,
                    close_price REAL NOT NULL,
                    volume REAL NOT NULL,
                    turnover REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, interval, timestamp)
                )
                """
            
            self._execute_query(query, fetch=False)
            
            # Создаём индексы для быстрого поиска
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_historical_klines_symbol ON historical_klines(symbol)",
                "CREATE INDEX IF NOT EXISTS idx_historical_klines_interval ON historical_klines(interval)",
                "CREATE INDEX IF NOT EXISTS idx_historical_klines_timestamp ON historical_klines(timestamp)",
                "CREATE INDEX IF NOT EXISTS idx_historical_klines_symbol_interval_timestamp ON historical_klines(symbol, interval, timestamp)"
            ]
            
            for index_query in indexes:
                try:
                    self._execute_query(index_query, fetch=False)
                except Exception as idx_err:
                    self.logger.warning(f"⚠️ Индекс уже существует или ошибка: {idx_err}")
            
            self.logger.info("✅ Таблица historical_klines и индексы созданы/проверены")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка создания таблицы historical_klines: {e}")

    def save_historical_klines(self, symbol: str, interval: str, klines: List[Dict]) -> int:
        """
        Сохраняет исторические свечи в БД (кеш).
        
        Args:
            symbol: Торговая пара
            interval: Таймфрейм
            klines: Список свечей
            
        Returns:
            int: Количество сохранённых свечей
        """
        try:
            saved_count = 0
            
            for kline in klines:
                try:
                    if self.db_type == 'postgresql':
                        query = """
                        INSERT INTO historical_klines 
                        (symbol, interval, timestamp, open_price, high_price, low_price, close_price, volume, turnover)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, interval, timestamp) DO UPDATE SET
                            open_price = EXCLUDED.open_price,
                            high_price = EXCLUDED.high_price,
                            low_price = EXCLUDED.low_price,
                            close_price = EXCLUDED.close_price,
                            volume = EXCLUDED.volume,
                            turnover = EXCLUDED.turnover
                        """
                    else:
                        query = """
                        INSERT OR REPLACE INTO historical_klines 
                        (symbol, interval, timestamp, open_price, high_price, low_price, close_price, volume, turnover)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """
                    
                    params = (
                        symbol,
                        interval,
                        kline['timestamp'],
                        kline['open'],
                        kline['high'],
                        kline['low'],
                        kline['close'],
                        kline['volume'],
                        kline.get('turnover', 0)
                    )
                    
                    self._execute_query(query, params, fetch=False)
                    saved_count += 1
                    
                except Exception as e:
                    self.logger.warning(f"⚠️ Ошибка сохранения свечи {kline.get('timestamp')}: {e}")
                    continue
            
            self.logger.info(f"✅ Сохранено {saved_count}/{len(klines)} свечей для {symbol} ({interval})")
            return saved_count
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка сохранения исторических данных: {e}")
            return 0

    def get_historical_klines_from_cache(self, symbol: str, interval: str, 
                                         start_timestamp: int | None = None,
                                         end_timestamp: int | None = None,
                                         limit: int | None = None) -> List[Dict]:
        """
        Загружает исторические свечи из кеша БД.
        
        Args:
            symbol: Торговая пара
            interval: Таймфрейм
            start_timestamp: Начальная временная метка в миллисекундах
            end_timestamp: Конечная временная метка в миллисекундах
            limit: Максимальное количество свечей
            
        Returns:
            List[Dict]: Список свечей
        """
        try:
            query = """
            SELECT timestamp, open_price, high_price, low_price, close_price, volume, turnover
            FROM historical_klines
            WHERE symbol = {} AND interval = {}
            """.format(
                '%s' if self.db_type == 'postgresql' else '?',
                '%s' if self.db_type == 'postgresql' else '?'
            )
            
            params = [symbol, interval]
            
            if start_timestamp is not None:
                query += f" AND timestamp >= {'%s' if self.db_type == 'postgresql' else '?'}"
                params.append(start_timestamp)
            
            if end_timestamp is not None:
                query += f" AND timestamp <= {'%s' if self.db_type == 'postgresql' else '?'}"
                params.append(end_timestamp)
            
            query += " ORDER BY timestamp ASC"
            
            if limit is not None:
                query += f" LIMIT {'%s' if self.db_type == 'postgresql' else '?'}"
                params.append(limit)
            
            result = self._execute_query(query, tuple(params))
            
            if not result:
                return []
            
            # Преобразуем в формат, совместимый с Bybit API
            klines = []
            for row in result:
                klines.append({
                    'timestamp': int(row['timestamp']),
                    'open': float(row['open_price']),
                    'high': float(row['high_price']),
                    'low': float(row['low_price']),
                    'close': float(row['close_price']),
                    'volume': float(row['volume']),
                    'turnover': float(row.get('turnover', 0)),
                    'datetime': datetime.fromtimestamp(int(row['timestamp']) / 1000).isoformat()
                })
            
            self.logger.info(f"✅ Загружено {len(klines)} свечей из кеша для {symbol} ({interval})")
            return klines
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка загрузки данных из кеша: {e}")
            return []

    def check_cache_coverage(self, symbol: str, interval: str, 
                            start_timestamp: int, end_timestamp: int) -> Dict:
        """
        Проверяет наличие данных в кеше для указанного периода.
        
        Returns:
            Dict: {
                'has_data': bool,
                'cached_count': int,
                'first_timestamp': int,
                'last_timestamp': int,
                'missing_ranges': List[tuple]
            }
        """
        try:
            if self.db_type == 'postgresql':
                query = """
                SELECT 
                    COUNT(*) as cached_count,
                    MIN(timestamp) as first_timestamp,
                    MAX(timestamp) as last_timestamp
                FROM historical_klines
                WHERE symbol = %s AND interval = %s 
                AND timestamp >= %s AND timestamp <= %s
                """
            else:
                query = """
                SELECT 
                    COUNT(*) as cached_count,
                    MIN(timestamp) as first_timestamp,
                    MAX(timestamp) as last_timestamp
                FROM historical_klines
                WHERE symbol = ? AND interval = ? 
                AND timestamp >= ? AND timestamp <= ?
                """
            
            params = (symbol, interval, start_timestamp, end_timestamp)
            result = self._execute_query(query, params)
            
            if result and result[0]['cached_count'] > 0:
                row = result[0]
                return {
                    'has_data': True,
                    'cached_count': int(row['cached_count']),
                    'first_timestamp': int(row['first_timestamp']),
                    'last_timestamp': int(row['last_timestamp']),
                    'coverage_start': start_timestamp,
                    'coverage_end': end_timestamp
                }
            else:
                return {
                    'has_data': False,
                    'cached_count': 0,
                    'first_timestamp': None,
                    'last_timestamp': None,
                    'coverage_start': start_timestamp,
                    'coverage_end': end_timestamp
                }
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка проверки кеша: {e}")
            return {
                'has_data': False,
                'cached_count': 0,
                'error': str(e)
            }

    def clear_historical_cache(self, symbol: str | None = None, 
                              interval: str | None = None,
                              older_than_days: int | None = None) -> int:
        """
        Очищает кеш исторических данных.
        
        Args:
            symbol: Очистить данные для конкретного символа (если None - все)
            interval: Очистить данные для конкретного интервала (если None - все)
            older_than_days: Очистить данные старше N дней
            
        Returns:
            int: Количество удалённых записей
        """
        try:
            query = "DELETE FROM historical_klines WHERE 1=1"
            params = []
            
            if symbol:
                query += f" AND symbol = {'%s' if self.db_type == 'postgresql' else '?'}"
                params.append(symbol)
            
            if interval:
                query += f" AND interval = {'%s' if self.db_type == 'postgresql' else '?'}"
                params.append(interval)
            
            if older_than_days:
                if self.db_type == 'postgresql':
                    query += " AND created_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * %s"
                else:
                    query += " AND created_at < datetime('now', '-' || ? || ' days')"
                params.append(older_than_days)
            
            # Получаем количество записей перед удалением
            count_query = query.replace("DELETE", "SELECT COUNT(*)")
            count_result = self._execute_query(count_query, tuple(params) if params else None)
            deleted_count = count_result[0]['count'] if count_result else 0
            
            # Удаляем
            self._execute_query(query, tuple(params) if params else None, fetch=False)
            
            self.logger.info(f"✅ Удалено {deleted_count} записей из кеша")
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка очистки кеша: {e}")
            return 0
