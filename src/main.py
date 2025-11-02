import logging
import signal
import sys
import time
from threading import Thread
from trading_strategy import TradingBot
from telegram_bot import TelegramBot
from config import Config
import os

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(
            '/app/logs/trading_bot.log' if os.path.exists('/app/logs') else 'trading_bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


class MainApp:
    def __init__(self):
        self.trading_bot = None
        self.telegram_bot = None
        self.is_running = False

    def setup_signal_handlers(self):
        """Обработка сигналов для graceful shutdown"""
        def signal_handler(sig, frame):
            logger.info("Получен сигнал завершения...")
            self.stop()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def start(self):
        """Запуск приложения"""
        logger.info("🚀 Запуск торгового бота...")

        # Проверка конфигурации
        if not Config.validate_config():
            sys.exit(1)

        # Создаем необходимые директории
        self._create_directories()

        try:
            # Инициализация бота
            self.trading_bot = TradingBot()
            self.telegram_bot = TelegramBot(self.trading_bot)

            # Запуск в отдельном потоке
            self.is_running = True
            self.setup_signal_handlers()

            # Запуск торгового бота в отдельном потоке
            trading_thread = Thread(target=self._run_trading_bot, daemon=True)
            trading_thread.start()

            # Запуск Telegram бота (блокирующий)
            logger.info("Запуск Telegram бота...")
            self.telegram_bot.run()

        except Exception as e:
            logger.error(f"❌ Ошибка запуска приложения: {e}")
        finally:
            self.stop()

    def _create_directories(self):
        """Создание необходимых директорий"""
        directories = ['/app/data', '/app/logs', '/app/backups']
        for directory in directories:
            if not os.path.exists(directory):
                try:
                    os.makedirs(directory, exist_ok=True)
                    logger.info(f"✅ Создана директория: {directory}")
                except Exception as e:
                    logger.warning(
                        f"⚠️ Не удалось создать директорию {directory}: {e}")

    def _run_trading_bot(self):
        """Запуск торгового бота в цикле"""
        while self.is_running:
            try:
                self.trading_bot.run_iteration()
            except Exception as e:
                logger.error(f"❌ Ошибка в торговом цикле: {e}")

            # Пауза между итерациями
            time.sleep(Config.TRADING_INTERVAL_MINUTES * 60)

    def stop(self):
        """Остановка приложения"""
        logger.info("Остановка приложения...")
        self.is_running = False
        if self.trading_bot:
            self.trading_bot.stop()
        if self.telegram_bot:
            self.telegram_bot.stop()
        sys.exit(0)


if __name__ == "__main__":
    app = MainApp()
    app.start()
