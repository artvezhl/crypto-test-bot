# 🐛 Сводка выявленных проблем

Этот документ содержит детальный анализ всех найденных проблем в коде с рекомендациями по исправлению.

**Дата анализа:** 2025-12-06  
**Версия:** 0.1.0-alpha  
**Проанализированные файлы:** 
- `src/virtual_trading_bot.py`
- `src/database.py`
- `src/bybit_client.py`

---

## 🔴 КРИТИЧЕСКИЕ (требуют немедленного исправления)

### 1. Дублирование данных в памяти и БД

**Приоритет:** 🔴 КРИТИЧЕСКИЙ  
**Файл:** `src/virtual_trading_bot.py`  
**Строки:** 40-44

**Проблема:**
```python
# Строки 40-44
self.virtual_positions = []  # ❌ Инициализируется, но не используется!
self.virtual_trades_count = 0  # ❌ Дублирует данные из БД
self.total_virtual_pnl = 0.0  # ❌ Дублирует данные из БД
```

После миграции на БД эти переменные больше не нужны, но код до сих пор их использует, что приводит к:
- Расхождению данных между памятью и БД
- Ошибкам в логике принятия решений
- Невозможности корректно проверять позиции

**Решение:**
1. Удалить `self.virtual_positions = []`
2. Удалить `self.virtual_trades_count`
3. Удалить `self.total_virtual_pnl`
4. Везде использовать методы БД:
   - `self.db.get_virtual_open_positions()`
   - Брать count из `get_virtual_trade_stats()`
   - Брать PnL из `get_virtual_trade_stats()`

**Затронутые методы:**
- `_update_virtual_positions_prices()` - строки 317-329
- `_check_virtual_position_conditions()` - строки 331-359
- `_execute_virtual_trading_decision()` - строки 381-382
- `get_virtual_positions()` - строка 754

**Влияние:** HIGH - бот не может корректно открывать/закрывать позиции

---

### 2. Метод _update_virtual_positions_prices() не работает

**Приоритет:** 🔴 КРИТИЧЕСКИЙ  
**Файл:** `src/virtual_trading_bot.py`  
**Строки:** 317-329

**Проблема:**
```python
def _update_virtual_positions_prices(self, symbol: str, current_price: float):
    """Обновление цен виртуальных позиций для конкретного символа"""
    for position in self.virtual_positions:  # ❌ self.virtual_positions = []
        if position['symbol'] == symbol and position['status'] == 'open':
            position['current_price'] = current_price
            # ... расчеты, которые никогда не выполняются
```

Метод итерируется по пустому списку, поэтому никогда не обновляет цены позиций.

**Последствия:**
- Цены позиций не обновляются
- PnL не рассчитывается
- Stop-loss и take-profit не срабатывают

**Решение:**
```python
def _update_virtual_positions_prices(self, symbol: str, current_price: float):
    """Обновление цен виртуальных позиций для конкретного символа из БД"""
    open_positions = self.db.get_virtual_open_positions(symbol)
    
    for position in open_positions:
        # Обновляем цену в БД
        self.db.update_virtual_position_price(position['id'], current_price)
        
        self.logger.debug(
            f"Updated position #{position['id']}: {symbol} @ ${current_price:.2f}"
        )
```

**Влияние:** HIGH - позиции не управляются корректно

---

### 3. Метод _check_virtual_position_conditions() не работает

**Приоритет:** 🔴 КРИТИЧЕСКИЙ  
**Файл:** `src/virtual_trading_bot.py`  
**Строки:** 331-359

**Проблема:**
Та же проблема - итерация по пустому `self.virtual_positions`.

```python
def _check_virtual_position_conditions(self, symbol: str, current_price: float):
    for position in self.virtual_positions:  # ❌ Пустой список!
        # Логика проверки никогда не выполняется
```

**Последствия:**
- Stop-loss НЕ срабатывает
- Take-profit НЕ срабатывает
- Позиции остаются открытыми бесконечно

**Решение:**
```python
def _check_virtual_position_conditions(self, symbol: str, current_price: float):
    """Проверка условий для закрытия виртуальных позиций"""
    open_positions = self.db.get_virtual_open_positions(symbol)
    
    for position in open_positions:
        stop_loss = position.get('stop_loss')
        take_profit = position.get('take_profit')
        
        if not (stop_loss and take_profit):
            continue
            
        should_close = False
        close_reason = ""
        
        if position['side'] == 'BUY':
            if current_price <= stop_loss:
                should_close = True
                close_reason = "stop_loss"
            elif current_price >= take_profit:
                should_close = True
                close_reason = "take_profit"
        else:  # SELL
            if current_price >= stop_loss:
                should_close = True
                close_reason = "stop_loss"
            elif current_price <= take_profit:
                should_close = True
                close_reason = "take_profit"
        
        if should_close:
            self._close_virtual_position(position, current_price, close_reason)
```

**Влияние:** HIGH - риск-менеджмент не работает

---

### 4. Проверка открытых позиций всегда возвращает пустой список

**Приоритет:** 🔴 КРИТИЧЕСКИЙ  
**Файл:** `src/virtual_trading_bot.py`  
**Строки:** 381-382

**Проблема:**
```python
def _execute_virtual_trading_decision(self, ...):
    current_positions = [
        p for p in self.virtual_positions  # ❌ Всегда []
        if p['symbol'] == symbol and p['status'] == 'open'
    ]
    has_position = len(current_positions) > 0  # Всегда False!
```

**Последствия:**
- Бот думает, что позиций никогда нет
- Открывает множественные позиции по одному символу
- Auto position reversal не работает

**Решение:**
```python
def _execute_virtual_trading_decision(self, symbol: str, signal: Dict, 
                                      market_data: Dict, position_amount: float):
    """Исполняет виртуальное торговое решение"""
    try:
        # Получаем позиции из БД
        current_positions = self.db.get_virtual_open_positions(symbol)
        has_position = len(current_positions) > 0
        
        signal_action = signal['action']
        
        # ... остальная логика
```

**Влияние:** HIGH - логика торговли сломана

---

### 5. Хардкод минимальной уверенности

**Приоритет:** 🔴 КРИТИЧЕСКИЙ  
**Файл:** `src/virtual_trading_bot.py`  
**Строка:** 313

**Проблема:**
```python
# Исполняем виртуальную сделку если сигнал хороший
if signal['confidence'] > 0.5:  # ❌ Хардкод!
    self._execute_virtual_trading_decision(...)
```

Должно использоваться `self.min_confidence`, которое загружается из БД и может быть изменено пользователем.

**Последствия:**
- Настройка `min_confidence` в БД игнорируется
- Невозможно управлять чувствительностью через Telegram
- Всегда используется порог 0.5 независимо от настроек

**Решение:**
```python
# Исполняем виртуальную сделку если сигнал хороший
if signal['confidence'] > self.min_confidence:
    self._execute_virtual_trading_decision(
        symbol, signal, market_data, position_amount)
```

**Влияние:** MEDIUM - но легко исправить

---

## 🟡 ВАЖНЫЕ (нужно исправить в ближайшее время)

### 6. Отсутствие транзакций в БД

**Приоритет:** 🟡 ВЫСОКИЙ  
**Файл:** `src/database.py`  

**Проблема:**
При операциях типа "закрыть старую позицию и открыть новую" нет транзакционности.

```python
# virtual_trading_bot.py:409-413
self._close_virtual_position(current_position, market_data['price'], "reversal")
time.sleep(1)  # ❌ Между операциями может произойти сбой!
self._execute_virtual_buy(symbol, signal, market_data, position_amount)
```

Если между `close` и `open` произойдет сбой:
- Старая позиция закроется
- Новая не откроется
- Данные будут неконсистентны

**Решение:**
```python
# database.py
from contextlib import contextmanager

class Database:
    @contextmanager
    def transaction(self):
        """Context manager для транзакций"""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            self.logger.error(f"Transaction rollback: {e}")
            raise
        finally:
            conn.close()

# virtual_trading_bot.py
with self.db.transaction():
    self.db.close_virtual_position(old_id, price, "reversal")
    self.db.add_virtual_position(symbol, side, ...)
```

**Влияние:** MEDIUM - редко, но может привести к потере данных

---

### 7. Отсутствие индексов на virtual_positions

**Приоритет:** 🟡 ВЫСОКИЙ  
**Файл:** `src/database.py`  
**Строки:** 720-775

**Проблема:**
Таблица `virtual_positions` не имеет индексов, что приводит к медленным запросам при большом количестве позиций.

**Частые запросы без индексов:**
```sql
-- Выполняется часто, но нет индекса на status
SELECT * FROM virtual_positions WHERE status = 'open';

-- Выполняется часто, но нет индекса на symbol
SELECT * FROM virtual_positions WHERE symbol = 'BTCUSDT' AND status = 'open';

-- Используется в статистике, нет индекса на created_at
SELECT ... FROM virtual_positions WHERE created_at >= ...
```

**Решение:**
```python
def _create_virtual_positions_table(self):
    """Создание таблицы для виртуальных позиций"""
    try:
        # ... создание таблицы ...
        
        # Создаем индексы
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_virtual_positions_status ON virtual_positions(status)",
            "CREATE INDEX IF NOT EXISTS idx_virtual_positions_symbol ON virtual_positions(symbol)",
            "CREATE INDEX IF NOT EXISTS idx_virtual_positions_created_at ON virtual_positions(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_virtual_positions_symbol_status ON virtual_positions(symbol, status)"
        ]
        
        for index_query in indexes:
            self._execute_query(index_query, fetch=False)
        
        self.logger.info("✅ Индексы для virtual_positions созданы")
```

**Влияние:** LOW сейчас, HIGH при масштабировании

---

### 8. SQL Injection риск в запросах с INTERVAL

**Приоритет:** 🟡 СРЕДНИЙ  
**Файл:** `src/database.py`  
**Строка:** 943

**Проблема:**
```python
# PostgreSQL
query = """
SELECT ... 
FROM virtual_positions 
WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '%s days'  # ❌ Неправильно!
"""
result = self._execute_query(query, (days,))
```

PostgreSQL не позволяет использовать параметры в INTERVAL таким образом.

**Решение:**
```python
# Вариант 1: Использовать умножение
query = """
SELECT ... 
FROM virtual_positions 
WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '1 day' * %s
"""

# Вариант 2: Вычислить дату в Python
from datetime import datetime, timedelta

start_date = datetime.now() - timedelta(days=days)
query = """
SELECT ... 
FROM virtual_positions 
WHERE created_at >= %s
"""
result = self._execute_query(query, (start_date,))
```

**Влияние:** LOW - работает, но потенциально опасно

---

### 9. Отсутствие валидации входных данных

**Приоритет:** 🟡 СРЕДНИЙ  
**Файл:** `src/database.py`  

**Проблема:**
Методы принимают параметры без валидации:

```python
def add_virtual_position(self, symbol: str, side: str, size: float, ...):
    # ❌ Нет проверок:
    # - side может быть "INVALID"
    # - size может быть -100
    # - symbol может быть пустым
    ...
```

**Последствия:**
- Невалидные данные попадают в БД
- Сложно отследить источник ошибки
- Возможны исключения в runtime

**Решение:**
```python
def add_virtual_position(self, symbol: str, side: str, size: float, 
                        entry_price: float, leverage: int = 1, 
                        stop_loss: float = None, take_profit: float = None) -> int:
    """Добавление новой виртуальной позиции с валидацией"""
    
    # Валидация
    if side not in ['BUY', 'SELL']:
        raise ValueError(f"Invalid side: {side}. Must be 'BUY' or 'SELL'")
    
    if size <= 0:
        raise ValueError(f"Invalid size: {size}. Must be > 0")
    
    if entry_price <= 0:
        raise ValueError(f"Invalid entry_price: {entry_price}. Must be > 0")
    
    if leverage < 1 or leverage > 125:
        raise ValueError(f"Invalid leverage: {leverage}. Must be 1-125")
    
    if not symbol or len(symbol) < 3:
        raise ValueError(f"Invalid symbol: {symbol}")
    
    # Валидация stop-loss и take-profit
    if side == 'BUY':
        if stop_loss and stop_loss >= entry_price:
            raise ValueError("Stop-loss must be below entry price for BUY")
        if take_profit and take_profit <= entry_price:
            raise ValueError("Take-profit must be above entry price for BUY")
    else:  # SELL
        if stop_loss and stop_loss <= entry_price:
            raise ValueError("Stop-loss must be above entry price for SELL")
        if take_profit and take_profit >= entry_price:
            raise ValueError("Take-profit must be below entry price for SELL")
    
    # Добавление в БД
    ...
```

**Влияние:** MEDIUM - предотвращает баги

---

### 10. N+1 проблема в запросах

**Приоритет:** 🟡 СРЕДНИЙ  
**Файл:** `src/virtual_trading_bot.py`  
**Строки:** 592-603

**Проблема:**
```python
def _update_virtual_balance(self):
    open_positions = self.db.get_virtual_open_positions()
    
    for position in open_positions:
        # ❌ Отдельный запрос к Bybit API для КАЖДОЙ позиции!
        market_data = self.bybit.get_market_data(position['symbol'])
        ...
```

Если открыто 10 позиций по разным символам - 10 запросов.
Если открыто 50 позиций (10 символов х 5 позиций) - все равно нужно 10 запросов, но делается 50!

**Решение:**
```python
def _update_virtual_balance(self):
    """Обновляет виртуальный баланс с оптимизацией запросов"""
    open_positions = self.db.get_virtual_open_positions()
    
    # Группируем позиции по символам
    positions_by_symbol = {}
    for position in open_positions:
        symbol = position['symbol']
        if symbol not in positions_by_symbol:
            positions_by_symbol[symbol] = []
        positions_by_symbol[symbol].append(position)
    
    total_unrealized_pnl = 0.0
    
    # Один запрос на символ вместо N запросов
    for symbol, positions in positions_by_symbol.items():
        market_data = self.bybit.get_market_data(symbol)
        if not market_data:
            continue
            
        current_price = market_data['price']
        
        # Обновляем все позиции этого символа
        for position in positions:
            self.db.update_virtual_position_price(position['id'], current_price)
            
            # Расчет PnL
            if position['side'] == 'BUY':
                pnl = (current_price - position['entry_price']) * position['size']
            else:
                pnl = (position['entry_price'] - current_price) * position['size']
            
            total_unrealized_pnl += pnl
    
    # ... остальная логика
```

**Влияние:** LOW сейчас, HIGH при масштабировании

---

## 🟢 ЖЕЛАТЕЛЬНЫЕ УЛУЧШЕНИЯ

### 11. Нет конвертации Decimal → Float

**Приоритет:** 🟢 НИЗКИЙ  
**Файл:** `src/database.py`  

**Проблема:**
PostgreSQL возвращает числа как `Decimal`, Python работает с `float`. При сравнениях могут быть проблемы:

```python
position = db.get_virtual_position(1)
# position['size'] = Decimal('0.001')

if position['size'] > 0.001:  # Может работать некорректно!
    ...
```

**Решение:**
```python
from decimal import Decimal

class Database:
    def _convert_row_to_dict(self, row: Dict) -> Dict:
        """Конвертирует Decimal в float для удобства"""
        return {
            key: float(value) if isinstance(value, Decimal) else value
            for key, value in row.items()
        }
    
    def get_virtual_position(self, position_id: int) -> Optional[Dict]:
        ...
        result = self._execute_query(query, (position_id,))
        if result:
            return self._convert_row_to_dict(result[0])
        return None
```

**Влияние:** LOW - но улучшает надежность

---

### 12. Отсутствует логирование производительности

**Приоритет:** 🟢 НИЗКИЙ  

**Проблема:**
Не видно, какие операции занимают много времени.

**Решение:**
```python
# utils/performance.py
import time
import functools
import logging

logger = logging.getLogger(__name__)

def log_performance(func):
    """Декоратор для логирования производительности"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            duration = time.time() - start
            if duration > 1.0:  # Логируем только медленные операции
                logger.warning(
                    f"{func.__name__} took {duration:.2f}s (slow!)"
                )
            else:
                logger.debug(
                    f"{func.__name__} took {duration:.3f}s"
                )
    return wrapper

# Использование:
@log_performance
def _update_virtual_balance(self):
    ...
```

**Влияние:** LOW - для оптимизации

---

### 13. Потенциальная утечка памяти в WebSocket

**Приоритет:** 🟢 НИЗКИЙ  
**Файл:** `src/bybit_client.py`  
**Строки:** 299-304

**Проблема:**
```python
def keep_alive():
    while self.is_ws_running:
        time.sleep(10)  # ❌ Бесконечный цикл

thread = threading.Thread(target=keep_alive, daemon=True)
thread.start()
```

Если WebSocket переподключается много раз, могут накапливаться потоки.

**Решение:**
```python
def start_websocket(self):
    if self.is_ws_running:
        return
    
    # Останавливаем старый поток если есть
    if hasattr(self, 'ws_thread') and self.ws_thread.is_alive():
        self.is_ws_running = False
        self.ws_thread.join(timeout=5)
    
    # ... остальной код ...
    
    self.ws_thread = threading.Thread(target=keep_alive, daemon=True)
    self.ws_thread.start()
```

**Влияние:** LOW - редкий случай

---

## 📊 Сводная таблица

| # | Проблема | Приоритет | Файл | Строки | Влияние | Сложность |
|---|----------|-----------|------|--------|---------|-----------|
| 1 | Дублирование данных | 🔴 КРИТИЧЕСКИЙ | virtual_trading_bot.py | 40-44 | HIGH | EASY |
| 2 | _update_virtual_positions_prices | 🔴 КРИТИЧЕСКИЙ | virtual_trading_bot.py | 317-329 | HIGH | EASY |
| 3 | _check_virtual_position_conditions | 🔴 КРИТИЧЕСКИЙ | virtual_trading_bot.py | 331-359 | HIGH | EASY |
| 4 | Проверка позиций | 🔴 КРИТИЧЕСКИЙ | virtual_trading_bot.py | 381-382 | HIGH | EASY |
| 5 | Хардкод min_confidence | 🔴 КРИТИЧЕСКИЙ | virtual_trading_bot.py | 313 | MEDIUM | TRIVIAL |
| 6 | Нет транзакций | 🟡 ВЫСОКИЙ | database.py | - | MEDIUM | MEDIUM |
| 7 | Нет индексов | 🟡 ВЫСОКИЙ | database.py | 720-775 | LOW→HIGH | EASY |
| 8 | SQL Injection риск | 🟡 СРЕДНИЙ | database.py | 943 | LOW | EASY |
| 9 | Нет валидации | 🟡 СРЕДНИЙ | database.py | - | MEDIUM | MEDIUM |
| 10 | N+1 проблема | 🟡 СРЕДНИЙ | virtual_trading_bot.py | 592-603 | LOW→HIGH | MEDIUM |
| 11 | Decimal → Float | 🟢 НИЗКИЙ | database.py | - | LOW | EASY |
| 12 | Логирование perf | 🟢 НИЗКИЙ | - | - | LOW | EASY |
| 13 | Утечка памяти WS | 🟢 НИЗКИЙ | bybit_client.py | 299-304 | LOW | EASY |

## ✅ Рекомендации по порядку исправления

### Неделя 1: Критические баги (Спринт 1)

1. **День 1-2:** Проблемы 1-4 (удаление self.virtual_positions)
   - Это все связанные проблемы, исправляются вместе
   - После исправления бот заработает корректно

2. **День 2:** Проблема 5 (хардкод min_confidence)
   - 5 минут на исправление

**Результат:** Бот работает корректно, позиции управляются правильно

### Неделя 2: Оптимизация БД (Спринт 2)

3. **День 3-4:** Проблемы 6-7 (транзакции и индексы)
   - Повысит надежность и производительность

4. **День 5:** Проблемы 8-9 (SQL Injection и валидация)
   - Улучшит безопасность

**Результат:** БД быстрая, безопасная, надежная

### Неделя 3: Оптимизация (опционально)

5. **По желанию:** Проблемы 10-13
   - Не критично, но полезно

**Результат:** Код готов к продакшену

---

**Следующий шаг:** Начать со [Спринта 1](TASKS.md#спринт-1---исправление-критических-багов-1-2-дня) из TASKS.md

