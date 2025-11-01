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
    TRADING_INTERVAL_MINUTES = int(os.getenv('TRADING_INTERVAL_MINUTES', '15'))
    DEFAULT_SYMBOL = os.getenv('DEFAULT_SYMBOL', 'ETHUSDT')
    # POSITION_SIZE = 0.01  # ХАРДКОД! Убираем os.getenv чтобы избежать property
    POSITION_SIZE = float(os.getenv('POSITION_SIZE', '0.1'))
    # MIN_CONFIDENCE = 0.68
    MIN_CONFIDENCE = float(os.getenv('MIN_CONFIDENCE', '0.7'))
