from pybit.unified_trading import HTTP, WebSocket
from config import Config
import json
import logging
from typing import Dict, Optional, Callable, List
import threading
import time
from datetime import datetime, timedelta


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

    def get_historical_klines(self, symbol: str, interval: str, start_time: int | None = None, 
                             end_time: int | None = None, limit: int = 200) -> List[Dict]:
        """
        Получение исторических свечей с Bybit API.
        
        Args:
            symbol: Торговая пара (например, 'BTCUSDT')
            interval: Таймфрейм ('1', '5', '15', '30', '60', '240', 'D', 'W')
            start_time: Начальная временная метка в миллисекундах (опционально)
            end_time: Конечная временная метка в миллисекундах (опционально)
            limit: Количество свечей за один запрос (макс 1000)
            
        Returns:
            List[Dict]: Список свечей с данными OHLCV
        """
        try:
            params = {
                "category": "linear",
                "symbol": symbol,
                "interval": interval,
                "limit": min(limit, 1000)  # Bybit лимит - 1000
            }
            
            if start_time:
                params["start"] = start_time
            if end_time:
                params["end"] = end_time
            
            self.logger.info(f"📊 Загрузка исторических данных для {symbol}, интервал: {interval}")
            response = self.session.get_kline(**params)
            
            if response and 'result' in response and 'list' in response['result']:
                klines = response['result']['list']
                self.logger.info(f"✅ Загружено {len(klines)} свечей для {symbol}")
                
                # Преобразуем данные в удобный формат
                formatted_klines = []
                for kline in klines:
                    # Формат Bybit: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
                    formatted_klines.append({
                        'timestamp': int(kline[0]),
                        'open': float(kline[1]),
                        'high': float(kline[2]),
                        'low': float(kline[3]),
                        'close': float(kline[4]),
                        'volume': float(kline[5]),
                        'turnover': float(kline[6]) if len(kline) > 6 else 0,
                        'datetime': datetime.fromtimestamp(int(kline[0]) / 1000).isoformat()
                    })
                
                return formatted_klines
            else:
                self.logger.error(f"❌ Неожиданная структура ответа API для {symbol}")
                return []
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка загрузки исторических данных для {symbol}: {e}")
            return []

    def get_historical_klines_range(self, symbol: str, interval: str, 
                                   start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        Загружает исторические свечи за указанный период с автоматической пагинацией.
        
        Args:
            symbol: Торговая пара
            interval: Таймфрейм
            start_date: Начальная дата
            end_date: Конечная дата
            
        Returns:
            List[Dict]: Полный список свечей за период
        """
        try:
            # Конвертируем даты в миллисекунды
            start_ms = int(start_date.timestamp() * 1000)
            end_ms = int(end_date.timestamp() * 1000)
            
            # Определяем интервал в миллисекундах
            interval_ms = self._interval_to_milliseconds(interval)
            
            # Рассчитываем ожидаемое количество свечей
            expected_candles = int((end_ms - start_ms) / interval_ms)
            
            self.logger.info(
                f"📊 Начинаем загрузку ~{expected_candles} свечей для {symbol} "
                f"с {start_date.strftime('%Y-%m-%d %H:%M')} по {end_date.strftime('%Y-%m-%d %H:%M')}"
            )
            
            all_klines = []
            current_end = end_ms  # Используем отдельную переменную для текущего конца
            batch_count = 0
            
            # Загружаем данные порциями по 1000 свечей
            # Bybit возвращает свечи в обратном порядке, поэтому идем от end к start
            while current_end > start_ms:
                batch_count += 1
                
                # Загружаем порцию
                klines = self.get_historical_klines(
                    symbol=symbol,
                    interval=interval,
                    start_time=start_ms,
                    end_time=current_end,
                    limit=1000
                )
                
                if not klines or len(klines) == 0:
                    self.logger.warning(f"⚠️ Нет данных для периода до {current_end}")
                    break
                
                # Добавляем к результату
                all_klines.extend(klines)
                
                # Bybit возвращает свечи в обратном порядке (от новых к старым)
                # Берём timestamp самой старой свечи (последней в списке)
                oldest_timestamp = klines[-1]['timestamp']
                
                # Если самая старая свеча старше или равна start_ms - мы достигли начала
                if oldest_timestamp <= start_ms:
                    self.logger.info(f"✅ Достигнут начал периода, останавливаем загрузку")
                    break
                
                # Обновляем конечную точку для следующей порции
                # Следующая порция должна заканчиваться на timestamp старейшей загруженной свечи - 1ms
                current_end = oldest_timestamp - 1
                
                self.logger.info(
                    f"📦 Загружено порция {batch_count}: {len(klines)} свечей "
                    f"(всего: {len(all_klines)})"
                )
                
                # Задержка между запросами чтобы не превысить rate limit
                time.sleep(0.1)
                
                # Защита от бесконечного цикла (снижаем лимит до 50 итераций)
                if batch_count > 50:
                    self.logger.error("❌ Превышен лимит итераций (50), прерываем загрузку")
                    break
            
            self.logger.info(
                f"✅ Загрузка завершена: {len(all_klines)} свечей за {batch_count} запросов"
            )
            
            # Сортируем по времени (по возрастанию)
            all_klines.sort(key=lambda x: x['timestamp'])
            
            # Удаляем дубликаты по timestamp
            unique_klines = []
            seen_timestamps = set()
            for kline in all_klines:
                if kline['timestamp'] not in seen_timestamps:
                    unique_klines.append(kline)
                    seen_timestamps.add(kline['timestamp'])
            
            if len(unique_klines) < len(all_klines):
                self.logger.info(
                    f"🔄 Удалено {len(all_klines) - len(unique_klines)} дубликатов"
                )
            
            return unique_klines
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка загрузки исторических данных за период: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _interval_to_milliseconds(self, interval: str) -> int:
        """
        Конвертирует строковый интервал в миллисекунды.
        
        Args:
            interval: '1', '5', '15', '30', '60', '240', 'D', 'W'
            
        Returns:
            int: Количество миллисекунд в интервале
        """
        interval_map = {
            '1': 60 * 1000,           # 1 минута
            '3': 3 * 60 * 1000,       # 3 минуты
            '5': 5 * 60 * 1000,       # 5 минут
            '15': 15 * 60 * 1000,     # 15 минут
            '30': 30 * 60 * 1000,     # 30 минут
            '60': 60 * 60 * 1000,     # 1 час
            '120': 2 * 60 * 60 * 1000,   # 2 часа
            '240': 4 * 60 * 60 * 1000,   # 4 часа
            '360': 6 * 60 * 60 * 1000,   # 6 часов
            'D': 24 * 60 * 60 * 1000,    # 1 день
            'W': 7 * 24 * 60 * 60 * 1000 # 1 неделя
        }
        
        if interval not in interval_map:
            self.logger.warning(f"⚠️ Неизвестный интервал {interval}, используем 15 минут")
            return interval_map['15']
        
        return interval_map[interval]
