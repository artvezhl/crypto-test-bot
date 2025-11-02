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

    def place_order(self, symbol, side, qty, order_type="Market", market_unit="quoteCoin"):
        """Размещаем ордер на Bybit"""
        try:
            # Преобразуем qty в строку, как требует Bybit API
            qty_str = f"{qty:.2f}"

            print(
                f"🔍 Размещаем ордер: {side} {qty_str} {symbol} (market_unit: {market_unit})")

            # Базовые параметры ордера
            order_params = {
                "category": "spot",
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "timeInForce": "GTC"
            }

            # Добавляем параметры в зависимости от типа единицы измерения
            if market_unit == "quoteCoin":
                # Если используем quoteCoin, то qty - это сумма в USDT
                order_params["marketUnit"] = market_unit
                order_params["qty"] = qty_str
                print(f"💵 Ордер на сумму: {qty_str} USDT")
            else:
                # Если используем baseCoin, то qty - это количество монет
                order_params["qty"] = qty_str
                print(
                    f"🪙 Ордер на количество: {qty_str} {symbol.replace('USDT', '')}")

            order = self.session.place_order(**order_params)
            return order
        except Exception as e:
            print(f"Ошибка размещения ордера: {e}")
            return None

    def get_unified_balance(self):
        """Получаем баланс UNIFIED аккаунта с ручным расчетом available"""
        try:
            balance = self.session.get_wallet_balance(accountType="UNIFIED")
            print(f"📊 Полный ответ баланса: {json.dumps(balance, indent=2)}")

            if balance and 'result' in balance and balance['result']['list']:
                account_data = balance['result']['list'][0]

                # Основные поля баланса
                total_equity = float(account_data.get('totalEquity', 0))
                total_wallet_balance = float(
                    account_data.get('totalWalletBalance', 0))

                # Ручной расчет доступного баланса
                total_perp_upl = float(account_data.get('totalPerpUPL', 0))
                total_initial_margin = float(
                    account_data.get('totalInitialMargin', 0))
                total_maintenance_margin = float(
                    account_data.get('totalMaintenanceMargin', 0))

                # Расчет доступного баланса
                calculated_available = total_wallet_balance - total_perp_upl - \
                    total_initial_margin - total_maintenance_margin
                # Не может быть отрицательным
                calculated_available = max(0, calculated_available)

                # Получаем USDT баланс
                usdt_balance = 0
                if 'coin' in account_data:
                    for coin in account_data['coin']:
                        if coin['coin'] == 'USDT':
                            usdt_balance = float(coin.get('walletBalance', 0))
                            break

                return {
                    'total_equity': total_equity,
                    'total_wallet_balance': total_wallet_balance,
                    'total_available_balance': calculated_available,  # Наш расчет
                    'usdt_balance': usdt_balance,
                    'usdt_available': calculated_available,  # Используем расчет для USDT
                    # Дополнительное поле для информации
                    'calculated_available': calculated_available,
                    'full_response': balance
                }

            return {'total_equity': 0, 'total_wallet_balance': 0, 'total_available_balance': 0, 'usdt_balance': 0, 'usdt_available': 0, 'calculated_available': 0, 'full_response': balance}

        except Exception as e:
            print(f"Ошибка получения баланса UNIFIED: {e}")
            import traceback
            traceback.print_exc()
            return {
                'total_equity': 0, 'total_wallet_balance': 0, 'total_available_balance': 0,
                'usdt_balance': 0, 'usdt_available': 0, 'calculated_available': 0, 'full_response': None
            }

    def get_spot_balance(self):
        """Получаем баланс SPOT аккаунта - альтернативный метод"""
        try:
            balance = self.session.get_wallet_balance(accountType="SPOT")
            print(f"📊 SPOT баланс: {json.dumps(balance, indent=2)}")

            if balance and 'result' in balance and balance['result']['list']:
                account_data = balance['result']['list'][0]

                total_equity = float(account_data.get('totalEquity', 0))
                total_available_balance = float(
                    account_data.get('totalAvailableBalance', 0))

                # Ищем USDT в SPOT
                usdt_balance = 0
                if 'coin' in account_data:
                    for coin in account_data['coin']:
                        if coin['coin'] == 'USDT':
                            usdt_balance = float(coin.get('walletBalance', 0))
                            break

                return {
                    'total_equity': total_equity,
                    'total_available_balance': total_available_balance,
                    'usdt_balance': usdt_balance,
                    'full_response': balance
                }

            return {
                'total_equity': 0,
                'total_available_balance': 0,
                'usdt_balance': 0,
                'full_response': balance
            }

        except Exception as e:
            print(f"Ошибка получения SPOT баланса: {e}")
            return {
                'total_equity': 0,
                'total_available_balance': 0,
                'usdt_balance': 0,
                'full_response': None
            }
