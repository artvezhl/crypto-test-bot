class OrderHelper:
    """Помощник для работы с ордерами"""

    @staticmethod
    def get_validated_size(symbol, requested_size, current_price):
        """Возвращает валидный размер ордера для Bybit"""
        # Простая проверка - если размер меньше 0.01, увеличиваем до 0.01
        if requested_size < 0.01:
            return 0.01

        # Проверяем минимальную стоимость (10 USDT)
        order_value = requested_size * current_price
        if order_value < 10:
            min_size_by_value = 10 / current_price
            adjusted_size = max(0.01, min_size_by_value)
            return round(adjusted_size, 4)

        return requested_size
