import os
from dotenv import load_dotenv

load_dotenv()

# ПРОСТОЙ КЛАСС БЕЗ ВСЯКИХ PROPERTY!


class Config:
    # Bybit API
    BYBIT_API_KEY = os.getenv('BYBIT_API_KEY')
    BYBIT_API_SECRET = os.getenv('BYBIT_API_SECRET')
    BYBIT_TESTNET = os.getenv('BYBIT_TESTNET', 'true').lower() == 'true'

    # DeepSeek API
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

    # Trading settings - ПРОСТЫЕ ЧИСЛА!
    TRADING_INTERVAL_MINUTES = int(os.getenv('TRADING_INTERVAL_MINUTES', '1'))
    DEFAULT_SYMBOL = os.getenv('DEFAULT_SYMBOL', 'ETHUSDT')
    POSITION_SIZE = float(os.getenv('POSITION_SIZE', '0.1'))
    MIN_CONFIDENCE = float(os.getenv('MIN_CONFIDENCE', '0.7'))

    # Risk Management
    RISK_PERCENT = float(os.getenv('RISK_PERCENT', '1.0')
                         )  # 1% от баланса на сделку
    MAX_POSITION_PERCENT = float(
        os.getenv('MAX_POSITION_PERCENT', '5.0'))  # Макс 5% от баланса
    MIN_TRADE_USDT = float(
        os.getenv('MIN_TRADE_USDT', '10.0'))  # Минимум 10 USDT
    STOP_LOSS_PERCENT = float(os.getenv('STOP_LOSS_PERCENT', '2.0'))
    TAKE_PROFIT_PERCENT = float(os.getenv('TAKE_PROFIT_PERCENT', '5.0'))
    INITIAL_BALANCE = float(os.getenv('INITIAL_BALANCE', '1000.0'))
