class OrderValidator:
    """Валидатор ордеров для Bybit"""

    # Минимальные размеры ордеров для разных пар (из документации Bybit)
    MIN_ORDER_VALUES = {
        'BTCUSDT': 0.0001,  # ~6.5 USDT при цене 65000
        'ETHUSDT': 0.01,    # ~40 USDT при цене 4000
        'SOLUSDT': 0.1,     # ~20 USDT при цене 200
        'ADAUSDT': 10,      # ~5 USDT при цене 0.5
        'DOTUSDT': 0.1,     # ~7 USDT при цене 70
        # Добавьте другие пары по необходимости
    }

    MIN_ORDER_USDT = 10  # Абсолютный минимум в USDT

    @classmethod
    def validate_order_size(cls, symbol, size, current_price):
        """Проверяет и корректирует размер ордера"""
        # Проверяем минимальный размер для конкретной пары
        min_size = cls.MIN_ORDER_VALUES.get(symbol, 0.01)

        if size < min_size:
            print(
                f"⚠️ Размер ордера {size} слишком мал для {symbol}. Минимум: {min_size}")
            return min_size

        # Проверяем минимальную стоимость в USDT
        order_value = size * current_price
        if order_value < cls.MIN_ORDER_USDT:
            min_size_by_value = cls.MIN_ORDER_USDT / current_price
            adjusted_size = max(min_size, min_size_by_value)
            print(
                f"⚠️ Стоимость ордера ${order_value:.2f} слишком мала. Корректируем размер до {adjusted_size}")
            return adjusted_size

        return size

    @classmethod
    def calculate_proper_size(cls, symbol, usdt_amount, current_price):
        """Рассчитывает правильный размер ордера на основе суммы в USDT"""
        calculated_size = usdt_amount / current_price
        return cls.validate_order_size(symbol, calculated_size, current_price)
