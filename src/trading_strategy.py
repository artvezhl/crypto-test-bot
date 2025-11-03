import pytz
from deepseek_client import DeepSeekClient
from bybit_client import BybitClient
from database import Database
from config import Config
import time
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional
import threading


class TradingBot:
    def __init__(self):
        self.deepseek = DeepSeekClient()
        self.bybit = BybitClient()
        self.db = Database()

        # Настройки из базы или конфига
        self.symbol = self.db.get_setting('symbol', Config.DEFAULT_SYMBOL)
        self.leverage = int(self.db.get_setting('leverage', '10'))
        self.min_confidence = Config.MIN_CONFIDENCE

        # Настройки риск-менеджмента
        self.risk_percent = Config.RISK_PERCENT
        self.max_position_percent = Config.MAX_POSITION_PERCENT
        self.min_trade_usdt = Config.MIN_TRADE_USDT
        self.stop_loss_percent = Config.STOP_LOSS_PERCENT
        self.take_profit_percent = Config.TAKE_PROFIT_PERCENT

        # Трекер состояния
        self.balance_info = {}
        self.initial_balance = Config.INITIAL_BALANCE
        self.highest_balance = self.initial_balance
        self.lowest_balance = self.initial_balance

        # Настройка логирования
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        # Добавляем разрешенных пользователей
        self._setup_allowed_users()

        # Настраиваем WebSocket обработчики
        self._setup_websocket_handlers()

        # Запускаем WebSocket
        self.bybit.start_websocket()

        self.logger.info(
            f"🔧 Инициализирован бот для {self.symbol} с левериджем {self.leverage}x")

    def _setup_allowed_users(self):
        """Добавление разрешенных пользователей (здесь укажите свои user_id)"""
        allowed_users = [
            # Добавьте user_id разрешенных пользователей
            # Пример: (123456789, "username")
        ]

        for user_id, username in allowed_users:
            self.db.add_allowed_user(user_id, username)

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
                    # Можно добавить дополнительную логику обработки исполненных ордеров
                    self.logger.info(
                        f"✅ Ордер {order_id} исполнен по цене {current_price}")

        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки обновления ордера: {e}")

    def _send_position_closed_notification(self, position: Dict, close_price: float):
        """Отправка уведомления о закрытии позиции"""
        try:
            import requests
            from config import Config

            token = Config.TELEGRAM_BOT_TOKEN
            if not token or token == "your_telegram_token":
                return

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

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                'chat_id': Config.TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'Markdown'
            }

            requests.post(url, json=payload, timeout=10)

        except Exception as e:
            self.logger.warning(
                f"Не удалось отправить уведомление о закрытии позиции: {e}")

    def update_balance(self):
        """Обновляем информацию о балансе"""
        try:
            balance = self.bybit.get_wallet_balance("UNIFIED")

            if balance['total_equity'] > 0:
                self.balance_info = {
                    'source': 'UNIFIED',
                    'total_equity': balance['total_equity'],
                    'total_available': balance['total_available_balance'],
                    'usdt_balance': balance['usdt_balance'],
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
                    'full_info': balance
                }

            # Обновляем максимальный и минимальный баланс
            current_balance = self.balance_info['total_equity']
            if current_balance > self.highest_balance:
                self.highest_balance = current_balance
            if current_balance < self.lowest_balance:
                self.lowest_balance = current_balance

            self.logger.info(f"💰 Баланс: {current_balance:.2f} USDT")
            return True

        except Exception as e:
            self.logger.error(f"❌ Ошибка обновления баланса: {e}")
            return False

    def get_balance_change_info(self):
        """Рассчитывает информацию об изменении баланса"""
        if not self.balance_info:
            return "N/A", "N/A", "N/A", 0, 0

        current_balance = self.balance_info['total_equity']
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

    def calculate_position_size(self, market_price: float) -> float:
        """Рассчитываем размер позиции с учетом левериджа"""
        if not self.update_balance():
            return 0

        trading_balance = self.balance_info.get('total_available', 0)

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

        # Проверяем минимальную сумму
        if leveraged_amount < self.min_trade_usdt:
            self.logger.warning(
                f"⚠️ Сумма сделки {leveraged_amount:.2f} USDT меньше минимальной")
            return 0

        self.logger.info(
            f"📊 Расчет позиции: {leveraged_amount:.2f} USDT (леверидж {self.leverage}x)")
        return leveraged_amount

    def calculate_stop_loss_take_profit(self, entry_price: float, side: str) -> tuple:
        """Расчет стоп-лосса и тейк-профита"""
        if side == "BUY":
            stop_loss = entry_price * (1 - self.stop_loss_percent / 100)
            take_profit = entry_price * (1 + self.take_profit_percent / 100)
        else:  # SELL
            stop_loss = entry_price * (1 + self.stop_loss_percent / 100)
            take_profit = entry_price * (1 - self.take_profit_percent / 100)

        return stop_loss, take_profit

    def run_iteration(self):
        """Одна итерация торгового цикла"""
        try:
            # 0. Обновляем баланс
            if not self.update_balance():
                self.logger.error("❌ Не удалось обновить баланс")
                return

            # 1. Получаем рыночные данные
            market_data = self.bybit.get_market_data(self.symbol)
            if not market_data:
                return

            # 2. Обновляем цены открытых позиций
            self._update_positions_prices(market_data['price'])

            # 3. Проверяем условия для скользящих стоп-лоссов
            self._check_trailing_stops(market_data['price'])

            # 4. Получаем сигнал от DeepSeek
            signal = self.deepseek.get_trading_signal(market_data)

            # 5. Рассчитываем размер позиции
            position_amount = self.calculate_position_size(
                market_data['price'])
            if position_amount <= 0:
                return

            # 6. Исполняем сделку если сигнал хороший
            if signal['confidence'] > self.min_confidence:
                self._execute_trading_decision(
                    signal, market_data, position_amount)

        except Exception as e:
            self.logger.error(f"❌ Ошибка в торговой итерации: {e}")

    def _update_positions_prices(self, current_price: float):
        """Обновление цен открытых позиций"""
        open_positions = self.db.get_open_positions()
        for position in open_positions:
            self.db.update_position_price(position['id'], current_price)

    def _check_trailing_stops(self, current_price: float):
        """Проверка условий для скользящих стоп-лоссов для обоих направлений"""
        open_positions = self.db.get_open_positions()

        for position in open_positions:
            position_id = position['id']
            entry_price = position['entry_price']
            current_sl = position['stop_loss']
            current_tp = position['take_profit']
            side = position['side']

            if side == "BUY":
                # Для лонгов: поднимаем стоп-лосс когда цена растет
                if current_price > entry_price:
                    new_sl = entry_price * (1 + 0.005)  # +0.5% от цены входа
                    if not current_sl or new_sl > current_sl:
                        self.db.update_stop_loss(position_id, new_sl)
                        self.logger.info(
                            f"📈 Обновлен стоп-лосс для лонга: {new_sl:.2f}")

                # Проверяем достижение стоп-лосса или тейк-профита
                if current_sl and current_price <= current_sl:
                    self._close_position_by_id(
                        position_id, current_price, "stop_loss")
                elif current_tp and current_price >= current_tp:
                    self._close_position_by_id(
                        position_id, current_price, "take_profit")

            else:  # SELL
                # Для шортов: опускаем стоп-лосс когда цена падает
                if current_price < entry_price:
                    new_sl = entry_price * (1 - 0.005)  # -0.5% от цены входа
                    if not current_sl or new_sl < current_sl:
                        self.db.update_stop_loss(position_id, new_sl)
                        self.logger.info(
                            f"📉 Обновлен стоп-лосс для шорта: {new_sl:.2f}")

                # Проверяем достижение стоп-лосса или тейк-профита
                if current_sl and current_price >= current_sl:
                    self._close_position_by_id(
                        position_id, current_price, "stop_loss")
                elif current_tp and current_price <= current_tp:
                    self._close_position_by_id(
                        position_id, current_price, "take_profit")

    def _execute_trading_decision(self, signal: Dict, market_data: Dict, position_amount: float):
        """Исполняет торговое решение с поддержкой обоих направлений"""
        try:
            current_positions = self.db.get_open_positions()
            has_position = len(current_positions) > 0

            if signal['action'] == 'BUY':
                if not has_position:
                    # Нет позиций - открываем лонг
                    self._execute_buy(signal, market_data, position_amount)
                else:
                    # Есть позиция - проверяем направление
                    current_position = current_positions[0]
                    if current_position['side'] == 'SELL':
                        # Закрываем шорт и открываем лонг
                        self.logger.info("🔄 Переворот позиции: SELL → BUY")
                        self._close_position_by_id(
                            current_position['id'], market_data['price'], "reversal")
                        # Даем время на закрытие перед открытием новой позиции
                        time.sleep(1)
                        self._execute_buy(signal, market_data, position_amount)
                    # Если уже в лонге - ничего не делаем

            elif signal['action'] == 'SELL':
                if not has_position:
                    # Нет позиций - открываем шорт
                    self._execute_sell(signal, market_data, position_amount)
                else:
                    # Есть позиция - проверяем направление
                    current_position = current_positions[0]
                    if current_position['side'] == 'BUY':
                        # Закрываем лонг и открываем шорт
                        self.logger.info("🔄 Переворот позиции: BUY → SELL")
                        self._close_position_by_id(
                            current_position['id'], market_data['price'], "reversal")
                        # Даем время на закрытие перед открытием новой позиции
                        time.sleep(1)
                        self._execute_sell(
                            signal, market_data, position_amount)
                    # Если уже в шорте - ничего не делаем

        except Exception as e:
            self.logger.error(f"❌ Ошибка исполнения сделки: {e}")

    def get_current_position_direction(self) -> Optional[str]:
        """Возвращает направление текущей позиции или None если позиций нет"""
        positions = self.db.get_open_positions()
        if positions:
            return positions[0]['side']
        return None

    def _execute_buy(self, signal: Dict, market_data: Dict, position_amount: float):
        """Исполняет покупку"""
        self.logger.info(f"🎯 Исполняем BUY сигнал")

        entry_price = market_data['price']
        stop_loss, take_profit = self.calculate_stop_loss_take_profit(
            entry_price, "BUY")

        # Рассчитываем количество контрактов
        quantity = position_amount / entry_price

        order = self.bybit.place_order(
            symbol=self.symbol,
            side="Buy",
            qty=quantity,
            leverage=self.leverage,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        if order:
            # Сохраняем позицию в базу
            position_id = self.db.add_position(
                symbol=self.symbol,
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

    def _execute_sell(self, signal: Dict, market_data: Dict, position_amount: float):
        """Исполняет продажу"""
        self.logger.info(f"🎯 Исполняем SELL сигнал")

        entry_price = market_data['price']
        stop_loss, take_profit = self.calculate_stop_loss_take_profit(
            entry_price, "SELL")

        # Рассчитываем количество контрактов
        quantity = position_amount / entry_price

        order = self.bybit.place_order(
            symbol=self.symbol,
            side="Sell",
            qty=quantity,
            leverage=self.leverage,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        if order:
            # Сохраняем позицию в базу
            position_id = self.db.add_position(
                symbol=self.symbol,
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

    def _has_open_position(self) -> bool:
        """Проверяет, есть ли открытая позиция"""
        return len(self.db.get_open_positions()) > 0

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
        """Отправляет уведомление о сделке в Telegram"""
        try:
            import requests
            from config import Config

            token = Config.TELEGRAM_BOT_TOKEN

            if not token or token == "your_telegram_token":
                return

            # Получаем информацию о балансе
            arrow, balance_change, balance_change_percent, highest, lowest = self.get_balance_change_info()
            trading_balance = self.balance_info.get('total_equity', 0)
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
                💰 *Текущий баланс:* {trading_balance:.2f} USDT ({balance_source})
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

            # Отправляем сообщение через Telegram API
            url = f"https://api.telegram.org/bot{token}/sendMessage"

            payload = {
                'chat_id': Config.TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'Markdown'
            }

            requests.post(url, json=payload, timeout=10)

        except Exception as e:
            self.logger.warning(
                f"Не удалось отправить уведомление о сделке: {e}")

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
