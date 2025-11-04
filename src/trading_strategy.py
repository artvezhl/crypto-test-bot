import pytz
from deepseek_client import DeepSeekClient
from bybit_client import BybitClient
from database import Database
from config import Config
import time
import logging
from datetime import datetime
from typing import Dict, List


class TradingBot:
    def __init__(self):
        self.db = Database()
        # Настройка логирования
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        # Инициализируем настройки по умолчанию в БД при первом запуске
        self._initialize_default_settings()

        # Загружаем настройки из БД
        self._load_settings_from_db()

        # Инициализируем клиентов с настройками из БД
        self.deepseek = DeepSeekClient()
        self.bybit = BybitClient()

        # Трекер состояния
        self.balance_info = {}
        self.initial_balance = float(
            self.db.get_setting('initial_balance', '1000.0'))
        self.highest_balance = self.initial_balance
        self.lowest_balance = self.initial_balance

        # Добавляем разрешенных пользователей
        self._setup_allowed_users()

        # Настраиваем WebSocket обработчики
        self._setup_websocket_handlers()

        # Запускаем WebSocket
        self.bybit.start_websocket()

        self.logger.info(
            f"🔧 Инициализирован бот для {len(self.symbols)} символов с левериджем {self.leverage}x")

    def _initialize_default_settings(self):
        """Инициализация настроек по умолчанию в базе данных"""
        default_settings = {
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

            # Уведомления
            'enable_notifications': 'true',
            'enable_trade_logging': 'true',

            # Поведение торговли
            'allow_short_positions': 'true',
            'allow_long_positions': 'true',
            'auto_position_reversal': 'true',

            # DeepSeek настройки
            'deepseek_model': 'deepseek-reasoner',
            'deepseek_max_tokens': '5000',
            'deepseek_temperature': '1',

            # Интервал торговли
            'trading_interval_minutes': '15'
        }

        for key, value in default_settings.items():
            current_value = self.db.get_setting(key)
            if not current_value:
                self.db.set_setting(key, value)
                self.logger.info(
                    f"📝 Инициализирована настройка {key} = {value}")

    def _load_settings_from_db(self):
        """Загрузка всех настроек из базы данных"""
        # Торговые настройки
        self.symbols = self.db.get_setting(
            'trading_symbols', 'ETHUSDT,BTCUSDT,ADAUSDT').split(',')
        self.main_symbol = self.db.get_setting('default_symbol', 'ETHUSDT')
        self.leverage = int(self.db.get_setting('leverage', '5'))
        self.min_confidence = float(
            self.db.get_setting('min_confidence', '0.68'))

        # Риск-менеджмент
        self.risk_percent = float(self.db.get_setting('risk_percent', '2.0'))
        self.max_position_percent = float(
            self.db.get_setting('max_position_percent', '20.0'))
        self.max_total_position_percent = float(
            self.db.get_setting('max_total_position_percent', '30.0'))
        self.min_trade_usdt = float(
            self.db.get_setting('min_trade_usdt', '10.0'))
        self.stop_loss_percent = float(
            self.db.get_setting('stop_loss_percent', '2.0'))
        self.take_profit_percent = float(
            self.db.get_setting('take_profit_percent', '4.0'))

        # Трейлинг-стоп
        self.trailing_stop_activation = float(
            self.db.get_setting('trailing_stop_activation_percent', '0.5'))
        self.trailing_stop_distance = float(
            self.db.get_setting('trailing_stop_distance_percent', '0.3'))

        # Поведение торговли
        self.allow_short_positions = self.db.get_setting(
            'allow_short_positions', 'true').lower() == 'true'
        self.allow_long_positions = self.db.get_setting(
            'allow_long_positions', 'true').lower() == 'true'
        self.auto_position_reversal = self.db.get_setting(
            'auto_position_reversal', 'true').lower() == 'true'

        # Уведомления
        self.enable_notifications = self.db.get_setting(
            'enable_notifications', 'true').lower() == 'true'
        self.enable_trade_logging = self.db.get_setting(
            'enable_trade_logging', 'true').lower() == 'true'

        # DeepSeek настройки
        self.deepseek_model = self.db.get_setting(
            'deepseek_model', 'deepseek-chat')
        self.deepseek_max_tokens = int(
            self.db.get_setting('deepseek_max_tokens', '10000'))
        self.deepseek_temperature = float(
            self.db.get_setting('deepseek_temperature', '0.68'))

        # Интервал
        self.trading_interval_minutes = int(
            self.db.get_setting('trading_interval_minutes', '15'))

        self.logger.info("✅ Настройки загружены из базы данных")

    def update_setting(self, key: str, value: str):
        """Обновление настройки и перезагрузка"""
        self.db.set_setting(key, value)
        self._load_settings_from_db()
        self.logger.info(f"🔄 Настройка {key} обновлена на {value}")

    def _setup_allowed_users(self):
        """Добавление разрешенных пользователей (здесь укажите свои user_id)"""
        allowed_users = [
            # Добавьте user_id разрешенных пользователей
            # Пример: (123456789, "username", True) - True для администратора
        ]

        for user_id, username, is_admin in allowed_users:
            self.db.add_allowed_user(user_id, username, is_admin)

    def _setup_websocket_handlers(self):
        """Настройка обработчиков WebSocket"""
        self.bybit.add_position_handler(self._handle_position_update)
        self.bybit.add_order_handler(self._handle_order_update)

    def _handle_position_update(self, position_data: Dict):
        """Обработка обновлений позиций из WebSocket"""
        try:
            symbol = position_data.get('symbol', '')
            size = float(position_data.get('size', 0))
            side = position_data.get('side', '')
            avg_price = float(position_data.get('avgPrice', 0))
            position_value = float(position_data.get('positionValue', 0))
            position_status = position_data.get('positionStatus', '')
            created_time = position_data.get('createdTime', '')
            updated_time = position_data.get('updatedTime', '')

            self.logger.info(f"🔄 Обновление позиции: {symbol} {side} {size}")

            # Если позиция закрыта (размер = 0), но у нас она есть в базе
            if size == 0:
                open_positions = self.db.get_open_positions()
                for db_position in open_positions:
                    if db_position['symbol'] == symbol:
                        # Позиция закрыта на бирже, закрываем в базе
                        market_data = self.bybit.get_market_data(symbol)
                        close_price = market_data['price'] if market_data else db_position['current_price']

                        self.db.close_position(db_position['id'], close_price)
                        self.logger.info(
                            f"✅ Позиция #{db_position['id']} закрыта через WebSocket")

                        # Отправляем уведомление
                        self._send_position_closed_notification(
                            db_position, close_price)
                        break

            # Обновляем существующие позиции
            elif size > 0:
                open_positions = self.db.get_open_positions()
                for db_position in open_positions:
                    if db_position['symbol'] == symbol:
                        # Обновляем текущую цену в базе
                        self.db.update_position_price(
                            db_position['id'], avg_price)
                        break

        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки обновления позиции: {e}")

    def _handle_order_update(self, order_data: Dict):
        """Обработка обновлений ордеров из WebSocket"""
        try:
            order_id = order_data.get('orderId', '')
            order_status = order_data.get('orderStatus', '')
            symbol = order_data.get('symbol', '')
            side = order_data.get('side', '')
            order_type = order_data.get('orderType', '')
            qty = order_data.get('qty', '0')
            price = order_data.get('price', '0')
            created_time = order_data.get('createdTime', '')

            self.logger.info(
                f"🔄 Обновление ордера: {order_id} {order_status} {symbol}")

            # Если ордер исполнен
            if order_status in ['Filled', 'PartiallyFilled']:
                market_data = self.bybit.get_market_data(symbol)
                if market_data:
                    current_price = market_data['price']
                    self.logger.info(
                        f"✅ Ордер {order_id} исполнен по цене {current_price}")

        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки обновления ордера: {e}")

    def _send_position_closed_notification(self, position: Dict, close_price: float):
        """Отправка уведомления о закрытии позиции всем пользователям"""
        if not self.enable_notifications:
            return

        try:
            # Рассчитываем PnL
            pnl = (close_price - position['entry_price']) * position['size']
            pnl_percent = (
                (close_price - position['entry_price']) / position['entry_price']) * 100

            # Корректируем PnL для шорт позиций
            if position['side'] == 'SELL':
                pnl = -pnl
                pnl_percent = -pnl_percent

            moscow_time = self._get_moscow_time()
            pnl_emoji = "📈" if pnl >= 0 else "📉"

            message = f"""
            🔒 *ПОЗИЦИЯ ЗАКРЫТА*

            🆔 *ID:* #{position['id']}
            💹 *Символ:* {position['symbol']}
            📊 *Сторона:* {position['side']}
            💵 *Цена входа:* ${position['entry_price']:.2f}
            💰 *Цена выхода:* ${close_price:.2f}
            {pnl_emoji} *P&L:* {pnl:.2f} USDT ({pnl_percent:.2f}%)
            🔢 *Размер:* {position['size']:.4f}
            ⚡ *Леверидж:* {position['leverage']}x

            ⏰ *Время (МСК):* {moscow_time.strftime("%H:%M:%S")}
            📅 *Дата:* {moscow_time.strftime("%d.%m.%Y")}
            """

            # Отправляем сообщение всем пользователям
            self._broadcast_message(message)

            # Логируем закрытие позиции
            if self.enable_trade_logging:
                self.db.log_trade_event(
                    level='INFO',
                    message=f"Position closed: {position['side']} {position['symbol']}",
                    symbol=position['symbol'],
                    position_id=position['id'],
                    trade_action='CLOSE',
                    pnl=pnl
                )

        except Exception as e:
            self.logger.warning(
                f"Не удалось отправить уведомление о закрытии позиции: {e}")

    def update_balance(self):
        """Обновляем информацию о балансе с учетом открытых позиций"""
        try:
            balance = self.bybit.get_wallet_balance("UNIFIED")

            if balance['total_equity'] > 0:
                # Получаем информацию об открытых позициях
                open_positions = self.db.get_open_positions()
                total_position_value = self._calculate_total_position_value(
                    open_positions)
                unrealized_pnl = self._calculate_unrealized_pnl(open_positions)

                self.balance_info = {
                    'source': 'UNIFIED',
                    'total_equity': balance['total_equity'],
                    'total_available': balance['total_available_balance'],
                    'usdt_balance': balance['usdt_balance'],
                    'total_used_margin': balance.get('total_used_margin', 0),
                    'open_positions_value': total_position_value,
                    'unrealized_pnl': unrealized_pnl,
                    'total_balance_with_positions': balance['total_equity'] + unrealized_pnl,
                    'full_info': balance
                }
            else:
                # Пробуем SPOT как запасной вариант
                balance = self.bybit.get_wallet_balance("SPOT")
                self.balance_info = {
                    'source': 'SPOT',
                    'total_equity': balance['total_equity'],
                    'total_available': balance['total_available_balance'],
                    'usdt_balance': balance['usdt_balance'],
                    'open_positions_value': 0,
                    'unrealized_pnl': 0,
                    'total_balance_with_positions': balance['total_equity'],
                    'full_info': balance
                }

            # Обновляем максимальный и минимальный баланс
            current_balance = self.balance_info['total_balance_with_positions']
            if current_balance > self.highest_balance:
                self.highest_balance = current_balance
            if current_balance < self.lowest_balance:
                self.lowest_balance = current_balance

            self.logger.info(
                f"💰 Баланс: {current_balance:.2f} USDT (позиции: {self.balance_info['open_positions_value']:.2f} USDT)")
            return True

        except Exception as e:
            self.logger.error(f"❌ Ошибка обновления баланса: {e}")
            return False

    def get_all_settings(self) -> Dict[str, str]:
        """Получение всех текущих настроек"""
        settings_keys = [
            'trading_symbols', 'default_symbol', 'min_confidence', 'leverage',
            'risk_percent', 'max_position_percent', 'max_total_position_percent',
            'min_trade_usdt', 'stop_loss_percent', 'take_profit_percent',
            'trailing_stop_activation_percent', 'trailing_stop_distance_percent',
            'initial_balance', 'enable_notifications', 'enable_trade_logging',
            'allow_short_positions', 'allow_long_positions', 'auto_position_reversal',
            'deepseek_model', 'deepseek_max_tokens', 'deepseek_temperature',
            'trading_interval_minutes'
        ]

        settings = {}
        for key in settings_keys:
            settings[key] = self.db.get_setting(key, '')

        return settings

    def _calculate_total_position_value(self, positions: List[Dict]) -> float:
        """Рассчитывает общую стоимость открытых позиций"""
        total_value = 0.0
        for position in positions:
            position_value = position['size'] * position['current_price']
            total_value += position_value
        return total_value

    def _calculate_unrealized_pnl(self, positions: List[Dict]) -> float:
        """Рассчитывает нереализованный PnL"""
        total_pnl = 0.0
        for position in positions:
            total_pnl += position.get('pnl', 0)
        return total_pnl

    def get_balance_change_info(self):
        """Рассчитывает информацию об изменении баланса с учетом позиций"""
        if not self.balance_info:
            return "N/A", "N/A", "N/A", 0, 0

        current_balance = self.balance_info['total_balance_with_positions']
        balance_change = current_balance - self.initial_balance
        balance_change_percent = (
            balance_change / self.initial_balance) * 100 if self.initial_balance > 0 else 0

        # Выбираем эмодзи в зависимости от изменения
        if balance_change > 0:
            arrow = "🟢 ↗️"
        elif balance_change < 0:
            arrow = "🔴 ↘️"
        else:
            arrow = "⚪ ➡️"

        return arrow, balance_change, balance_change_percent, self.highest_balance, self.lowest_balance

    def calculate_position_size(self, symbol: str, market_price: float, available_for_trading: float | None = None) -> float:
        """Рассчитываем размер позиции с учетом левериджа и минимальных лимитов"""
        if not self.update_balance():
            return 0

        if available_for_trading is None:
            trading_balance = self.balance_info.get('total_available', 0)
        else:
            trading_balance = min(
                self.balance_info.get('total_available', 0),
                available_for_trading
            )

        if trading_balance <= 0:
            self.logger.error("❌ Баланс для торговли равен 0")
            return 0

        # Рассчитываем сумму для сделки на основе процента риска
        risk_amount = trading_balance * (self.risk_percent / 100)

        # Ограничиваем максимальный размер позиции
        max_position_amount = trading_balance * \
            (self.max_position_percent / 100)
        position_amount = min(risk_amount, max_position_amount)

        # Учитываем леверидж
        leveraged_amount = position_amount * self.leverage

        # Получаем минимальный размер ордера для символа
        min_order_qty = self.bybit.get_min_order_qty(symbol)
        min_order_value = min_order_qty * market_price

        # Проверяем минимальную сумму с учетом минимального размера ордера
        if leveraged_amount < max(self.min_trade_usdt, min_order_value):
            self.logger.warning(
                f"⚠️ Сумма сделки {leveraged_amount:.2f} USDT меньше минимальной "
                f"(min_trade: {self.min_trade_usdt}, min_order_value: {min_order_value:.2f})"
            )
            return 0

        # Рассчитываем количество
        quantity = leveraged_amount / market_price

        # Проверяем, что количество не меньше минимального
        if quantity < min_order_qty:
            self.logger.warning(
                f"⚠️ Рассчитанное количество {quantity:.6f} меньше минимального {min_order_qty:.6f}"
            )
            # Пробуем увеличить до минимального размера
            min_required_amount = min_order_qty * market_price / self.leverage
            if min_required_amount <= trading_balance:
                self.logger.info(
                    f"🔄 Увеличиваем размер до минимального: {min_required_amount:.2f} USDT")
                return min_required_amount * self.leverage
            else:
                self.logger.warning(
                    "⚠️ Недостаточно средств для минимального ордера")
                return 0

        self.logger.info(
            f"📊 Расчет позиции для {symbol}: {leveraged_amount:.2f} USDT "
            f"(леверидж {self.leverage}x), количество: {quantity:.6f}"
        )
        return leveraged_amount

    def calculate_stop_loss_take_profit(self, entry_price: float, side: str) -> tuple:
        """Расчет стоп-лосса и тейк-профита"""
        if side == "BUY":
            stop_loss = entry_price * (1 - self.stop_loss_percent / 100)
            take_profit = entry_price * \
                (1 + self.take_profit_percent / 100)
        else:  # SELL
            stop_loss = entry_price * (1 + self.stop_loss_percent / 100)
            take_profit = entry_price * \
                (1 - self.take_profit_percent / 100)

        return stop_loss, take_profit

    def run_iteration(self):
        """Одна итерация торгового цикла для всех символов"""
        try:
            # 0. Обновляем баланс
            if not self.update_balance():
                self.logger.error("❌ Не удалось обновить баланс")
                return

            # Получаем общий лимит позиций
            total_position_limit = self.balance_info['total_equity'] * (
                self.max_total_position_percent / 100)
            current_total_position_value = self._get_current_total_position_value()
            available_for_trading = total_position_limit - current_total_position_value

            if available_for_trading < self.min_trade_usdt:
                self.logger.info("⚠️  Достигнут общий лимит позиций")
                return

            # 1. Обрабатываем каждый символ
            for symbol in self.symbols:
                try:
                    self._process_symbol(symbol, available_for_trading)
                except Exception as e:
                    self.logger.error(
                        f"❌ Ошибка обработки символа {symbol}: {e}")

        except Exception as e:
            self.logger.error(f"❌ Ошибка в торговой итерации: {e}")

    def _process_symbol(self, symbol: str, available_for_trading: float):
        """Обработка одного символа"""
        # Получаем рыночные данные
        market_data = self.bybit.get_market_data(symbol)
        if not market_data:
            return

        # Обновляем цены открытых позиций для этого символа
        self._update_symbol_positions_prices(symbol, market_data['price'])

        # Проверяем условия для скользящих стоп-лоссов
        self._check_symbol_trailing_stops(symbol, market_data['price'])

        # Получаем сигнал от DeepSeek
        signal = self.get_trading_signal_with_logging(symbol, market_data)

        # Рассчитываем размер позиции с учетом общего лимита и минимальных требований
        position_amount = self.calculate_position_size(
            symbol, market_data['price'], available_for_trading)
        if position_amount <= 0:
            return

        # Исполняем сделку если сигнал хороший
        if signal['confidence'] > self.min_confidence:
            self._execute_trading_decision(
                symbol, signal, market_data, position_amount)

    def _get_current_total_position_value(self) -> float:
        """Получает общую стоимость всех открытых позиций"""
        open_positions = self.db.get_open_positions()
        total_value = 0.0

        for position in open_positions:
            position_value = position['size'] * position['current_price']
            total_value += position_value

        return total_value

    def _update_symbol_positions_prices(self, symbol: str, current_price: float):
        """Обновление цен открытых позиций для конкретного символа"""
        open_positions = self.db.get_open_positions()
        for position in open_positions:
            if position['symbol'] == symbol:
                self.db.update_position_price(position['id'], current_price)

    def _check_symbol_trailing_stops(self, symbol: str, current_price: float):
        """Проверка условий для скользящих стоп-лоссов для конкретного символа"""
        open_positions = self.db.get_open_positions()

        for position in open_positions:
            position_id = position['id']
            entry_price = position['entry_price']
            current_sl = position['stop_loss']
            side = position['side']

            if side == "BUY":
                # Для лонгов: поднимаем стоп-лосс когда цена растет
                price_change_percent = (
                    (current_price - entry_price) / entry_price) * 100
                if price_change_percent >= self.trailing_stop_activation:
                    new_sl = current_price * \
                        (1 - self.trailing_stop_distance / 100)
                    if not current_sl or new_sl > current_sl:
                        self.db.update_stop_loss(position_id, new_sl)
                        self.logger.info(
                            f"📈 Обновлен стоп-лосс для лонга {symbol}: {new_sl:.2f}")

                # Проверяем достижение стоп-лосса или тейк-профита
                if current_sl and current_price <= current_sl:
                    self._close_position_by_id(
                        position_id, current_price, "stop_loss")
                elif position['take_profit'] and current_price >= position['take_profit']:
                    self._close_position_by_id(
                        position_id, current_price, "take_profit")

            else:  # SELL
                # Для шортов: опускаем стоп-лосс когда цена падает
                price_change_percent = (
                    (entry_price - current_price) / entry_price) * 100
                if price_change_percent >= self.trailing_stop_activation:
                    new_sl = current_price * \
                        (1 + self.trailing_stop_distance / 100)
                    if not current_sl or new_sl < current_sl:
                        self.db.update_stop_loss(position_id, new_sl)
                        self.logger.info(
                            f"📉 Обновлен стоп-лосс для шорта {symbol}: {new_sl:.2f}")

                # Проверяем достижение стоп-лосса или тейк-профита
                if current_sl and current_price >= current_sl:
                    self._close_position_by_id(
                        position_id, current_price, "stop_loss")
                elif position['take_profit'] and current_price <= position['take_profit']:
                    self._close_position_by_id(
                        position_id, current_price, "take_profit")

    def get_trading_signal_with_logging(self, symbol: str, market_data: Dict) -> Dict:
        """Получение сигнала от DeepSeek с логированием"""
        signal = self.deepseek.get_trading_signal(market_data)

        # Логируем сигнал
        if self.enable_trade_logging:
            self.db.log_trade_event(
                level='INFO',
                message=f"DeepSeek signal received for {symbol}",
                symbol=symbol,
                signal_data=signal,
                confidence=signal.get('confidence'),
                trade_action=signal.get('action')
            )

        return signal

    def _execute_trading_decision(self, symbol: str, signal: Dict, market_data: Dict, position_amount: float):
        """Исполняет торговое решение с поддержкой обоих направлений"""
        try:
            current_positions = self.db.get_open_positions()
            has_position = len(current_positions) > 0

            signal_action = signal['action']

            # Проверяем разрешены ли направления
            if signal_action == 'BUY' and not self.allow_long_positions:
                self.logger.info(f"⏸️  Лонг позиции отключены для {symbol}")
                return
            elif signal_action == 'SELL' and not self.allow_short_positions:
                self.logger.info(f"⏸️  Шорт позиции отключены для {symbol}")
                return

            if signal_action == 'BUY':
                if not has_position:
                    # Нет позиций - открываем лонг
                    self._execute_buy(
                        symbol, signal, market_data, position_amount)
                elif self.auto_position_reversal:
                    # Есть позиция - проверяем направление
                    current_position = current_positions[0]
                    if current_position['side'] == 'SELL':
                        # Закрываем шорт и открываем лонг
                        self.logger.info(
                            f"🔄 Переворот позиции {symbol}: SELL → BUY")
                        self._close_position_by_id(
                            current_position['id'], market_data['price'], "reversal")
                        time.sleep(1)
                        self._execute_buy(
                            symbol, signal, market_data, position_amount)

            elif signal_action == 'SELL':
                if not has_position:
                    # Нет позиций - открываем шорт
                    self._execute_sell(
                        symbol, signal, market_data, position_amount)
                elif self.auto_position_reversal:
                    # Есть позиция - проверяем направление
                    current_position = current_positions[0]
                    if current_position['side'] == 'BUY':
                        # Закрываем лонг и открываем шорт
                        self.logger.info(
                            f"🔄 Переворот позиции {symbol}: BUY → SELL")
                        self._close_position_by_id(
                            current_position['id'], market_data['price'], "reversal")
                        time.sleep(1)
                        self._execute_sell(
                            symbol, signal, market_data, position_amount)

        except Exception as e:
            self.logger.error(f"❌ Ошибка исполнения сделки для {symbol}: {e}")

    def _execute_buy(self, symbol: str, signal: Dict, market_data: Dict, position_amount: float):
        """Исполняет покупку"""
        self.logger.info(f"🎯 Исполняем BUY сигнал для {symbol}")

        entry_price = market_data['price']
        stop_loss, take_profit = self.calculate_stop_loss_take_profit(
            entry_price, "BUY")

        # Рассчитываем количество контрактов
        quantity = position_amount / entry_price

        order = self.bybit.place_order(
            symbol=symbol,
            side="Buy",
            qty=quantity,
            leverage=self.leverage,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        if order:
            # Сохраняем позицию в базу
            position_id = self.db.add_position(
                symbol=symbol,
                side="BUY",
                size=quantity,
                entry_price=entry_price,
                leverage=self.leverage,
                stop_loss=stop_loss,
                take_profit=take_profit
            )

            # Отправляем уведомление
            self._send_trade_notification(
                "🟢 ПОКУПКА", position_id, signal, entry_price)

            # Логируем сделку
            if self.enable_trade_logging:
                self.db.log_trade_event(
                    level='INFO',
                    message=f"BUY position opened for {symbol}",
                    symbol=symbol,
                    position_id=position_id,
                    trade_action='BUY',
                    confidence=signal.get('confidence')
                )

    def _execute_sell(self, symbol: str, signal: Dict, market_data: Dict, position_amount: float):
        """Исполняет продажу"""
        self.logger.info(f"🎯 Исполняем SELL сигнал для {symbol}")

        entry_price = market_data['price']
        stop_loss, take_profit = self.calculate_stop_loss_take_profit(
            entry_price, "SELL")

        # Рассчитываем количество контрактов
        quantity = position_amount / entry_price

        order = self.bybit.place_order(
            symbol=symbol,
            side="Sell",
            qty=quantity,
            leverage=self.leverage,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        if order:
            # Сохраняем позицию в базу
            position_id = self.db.add_position(
                symbol=symbol,
                side="SELL",
                size=quantity,
                entry_price=entry_price,
                leverage=self.leverage,
                stop_loss=stop_loss,
                take_profit=take_profit
            )

            # Отправляем уведомление
            self._send_trade_notification(
                "🔴 ПРОДАЖА", position_id, signal, entry_price)

            # Логируем сделку
            if self.enable_trade_logging:
                self.db.log_trade_event(
                    level='INFO',
                    message=f"SELL position opened for {symbol}",
                    symbol=symbol,
                    position_id=position_id,
                    trade_action='SELL',
                    confidence=signal.get('confidence')
                )

    def _close_position_by_id(self, position_id: int, exit_price: float, reason: str):
        """Закрытие позиции по ID"""
        position = self.db.get_position(position_id)
        if position and position['status'] == 'open':
            success = self.bybit.close_position(
                position['symbol'], position['side'])
            if success:
                self.db.close_position(position_id, exit_price)
                self.logger.info(
                    f"✅ Позиция #{position_id} закрыта по причине: {reason}")

    def _send_trade_notification(self, action: str, position_id: int, signal: Dict, entry_price: float):
        """Отправляет уведомление о сделке всем пользователям бота"""
        if not self.enable_notifications:
            return

        try:
            # Получаем информацию о балансе
            arrow, balance_change, balance_change_percent, highest, lowest = self.get_balance_change_info()
            trading_balance = self.balance_info.get(
                'total_balance_with_positions', 0)
            balance_source = self.balance_info.get('source', 'UNKNOWN')

            # Получаем позицию из базы
            position = self.db.get_position(position_id)
            if not position:
                self.logger.error(f"Позиция {position_id} не найдена в базе")
                return

            moscow_time = self._get_moscow_time()

            # Определяем эмодзи для направления
            direction_emoji = "🟢" if position['side'] == 'BUY' else "🔴"
            direction_text = "ЛОНГ" if position['side'] == 'BUY' else "ШОРТ"

            message = f"""
{direction_emoji} *{action} - {direction_text}*

🆔 *ID позиции:* #{position_id}
💹 *Символ:* {position['symbol']}
💰 *Общий баланс:* {trading_balance:.2f} USDT ({balance_source})
{arrow} *Изменение:* {balance_change:+.2f} USDT ({balance_change_percent:+.2f}%)
📊 *Начальный баланс:* {self.initial_balance:.2f} USDT
💵 *Размер позиции:* {position['size']:.4f}
🔢 *Леверидж:* {position['leverage']}x
💸 *Цена входа:* ${entry_price:.2f}
📉 *Стоп-лосс:* ${position.get('stop_loss', 0):.2f}
📈 *Тейк-профит:* ${position.get('take_profit', 0):.2f}

🎯 *Сигнал AI:* {signal.get('action', 'N/A')}
⭐ *Уверенность:* {signal.get('confidence', 0):.2f}
💭 *Причина:* {signal.get('reason', 'N/A')}

⏰ *Время (МСК):* {moscow_time.strftime("%H:%M:%S")}
📅 *Дата:* {moscow_time.strftime("%d.%m.%Y")}
"""

            # Отправляем сообщение всем пользователям
            self._broadcast_message(message)

        except Exception as e:
            self.logger.warning(
                f"Не удалось отправить уведомление о сделке: {e}")

    def _broadcast_message(self, message: str, parse_mode: str = 'Markdown'):
        """Рассылает сообщение всем пользователям бота"""
        try:
            import requests
            from config import Config

            token = Config.TELEGRAM_BOT_TOKEN
            if not token or token == "your_telegram_token":
                return

            # Получаем всех пользователей из базы
            users = self.db.get_all_users()
            if not users:
                self.logger.warning("Нет пользователей для рассылки")
                return

            url = f"https://api.telegram.org/bot{token}/sendMessage"

            successful_sends = 0
            failed_sends = 0

            for user in users:
                try:
                    payload = {
                        'chat_id': user['user_id'],
                        'text': message,
                        'parse_mode': parse_mode
                    }

                    response = requests.post(url, json=payload, timeout=10)
                    if response.status_code == 200:
                        successful_sends += 1
                    else:
                        failed_sends += 1
                        self.logger.warning(
                            f"Не удалось отправить сообщение пользователю {user['user_id']}: {response.text}")

                except Exception as e:
                    failed_sends += 1
                    self.logger.warning(
                        f"Ошибка отправки пользователю {user['user_id']}: {e}")

            self.logger.info(
                f"📢 Рассылка завершена: успешно {successful_sends}, ошибок {failed_sends}")

        except Exception as e:
            self.logger.error(f"❌ Ошибка при рассылке сообщений: {e}")

    def _get_moscow_time(self):
        """Возвращает текущее время по Москве"""
        try:
            moscow_tz = pytz.timezone('Europe/Moscow')
            return datetime.now(moscow_tz)
        except:
            from datetime import timedelta
            return datetime.utcnow() + timedelta(hours=3)

    def stop(self):
        """Остановка бота"""
        self.bybit.stop_websocket()
