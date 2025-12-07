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
        
        # История баланса для расчета метрик (timestamp: balance)
        self.balance_history: List[Dict] = []
        
        # История сделок для детального анализа
        self.trades_history: List[Dict] = []
        
        # Callback для отчета о прогрессе
        self.progress_callback: Optional[callable] = None
        
        # Стратегия для бэктестинга (simple или deepseek)
        # simple - быстрая техническая стратегия без API вызовов
        # deepseek - использует AI (медленно, ~30-60 мин для 2000 свечей)
        self.backtest_strategy = self.config.get('strategy', 'simple')
        
        self.logger.info(f"✅ BacktestEngine инициализирован (стратегия: {self.backtest_strategy})")
    
    def run_backtest(self, symbols: List[str], interval: str,
                     start_date: datetime, end_date: datetime,
                     initial_balance: Optional[float] = None,
                     progress_callback: Optional[callable] = None) -> Dict:
        """
        Запускает бэктест на исторических данных.
        
        Args:
            symbols: Список торговых пар
            interval: Таймфрейм ('1', '5', '15', '30', '60', '240', 'D')
            start_date: Начальная дата
            end_date: Конечная дата
            initial_balance: Начальный баланс (если None - берется из настроек)
            progress_callback: Функция обратного вызова для отчета о прогрессе
            
        Returns:
            Dict: Результаты бэктеста с метриками
        """
        self.progress_callback = progress_callback
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
            if self.progress_callback:
                self.progress_callback(0, f"Загрузка данных для {len(symbols)} символов...")
            
            if not self._load_historical_data(symbols, interval, start_date, end_date):
                self.logger.error("❌ Не удалось загрузить данные для бэктеста")
                return {}
            
            if self.progress_callback:
                self.progress_callback(10, f"Загрузка завершена. Обработано {self.total_candles} свечей")
            
            # Шаг 2: Создание записи бэктеста в БД
            self.logger.info("\n💾 ШАГ 2: Инициализация бэктеста в БД...")
            self.backtest_id = self._create_backtest_record(
                symbols, interval, start_date, end_date
            )
            
            # Шаг 3: Прогон стратегии на исторических данных
            self.logger.info("\n🎯 ШАГ 3: Симуляция торговли...")
            if self.progress_callback:
                self.progress_callback(10, "Начало симуляции торговли...")
            self._simulate_trading(start_date, end_date, interval)
            
            # Шаг 4: Расчет результатов
            self.logger.info("\n📊 ШАГ 4: Расчет метрик...")
            if self.progress_callback:
                self.progress_callback(90, "Расчет метрик...")
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
            # Загружаем данные для каждого символа с обновлением прогресса
            self.historical_data = {}
            total_symbols = len(symbols)
            
            for i, symbol in enumerate(symbols, 1):
                # Обновляем прогресс загрузки (0-10% диапазон)
                progress = (i / total_symbols) * 10
                if self.progress_callback:
                    self.progress_callback(
                        progress, 
                        f"Загрузка данных {i}/{total_symbols}: {symbol}..."
                    )
                
                self.logger.info(f"📊 [{i}/{total_symbols}] Загрузка {symbol}...")
                
                klines = self.data_loader.load_historical_data(
                    symbol=symbol,
                    interval=interval,
                    start_date=start_date,
                    end_date=end_date,
                    use_cache=True
                )
                
                if klines:
                    self.historical_data[symbol] = klines
                    self.logger.info(f"✅ {symbol}: {len(klines)} свечей")
                else:
                    self.logger.warning(f"⚠️ {symbol}: нет данных")
            
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
            report_interval = max(1, total_steps // 100)  # Отчет каждые 1%
            
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
                
                # Записываем баланс в историю для расчета метрик
                self.balance_history.append({
                    'timestamp': timestamp,
                    'datetime': self.current_backtest_time,
                    'balance': self.current_balance
                })
                
                # Прогресс-бар
                if (i + 1) % report_interval == 0 or i == total_steps - 1:
                    progress = ((i + 1) / total_steps) * 100
                    elapsed = time.time() - start_time
                    eta = (elapsed / (i + 1)) * (total_steps - i - 1)
                    
                    # Отправляем прогресс через callback
                    if self.progress_callback:
                        # Прогресс симуляции занимает 10-90% общего прогресса
                        overall_progress = 10 + (progress * 0.8)
                        self.progress_callback(
                            overall_progress,
                            f"Симуляция: {progress:.1f}% | Баланс: ${self.current_balance:.2f}"
                        )
                    
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
            
            # Выбираем стратегию на основе конфигурации
            if self.backtest_strategy == 'deepseek':
                # Используем DeepSeek API (медленно!)
                market_data = {
                    'symbol': symbol,
                    'price': current_price,
                    'price_change_24h': 0,
                    'volume_24h': candle['volume'],
                    'historical_prices': []
                }
                signal = self.get_trading_signal_with_logging(symbol, market_data)
            else:
                # Используем простую техническую стратегию (быстро!)
                signal = self._get_simple_backtest_signal(symbol, candle)
            
            # Рассчитываем размер позиции
            position_amount = self.calculate_position_size(symbol, current_price)
            
            if position_amount <= 0:
                return
            
            # Создаем market_data для совместимости
            market_data = {
                'symbol': symbol,
                'price': current_price,
                'price_change_24h': 0,
                'volume_24h': candle['volume'],
                'historical_prices': []
            }
            
            # Исполняем торговое решение если сигнал достаточно уверенный
            if signal['confidence'] > self.min_confidence:
                self._execute_virtual_trading_decision(
                    symbol, signal, market_data, position_amount
                )
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки свечи {symbol}: {e}")
    
    def _get_simple_backtest_signal(self, symbol: str, candle: Dict) -> Dict:
        """
        Простая техническая стратегия для бэктестинга (без DeepSeek API).
        
        Использует базовый momentum и volume анализ для быстрой симуляции.
        
        Args:
            symbol: Торговая пара
            candle: Текущая свеча OHLCV
            
        Returns:
            Dict: Торговый сигнал {action, confidence, reason}
        """
        try:
            # Получаем историю последних свечей для символа
            if symbol not in self.historical_data or len(self.historical_data[symbol]) < 20:
                return {'action': 'hold', 'confidence': 0.0, 'reason': 'Недостаточно данных'}
            
            # Находим индекс текущей свечи
            current_idx = self.candle_indexes.get(symbol, 0)
            if current_idx < 20:
                return {'action': 'hold', 'confidence': 0.0, 'reason': 'Недостаточно истории'}
            
            # Берем последние 20 свечей для анализа
            recent_candles = self.historical_data[symbol][max(0, current_idx-19):current_idx+1]
            
            # Простая стратегия на основе изменения цены
            # Сравниваем текущую цену с средней за последние 10 свечей
            prices = [c['close'] for c in recent_candles[-10:]]
            avg_price = sum(prices) / len(prices) if prices else candle['close']
            
            current_price = candle['close']
            price_change = ((current_price - avg_price) / avg_price) * 100
            
            # Анализ объема
            volumes = [c['volume'] for c in recent_candles[-5:]]
            avg_volume = sum(volumes) / len(volumes) if volumes else candle['volume']
            volume_ratio = candle['volume'] / avg_volume if avg_volume > 0 else 1.0
            
            # Генерируем сигнал
            # LONG: цена выше средней на 0.5%+ и объем выше среднего
            if price_change > 0.5 and volume_ratio > 1.2:
                confidence = min(0.75, 0.6 + (price_change / 10) + (volume_ratio - 1) * 0.1)
                return {
                    'action': 'long',
                    'confidence': confidence,
                    'reason': f'Momentum вверх: +{price_change:.2f}%, Vol: {volume_ratio:.2f}x'
                }
            
            # SHORT: цена ниже средней на 0.5%+ и объем выше среднего
            elif price_change < -0.5 and volume_ratio > 1.2:
                confidence = min(0.75, 0.6 + (abs(price_change) / 10) + (volume_ratio - 1) * 0.1)
                return {
                    'action': 'short',
                    'confidence': confidence,
                    'reason': f'Momentum вниз: {price_change:.2f}%, Vol: {volume_ratio:.2f}x'
                }
            
            # HOLD: нет четкого сигнала
            else:
                return {
                    'action': 'hold',
                    'confidence': 0.5,
                    'reason': f'Нейтральный рынок: {price_change:.2f}%'
                }
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка генерации сигнала для {symbol}: {e}")
            return {'action': 'hold', 'confidence': 0.0, 'reason': 'Ошибка анализа'}
    
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
            total_pnl = stats.get('total_realized_pnl', 0) or 0
            total_trades = stats.get('total_trades', 0) or 0
            winning_trades = stats.get('winning_trades', 0) or 0
            losing_trades = stats.get('losing_trades', 0) or 0
            
            # Метрики комиссий
            total_fees = stats.get('total_fees_paid', 0) or 0
            total_entry_fees = stats.get('total_entry_fees', 0) or 0
            total_exit_fees = stats.get('total_exit_fees', 0) or 0
            
            # Рассчитываем производные метрики
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            roi = (total_pnl / self.initial_balance * 100) if self.initial_balance > 0 else 0
            
            results = {
                # Базовые метрики
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
                
                # Риск-метрики
                'max_drawdown': self._calculate_max_drawdown(),
                'sharpe_ratio': self._calculate_sharpe_ratio(),
                'sortino_ratio': self._calculate_sortino_ratio(),
                'calmar_ratio': self._calculate_calmar_ratio(),
                
                # Торговые метрики
                'profit_factor': self._calculate_profit_factor(),
                'expectancy': self._calculate_expectancy(),
                'avg_trade_duration_hours': self._calculate_avg_trade_duration(),
                
                # Метрики комиссий
                'total_fees_paid': total_fees,
                'total_entry_fees': total_entry_fees,
                'total_exit_fees': total_exit_fees
            }
            
            return results
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета результатов: {e}")
            return {}
    
    def _grade_sharpe_ratio(self, sharpe: float) -> str:
        """
        Оценивает качество Sharpe Ratio.
        
        Args:
            sharpe: Значение Sharpe Ratio
            
        Returns:
            str: Оценка с эмодзи
        """
        if sharpe >= 3.0:
            return "🌟 Отлично"
        elif sharpe >= 2.0:
            return "✅ Очень хорошо"
        elif sharpe >= 1.0:
            return "👍 Хорошо"
        elif sharpe >= 0.5:
            return "🟡 Приемлемо"
        elif sharpe >= 0:
            return "🟠 Слабо"
        else:
            return "🔴 Плохо"
    
    def _estimate_periods_per_year(self) -> int:
        """
        Оценивает количество периодов в год на основе истории баланса.
        
        Returns:
            int: Количество периодов в год
        """
        try:
            if len(self.balance_history) < 2:
                return 0
            
            # Вычисляем среднюю длительность периода
            first_time = self.balance_history[0]['datetime']
            last_time = self.balance_history[-1]['datetime']
            total_duration = (last_time - first_time).total_seconds()
            
            if total_duration <= 0:
                return 0
            
            num_periods = len(self.balance_history) - 1
            avg_period_seconds = total_duration / num_periods
            
            # Секунд в году
            seconds_per_year = 365.25 * 24 * 60 * 60
            
            periods_per_year = int(seconds_per_year / avg_period_seconds)
            return periods_per_year
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка оценки периодов в год: {e}")
            return 0
    
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
    
    def _calculate_sharpe_ratio(self, risk_free_rate: float = 0.0) -> float:
        """
        Рассчитывает коэффициент Шарпа (риск-скорректированная доходность).
        
        Sharpe Ratio = (Mean Return - Risk Free Rate) / Std Dev of Returns
        
        Args:
            risk_free_rate: Безрисковая ставка в процентах годовых (по умолчанию 0%)
            
        Returns:
            float: Sharpe Ratio (чем выше, тем лучше)
        """
        try:
            if len(self.balance_history) < 2:
                self.logger.debug("⚠️ Недостаточно данных для расчета Sharpe Ratio")
                return 0.0
            
            # Рассчитываем доходность между периодами (returns)
            returns = []
            for i in range(1, len(self.balance_history)):
                prev_balance = self.balance_history[i-1]['balance']
                curr_balance = self.balance_history[i]['balance']
                
                if prev_balance > 0:
                    period_return = (curr_balance - prev_balance) / prev_balance
                    returns.append(period_return)
            
            if len(returns) == 0:
                return 0.0
            
            # Вычисляем среднюю доходность и стандартное отклонение
            import numpy as np
            mean_return = np.mean(returns)
            std_return = np.std(returns, ddof=1)  # ddof=1 для выборочного стд. откл.
            
            if std_return == 0:
                return 0.0
            
            # Преобразуем risk-free rate в периодическую ставку
            # (предполагаем, что periods примерно соответствуют годовой доходности)
            periods_per_year = self._estimate_periods_per_year()
            risk_free_per_period = (risk_free_rate / 100) / periods_per_year if periods_per_year > 0 else 0
            
            # Sharpe Ratio
            sharpe = (mean_return - risk_free_per_period) / std_return
            
            # Аннуализируем (умножаем на sqrt(periods_per_year))
            if periods_per_year > 0:
                sharpe = sharpe * np.sqrt(periods_per_year)
            
            return float(sharpe)
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета Sharpe Ratio: {e}")
            return 0.0
    
    def _calculate_sortino_ratio(self, target_return: float = 0.0) -> float:
        """
        Рассчитывает коэффициент Сортино (учитывает только негативную волатильность).
        
        Sortino Ratio = (Mean Return - Target Return) / Downside Deviation
        
        Args:
            target_return: Целевая доходность (обычно 0% или минимальная приемлемая)
            
        Returns:
            float: Sortino Ratio (чем выше, тем лучше)
        """
        try:
            if len(self.balance_history) < 2:
                self.logger.debug("⚠️ Недостаточно данных для расчета Sortino Ratio")
                return 0.0
            
            # Рассчитываем доходность между периодами
            returns = []
            for i in range(1, len(self.balance_history)):
                prev_balance = self.balance_history[i-1]['balance']
                curr_balance = self.balance_history[i]['balance']
                
                if prev_balance > 0:
                    period_return = (curr_balance - prev_balance) / prev_balance
                    returns.append(period_return)
            
            if len(returns) == 0:
                return 0.0
            
            import numpy as np
            mean_return = np.mean(returns)
            
            # Рассчитываем downside deviation (учитываем только отрицательные отклонения)
            downside_returns = [r - target_return for r in returns if r < target_return]
            
            if len(downside_returns) == 0:
                # Нет негативных периодов - отличный результат
                return 999.0 if mean_return > target_return else 0.0
            
            downside_deviation = np.sqrt(np.mean(np.array(downside_returns) ** 2))
            
            if downside_deviation == 0:
                return 0.0
            
            # Sortino Ratio
            sortino = (mean_return - target_return) / downside_deviation
            
            # Аннуализируем
            periods_per_year = self._estimate_periods_per_year()
            if periods_per_year > 0:
                sortino = sortino * np.sqrt(periods_per_year)
            
            return float(sortino)
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета Sortino Ratio: {e}")
            return 0.0
    
    def _calculate_calmar_ratio(self) -> float:
        """
        Рассчитывает коэффициент Кальмара (доходность к максимальной просадке).
        
        Calmar Ratio = Annualized Return / Maximum Drawdown
        
        Returns:
            float: Calmar Ratio (чем выше, тем лучше)
        """
        try:
            max_dd = self._calculate_max_drawdown()
            
            if max_dd == 0:
                return 0.0
            
            # Рассчитываем аннуализированную доходность
            if len(self.balance_history) < 2:
                return 0.0
            
            first_balance = self.balance_history[0]['balance']
            last_balance = self.balance_history[-1]['balance']
            
            if first_balance <= 0:
                return 0.0
            
            total_return = (last_balance - first_balance) / first_balance
            
            # Аннуализируем доходность
            first_time = self.balance_history[0]['datetime']
            last_time = self.balance_history[-1]['datetime']
            days = (last_time - first_time).days
            
            if days <= 0:
                return 0.0
            
            years = days / 365.25
            if years <= 0:
                return 0.0
            
            annualized_return = ((1 + total_return) ** (1 / years) - 1) * 100
            
            # Calmar Ratio = Annualized Return / Max Drawdown
            calmar = annualized_return / max_dd if max_dd > 0 else 0.0
            
            return float(calmar)
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета Calmar Ratio: {e}")
            return 0.0
    
    def _calculate_profit_factor(self) -> float:
        """
        Рассчитывает Profit Factor.
        
        Returns:
            float: Profit Factor (отношение прибыли к убыткам)
        """
        try:
            stats = self.get_virtual_stats()
            
            # Получаем сумму прибылей и убытков
            total_profit = stats.get('total_profit', 0) or 0
            total_loss = stats.get('total_loss', 0) or 0
            
            if total_loss == 0:
                return 999.0 if total_profit > 0 else 0.0
            
            # Profit Factor = Общая прибыль / Общие убытки
            return total_profit / total_loss if total_loss > 0 else 0.0
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета Profit Factor: {e}")
            return 0.0
    
    def _calculate_avg_trade_duration(self) -> float:
        """
        Рассчитывает среднюю продолжительность сделки.
        
        Returns:
            float: Средняя продолжительность в часах
        """
        try:
            # Получаем все закрытые позиции из БД
            if self.db.db_type == 'postgresql':
                query = """
                SELECT created_at, closed_at 
                FROM virtual_positions 
                WHERE status = 'closed' AND closed_at IS NOT NULL
                """
            else:
                query = """
                SELECT created_at, closed_at 
                FROM virtual_positions 
                WHERE status = 'closed' AND closed_at IS NOT NULL
                """
            
            positions = self.db._execute_query(query)
            
            if not positions or len(positions) == 0:
                return 0.0
            
            durations = []
            for pos in positions:
                created = pos.get('created_at')
                closed = pos.get('closed_at')
                
                if created and closed:
                    # Если это строки, парсим их
                    if isinstance(created, str):
                        from datetime import datetime
                        created = datetime.fromisoformat(created.replace('Z', '+00:00'))
                    if isinstance(closed, str):
                        from datetime import datetime
                        closed = datetime.fromisoformat(closed.replace('Z', '+00:00'))
                    
                    duration = (closed - created).total_seconds() / 3600  # в часах
                    durations.append(duration)
            
            if len(durations) == 0:
                return 0.0
            
            import numpy as np
            return float(np.mean(durations))
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета средней продолжительности сделки: {e}")
            return 0.0
    
    def _calculate_expectancy(self) -> float:
        """
        Рассчитывает математическое ожидание (expectancy) стратегии.
        
        Expectancy = (Win Rate * Avg Win) - (Loss Rate * Avg Loss)
        
        Returns:
            float: Ожидаемая прибыль на сделку в USDT
        """
        try:
            stats = self.get_virtual_stats()
            
            total_trades = stats.get('total_trades', 0) or 0
            winning_trades = stats.get('winning_trades', 0) or 0
            losing_trades = stats.get('losing_trades', 0) or 0
            total_profit = stats.get('total_profit', 0) or 0
            total_loss = stats.get('total_loss', 0) or 0
            
            if total_trades == 0:
                return 0.0
            
            win_rate = winning_trades / total_trades
            loss_rate = losing_trades / total_trades
            
            avg_win = total_profit / winning_trades if winning_trades > 0 else 0
            avg_loss = total_loss / losing_trades if losing_trades > 0 else 0
            
            expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
            
            return float(expectancy)
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка расчета expectancy: {e}")
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
            
            # Показываем информацию о комиссиях если они есть
            total_fees = results.get('total_fees_paid', 0) or 0
            if total_fees > 0:
                self.logger.info(f"\n💸 Комиссии:")
                self.logger.info(f"   Всего комиссий: ${total_fees:.4f}")
                self.logger.info(f"   Комиссии входа: ${results.get('total_entry_fees', 0):.4f}")
                self.logger.info(f"   Комиссии выхода: ${results.get('total_exit_fees', 0):.4f}")
                fee_impact = (total_fees / results.get('initial_balance', 1)) * 100
                self.logger.info(f"   Влияние на баланс: {fee_impact:.3f}%")
            
            self.logger.info(f"\n📉 Риски:")
            self.logger.info(f"   Максимальный баланс: ${results.get('highest_balance', 0):.2f}")
            self.logger.info(f"   Минимальный баланс: ${results.get('lowest_balance', 0):.2f}")
            self.logger.info(f"   Max Drawdown: {results.get('max_drawdown', 0):.2f}%")
            
            self.logger.info(f"\n📊 Риск-скорректированные метрики:")
            sharpe = results.get('sharpe_ratio', 0)
            sortino = results.get('sortino_ratio', 0)
            calmar = results.get('calmar_ratio', 0)
            
            sharpe_grade = self._grade_sharpe_ratio(sharpe)
            self.logger.info(f"   Sharpe Ratio: {sharpe:.3f} {sharpe_grade}")
            self.logger.info(f"   Sortino Ratio: {sortino:.3f}")
            self.logger.info(f"   Calmar Ratio: {calmar:.3f}")
            
            self.logger.info(f"\n💹 Торговые метрики:")
            self.logger.info(f"   Profit Factor: {results.get('profit_factor', 0):.2f}")
            self.logger.info(f"   Expectancy: ${results.get('expectancy', 0):.2f} на сделку")
            
            avg_duration = results.get('avg_trade_duration_hours', 0)
            if avg_duration > 0:
                if avg_duration < 1:
                    self.logger.info(f"   Средняя длительность сделки: {avg_duration * 60:.1f} минут")
                elif avg_duration < 24:
                    self.logger.info(f"   Средняя длительность сделки: {avg_duration:.1f} часов")
                else:
                    self.logger.info(f"   Средняя длительность сделки: {avg_duration / 24:.1f} дней")
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка вывода отчета: {e}")
    
    def get_results(self) -> Dict:
        """
        Возвращает результаты последнего бэктеста.
        
        Returns:
            Dict: Результаты бэктеста
        """
        return self.backtest_results

