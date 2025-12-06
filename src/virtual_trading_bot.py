import pytz
from deepseek_client import DeepSeekClient
from bybit_client import BybitClient
from database import Database
from utils.performance import log_performance
import time
import logging
from datetime import datetime
from typing import Dict


class VirtualTradingBot:
    def __init__(self):
        # Настройка логирования
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        try:
            self.db = Database()
            self.deepseek = DeepSeekClient(self.db)
            self.bybit = BybitClient()

            # Инициализируем настройки по умолчанию в БД при первом запуске
            self._initialize_default_settings()

            # Загружаем настройки из БД
            self._load_settings_from_db()

            # Загружаем открытые виртуальные позиции из БД
            self._load_virtual_positions_from_db()

            # Трекер состояния
            self.balance_info = {}
            self.initial_balance = float(
                self.db.get_setting('initial_balance', '10000.0'))
            self.current_balance = self.initial_balance
            self.highest_balance = self.initial_balance
            self.lowest_balance = self.initial_balance

            # Статистика виртуальной торговли загружается из БД по запросу
            # (self.virtual_positions, virtual_trades_count, total_virtual_pnl удалены - данные берутся из БД)

            self.logger.info(
                f"🔧 Инициализирован ВИРТУАЛЬНЫЙ торговый бот для {len(self.symbols)} символов")

        except Exception as e:
            self.logger.error(f"❌ Ошибка инициализации VirtualTradingBot: {e}")
            raise

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
        self.leverage = int(self.db.get_setting('leverage', '10'))
        self.min_confidence = float(
            self.db.get_setting('min_confidence', '0.7'))

        # Риск-менеджмент
        self.risk_percent = float(self.db.get_setting('risk_percent', '2.0'))
        self.max_position_percent = float(
            self.db.get_setting('max_position_percent', '20.0'))
        self.max_total_position_percent = float(
            self.db.get_setting('max_total_position_percent', '50.0'))
        self.min_trade_usdt = float(
            self.db.get_setting('min_trade_usdt', '50.0'))
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

        self.logger.info(
            "✅ Настройки виртуального бота загружены из базы данных")

    def update_balance(self):
        """Обновляем информацию о реальном балансе (только для информации)"""
        try:
            # Получаем реальный баланс с Bybit (только для информации)
            balance = self.bybit.get_wallet_balance("UNIFIED")

            if balance['total_equity'] > 0:
                self.balance_info = {
                    'source': 'UNIFIED',
                    'total_equity': balance['total_equity'],
                    'total_available': balance['total_available_balance'],
                    'usdt_balance': balance['usdt_balance'],
                    'is_real_balance': True
                }
            else:
                self.balance_info = {
                    'source': 'VIRTUAL',
                    'total_equity': self.current_balance,
                    'total_available': self.current_balance,
                    'usdt_balance': self.current_balance,
                    'is_real_balance': False
                }

            # Обновляем виртуальный баланс на основе виртуальных позиций
            self._update_virtual_balance()

            self.logger.info(
                f"💰 Реальный баланс: {balance['total_equity']:.2f} USDT, Виртуальный: {self.current_balance:.2f} USDT")
            return True

        except Exception as e:
            self.logger.error(f"❌ Ошибка обновления баланса: {e}")
            # Используем виртуальный баланс в случае ошибки
            self.balance_info = {
                'source': 'VIRTUAL',
                'total_equity': self.current_balance,
                'total_available': self.current_balance,
                'usdt_balance': self.current_balance,
                'is_real_balance': False
            }
            return True

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

    def get_balance_change_info(self):
        """Рассчитывает информацию об изменении виртуального баланса"""
        balance_change = self.current_balance - self.initial_balance
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

    def calculate_position_size(self, symbol: str, market_price: float) -> float:
        """Рассчитываем размер виртуальной позиции"""
        # Используем виртуальный баланс для расчетов
        trading_balance = self.current_balance

        if trading_balance <= 0:
            self.logger.error("❌ Виртуальный баланс для торговли равен 0")
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
                f"⚠️ Виртуальная сумма сделки {leveraged_amount:.2f} USDT меньше минимальной")
            return 0

        # Рассчитываем количество
        quantity = leveraged_amount / market_price

        self.logger.info(
            f"📊 Расчет виртуальной позиции для {symbol}: {leveraged_amount:.2f} USDT "
            f"(леверидж {self.leverage}x), количество: {quantity:.6f}"
        )
        return leveraged_amount

    def calculate_stop_loss_take_profit(self, entry_price: float, side: str) -> tuple:
        """Расчет стоп-лосса и тейк-профита для виртуальной позиции"""
        if side == "BUY":
            stop_loss = entry_price * (1 - self.stop_loss_percent / 100)
            take_profit = entry_price * (1 + self.take_profit_percent / 100)
        else:  # SELL
            stop_loss = entry_price * (1 + self.stop_loss_percent / 100)
            take_profit = entry_price * (1 - self.take_profit_percent / 100)

        return stop_loss, take_profit

    @log_performance(threshold_seconds=30.0)
    def run_iteration(self):
        """Одна итерация виртуального торгового цикла"""
        try:
            # 0. Обновляем баланс (реальный и виртуальный)
            if not self.update_balance():
                self.logger.error("❌ Не удалось обновить баланс")
                return

            # 1. Обрабатываем каждый символ
            for symbol in self.symbols:
                try:
                    self._process_symbol(symbol)
                except Exception as e:
                    self.logger.error(
                        f"❌ Ошибка обработки символа {symbol}: {e}")

        except Exception as e:
            self.logger.error(f"❌ Ошибка в виртуальной торговой итерации: {e}")

    @log_performance(threshold_seconds=10.0)
    def _process_symbol(self, symbol: str):
        """Обработка одного символа для виртуальной торговли"""
        # Получаем реальные рыночные данные
        market_data = self.bybit.get_market_data(symbol)
        if not market_data:
            return

        # Обновляем цены виртуальных позиций
        self._update_virtual_positions_prices(symbol, market_data['price'])

        # Проверяем условия для закрытия виртуальных позиций
        self._check_virtual_position_conditions(symbol, market_data['price'])

        # Получаем сигнал от DeepSeek
        signal = self.get_trading_signal_with_logging(symbol, market_data)

        # Рассчитываем размер виртуальной позиции
        position_amount = self.calculate_position_size(
            symbol, market_data['price'])
        if position_amount <= 0:
            return

        # Исполняем виртуальную сделку если сигнал хороший (используем настройку из БД)
        if signal['confidence'] > self.min_confidence:
            self._execute_virtual_trading_decision(
                symbol, signal, market_data, position_amount)

    def _update_virtual_positions_prices(self, symbol: str, current_price: float):
        """Обновление цен виртуальных позиций для конкретного символа из БД"""
        open_positions = self.db.get_virtual_open_positions(symbol)
        
        for position in open_positions:
            # Обновляем цену в БД (метод также рассчитывает PnL)
            self.db.update_virtual_position_price(position['id'], current_price)
            
            self.logger.debug(
                f"Updated position #{position['id']}: {symbol} @ ${current_price:.2f}"
            )

    def _check_virtual_position_conditions(self, symbol: str, current_price: float):
        """Проверка условий для закрытия виртуальных позиций из БД"""
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
                self.logger.info(
                    f"🎯 Условие {close_reason} сработало для позиции #{position['id']} "
                    f"({symbol} @ ${current_price:.2f})"
                )
                self._close_virtual_position(position, current_price, close_reason)

    @log_performance(threshold_seconds=30.0)
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

    def _execute_virtual_trading_decision(self, symbol: str, signal: Dict, market_data: Dict, position_amount: float):
        """Исполняет виртуальное торговое решение"""
        try:
            # Получаем позиции из БД вместо памяти
            current_positions = self.db.get_virtual_open_positions(symbol)
            has_position = len(current_positions) > 0

            signal_action = signal['action']

            # Проверяем разрешены ли направления
            if signal_action == 'BUY' and not self.allow_long_positions:
                self.logger.info(
                    f"⏸️ Виртуальные лонг позиции отключены для {symbol}")
                return
            elif signal_action == 'SELL' and not self.allow_short_positions:
                self.logger.info(
                    f"⏸️ Виртуальные шорт позиции отключены для {symbol}")
                return

            if signal_action == 'BUY':
                if not has_position:
                    # Нет позиций - открываем виртуальный лонг
                    self._execute_virtual_buy(
                        symbol, signal, market_data, position_amount)
                elif self.auto_position_reversal:
                    # Есть позиция - проверяем направление
                    current_position = current_positions[0]
                    if current_position['side'] == 'SELL':
                        # Закрываем виртуальный шорт и открываем лонг
                        self.logger.info(
                            f"🔄 Виртуальный переворот позиции {symbol}: SELL → BUY")
                        self._close_virtual_position(
                            current_position, market_data['price'], "reversal")
                        time.sleep(1)
                        self._execute_virtual_buy(
                            symbol, signal, market_data, position_amount)

            elif signal_action == 'SELL':
                if not has_position:
                    # Нет позиций - открываем виртуальный шорт
                    self._execute_virtual_sell(
                        symbol, signal, market_data, position_amount)
                elif self.auto_position_reversal:
                    # Есть позиция - проверяем направление
                    current_position = current_positions[0]
                    if current_position['side'] == 'BUY':
                        # Закрываем виртуальный лонг и открываем шорт
                        self.logger.info(
                            f"🔄 Виртуальный переворот позиции {symbol}: BUY → SELL")
                        self._close_virtual_position(
                            current_position, market_data['price'], "reversal")
                        time.sleep(1)
                        self._execute_virtual_sell(
                            symbol, signal, market_data, position_amount)

        except Exception as e:
            self.logger.error(
                f"❌ Ошибка исполнения виртуальной сделки для {symbol}: {e}")

    def _send_virtual_trade_notification(self, action: str, position_id: int, signal: Dict, entry_price: float):
        """Отправляет уведомление о виртуальной сделке"""
        if not self.enable_notifications:
            return

        try:
            # Получаем информацию о балансе
            arrow, balance_change, balance_change_percent, highest, lowest = self.get_balance_change_info()

            message = f"""
🤖 *{action}*

🆔 *ID позиции:* #{position_id} (ВИРТУАЛЬНАЯ)
💹 *Символ:* {signal.get('symbol', 'N/A')}
💰 *Виртуальный баланс:* {self.current_balance:.2f} USDT
{arrow} *Изменение:* {balance_change:+.2f} USDT ({balance_change_percent:+.2f}%)
📊 *Начальный баланс:* {self.initial_balance:.2f} USDT
💵 *Размер позиции:* {signal.get('position_size', 'N/A')}
🔢 *Леверидж:* {self.leverage}x
💸 *Цена входа:* ${entry_price:.2f}

🎯 *Сигнал AI:* {signal.get('action', 'N/A')}
⭐ *Уверенность:* {signal.get('confidence', 0):.2f}
💭 *Причина:* {signal.get('reason', 'N/A')}

⏰ *Время (МСК):* {self._get_moscow_time().strftime("%H:%M:%S")}
📅 *Дата:* {self._get_moscow_time().strftime("%d.%m.%Y")}

*⚠️ ВНИМАНИЕ: Это виртуальная сделка!*
"""

            # Отправляем сообщение всем пользователям
            self._broadcast_message(message)

        except Exception as e:
            self.logger.warning(
                f"Не удалось отправить уведомление о виртуальной сделке: {e}")

    def _send_virtual_position_closed_notification(self, position: Dict, close_price: float):
        """Отправка уведомления о закрытии виртуальной позиции"""
        if not self.enable_notifications:
            return

        try:
            # Получаем актуальную статистику из БД
            stats = self.db.get_virtual_trade_stats(365)
            total_pnl = stats.get('total_realized_pnl', 0) or 0
            total_trades = stats.get('total_trades', 0) or 0
            
            # Рассчитываем PnL
            pnl = position.get('realized_pnl', 0)
            pnl_percent = (
                pnl / (position['entry_price'] * position['size'])) * 100 if position['entry_price'] * position['size'] > 0 else 0

            moscow_time = self._get_moscow_time()
            pnl_emoji = "📈" if pnl >= 0 else "📉"

            message = f"""
🔒 *ВИРТУАЛЬНАЯ ПОЗИЦИЯ ЗАКРЫТА*

🆔 *ID:* #{position['id']} (ВИРТУАЛЬНАЯ)
💹 *Символ:* {position['symbol']}
📊 *Сторона:* {position['side']}
💵 *Цена входа:* ${position['entry_price']:.2f}
💰 *Цена выхода:* ${close_price:.2f}
{pnl_emoji} *P&L:* {pnl:.2f} USDT ({pnl_percent:.2f}%)
🔢 *Размер:* {position['size']:.4f}
⚡ *Леверидж:* {position['leverage']}x
📝 *Причина:* {position.get('close_reason', 'N/A')}

💰 *Общий виртуальный PnL:* {total_pnl:.2f} USDT
🔢 *Всего виртуальных сделок:* {total_trades}

⏰ *Время (МСК):* {moscow_time.strftime("%H:%M:%S")}
📅 *Дата:* {moscow_time.strftime("%d.%m.%Y")}

*⚠️ ВНИМАНИЕ: Это виртуальная позиция!*
"""

            # Отправляем сообщение всем пользователям
            self._broadcast_message(message)

        except Exception as e:
            self.logger.warning(
                f"Не удалось отправить уведомление о закрытии виртуальной позиции: {e}")

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
        """Остановка виртуального бота"""
        self.logger.info("✅ Виртуальный бот остановлен")

    def _load_virtual_positions_from_db(self):
        """Загрузка виртуальных позиций из базы данных"""
        try:
            # Эта функция может понадобиться для инициализации, но основные данные будем брать напрямую из БД
            self.logger.info(
                "✅ Виртуальные позиции будут загружаться из БД по мере необходимости")
        except Exception as e:
            self.logger.error(
                f"❌ Ошибка загрузки виртуальных позиций из БД: {e}")

    @log_performance(threshold_seconds=5.0)
    def _update_virtual_balance(self):
        """Обновляет виртуальный баланс на основе открытых виртуальных позиций из БД"""
        try:
            # Получаем открытые позиции из БД
            open_positions = self.db.get_virtual_open_positions()
            total_unrealized_pnl = 0.0

            for position in open_positions:
                # Получаем текущую цену
                market_data = self.bybit.get_market_data(position['symbol'])
                if market_data:
                    current_price = market_data['price']
                    # Обновляем цену в БД
                    self.db.update_virtual_position_price(
                        position['id'], current_price)

                    # Расчет PnL
                    if position['side'] == 'BUY':
                        pnl = (current_price -
                               position['entry_price']) * position['size']
                    else:  # SELL
                        pnl = (position['entry_price'] -
                               current_price) * position['size']

                    total_unrealized_pnl += pnl

            # Получаем реализованный PnL из БД
            stats = self.db.get_virtual_trade_stats(365)  # За последний год
            total_realized_pnl = stats.get('total_realized_pnl', 0) or 0

            # Виртуальный баланс = начальный баланс + реализованный PnL + нереализованный PnL
            self.current_balance = self.initial_balance + \
                total_realized_pnl + total_unrealized_pnl

            # Обновляем максимальный и минимальный баланс
            if self.current_balance > self.highest_balance:
                self.highest_balance = self.current_balance
            if self.current_balance < self.lowest_balance:
                self.lowest_balance = self.current_balance

        except Exception as e:
            self.logger.error(f"❌ Ошибка обновления виртуального баланса: {e}")

    def _execute_virtual_buy(self, symbol: str, signal: Dict, market_data: Dict, position_amount: float):
        """Исполняет виртуальную покупку с записью в БД"""
        self.logger.info(f"🎯 Исполняем ВИРТУАЛЬНЫЙ BUY сигнал для {symbol}")

        entry_price = market_data['price']
        stop_loss, take_profit = self.calculate_stop_loss_take_profit(
            entry_price, "BUY")

        # Рассчитываем количество контрактов
        quantity = position_amount / entry_price

        # Создаем виртуальную позицию в БД
        position_id = self.db.add_virtual_position(
            symbol=symbol,
            side='BUY',
            size=quantity,
            entry_price=entry_price,
            leverage=self.leverage,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        if position_id:
            # Отправляем уведомление
            self._send_virtual_trade_notification(
                "🟢 ВИРТУАЛЬНАЯ ПОКУПКА", position_id, signal, entry_price)

            # Логируем сделку
            if self.enable_trade_logging:
                self.db.log_trade_event(
                    level='INFO',
                    message=f"VIRTUAL BUY position opened for {symbol}",
                    symbol=symbol,
                    position_id=position_id,
                    trade_action='VIRTUAL_BUY',
                    confidence=signal.get('confidence')
                )
        else:
            self.logger.error(
                f"❌ Не удалось создать виртуальную позицию для {symbol}")

    def _execute_virtual_sell(self, symbol: str, signal: Dict, market_data: Dict, position_amount: float):
        """Исполняет виртуальную продажу с записью в БД"""
        self.logger.info(f"🎯 Исполняем ВИРТУАЛЬНЫЙ SELL сигнал для {symbol}")

        entry_price = market_data['price']
        stop_loss, take_profit = self.calculate_stop_loss_take_profit(
            entry_price, "SELL")

        # Рассчитываем количество контрактов
        quantity = position_amount / entry_price

        # Создаем виртуальную позицию в БД
        position_id = self.db.add_virtual_position(
            symbol=symbol,
            side='SELL',
            size=quantity,
            entry_price=entry_price,
            leverage=self.leverage,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        if position_id:
            # Отправляем уведомление
            self._send_virtual_trade_notification(
                "🔴 ВИРТУАЛЬНАЯ ПРОДАЖА", position_id, signal, entry_price)

            # Логируем сделку
            if self.enable_trade_logging:
                self.db.log_trade_event(
                    level='INFO',
                    message=f"VIRTUAL SELL position opened for {symbol}",
                    symbol=symbol,
                    position_id=position_id,
                    trade_action='VIRTUAL_SELL',
                    confidence=signal.get('confidence')
                )
        else:
            self.logger.error(
                f"❌ Не удалось создать виртуальную позицию для {symbol}")

    def _close_virtual_position(self, position: Dict, exit_price: float, reason: str):
        """Закрытие виртуальной позиции с записью в БД"""
        try:
            # Закрываем позицию в БД
            self.db.close_virtual_position(position['id'], exit_price, reason)

            self.logger.info(
                f"✅ Виртуальная позиция #{position['id']} закрыта. Причина: {reason}")

            # Отправляем уведомление о закрытии
            self._send_virtual_position_closed_notification(
                position, exit_price)

            # Логируем закрытие
            if self.enable_trade_logging:
                # Получаем актуальные данные позиции из БД
                updated_position = self.db.get_virtual_position(position['id'])
                if updated_position:
                    pnl = updated_position.get('realized_pnl', 0)
                    self.db.log_trade_event(
                        level='INFO',
                        message=f"VIRTUAL position closed: {position['side']} {position['symbol']}",
                        symbol=position['symbol'],
                        position_id=position['id'],
                        trade_action='VIRTUAL_CLOSE',
                        pnl=pnl
                    )

        except Exception as e:
            self.logger.error(f"❌ Ошибка закрытия виртуальной позиции: {e}")

    def get_virtual_positions(self):
        """Возвращает список виртуальных позиций из БД"""
        return self.db.get_virtual_open_positions()

    def get_virtual_stats(self):
        """Возвращает статистику виртуальной торговли из БД"""
        stats = self.db.get_virtual_trade_stats(365)  # Статистика за год
        open_positions = self.get_virtual_positions()

        return {
            'initial_balance': self.initial_balance,
            'current_balance': self.current_balance,
            'total_realized_pnl': stats.get('total_realized_pnl', 0) or 0,
            'total_unrealized_pnl': stats.get('total_unrealized_pnl', 0) or 0,
            'total_trades': stats.get('total_trades', 0) or 0,
            'closed_trades': stats.get('closed_trades', 0) or 0,
            'open_positions': len(open_positions),
            'winning_trades': stats.get('winning_trades', 0) or 0,
            'losing_trades': stats.get('losing_trades', 0) or 0,
            'avg_pnl_percent': stats.get('avg_pnl_percent', 0) or 0,
            'highest_balance': self.highest_balance,
            'lowest_balance': self.lowest_balance
        }
