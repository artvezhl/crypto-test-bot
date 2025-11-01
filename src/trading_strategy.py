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

        # УВЕЛИЧИВАЕМ размер позиции для соответствия минимальным требованиям Bybit
        self.position_size = 0.03  # 0.03 ETH ≈ 120 USDT при цене 4000
        self.min_confidence = 0.68

        # Трекер состояния
        self.positions = []

        # Настройка логирования
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        self.logger.info(
            f"🔧 Инициализирован бот с размером позиции: {self.position_size} ETH")

    def run_iteration(self):
        """Одна итерация торгового цикла"""
        iteration_start = time.time()

        try:
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

            # 3. Проверяем уверенность и исполняем сделку
            if signal['confidence'] > self.min_confidence:
                self._execute_trading_decision(signal, market_data)
            else:
                self.logger.info(
                    f"Сигнал отклонен: уверенность {signal['confidence']} ниже порога {self.min_confidence}")

            # 4. Логируем результат
            self._log_trading_action(market_data, signal)

        except Exception as e:
            self.logger.error(f"Ошибка в торговой итерации: {e}")
            import traceback
            traceback.print_exc()

    def _execute_trading_decision(self, signal, market_data):
        """Исполняет торговое решение"""
        try:
            # ПРОВЕРЯЕМ МИНИМАЛЬНУЮ СТОИМОСТЬ ОРДЕРА ПЕРЕД ИСПОЛНЕНИЕМ
            order_value = self.position_size * market_data['price']
            self.logger.info(
                f"💵 Расчетная стоимость ордера: ${order_value:.2f}")

            if order_value < 50:  # Bybit требует минимум ~50 USDT для ETH
                self.logger.warning(
                    f"⚠️ Стоимость ордера ${order_value:.2f} слишком мала. Минимум $50")
                return

            if signal['action'] == 'BUY':
                self._execute_buy(signal, market_data)
            elif signal['action'] == 'SELL':
                self._execute_sell(signal, market_data)
            elif signal['action'] == 'HOLD':
                self.logger.info("Сигнал HOLD - бездействуем")
            else:
                self.logger.warning(
                    f"Неизвестное действие: {signal['action']}")

        except Exception as e:
            self.logger.error(f"Ошибка исполнения сделки: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _execute_buy(self, signal, market_data):
        """Исполняет покупку"""
        self.logger.info(
            f"🎯 Исполняем BUY сигнал (уверенность: {signal['confidence']})")

        # Проверяем, нет ли уже открытой позиции
        if self._has_open_position():
            self.logger.info("⏸️ Пропускаем BUY - уже есть открытая позиция")
            return

        order = self.bybit.place_order(
            symbol=self.symbol,
            side="Buy",
            qty=self.position_size
        )

        if order:
            order_value = self.position_size * market_data['price']
            self.logger.info(
                f"✅ Куплено {self.position_size} {self.symbol} (${order_value:.2f})")

            # Записываем позицию
            position = {
                'symbol': self.symbol,
                'side': 'BUY',
                'size': self.position_size,
                'entry_price': market_data['price'],
                'timestamp': datetime.now().isoformat(),
                'signal': signal
            }
            self.positions.append(position)

            # Отправляем уведомление в Telegram
            self._send_trade_notification("🟢 ПОКУПКА", position, signal)
        else:
            self.logger.error("❌ Не удалось разместить ордер на покупку")

    def _execute_sell(self, signal, market_data):
        """Исполняет продажу"""
        self.logger.info(
            f"🎯 Исполняем SELL сигнал (уверенность: {signal['confidence']})")

        # Проверяем, есть ли открытая позиция для продажи
        if not self._has_open_position():
            self.logger.info("⏸️ Пропускаем SELL - нет открытой позиции")
            return

        # Используем размер последней позиции
        sell_size = self.positions[-1]['size'] if self.positions else self.position_size

        order = self.bybit.place_order(
            symbol=self.symbol,
            side="Sell",
            qty=sell_size
        )

        if order:
            order_value = sell_size * market_data['price']
            self.logger.info(
                f"✅ Продано {sell_size} {self.symbol} (${order_value:.2f})")

            # Закрываем позицию
            closed_position = self.positions.pop() if self.positions else None

            # Отправляем уведомление в Telegram
            self._send_trade_notification("🔴 ПРОДАЖА", {
                'symbol': self.symbol,
                'side': 'SELL',
                'size': sell_size,
                'exit_price': market_data['price'],
                'timestamp': datetime.now().isoformat(),
                'signal': signal
            }, signal)
        else:
            self.logger.error("❌ Не удалось разместить ордер на продажу")

    def _has_open_position(self):
        """Проверяет, есть ли открытая позиция"""
        return len(self.positions) > 0

    def _log_trading_action(self, market_data, signal):
        """Логирует торговое действие"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'symbol': self.symbol,
            'price': market_data['price'],
            'signal': signal,
            'position_size': self.position_size,
            'open_positions': len(self.positions)
        }
        self.logger.info(f"Торговая запись: {log_entry}")

    def _send_trade_notification(self, action, position, signal):
        """Отправляет уведомление о сделке в Telegram"""
        try:
            import requests
            from config import Config

            token = Config.TELEGRAM_BOT_TOKEN
            chat_id = Config.TELEGRAM_CHAT_ID

            if not token or token == "your_telegram_token":
                return

            price = position.get(
                'entry_price', position.get('exit_price', 'N/A'))
            order_value = position['size'] * \
                price if isinstance(price, (int, float)) else 'N/A'

            notification = f"""
{action}

💹 Символ: {position['symbol']}
📊 Размер: {position['size']}
💰 Цена: ${price}
💵 Стоимость: ${order_value if isinstance(order_value, (int, float)) else order_value}

🎯 Сигнал AI: {signal['action']}
⭐ Уверенность: {signal['confidence']:.2f}
💭 Причина: {signal['reason']}

⏰ Время: {datetime.now().strftime("%H:%M:%S")}
"""

            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': notification,
                'parse_mode': 'Markdown'
            }

            requests.post(url, json=payload, timeout=10)

        except Exception as e:
            self.logger.warning(
                f"Не удалось отправить уведомление о сделке: {e}")
