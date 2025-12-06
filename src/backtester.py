"""
Backtester - система бэктестинга торговых стратегий.

Этот модуль отвечает за:
1. Симуляцию торговли на исторических данных
2. Расчет метрик эффективности стратегии
3. Генерацию отчетов по результатам
4. Сохранение результатов в БД
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from virtual_trading_bot import VirtualTradingBot
from data_loader import DataLoader
from database import Database
import time


class BacktestEngine(VirtualTradingBot):
    """
    Движок бэктестинга на основе VirtualTradingBot.
    
    Наследуется от VirtualTradingBot и переиспользует всю логику торговли,
    но работает с историческими данными вместо реального времени.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Инициализация движка бэктестинга.
        
        Args:
            config: Словарь с настройками бэктеста (опционально)
        """
        # Инициализируем родительский класс
        super().__init__()
        
        self.logger = logging.getLogger(__name__)
        
        # Режим бэктестинга
        self.backtest_mode = True
        
        # Загрузчик данных
        self.data_loader = DataLoader(self.bybit, self.db)
        
        # Настройки бэктеста
        self.config = config or {}
        
        # Исторические данные для всех символов
        self.historical_data: Dict[str, List[Dict]] = {}
        
        # Текущая временная метка в процессе бэктеста
        self.current_backtest_time: Optional[datetime] = None
        
        # Индекс текущей свечи для каждого символа
        self.candle_indexes: Dict[str, int] = {}
        
        # Результаты бэктеста
        self.backtest_results: Dict = {}
        
        # ID текущего бэктеста в БД
        self.backtest_id: Optional[int] = None
        
        # Счетчики для прогресса
        self.total_candles = 0
        self.processed_candles = 0
        
        self.logger.info("✅ BacktestEngine инициализирован")
    
    def run_backtest(self, symbols: List[str], interval: str,
                     start_date: datetime, end_date: datetime,
                     initial_balance: Optional[float] = None) -> Dict:
        """
        Запускает бэктест на исторических данных.
        
        Args:
            symbols: Список торговых пар
            interval: Таймфрейм ('1', '5', '15', '30', '60', '240', 'D')
            start_date: Начальная дата
            end_date: Конечная дата
            initial_balance: Начальный баланс (если None - берется из настроек)
            
        Returns:
            Dict: Результаты бэктеста с метриками
        """
        try:
            self.logger.info("=" * 80)
            self.logger.info("🚀 ЗАПУСК БЭКТЕСТА")
            self.logger.info("=" * 80)
            self.logger.info(f"📅 Период: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
            self.logger.info(f"📊 Символы: {', '.join(symbols)}")
            self.logger.info(f"⏱️  Таймфрейм: {interval} минут")
            
            # Устанавливаем начальный баланс
            if initial_balance:
                self.initial_balance = initial_balance
                self.current_balance = initial_balance
            
            self.logger.info(f"💰 Начальный баланс: ${self.initial_balance:.2f}")
            
            # Шаг 1: Загрузка исторических данных
            self.logger.info("\n📦 ШАГ 1: Загрузка исторических данных...")
            if not self._load_historical_data(symbols, interval, start_date, end_date):
                self.logger.error("❌ Не удалось загрузить данные для бэктеста")
                return {}
            
            # Шаг 2: Создание записи бэктеста в БД
            self.logger.info("\n💾 ШАГ 2: Инициализация бэктеста в БД...")
            self.backtest_id = self._create_backtest_record(
                symbols, interval, start_date, end_date
            )
            
            # Шаг 3: Прогон стратегии на исторических данных
            self.logger.info("\n🎯 ШАГ 3: Симуляция торговли...")
            self._simulate_trading(start_date, end_date, interval)
            
            # Шаг 4: Расчет результатов
            self.logger.info("\n📊 ШАГ 4: Расчет метрик...")
            results = self._calculate_results()
            
            # Шаг 5: Сохранение результатов
            self.logger.info("\n💾 ШАГ 5: Сохранение результатов...")
            self._save_results(results)
            
            # Шаг 6: Вывод отчета
            self.logger.info("\n" + "=" * 80)
            self._print_report(results)
            self.logger.info("=" * 80)
            
            self.backtest_results = results
            return results
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка выполнения бэктеста: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def _load_historical_data(self, symbols: List[str], interval: str,
                             start_date: datetime, end_date: datetime) -> bool:
        """
        Загружает исторические данные для всех символов.
        
        Returns:
            bool: True если данные успешно загружены
        """
        try:
            self.historical_data = self.data_loader.preload_data_for_backtest(
                symbols=symbols,
                interval=interval,
                start_date=start_date,
                end_date=end_date
            )
            
            if not self.historical_data:
                self.logger.error("❌ Не удалось загрузить исторические данные")
                return False
            
            # Инициализируем индексы для каждого символа
            for symbol in self.historical_data.keys():
                self.candle_indexes[symbol] = 0
                self.total_candles += len(self.historical_data[symbol])
            
            self.logger.info(f"✅ Загружено данных для {len(self.historical_data)} символов")
            self.logger.info(f"📊 Всего свечей для обработки: {self.total_candles}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка загрузки исторических данных: {e}")
            return False
    
    def _simulate_trading(self, start_date: datetime, end_date: datetime, interval: str):
        """
        Симулирует торговлю на исторических данных.
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            interval: Таймфрейм
        """
        try:
            # Создаем временную шкалу (timeline) из всех уникальных timestamp
            timeline = self._create_timeline()
            
            if not timeline:
                self.logger.error("❌ Не удалось создать временную шкалу")
                return
            
            self.logger.info(f"⏱️  Временная шкала: {len(timeline)} точек")
            
            # Прогресс
            total_steps = len(timeline)
            report_interval = max(1, total_steps // 20)  # Отчет каждые 5%
            
            start_time = time.time()
            
            # Проходим по каждой точке на временной шкале
            for i, timestamp in enumerate(timeline):
                self.current_backtest_time = datetime.fromtimestamp(timestamp / 1000)
                
                # Обрабатываем каждый символ на этом временном срезе
                for symbol in self.historical_data.keys():
                    candle = self._get_candle_at_timestamp(symbol, timestamp)
                    
                    if candle:
                        # Обрабатываем свечу (аналогично _process_symbol в VirtualTradingBot)
                        self._process_historical_candle(symbol, candle)
                
                # Прогресс-бар
                if (i + 1) % report_interval == 0 or i == total_steps - 1:
                    progress = ((i + 1) / total_steps) * 100
                    elapsed = time.time() - start_time
                    eta = (elapsed / (i + 1)) * (total_steps - i - 1)
                    
                    self.logger.info(
                        f"📈 Прогресс: {progress:.1f}% ({i + 1}/{total_steps}) | "
                        f"⏱️ Прошло: {elapsed:.1f}s | ETA: {eta:.1f}s | "
                        f"💰 Баланс: ${self.current_balance:.2f}"
                    )
            
            total_time = time.time() - start_time
            self.logger.info(f"\n✅ Симуляция завершена за {total_time:.1f}s")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка симуляции торговли: {e}")
            import traceback
            traceback.print_exc()
    
    def _create_timeline(self) -> List[int]:
        """
        Создает временную шкалу из всех уникальных timestamp.
        
        Returns:
            List[int]: Отсортированный список timestamp в миллисекундах
        """
        all_timestamps = set()
        
        for symbol, candles in self.historical_data.items():
            for candle in candles:
                all_timestamps.add(candle['timestamp'])
        
        return sorted(list(all_timestamps))
    
    def _get_candle_at_timestamp(self, symbol: str, timestamp: int) -> Optional[Dict]:
        """
        Получает свечу для символа на определенный timestamp.
        
        Args:
            symbol: Торговая пара
            timestamp: Временная метка
            
        Returns:
            Dict: Свеча или None если не найдена
        """
        if symbol not in self.historical_data:
            return None
        
        candles = self.historical_data[symbol]
        
        # Ищем свечу с нужным timestamp
        for candle in candles:
            if candle['timestamp'] == timestamp:
                return candle
        
        return None
    
    def _process_historical_candle(self, symbol: str, candle: Dict):
        """
        Обрабатывает историческую свечу (аналог _process_symbol).
        
        Args:
            symbol: Торговая пара
            candle: Данные свечи OHLCV
        """
        try:
            current_price = candle['close']
            
            # Обновляем цены виртуальных позиций
            self._update_virtual_positions_prices(symbol, current_price)
            
            # Проверяем условия для закрытия позиций
            self._check_virtual_position_conditions(symbol, current_price)
            
            # Создаем market_data в формате, совместимом с VirtualTradingBot
            market_data = {
                'symbol': symbol,
                'price': current_price,
                'price_change_24h': 0,  # Можно рассчитать если нужно
                'volume_24h': candle['volume'],
                'historical_prices': []  # Можно добавить предыдущие свечи
            }
            
            # Получаем сигнал от DeepSeek (или используем другую стратегию)
            signal = self.get_trading_signal_with_logging(symbol, market_data)
            
            # Рассчитываем размер позиции
            position_amount = self.calculate_position_size(symbol, current_price)
            
            if position_amount <= 0:
                return
            
            # Исполняем торговое решение если сигнал достаточно уверенный
            if signal['confidence'] > self.min_confidence:
                self._execute_virtual_trading_decision(
                    symbol, signal, market_data, position_amount
                )
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки свечи {symbol}: {e}")
    
    def _create_backtest_record(self, symbols: List[str], interval: str,
                                start_date: datetime, end_date: datetime) -> Optional[int]:
        """
        Создает запись бэктеста в БД.
        
        Returns:
            int: ID созданного бэктеста
        """
        try:
            # TODO: Добавить метод в Database для создания записи бэктеста
            # Пока возвращаем временный ID
            self.logger.info("📝 Запись бэктеста создана (временная)")
            return 1
        except Exception as e:
            self.logger.error(f"❌ Ошибка создания записи бэктеста: {e}")
            return None
    
    def _calculate_results(self) -> Dict:
        """
        Рассчитывает результаты бэктеста.
        
        Returns:
            Dict: Словарь с метриками
        """
        try:
            # Получаем статистику виртуальной торговли
            stats = self.get_virtual_stats()
            
            # Базовые метрики
            total_pnl = stats.get('total_realized_pnl', 0)
            total_trades = stats.get('total_trades', 0)
            winning_trades = stats.get('winning_trades', 0)
            losing_trades = stats.get('losing_trades', 0)
            
            # Рассчитываем производные метрики
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            roi = (total_pnl / self.initial_balance * 100) if self.initial_balance > 0 else 0
            
            results = {
                'initial_balance': self.initial_balance,
                'final_balance': self.current_balance,
                'total_pnl': total_pnl,
                'roi_percent': roi,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': win_rate,
                'highest_balance': self.highest_balance,
                'lowest_balance': self.lowest_balance,
                'max_drawdown': self._calculate_max_drawdown(),
                'sharpe_ratio': self._calculate_sharpe_ratio(),
                'profit_factor': self._calculate_profit_factor()
            }
            
            return results
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета результатов: {e}")
            return {}
    
    def _calculate_max_drawdown(self) -> float:
        """
        Рассчитывает максимальную просадку.
        
        Returns:
            float: Максимальная просадка в процентах
        """
        try:
            if self.highest_balance == 0:
                return 0.0
            
            drawdown = ((self.highest_balance - self.lowest_balance) / self.highest_balance) * 100
            return drawdown
        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета Max Drawdown: {e}")
            return 0.0
    
    def _calculate_sharpe_ratio(self) -> float:
        """
        Рассчитывает коэффициент Шарпа.
        
        Returns:
            float: Sharpe Ratio
        """
        try:
            # TODO: Реализовать полный расчет Sharpe Ratio
            # Требуется история баланса по времени
            self.logger.debug("⚠️ Sharpe Ratio - базовая реализация")
            return 0.0
        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета Sharpe Ratio: {e}")
            return 0.0
    
    def _calculate_profit_factor(self) -> float:
        """
        Рассчитывает Profit Factor.
        
        Returns:
            float: Profit Factor (отношение прибыли к убыткам)
        """
        try:
            stats = self.get_virtual_stats()
            
            # Получаем детальную статистику сделок
            # TODO: Добавить методы в Database для получения суммы прибылей и убытков
            
            # Временная заглушка
            winning_trades = stats.get('winning_trades', 0)
            losing_trades = stats.get('losing_trades', 0)
            
            if losing_trades == 0:
                return 999.0 if winning_trades > 0 else 0.0
            
            # Упрощенный расчет (нужна сумма прибылей и убытков отдельно)
            return winning_trades / losing_trades if losing_trades > 0 else 0.0
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета Profit Factor: {e}")
            return 0.0
    
    def _save_results(self, results: Dict):
        """
        Сохраняет результаты бэктеста в БД.
        
        Args:
            results: Словарь с результатами
        """
        try:
            # TODO: Добавить метод в Database для сохранения результатов
            self.logger.info("💾 Результаты сохранены в БД (временная реализация)")
        except Exception as e:
            self.logger.error(f"❌ Ошибка сохранения результатов: {e}")
    
    def _print_report(self, results: Dict):
        """
        Выводит отчет о результатах бэктеста.
        
        Args:
            results: Словарь с результатами
        """
        try:
            self.logger.info("📊 РЕЗУЛЬТАТЫ БЭКТЕСТА")
            self.logger.info("=" * 80)
            
            self.logger.info(f"💰 Начальный баланс: ${results.get('initial_balance', 0):.2f}")
            self.logger.info(f"💰 Финальный баланс: ${results.get('final_balance', 0):.2f}")
            self.logger.info(f"📈 Прибыль/Убыток: ${results.get('total_pnl', 0):.2f}")
            self.logger.info(f"📊 ROI: {results.get('roi_percent', 0):.2f}%")
            
            self.logger.info(f"\n🎯 Сделки:")
            self.logger.info(f"   Всего сделок: {results.get('total_trades', 0)}")
            self.logger.info(f"   Прибыльных: {results.get('winning_trades', 0)}")
            self.logger.info(f"   Убыточных: {results.get('losing_trades', 0)}")
            self.logger.info(f"   Win Rate: {results.get('win_rate', 0):.2f}%")
            
            self.logger.info(f"\n📉 Риски:")
            self.logger.info(f"   Максимальный баланс: ${results.get('highest_balance', 0):.2f}")
            self.logger.info(f"   Минимальный баланс: ${results.get('lowest_balance', 0):.2f}")
            self.logger.info(f"   Max Drawdown: {results.get('max_drawdown', 0):.2f}%")
            
            self.logger.info(f"\n📊 Метрики:")
            self.logger.info(f"   Sharpe Ratio: {results.get('sharpe_ratio', 0):.2f}")
            self.logger.info(f"   Profit Factor: {results.get('profit_factor', 0):.2f}")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка вывода отчета: {e}")
    
    def get_results(self) -> Dict:
        """
        Возвращает результаты последнего бэктеста.
        
        Returns:
            Dict: Результаты бэктеста
        """
        return self.backtest_results

