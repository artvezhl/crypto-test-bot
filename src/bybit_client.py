from pybit.unified_trading import HTTP, WebSocket
from config import Config
import json
import logging
from typing import Dict, Optional, Callable
import threading
import time


class BybitClient:
    def __init__(self):
        self.session = HTTP(
            testnet=Config.BYBIT_TESTNET,
            api_key=Config.BYBIT_API_KEY,
            api_secret=Config.BYBIT_API_SECRET
        )
        self.logger = logging.getLogger(__name__)
        self.ws = None
        self.position_handlers = []
        self.order_handlers = []
        self.is_ws_running = False

    def get_market_data(self, symbol="ETHUSDT"):
        """Получаем рыночные данные для анализа"""
        try:
            # Для маржинальной торговли используем linear категорию
            ticker = self.session.get_tickers(category="linear", symbol=symbol)

            kline = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval="15",
                limit=100
            )

            if ('result' in ticker and 'list' in ticker['result'] and
                len(ticker['result']['list']) > 0 and
                    'result' in kline and 'list' in kline['result']):

                ticker_data = ticker['result']['list'][0]
                prices = [float(item[4]) for item in kline['result']['list']]

                return {
                    'symbol': symbol,
                    'price': float(ticker_data.get('lastPrice', 0)),
                    'price_change_24h': float(ticker_data.get('price24hPcnt', 0)) * 100,
                    'volume_24h': float(ticker_data.get('volume24h', 0)),
                    'historical_prices': prices
                }
            else:
                self.logger.error("Unexpected API response structure")
                return {}

        except Exception as e:
            self.logger.error(f"Ошибка получения данных с Bybit: {e}")
            return {}

    def get_symbol_info(self, symbol: str) -> Dict | None:
        """Получение информации о символе, включая минимальные лимиты"""
        try:
            response = self.session.get_instruments_info(
                category="linear",
                symbol=symbol
            )

            if response and 'result' in response and 'list' in response['result']:
                symbol_info = response['result']['list'][0]
                self.logger.info(
                    f"📊 Информация о символе {symbol}: {symbol_info}")
                return symbol_info
            return None

        except Exception as e:
            self.logger.error(f"❌ Ошибка получения информации о символе: {e}")
            return None

    def get_min_order_qty(self, symbol: str) -> float:
        """Получение минимального количества для ордера"""
        try:
            symbol_info = self.get_symbol_info(symbol)
            if symbol_info and 'lotSizeFilter' in symbol_info:
                min_qty = float(symbol_info['lotSizeFilter']['minOrderQty'])
                self.logger.info(
                    f"📊 Минимальный размер ордера для {symbol}: {min_qty}")
                return min_qty
            return 0.01  # Значение по умолчанию
        except Exception as e:
            self.logger.error(
                f"❌ Ошибка получения минимального размера ордера: {e}")
            return 0.01

    def place_order(self, symbol: str, side: str, qty: float, order_type: str = "Market",
                    leverage: int = 5, stop_loss: float | None = None, take_profit: float | None = None):
        """Размещаем ордер на Bybit с проверкой минимальных лимитов"""
        try:
            # Проверяем минимальное количество
            min_qty = self.get_min_order_qty(symbol)
            if qty < min_qty:
                self.logger.error(
                    f"❌ Количество {qty} меньше минимального {min_qty} для {symbol}")
                return None

            # Сначала устанавливаем леверидж
            self.set_leverage(symbol, leverage)

            # Базовые параметры ордера
            order_params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": "{qty:.2f}",
                "timeInForce": "GTC",
            }

            # Добавляем стоп-лосс и тейк-профит если указаны
            if stop_loss:
                order_params["stopLoss"] = "{stop_loss:.2f}"
            if take_profit:
                order_params["takeProfit"] = "{take_profit:.2f}"

            self.logger.info(f"📊 Параметры ордера: {order_params}")
            order = self.session.place_order(**order_params)

            if order and 'result' in order:
                self.logger.info(f"✅ Ордер размещен: {order['result']}")
                return order['result']
            else:
                self.logger.error(f"❌ Ошибка ордера: {order}")
                return None

        except Exception as e:
            self.logger.error(f"❌ Ошибка размещения ордера: {e}")
            return None

    def set_leverage(self, symbol: str, leverage: int):
        """Установка левериджа"""
        try:
            self.session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage)
            )
            self.logger.info(
                f"✅ Леверидж установлен: {leverage}x для {symbol}")
        except Exception as e:
            self.logger.error(f"❌ Ошибка установки левериджа: {e}")

    def get_positions(self, symbol: str | None = None):
        """Получение открытых позиций"""
        try:
            params = {"category": "linear"}
            if symbol:
                params["symbol"] = symbol

            positions = self.session.get_positions(**params)

            if positions and 'result' in positions and positions['result']['list']:
                return positions['result']['list']
            return []
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения позиций: {e}")
            return []

    def close_position(self, symbol: str, side: str | None = None):
        """Закрытие позиции"""
        try:
            params = {
                "category": "linear",
                "symbol": symbol,
                "orderType": "Market"
            }

            if side:
                params["side"] = "Buy" if side == "Sell" else "Sell"

            result = self.session.close_position(**params)

            if result and 'result' in result:
                self.logger.info(f"✅ Позиция закрыта: {symbol}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"❌ Ошибка закрытия позиции: {e}")
            return False

    def get_wallet_balance(self, account_type: str = "UNIFIED"):
        """Получение баланса"""
        try:
            balance = self.session.get_wallet_balance(accountType=account_type)

            if balance and 'result' in balance and balance['result']['list']:
                account_data = balance['result']['list'][0]

                total_equity = float(account_data.get('totalEquity', 0))
                total_wallet_balance = float(
                    account_data.get('totalWalletBalance', 0))

                # Расчет доступного баланса
                total_available_balance = total_wallet_balance

                # Получаем USDT баланс
                usdt_balance: float = 0
                if 'coin' in account_data:
                    for coin in account_data['coin']:
                        if coin['coin'] == 'USDT':
                            usdt_balance = float(
                                coin.get('walletBalance', '0'))
                            break

                return {
                    'total_equity': total_equity,
                    'total_wallet_balance': total_wallet_balance,
                    'total_available_balance': total_available_balance,
                    'usdt_balance': usdt_balance,
                    'account_type': account_type
                }

            return {
                'total_equity': 0,
                'total_wallet_balance': 0,
                'total_available_balance': 0,
                'usdt_balance': 0,
                'account_type': account_type
            }

        except Exception as e:
            self.logger.error(f"❌ Ошибка получения баланса: {e}")
            return {
                'total_equity': 0,
                'total_wallet_balance': 0,
                'total_available_balance': 0,
                'usdt_balance': 0,
                'account_type': account_type
            }

    def add_position_handler(self, handler: Callable):
        """Добавление обработчика изменений позиций"""
        self.position_handlers.append(handler)

    def add_order_handler(self, handler: Callable):
        """Добавление обработчика изменений ордеров"""
        self.order_handlers.append(handler)

    def _handle_position_update(self, message):
        """Обработка обновлений позиций из WebSocket"""
        try:
            if 'data' in message:
                for position_data in message['data']:
                    self.logger.info(f"📡 WebSocket позиция: {position_data}")
                    for handler in self.position_handlers:
                        try:
                            handler(position_data)
                        except Exception as e:
                            self.logger.error(
                                f"Ошибка в обработчике позиции: {e}")
        except Exception as e:
            self.logger.error(f"Ошибка обработки позиции WebSocket: {e}")

    def _handle_order_update(self, message):
        """Обработка обновлений ордеров из WebSocket"""
        try:
            if 'data' in message:
                for order_data in message['data']:
                    self.logger.info(f"📡 WebSocket ордер: {order_data}")
                    for handler in self.order_handlers:
                        try:
                            handler(order_data)
                        except Exception as e:
                            self.logger.error(
                                f"Ошибка в обработчике ордера: {e}")
        except Exception as e:
            self.logger.error(f"Ошибка обработки ордера WebSocket: {e}")

    def start_websocket(self):
        """Запуск WebSocket соединения"""
        if self.is_ws_running:
            return

        try:
            self.ws = WebSocket(
                testnet=Config.BYBIT_TESTNET,
                channel_type="private",
                api_key=Config.BYBIT_API_KEY,
                api_secret=Config.BYBIT_API_SECRET,
                trace_logging=True
            )

            # Подписываемся на позиции и ордера
            self.ws.position_stream(callback=self._handle_position_update)
            self.ws.order_stream(callback=self._handle_order_update)

            self.is_ws_running = True
            self.logger.info(
                "✅ WebSocket подключен для отслеживания позиций и ордеров")

            # Запускаем в отдельном потоке для поддержания соединения
            def keep_alive():
                while self.is_ws_running:
                    time.sleep(10)

            thread = threading.Thread(target=keep_alive, daemon=True)
            thread.start()

        except Exception as e:
            self.logger.error(f"❌ Ошибка запуска WebSocket: {e}")

    def stop_websocket(self):
        """Остановка WebSocket соединения"""
        self.is_ws_running = False
        if self.ws:
            try:
                self.ws.close()
                self.logger.info("✅ WebSocket отключен")
            except Exception as e:
                self.logger.error(f"Ошибка отключения WebSocket: {e}")
