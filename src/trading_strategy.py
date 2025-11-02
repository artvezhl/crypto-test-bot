import pytz
from deepseek_client import DeepSeekClient
from bybit_client import BybitClient
from config import Config
import time
import logging
import json
from datetime import datetime


class TradingBot:
    def __init__(self):
        self.deepseek = DeepSeekClient()
        self.bybit = BybitClient()
        self.symbol = Config.DEFAULT_SYMBOL
        self.min_confidence = Config.MIN_CONFIDENCE

        # Настройки риск-менеджмента
        self.risk_percent = Config.RISK_PERCENT
        self.max_position_percent = Config.MAX_POSITION_PERCENT
        self.min_trade_usdt = Config.MIN_TRADE_USDT

        # Трекер состояния
        self.positions = []
        self.balance_info = {}

        # Начальный баланс (захардкоженный)
        # Добавьте эту переменную в config.py
        self.initial_balance = Config.INITIAL_BALANCE
        # Для отслеживания максимального баланса
        self.highest_balance = self.initial_balance
        # Для отслеживания минимального баланса
        self.lowest_balance = self.initial_balance

        # Настройка логирования
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        self.logger.info(
            f"🔧 Инициализирован бот с риск-менеджментом: {self.risk_percent}% риска на сделку")
        self.logger.info(
            f"💰 Начальный баланс: {self.initial_balance:.2f} USDT")

    def update_balance(self):
        """Обновляем информацию о балансе - пробуем оба метода"""
        try:
            # Пробуем получить баланс UNIFIED аккаунта
            unified_balance = self.bybit.get_unified_balance()

            # Если в UNIFIED нет баланса, пробуем SPOT
            if unified_balance['total_equity'] <= 0 and unified_balance['usdt_balance'] <= 0:
                self.logger.info("🔄 UNIFIED баланс пустой, проверяем SPOT...")
                spot_balance = self.bybit.get_spot_balance()

                if spot_balance['total_equity'] > 0:
                    self.balance_info = {
                        'source': 'SPOT',
                        'total_equity': spot_balance['total_equity'],
                        'total_available': spot_balance['total_available_balance'],
                        'usdt_balance': spot_balance['usdt_balance'],
                        'full_info': spot_balance
                    }
                else:
                    self.balance_info = {
                        'source': 'UNIFIED',
                        'total_equity': unified_balance['total_equity'],
                        'total_available': unified_balance['total_available_balance'],
                        'usdt_balance': unified_balance['usdt_balance'],
                        'full_info': unified_balance
                    }
            else:
                self.balance_info = {
                    'source': 'UNIFIED',
                    'total_equity': unified_balance['total_equity'],
                    'total_available': unified_balance['total_available_balance'],
                    'usdt_balance': unified_balance['usdt_balance'],
                    'full_info': unified_balance
                }

            # Обновляем максимальный и минимальный баланс
            current_balance = self.balance_info['total_equity']
            if current_balance > self.highest_balance:
                self.highest_balance = current_balance
            if current_balance < self.lowest_balance:
                self.lowest_balance = current_balance

            self.logger.info(
                f"💰 Баланс [{self.balance_info['source']}]: {self.balance_info['total_equity']:.2f} USDT (доступно: {self.balance_info['total_available']:.2f} USDT)")
            return True

        except Exception as e:
            self.logger.error(f"Ошибка обновления баланса: {e}")
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

    def get_trading_balance(self):
        """Возвращает баланс для торговли с приоритетом доступного"""
        if not self.balance_info:
            return 0

        # Используем доступный баланс, если он есть, иначе общий equity
        if self.balance_info['total_available'] > 0:
            return self.balance_info['total_available']
        else:
            return self.balance_info['total_equity']

    def calculate_position_size(self, market_price):
        """Рассчитываем размер позиции на основе риск-менеджмента"""
        if not self.update_balance():
            return 0

        trading_balance = self.get_trading_balance()

        if trading_balance <= 0:
            self.logger.error("❌ Баланс для торговли равен 0")
            return 0

        # Рассчитываем сумму для сделки на основе процента риска
        risk_amount = trading_balance * (self.risk_percent / 100)

        # Ограничиваем максимальный размер позиции
        max_position_amount = trading_balance * \
            (self.max_position_percent / 100)
        position_amount = min(risk_amount, max_position_amount)

        # Проверяем минимальную сумму
        if position_amount < self.min_trade_usdt:
            self.logger.warning(
                f"⚠️ Расчетная сумма сделки {position_amount:.2f} USDT меньше минимальной {self.min_trade_usdt} USDT")
            return 0

        # Для quoteCoin ордеров проверяем, что сумма не меньше минимальной для Bybit
        min_bybit_amount = 10  # Минимум 10 USDT для Bybit
        if position_amount < min_bybit_amount:
            self.logger.warning(
                f"⚠️ Сумма сделки {position_amount:.2f} USDT меньше минимальной для Bybit {min_bybit_amount} USDT")
            return 0

        self.logger.info(
            f"📊 Расчет позиции: {position_amount:.2f} USDT ({self.risk_percent}% от баланса {trading_balance:.2f} USDT)")
        return position_amount

    def run_iteration(self):
        """Одна итерация торгового цикла"""
        iteration_start = time.time()

        try:
            # 0. Обновляем баланс
            if not self.update_balance():
                self.logger.error(
                    "❌ Не удалось обновить баланс, пропускаем итерацию")
                return

            trading_balance = self.get_trading_balance()
            if trading_balance <= 0:
                self.logger.error("❌ Нет средств для торговли")
                self._send_balance_report(
                    None, None, "Нет средств для торговли")
                return

            # 1. Получаем рыночные данные
            self.logger.info("📊 Получение рыночных данных...")
            market_data = self.bybit.get_market_data(self.symbol)
            if not market_data:
                self.logger.error("Не удалось получить рыночные данные")
                return

            # 2. Получаем сигнал от DeepSeek
            self.logger.info("🧠 Анализ с помощью DeepSeek...")
            signal = self.deepseek.get_trading_signal(market_data)
            self.logger.info(f"Получен сигнал: {signal}")

            # 3. Рассчитываем размер позиции
            position_amount = self.calculate_position_size(
                market_data['price'])
            if position_amount <= 0:
                self.logger.warning(
                    "❌ Не удалось рассчитать размер позиции, пропускаем сделку")
                self._send_balance_report(
                    market_data, signal, "Пропуск сделки - недостаточно средств или маленькая сумма")
                return

            # 4. Проверяем уверенность и исполняем сделку
            if signal['confidence'] > self.min_confidence:
                self._execute_trading_decision(
                    signal, market_data, position_amount)
            else:
                self.logger.info(
                    f"Сигнал отклонен: уверенность {signal['confidence']} ниже порога {self.min_confidence}")
                self._send_balance_report(
                    market_data, signal, "Пропуск сделки - низкая уверенность")

            # 5. Логируем результат
            self._log_trading_action(market_data, signal, position_amount)

        except Exception as e:
            self.logger.error(f"Ошибка в торговой итерации: {e}")
            import traceback
            traceback.print_exc()

    def _execute_trading_decision(self, signal, market_data, position_amount):
        """Исполняет торговое решение"""
        try:
            if signal['action'] == 'BUY':
                self._execute_buy(signal, market_data, position_amount)
            elif signal['action'] == 'SELL':
                self._execute_sell(signal, market_data, position_amount)
            elif signal['action'] == 'HOLD':
                self.logger.info("Сигнал HOLD - бездействуем")
                self._send_balance_report(
                    market_data, signal, "Удержание позиции")
            else:
                self.logger.warning(
                    f"Неизвестное действие: {signal['action']}")

        except Exception as e:
            self.logger.error(f"Ошибка исполнения сделки: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _execute_buy(self, signal, market_data, position_amount):
        """Исполняет покупку"""
        self.logger.info(
            f"🎯 Исполняем BUY сигнал (уверенность: {signal['confidence']}, сумма: {position_amount:.2f} USDT)")

        # Проверяем, нет ли уже открытой позиции
        if self._has_open_position():
            self.logger.info("⏸️ Пропускаем BUY - уже есть открытая позиция")
            self._send_balance_report(
                market_data, signal, "Пропуск покупки - позиция уже открыта")
            return

        # Используем quoteCoin - покупаем на рассчитанную сумму в USDT
        order = self.bybit.place_order(
            symbol=self.symbol,
            side="Buy",
            qty=position_amount,
            market_unit="quoteCoin"  # Указываем, что qty - это сумма в USDT
        )

        if order:
            # Рассчитываем примерное количество купленного ETH
            eth_amount = position_amount / market_data['price']

            self.logger.info(
                f"✅ Куплено на {position_amount:.2f} USDT (~{eth_amount:.6f} ETH)")

            # Записываем позицию
            position = {
                'symbol': self.symbol,
                'side': 'BUY',
                'size_usdt': position_amount,
                'size_eth': eth_amount,
                'entry_price': market_data['price'],
                'timestamp': datetime.now().isoformat(),
                'signal': signal
            }
            self.positions.append(position)

            # Обновляем баланс после сделки
            self.update_balance()

            # Отправляем уведомление в Telegram
            self._send_trade_notification("🟢 ПОКУПКА", position, signal)
        else:
            self.logger.error("❌ Не удалось разместить ордер на покупку")
            self._send_error_notification(
                f"Не удалось разместить ордер на покупку {position_amount:.2f} USDT")

    def _execute_sell(self, signal, market_data, position_amount):
        """Исполняет продажу"""
        self.logger.info(
            f"🎯 Исполняем SELL сигнал (уверенность: {signal['confidence']})")

        # Проверяем, есть ли открытая позиция для продажи
        if not self._has_open_position():
            self.logger.info("⏸️ Пропускаем SELL - нет открытой позиции")
            self._send_balance_report(
                market_data, signal, "Пропуск продажи - нет открытой позиции")
            return

        # Используем размер последней позиции в ETH
        position = self.positions[-1] if self.positions else None
        if not position:
            self.logger.error("❌ Нет данных о позиции для продажи")
            return

        # Продаем всё количество ETH из позиции
        order = self.bybit.place_order(
            symbol=self.symbol,
            side="Sell",
            qty=position['size_eth'],  # Количество ETH для продажи
            market_unit="baseCoin"  # Указываем, что qty - это количество монет
        )

        if order:
            # Рассчитываем P&L
            pnl = (market_data['price'] -
                   position['entry_price']) * position['size_eth']
            pnl_percent = (
                (market_data['price'] - position['entry_price']) / position['entry_price']) * 100

            self.logger.info(
                f"✅ Продано {position['size_eth']:.6f} {self.symbol} (P&L: {pnl:.2f} USDT, {pnl_percent:.2f}%)")

            # Закрываем позицию
            closed_position = self.positions.pop()

            # Обновляем баланс после сделки
            self.update_balance()

            # Отправляем уведомление в Telegram
            self._send_trade_notification("🔴 ПРОДАЖА", {
                'symbol': self.symbol,
                'side': 'SELL',
                'size_eth': position['size_eth'],
                'size_usdt': position['size_usdt'],
                'entry_price': position['entry_price'],
                'exit_price': market_data['price'],
                'pnl': pnl,
                'pnl_percent': pnl_percent,
                'timestamp': datetime.now().isoformat(),
                'signal': signal
            }, signal)
        else:
            self.logger.error("❌ Не удалось разместить ордер на продажу")
            self._send_error_notification(
                f"Не удалось разместить ордер на продажу {position['size_eth']:.6f} ETH")

    def _has_open_position(self):
        """Проверяет, есть ли открытая позиция"""
        return len(self.positions) > 0

    def _log_trading_action(self, market_data, signal, position_amount):
        """Логирует торговое действие"""
        trading_balance = self.get_trading_balance()
        arrow, balance_change, balance_change_percent, highest, lowest = self.get_balance_change_info()

        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'symbol': self.symbol,
            'price': market_data['price'],
            'signal': signal,
            'position_amount': position_amount,
            'trading_balance': trading_balance,
            'balance_source': self.balance_info.get('source', 'unknown'),
            'open_positions': len(self.positions),
            'balance_change': balance_change,
            'balance_change_percent': balance_change_percent,
            'highest_balance': highest,
            'lowest_balance': lowest
        }
        self.logger.info(f"Торговая запись: {log_entry}")

    def _get_moscow_time(self):
        """Возвращает текущее время по Москве"""
        try:
            moscow_tz = pytz.timezone('Europe/Moscow')
            return datetime.now(moscow_tz)
        except:
            # Если pytz не работает, возвращаем UTC+3
            from datetime import timedelta
            return datetime.utcnow() + timedelta(hours=3)

    def _send_trade_notification(self, action, position, signal):
        """Отправляет уведомление о сделке в Telegram"""
        try:
            import requests
            from config import Config

            token = Config.TELEGRAM_BOT_TOKEN
            chat_id = Config.TELEGRAM_CHAT_ID

            if not token or token == "your_telegram_token":
                return

            trading_balance = self.get_trading_balance()
            balance_source = self.balance_info.get('source', 'UNKNOWN')
            moscow_time = self._get_moscow_time()

            # Получаем информацию об изменении баланса
            arrow, balance_change, balance_change_percent, highest, lowest = self.get_balance_change_info()

            if action == "🟢 ПОКУПКА":
                message = f"""
{action}

💹 *Символ:* {position['symbol']}
💰 *Текущий баланс:* {trading_balance:.2f} USDT ({balance_source})
{arrow} *Изменение:* {balance_change:+.2f} USDT ({balance_change_percent:+.2f}%)
📊 *Начальный баланс:* {self.initial_balance:.2f} USDT
💵 *Сумма сделки:* {position['size_usdt']:.2f} USDT
📊 *Размер позиции:* {self.risk_percent}% от баланса
🪙 *Количество:* {position['size_eth']:.6f} ETH
💸 *Цена входа:* ${position['entry_price']:.2f}

🎯 *Сигнал AI:* {signal['action']}
⭐ *Уверенность:* {signal['confidence']:.2f}
💭 *Причина:* {signal['reason']}

⏰ *Время (МСК):* {moscow_time.strftime("%H:%M:%S")}
📅 *Дата:* {moscow_time.strftime("%d.%m.%Y")}
"""
            else:
                # Для продажи
                pnl_emoji = "📈" if position['pnl'] >= 0 else "📉"
                message = f"""
{action}

💹 *Символ:* {position['symbol']}
💰 *Текущий баланс:* {trading_balance:.2f} USDT ({balance_source})
{arrow} *Изменение:* {balance_change:+.2f} USDT ({balance_change_percent:+.2f}%)
📊 *Начальный баланс:* {self.initial_balance:.2f} USDT
🪙 *Количество:* {position['size_eth']:.6f} ETH
💸 *Цена входа:* ${position['entry_price']:.2f}
💰 *Цена выхода:* ${position['exit_price']:.2f}
{pnl_emoji} *P&L:* {position['pnl']:.2f} USDT ({position['pnl_percent']:.2f}%)

🎯 *Сигнал AI:* {signal['action']}
⭐ *Уверенность:* {signal['confidence']:.2f}
💭 *Причина:* {signal['reason']}

⏰ *Время (МСК):* {moscow_time.strftime("%H:%M:%S")}
📅 *Дата:* {moscow_time.strftime("%d.%m.%Y")}
"""

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }

            requests.post(url, json=payload, timeout=10)

        except Exception as e:
            self.logger.warning(
                f"Не удалось отправить уведомление о сделке: {e}")

    def _send_balance_report(self, market_data, signal, status):
        """Отправляет отчет о балансе без сделки"""
        try:
            import requests
            from config import Config

            token = Config.TELEGRAM_BOT_TOKEN
            chat_id = Config.TELEGRAM_CHAT_ID

            if not token or token == "your_telegram_token":
                return

            trading_balance = self.get_trading_balance()
            balance_source = self.balance_info.get('source', 'UNKNOWN')
            moscow_time = self._get_moscow_time()

            # Получаем информацию об изменении баланса
            arrow, balance_change, balance_change_percent, highest, lowest = self.get_balance_change_info()

            price_info = ""
            if market_data:
                price_info = f"📈 *Цена:* ${market_data['price']:.2f}\n"

            signal_info = ""
            if signal:
                signal_info = f"""
🎯 *Сигнал AI:* {signal['action']}
⭐ *Уверенность:* {signal['confidence']:.2f}
💭 *Причина:* {signal['reason']}
"""

            message = f"""
📊 *ОТЧЕТ О БАЛАНСЕ*

💹 *Символ:* {self.symbol}
💰 *Текущий баланс:* {trading_balance:.2f} USDT ({balance_source})
{arrow} *Изменение:* {balance_change:+.2f} USDT ({balance_change_percent:+.2f}%)
📊 *Начальный баланс:* {self.initial_balance:.2f} USDT
📈 *Максимальный баланс:* {highest:.2f} USDT
📉 *Минимальный баланс:* {lowest:.2f} USDT
{price_info}
📊 *Размер позиции:* {self.risk_percent}% от баланса
{signal_info}
📋 *Статус:* {status}

⏰ *Время (МСК):* {moscow_time.strftime("%H:%M:%S")}
📅 *Дата:* {moscow_time.strftime("%d.%m.%Y")}
"""

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }

            requests.post(url, json=payload, timeout=10)

        except Exception as e:
            self.logger.warning(f"Не удалось отправить отчет о балансе: {e}")

    def _send_error_notification(self, error_message):
        """Отправляет уведомление об ошибке"""
        try:
            import requests
            from config import Config

            token = Config.TELEGRAM_BOT_TOKEN
            chat_id = Config.TELEGRAM_CHAT_ID

            if not token or token == "your_telegram_token":
                return

            trading_balance = self.get_trading_balance()
            balance_source = self.balance_info.get('source', 'UNKNOWN')
            moscow_time = self._get_moscow_time()

            # Получаем информацию об изменении баланса
            arrow, balance_change, balance_change_percent, highest, lowest = self.get_balance_change_info()

            message = f"""
🚨 *ОШИБКА ТОРГОВЛИ*

💹 *Символ:* {self.symbol}
💰 *Текущий баланс:* {trading_balance:.2f} USDT ({balance_source})
{arrow} *Изменение:* {balance_change:+.2f} USDT ({balance_change_percent:+.2f}%)
📊 *Начальный баланс:* {self.initial_balance:.2f} USDT

❌ *Ошибка:* {error_message}

⏰ *Время (МСК):* {moscow_time.strftime("%H:%M:%S")}
📅 *Дата:* {moscow_time.strftime("%d.%m.%Y")}
"""

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }

            requests.post(url, json=payload, timeout=10)

        except Exception as e:
            self.logger.error(
                f"Не удалось отправить уведомление об ошибке: {e}")
