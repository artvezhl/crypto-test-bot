"""
DataLoader - умная загрузка исторических данных с кешированием.

Этот модуль отвечает за:
1. Загрузку исторических данных с Bybit API
2. Кеширование данных в БД
3. Оптимизацию загрузки (использование кеша когда возможно)
4. Валидацию и очистку данных
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from bybit_client import BybitClient
from database import Database


class DataLoader:
    """
    Класс для загрузки и кеширования исторических данных.
    
    Автоматически использует кеш БД когда данные уже загружены,
    загружает с API только недостающие данные.
    """
    
    def __init__(self, bybit_client: Optional[BybitClient] = None, 
                 database: Optional[Database] = None):
        """
        Инициализация DataLoader.
        
        Args:
            bybit_client: Экземпляр BybitClient (создаётся автоматически если не указан)
            database: Экземпляр Database (создаётся автоматически если не указан)
        """
        self.logger = logging.getLogger(__name__)
        self.bybit = bybit_client or BybitClient()
        self.db = database or Database()
        
        self.logger.info("✅ DataLoader инициализирован")
    
    def load_historical_data(self, symbol: str, interval: str, 
                            start_date: datetime, end_date: datetime,
                            use_cache: bool = True, force_reload: bool = False) -> List[Dict]:
        """
        Загружает исторические данные с оптимальным использованием кеша.
        
        Args:
            symbol: Торговая пара (например, 'BTCUSDT')
            interval: Таймфрейм ('1', '5', '15', '30', '60', '240', 'D', 'W')
            start_date: Начальная дата
            end_date: Конечная дата
            use_cache: Использовать кеш БД (по умолчанию True)
            force_reload: Принудительно загрузить с API даже если есть в кеше
            
        Returns:
            List[Dict]: Список свечей OHLCV
        """
        try:
            # Конвертируем даты в миллисекунды
            start_ms = int(start_date.timestamp() * 1000)
            end_ms = int(end_date.timestamp() * 1000)
            
            self.logger.info(
                f"📊 Загрузка данных для {symbol} ({interval}) "
                f"с {start_date.strftime('%Y-%m-%d %H:%M')} "
                f"по {end_date.strftime('%Y-%m-%d %H:%M')}"
            )
            
            # Если принудительная перезагрузка - загружаем с API
            if force_reload:
                self.logger.info("🔄 Принудительная перезагрузка с API")
                return self._load_from_api_and_cache(symbol, interval, start_date, end_date)
            
            # Если не используем кеш - загружаем только с API
            if not use_cache:
                self.logger.info("📡 Загрузка только с API (кеш отключён)")
                return self.bybit.get_historical_klines_range(symbol, interval, start_date, end_date)
            
            # Проверяем наличие данных в кеше
            cache_info = self.db.check_cache_coverage(symbol, interval, start_ms, end_ms)
            
            if cache_info['has_data']:
                self.logger.info(
                    f"💾 Найдено {cache_info['cached_count']} свечей в кеше"
                )
                
                # Загружаем из кеша
                cached_data = self.db.get_historical_klines_from_cache(
                    symbol, interval, start_ms, end_ms
                )
                
                # Проверяем полноту данных
                if self._is_data_complete(cached_data, start_ms, end_ms, interval):
                    self.logger.info(f"✅ Данные полные, используем кеш ({len(cached_data)} свечей)")
                    return cached_data
                else:
                    self.logger.warning(
                        "⚠️ Данные в кеше неполные, догружаем с API"
                    )
                    return self._fill_missing_data(
                        symbol, interval, start_date, end_date, cached_data
                    )
            else:
                self.logger.info("📡 Данных нет в кеше, загружаем с API")
                return self._load_from_api_and_cache(symbol, interval, start_date, end_date)
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка загрузки исторических данных: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _load_from_api_and_cache(self, symbol: str, interval: str,
                                 start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        Загружает данные с API и сохраняет в кеш.
        
        Args:
            symbol: Торговая пара
            interval: Таймфрейм
            start_date: Начальная дата
            end_date: Конечная дата
            
        Returns:
            List[Dict]: Загруженные свечи
        """
        try:
            # Загружаем с API
            klines = self.bybit.get_historical_klines_range(
                symbol, interval, start_date, end_date
            )
            
            if not klines:
                self.logger.warning(f"⚠️ Не удалось загрузить данные с API для {symbol}")
                return []
            
            # Сохраняем в кеш
            saved_count = self.db.save_historical_klines(symbol, interval, klines)
            self.logger.info(f"💾 Сохранено {saved_count} свечей в кеш")
            
            return klines
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка загрузки с API: {e}")
            return []
    
    def _fill_missing_data(self, symbol: str, interval: str,
                          start_date: datetime, end_date: datetime,
                          cached_data: List[Dict]) -> List[Dict]:
        """
        Догружает недостающие данные к уже загруженным из кеша.
        
        Args:
            symbol: Торговая пара
            interval: Таймфрейм
            start_date: Начальная дата
            end_date: Конечная дата
            cached_data: Данные из кеша
            
        Returns:
            List[Dict]: Полный набор данных
        """
        try:
            # Находим пропуски в данных
            missing_ranges = self._find_missing_ranges(
                cached_data, 
                int(start_date.timestamp() * 1000),
                int(end_date.timestamp() * 1000),
                interval
            )
            
            if not missing_ranges:
                return cached_data
            
            self.logger.info(f"🔍 Найдено {len(missing_ranges)} пропусков в данных")
            
            # Загружаем недостающие данные
            all_data = list(cached_data)
            
            for range_start, range_end in missing_ranges:
                range_start_date = datetime.fromtimestamp(range_start / 1000)
                range_end_date = datetime.fromtimestamp(range_end / 1000)
                
                self.logger.info(
                    f"📡 Загружаем пропуск: "
                    f"{range_start_date.strftime('%Y-%m-%d %H:%M')} - "
                    f"{range_end_date.strftime('%Y-%m-%d %H:%M')}"
                )
                
                missing_data = self.bybit.get_historical_klines_range(
                    symbol, interval, range_start_date, range_end_date
                )
                
                if missing_data:
                    # Сохраняем в кеш
                    self.db.save_historical_klines(symbol, interval, missing_data)
                    all_data.extend(missing_data)
            
            # Сортируем и удаляем дубликаты
            all_data.sort(key=lambda x: x['timestamp'])
            unique_data = self._remove_duplicates(all_data)
            
            self.logger.info(f"✅ Собрано {len(unique_data)} уникальных свечей")
            return unique_data
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка заполнения пропусков: {e}")
            return cached_data
    
    def _is_data_complete(self, data: List[Dict], start_ms: int, 
                         end_ms: int, interval: str) -> bool:
        """
        Проверяет полноту данных.
        
        Args:
            data: Список свечей
            start_ms: Начальная временная метка
            end_ms: Конечная временная метка
            interval: Таймфрейм
            
        Returns:
            bool: True если данные полные
        """
        if not data:
            return False
        
        # Проверяем границы
        first_timestamp = data[0]['timestamp']
        last_timestamp = data[-1]['timestamp']
        
        # Допускаем небольшое отклонение (1 интервал)
        interval_ms = self.bybit._interval_to_milliseconds(interval)
        
        if first_timestamp > start_ms + interval_ms:
            self.logger.debug(f"⚠️ Первая свеча позже начала периода")
            return False
        
        if last_timestamp < end_ms - interval_ms:
            self.logger.debug(f"⚠️ Последняя свеча раньше конца периода")
            return False
        
        # Проверяем наличие больших пропусков
        expected_count = (end_ms - start_ms) // interval_ms
        actual_count = len(data)
        
        # Допускаем отклонение до 5%
        if actual_count < expected_count * 0.95:
            self.logger.debug(
                f"⚠️ Недостаточно данных: {actual_count} из ожидаемых ~{expected_count}"
            )
            return False
        
        return True
    
    def _find_missing_ranges(self, data: List[Dict], start_ms: int,
                            end_ms: int, interval: str) -> List[tuple]:
        """
        Находит пропуски во временных рядах.
        
        Args:
            data: Список свечей
            start_ms: Начальная временная метка
            end_ms: Конечная временная метка
            interval: Таймфрейм
            
        Returns:
            List[tuple]: Список пропусков [(start, end), ...]
        """
        if not data:
            return [(start_ms, end_ms)]
        
        missing_ranges = []
        interval_ms = self.bybit._interval_to_milliseconds(interval)
        
        # Сортируем данные
        sorted_data = sorted(data, key=lambda x: x['timestamp'])
        
        # Проверяем начало
        first_timestamp = sorted_data[0]['timestamp']
        if first_timestamp > start_ms + interval_ms:
            missing_ranges.append((start_ms, first_timestamp - interval_ms))
        
        # Проверяем пропуски между свечами
        for i in range(len(sorted_data) - 1):
            current_ts = sorted_data[i]['timestamp']
            next_ts = sorted_data[i + 1]['timestamp']
            
            expected_next = current_ts + interval_ms
            
            # Если пропуск больше 2 интервалов
            if next_ts > expected_next + interval_ms:
                missing_ranges.append((expected_next, next_ts - interval_ms))
        
        # Проверяем конец
        last_timestamp = sorted_data[-1]['timestamp']
        if last_timestamp < end_ms - interval_ms:
            missing_ranges.append((last_timestamp + interval_ms, end_ms))
        
        return missing_ranges
    
    def _remove_duplicates(self, data: List[Dict]) -> List[Dict]:
        """
        Удаляет дубликаты по timestamp.
        
        Args:
            data: Список свечей
            
        Returns:
            List[Dict]: Уникальные свечи
        """
        seen = set()
        unique_data = []
        
        for item in data:
            ts = item['timestamp']
            if ts not in seen:
                seen.add(ts)
                unique_data.append(item)
        
        return unique_data
    
    def preload_data_for_backtest(self, symbols: List[str], interval: str,
                                  start_date: datetime, end_date: datetime) -> Dict[str, List[Dict]]:
        """
        Предзагружает данные для нескольких символов (для бэктеста).
        
        Args:
            symbols: Список торговых пар
            interval: Таймфрейм
            start_date: Начальная дата
            end_date: Конечная дата
            
        Returns:
            Dict[str, List[Dict]]: Словарь {symbol: klines}
        """
        try:
            self.logger.info(
                f"📦 Предзагрузка данных для {len(symbols)} символов "
                f"с {start_date.strftime('%Y-%m-%d')} по {end_date.strftime('%Y-%m-%d')}"
            )
            
            all_data = {}
            
            for i, symbol in enumerate(symbols, 1):
                self.logger.info(f"📊 [{i}/{len(symbols)}] Загрузка {symbol}...")
                
                klines = self.load_historical_data(
                    symbol=symbol,
                    interval=interval,
                    start_date=start_date,
                    end_date=end_date,
                    use_cache=True
                )
                
                if klines:
                    all_data[symbol] = klines
                    self.logger.info(f"✅ {symbol}: {len(klines)} свечей")
                else:
                    self.logger.warning(f"⚠️ {symbol}: нет данных")
            
            self.logger.info(
                f"✅ Предзагрузка завершена: {len(all_data)}/{len(symbols)} символов"
            )
            
            return all_data
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка предзагрузки данных: {e}")
            return {}
    
    def clear_old_cache(self, days: int = 30):
        """
        Очищает старые данные из кеша.
        
        Args:
            days: Удалить данные старше N дней
        """
        try:
            deleted_count = self.db.clear_historical_cache(older_than_days=days)
            self.logger.info(f"🗑️ Очищено {deleted_count} старых записей из кеша (>{days} дней)")
        except Exception as e:
            self.logger.error(f"❌ Ошибка очистки кеша: {e}")
    
    def get_cache_stats(self, symbol: Optional[str] = None) -> Dict:
        """
        Получает статистику по кешу.
        
        Args:
            symbol: Символ для статистики (если None - общая)
            
        Returns:
            Dict: Статистика кеша
        """
        try:
            # TODO: Реализовать метод get_cache_stats в Database
            self.logger.info("📊 Статистика кеша пока не реализована")
            return {}
        except Exception as e:
            self.logger.error(f"❌ Ошибка получения статистики: {e}")
            return {}


