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
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица истории баланса
CREATE TABLE IF NOT EXISTS balance_history (
    id SERIAL PRIMARY KEY,
    total_equity DECIMAL(20, 8) NOT NULL,
    total_available DECIMAL(20, 8) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица логов торговли
CREATE TABLE IF NOT EXISTS trade_logs (
    id SERIAL PRIMARY KEY,
    level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    symbol VARCHAR(20),
    position_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для улучшения производительности
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_balance_history_timestamp ON balance_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_trade_logs_created_at ON trade_logs(created_at);

-- Начальные настройки
INSERT INTO settings (key, value) VALUES 
('symbol', 'ETHUSDT'),
('leverage', '10')
ON CONFLICT (key) DO NOTHING;