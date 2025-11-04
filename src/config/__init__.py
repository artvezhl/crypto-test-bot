import os


class Config:
    # Секреты (единственное, что остается в .env)
    BYBIT_API_KEY = os.getenv('BYBIT_API_KEY', '')
    BYBIT_API_SECRET = os.getenv('BYBIT_API_SECRET', '')
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

    # Критически важные настройки, нужные до инициализации БД
    BYBIT_TESTNET = os.getenv('BYBIT_TESTNET', 'true').lower() == 'true'
    DATABASE_URL = os.getenv('DATABASE_URL', '')

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
