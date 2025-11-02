import time
import schedule
from trading_strategy import TradingBot
import logging
from config import Config


class MoscowTimeFormatter(logging.Formatter):
    """Форматтер для московского времени в логах"""

    def formatTime(self, record, datefmt=None):
        moscow_tz = pytz.timezone('Europe/Moscow')
        ct = datetime.fromtimestamp(record.created, moscow_tz)
        if datefmt:
            s = ct.strftime(datefmt)
        else:
            s = ct.strftime("%Y-%m-%d %H:%M:%S")
        return s


def main():
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Инициализация бота
    bot = TradingBot()
    logger.info("Торговый бот инициализирован")

    # Запуск по расписанию
    schedule.every(Config.TRADING_INTERVAL_MINUTES).minutes.do(
        bot.run_iteration)

    # Также можно запускать каждую минуту для тестирования
    # schedule.every(1).minutes.do(bot.run_iteration)

    logger.info("Бот запущен. Ожидание сигналов...")

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")


if __name__ == "__main__":
    main()
