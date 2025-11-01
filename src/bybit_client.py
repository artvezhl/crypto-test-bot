from pybit.unified_trading import HTTP  # type: ignore
from pybit.unified_trading import WebSocket  # type: ignore
from config import Config
import json


class BybitClient:
    def __init__(self):
        self.session = HTTP(
            testnet=Config.BYBIT_TESTNET,
            api_key=Config.BYBIT_API_KEY,
            api_secret=Config.BYBIT_API_SECRET
        )

    def get_market_data(self, symbol="ETHUSDT"):
        """Получаем рыночные данные для анализа"""
        try:
            # Получаем текущую цену
            ticker = self.session.get_tickers(category="spot", symbol=symbol)

            # Получаем исторические данные
            kline = self.session.get_kline(
                category="spot",
                symbol=symbol,
                interval="15",
                limit=100
            )

            # Проверяем структуру ответа
            if ('result' in ticker and 'list' in ticker['result'] and
                len(ticker['result']['list']) > 0 and
                    'result' in kline and 'list' in kline['result']):

                ticker_data = ticker['result']['list'][0]
                prices = [float(item[4])
                          for item in kline['result']['list']]  # Close prices

                return {
                    'symbol': symbol,
                    'price': float(ticker_data.get('lastPrice', 0)),
                    'price_change_24h': float(ticker_data.get('price24hPcnt', 0)) * 100,
                    'volume_24h': float(ticker_data.get('volume24h', 0)),
                    'historical': f"Последние 10 цен закрытия: {prices[-10:]}"
                }
            else:
                print("Unexpected API response structure")
                return {}

        except Exception as e:
            print(f"Ошибка получения данных с Bybit: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def place_order(self, symbol, side, qty, order_type="Market"):
        """Размещаем ордер на Bybit"""
        try:
            # Преобразуем qty в строку, как требует Bybit API
            qty_str = str(qty)
            balance = self.get_balance()

            print(f"🔍 Баланс: {balance}")
            print(f"🔍 Размещаем ордер: {side} {qty_str} {symbol}")

            order = self.session.place_order(
                category="spot",
                symbol=symbol,
                side=side,
                marketUnit="quoteCoin",
                orderType=order_type,
                qty=qty_str,
                timeInForce="ImmediateOrCancel"
            )

            return order
        except Exception as e:
            print(f"Ошибка размещения ордера: {e}")
            return None

    def get_balance(self):
        """Получаем баланс счета"""
        try:
            balance = self.session.get_wallet_balance(accountType="UNIFIED")
            return balance
        except Exception as e:
            print(f"Ошибка получения баланса: {e}")
            return None
