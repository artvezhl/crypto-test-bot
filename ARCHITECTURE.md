# 🏗️ Архитектура проекта

Этот документ описывает архитектурные решения и структуру криптовалютного торгового бота.

## 📊 Общая архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                          USER INTERFACE                          │
│                        (Telegram Bot)                            │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│                     TRADING BOT LAYER                            │
│  ┌──────────────────────┐      ┌──────────────────────┐        │
│  │  Virtual Trading Bot │      │   Real Trading Bot   │        │
│  │  (virtual_trading_   │      │  (trading_strategy.  │        │
│  │        bot.py)       │      │         py)          │        │
│  └──────────┬───────────┘      └──────────┬───────────┘        │
└─────────────┼──────────────────────────────┼───────────────────┘
              │                              │
              ↓                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      SERVICES LAYER                              │
│  ┌────────────┐  ┌──────────────┐  ┌────────────────────┐      │
│  │  DeepSeek  │  │    Bybit     │  │     Database       │      │
│  │   Client   │  │   Client     │  │     Service        │      │
│  │(deepseek_  │  │  (bybit_     │  │   (database.py)    │      │
│  │client.py)  │  │  client.py)  │  │                    │      │
│  └─────┬──────┘  └──────┬───────┘  └─────────┬──────────┘      │
└────────┼─────────────────┼────────────────────┼─────────────────┘
         │                 │                    │
         ↓                 ↓                    ↓
┌─────────────────────────────────────────────────────────────────┐
│                    EXTERNAL SERVICES                             │
│  ┌────────────┐  ┌──────────────┐  ┌────────────────────┐      │
│  │ DeepSeek   │  │   Bybit      │  │   PostgreSQL /     │      │
│  │    API     │  │    API       │  │     SQLite         │      │
│  └────────────┘  └──────────────┘  └────────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

## 🗂️ Структура проекта

```
crypto-trading-bot/
├── src/                          # Исходный код
│   ├── config/                   # Конфигурация
│   │   └── __init__.py          # Config класс
│   ├── bybit_client.py          # Клиент Bybit API
│   ├── deepseek_client.py       # Клиент DeepSeek AI
│   ├── database.py              # Работа с БД
│   ├── telegram_bot.py          # Telegram интерфейс
│   ├── virtual_trading_bot.py   # Виртуальная торговля
│   ├── trading_strategy.py      # Реальная торговля
│   └── main.py                  # Точка входа
│
├── tests/                        # Тесты
│   ├── test_basic.py
│   ├── test_components.py
│   └── test_connection.py
│
├── data/                         # Данные и БД
│   └── trading_bot.db           # SQLite база
│
├── logs/                         # Логи
│   └── trading_bot.log
│
├── backups/                      # Бэкапы БД
│
├── .github/                      # GitHub настройки
│   └── workflows/
│       └── deploy.yml           # CI/CD pipeline
│
├── docker-compose.yml            # Dev окружение
├── docker-compose.prod.yml       # Prod окружение
├── Dockerfile                    # Образ для production
├── requirements.txt              # Python зависимости
│
├── README.md                     # Документация
├── CHANGELOG.md                  # История изменений
├── TASKS.md                      # План работ
├── ARCHITECTURE.md               # Этот файл
└── CONTRIBUTING.md               # Руководство для контрибьюторов
```

## 🔧 Компоненты системы

### 1. VirtualTradingBot (`virtual_trading_bot.py`)

**Назначение:** Виртуальная торговля для тестирования стратегий без риска.

**Основные методы:**
- `run_iteration()` - один цикл торговли
- `_process_symbol()` - обработка одного торгового символа
- `_execute_virtual_buy()` - открытие виртуальной длинной позиции
- `_execute_virtual_sell()` - открытие виртуальной короткой позиции
- `_close_virtual_position()` - закрытие позиции
- `_update_virtual_balance()` - обновление баланса
- `get_virtual_stats()` - получение статистики

**Зависимости:**
- Database (хранение позиций)
- DeepSeekClient (AI сигналы)
- BybitClient (рыночные данные)

**Текущие проблемы:**
- ❌ Использует `self.virtual_positions` вместо БД
- ❌ Дублирование данных
- ❌ Некорректная проверка позиций

### 2. Database (`database.py`)

**Назначение:** Управление данными в PostgreSQL/SQLite.

**Таблицы:**
```sql
-- Реальные позиции
positions (id, symbol, side, size, entry_price, current_price, 
           stop_loss, take_profit, leverage, status, pnl, 
           created_at, updated_at)

-- Виртуальные позиции
virtual_positions (id, symbol, side, size, entry_price, current_price,
                   exit_price, stop_loss, take_profit, leverage, status,
                   unrealized_pnl, realized_pnl, pnl_percent, close_reason,
                   created_at, updated_at, closed_at)

-- Настройки
settings (key, value, updated_at)

-- Пользователи
allowed_users (user_id, username, is_admin, added_at)

-- История баланса
balance_history (id, total_equity, total_available, timestamp)

-- Логи торговли
trade_logs (id, level, message, symbol, position_id, signal_data,
            confidence, trade_action, response_time, error_details,
            pnl, created_at)
```

**Основные методы:**
- `add_virtual_position()` - создание позиции
- `get_virtual_open_positions()` - получение открытых позиций
- `update_virtual_position_price()` - обновление цены и PnL
- `close_virtual_position()` - закрытие позиции
- `get_virtual_trade_stats()` - статистика торговли
- `get_setting()` / `set_setting()` - управление настройками

**Текущие проблемы:**
- ❌ Нет индексов на virtual_positions
- ❌ Нет транзакционности
- ❌ SQL Injection риск в INTERVAL
- ❌ Нет валидации входных данных

### 3. BybitClient (`bybit_client.py`)

**Назначение:** Интеграция с Bybit API.

**Основные методы:**
- `get_market_data()` - получение рыночных данных
- `place_order()` - размещение ордера
- `get_positions()` - получение позиций
- `close_position()` - закрытие позиции
- `get_wallet_balance()` - получение баланса
- `start_websocket()` - WebSocket для real-time данных

**API категории:**
- `linear` - Perpetual контракты (основное)
- `spot` - Спотовая торговля
- `option` - Опционы

**Текущие проблемы:**
- ❌ WebSocket keep_alive может создавать утечку памяти
- ⚠️ Нет retry логики для API запросов

### 4. DeepSeekClient (`deepseek_client.py`)

**Назначение:** AI анализ рынка через DeepSeek API.

**Основные методы:**
- `get_trading_signal()` - получение торгового сигнала
- `_build_market_analysis_prompt()` - построение промпта
- `_parse_ai_response()` - парсинг ответа AI

**Формат сигнала:**
```python
{
    'action': 'BUY' | 'SELL' | 'HOLD',
    'confidence': 0.0 - 1.0,
    'reason': 'текстовое объяснение',
    'symbol': 'BTCUSDT'
}
```

**Настройки:**
- `model` - модель DeepSeek (deepseek-reasoner)
- `max_tokens` - максимум токенов
- `temperature` - креативность (0-2)

### 5. TelegramBot (`telegram_bot.py`)

**Назначение:** Интерфейс управления через Telegram.

**Команды:**
- `/start` - запуск бота
- `/status` - текущий статус
- `/balance` - баланс и статистика
- `/positions` - открытые позиции
- `/stats` - детальная статистика
- `/settings` - просмотр настроек
- `/set <key> <value>` - изменение настройки

**Безопасность:**
- Whitelist пользователей в БД
- Admin права для критических команд
- Валидация входных данных

## 🔄 Поток данных

### Виртуальная торговля (текущая реализация)

```
1. Timer (каждые N минут)
   ↓
2. VirtualTradingBot.run_iteration()
   ↓
3. Для каждого символа:
   ↓
4. BybitClient.get_market_data(symbol)
   ↓
5. DeepSeekClient.get_trading_signal(market_data)
   ↓
6. Если confidence > threshold:
   ↓
7. Database.add_virtual_position(...)
   ↓
8. TelegramBot.send_notification()
   ↓
9. Database.log_trade_event(...)
```

### Проверка позиций

```
1. Получить открытые позиции из БД
   ↓
2. Для каждой позиции:
   ↓
3. Получить текущую цену с Bybit
   ↓
4. Обновить unrealized_pnl в БД
   ↓
5. Проверить stop-loss / take-profit
   ↓
6. Если сработал:
   ↓
7. Database.close_virtual_position(...)
   ↓
8. TelegramBot.send_notification()
```

## 🗃️ Модель данных

### Virtual Position (виртуальная позиция)

```python
{
    'id': int,                      # Уникальный ID
    'symbol': str,                  # Торговая пара (BTCUSDT)
    'side': 'BUY' | 'SELL',        # Направление
    'size': float,                  # Размер в контрактах
    'entry_price': float,           # Цена входа
    'current_price': float,         # Текущая цена
    'exit_price': float | None,     # Цена выхода (если закрыта)
    'stop_loss': float | None,      # Stop-loss уровень
    'take_profit': float | None,    # Take-profit уровень
    'leverage': int,                # Леверидж
    'status': 'open' | 'closed',    # Статус
    'unrealized_pnl': float,        # Нереализованный PnL
    'realized_pnl': float,          # Реализованный PnL (при закрытии)
    'pnl_percent': float,           # PnL в процентах
    'close_reason': str | None,     # Причина закрытия
    'created_at': datetime,         # Время открытия
    'updated_at': datetime,         # Последнее обновление
    'closed_at': datetime | None    # Время закрытия
}
```

### Trading Settings (настройки)

```python
{
    # Торговые настройки
    'trading_symbols': 'ETHUSDT,BTCUSDT,SOLUSDT',
    'default_symbol': 'ETHUSDT',
    'min_confidence': '0.68',
    'leverage': '5',
    
    # Риск-менеджмент
    'risk_percent': '2.0',
    'max_position_percent': '20.0',
    'max_total_position_percent': '30.0',
    'min_trade_usdt': '10.0',
    'stop_loss_percent': '2.0',
    'take_profit_percent': '4.0',
    
    # Трейлинг-стоп
    'trailing_stop_activation_percent': '0.5',
    'trailing_stop_distance_percent': '0.3',
    
    # Баланс
    'initial_balance': '10000.0',
    
    # Поведение
    'allow_short_positions': 'true',
    'allow_long_positions': 'true',
    'auto_position_reversal': 'true',
    
    # DeepSeek
    'deepseek_model': 'deepseek-reasoner',
    'deepseek_max_tokens': '5000',
    'deepseek_temperature': '1',
    
    # Интервал
    'trading_interval_minutes': '15'
}
```

## 🚀 Планируемые архитектурные улучшения

### Краткосрочные (Спринт 1-3)

1. **Удаление дублирования данных**
   - Убрать `self.virtual_positions`
   - Использовать только БД как источник истины

2. **Добавление транзакционности**
   ```python
   with db.transaction():
       db.close_virtual_position(old_id, ...)
       db.add_virtual_position(...)
   ```

3. **Репозиторий паттерн**
   ```python
   class VirtualPositionRepository:
       def get_open_by_symbol(self, symbol: str) -> List[Position]
       def close_position(self, position_id: int, exit_price: float)
   ```

### Среднесрочные (Спринт 4-6)

4. **Event-Driven Architecture**
   ```python
   class EventBus:
       def emit(event: str, data: Dict)
       def on(event: str, handler: Callable)
   
   # Использование:
   events.emit('position.opened', position_data)
   events.on('position.opened', send_telegram_notification)
   events.on('position.opened', log_to_database)
   ```

5. **Strategy Pattern для множественных стратегий**
   ```python
   class TradingStrategy(ABC):
       @abstractmethod
       def get_signal(self, market_data: Dict) -> Signal
   
   class DeepSeekStrategy(TradingStrategy): ...
   class TrendFollowingStrategy(TradingStrategy): ...
   class MeanReversionStrategy(TradingStrategy): ...
   ```

6. **Service Layer**
   ```python
   class TradingService:
       def open_position(self, signal: Signal) -> Position
       def close_position(self, position_id: int) -> Position
       def update_positions(self) -> None
   
   class RiskManagementService:
       def calculate_position_size(self, ...) -> float
       def check_risk_limits(self, ...) -> bool
   ```

### Долгосрочные (Спринт 7+)

7. **Микросервисная архитектура**
   ```
   ┌─────────────┐
   │ API Gateway │
   └──────┬──────┘
          │
          ├────→ Strategy Service (анализ и сигналы)
          ├────→ Trading Service (исполнение)
          ├────→ Risk Service (управление рисками)
          ├────→ Data Service (рыночные данные)
          ├────→ Notification Service (уведомления)
          └────→ Analytics Service (статистика)
   ```

8. **Message Queue для асинхронности**
   ```python
   # RabbitMQ / Redis
   queue.publish('market.data.updated', market_data)
   queue.subscribe('position.check', check_position_handler)
   ```

## 🔒 Безопасность

### Текущие меры

1. **API ключи в environment variables**
2. **Whitelist пользователей Telegram**
3. **Admin права для критических операций**
4. **SQL параметризация (частично)**

### Планируемые улучшения

1. **Secrets management** (HashiCorp Vault)
2. **Rate limiting** на API endpoints
3. **Input sanitization** для всех пользовательских данных
4. **Audit logging** для всех изменений
5. **Encryption at rest** для sensitive данных

## 📈 Масштабируемость

### Текущие ограничения

- Один инстанс бота
- Синхронная обработка символов
- Нет кеширования
- Нет load balancing

### Планы по масштабированию

1. **Horizontal scaling** - несколько инстансов ботов
2. **Асинхронность** - asyncio для параллельной обработки
3. **Кеширование** - Redis для рыночных данных
4. **Database sharding** - по символам/времени
5. **CDN** для web UI

## 🔍 Мониторинг и Observability

### Планируется

1. **Metrics** - Prometheus
   - Количество открытых позиций
   - Успешность сделок
   - Latency API запросов
   - Ошибки и исключения

2. **Logging** - структурированное логирование
   - JSON формат
   - Correlation IDs
   - Log levels

3. **Tracing** - Jaeger для distributed tracing

4. **Alerting** - AlertManager
   - Критические ошибки
   - Аномалии в торговле
   - Проблемы с API

5. **Dashboards** - Grafana
   - Real-time метрики
   - Equity curve
   - Position distribution

---

**Последнее обновление:** 2025-12-06  
**Версия документа:** 1.0

