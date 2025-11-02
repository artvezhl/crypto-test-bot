import os


class Config:
    # Bybit API
    BYBIT_API_KEY = os.getenv('BYBIT_API_KEY', '')
    BYBIT_API_SECRET = os.getenv('BYBIT_API_SECRET', '')
    BYBIT_TESTNET = os.getenv('BYBIT_TESTNET', 'true').lower() == 'true'

    # DeepSeek API
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '')

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    # Может не использоваться, если бот приватный
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

    # Trading Settings
    TRADING_INTERVAL_MINUTES = int(os.getenv('TRADING_INTERVAL_MINUTES', '15'))
    DEFAULT_SYMBOL = os.getenv('DEFAULT_SYMBOL', 'ETHUSDT')
    POSITION_SIZE = float(os.getenv('POSITION_SIZE', '0.05'))
    MIN_CONFIDENCE = float(os.getenv('MIN_CONFIDENCE', '0.68'))

    # Risk Management
    RISK_PERCENT = float(os.getenv('RISK_PERCENT', '1.0'))
    MAX_POSITION_PERCENT = float(os.getenv('MAX_POSITION_PERCENT', '5.0'))
    MIN_TRADE_USDT = float(os.getenv('MIN_TRADE_USDT', '10.0'))
    STOP_LOSS_PERCENT = float(os.getenv('STOP_LOSS_PERCENT', '2.0'))
    TAKE_PROFIT_PERCENT = float(os.getenv('TAKE_PROFIT_PERCENT', '5.0'))

    # Initial Balance
    INITIAL_BALANCE = float(os.getenv('INITIAL_BALANCE', '10000.0'))

    @classmethod
    def validate_config(cls):
        """Validate that all required environment variables are set"""
        required_vars = [
            'BYBIT_API_KEY', 'BYBIT_API_SECRET', 'DEEPSEEK_API_KEY',
            'TELEGRAM_BOT_TOKEN'
        ]

        missing_vars = []
        for var in required_vars:
            if not getattr(cls, var):
                missing_vars.append(var)

        if missing_vars:
            print(
                f"❌ Missing required environment variables: {', '.join(missing_vars)}")
            return False

        print("✅ All required configuration variables are set")
        return True
