#!/usr/bin/env python3
"""
Тестовый скрипт для проверки загрузки исторических данных.

Использование:
    python src/test_data_loader.py
"""

import logging
from datetime import datetime, timedelta
from data_loader import DataLoader


def setup_logging():
    """Настройка логирования"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def test_data_loading():
    """Тест загрузки данных"""
    print("=" * 80)
    print("🧪 ТЕСТ ЗАГРУЗКИ ИСТОРИЧЕСКИХ ДАННЫХ")
    print("=" * 80)
    
    # Создаём загрузчик
    loader = DataLoader()
    
    # Настраиваем период (последние 7 дней)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    print(f"\n📅 Период: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    
    # Тест 1: Загрузка данных для BTCUSDT
    print("\n" + "-" * 80)
    print("Тест 1: Загрузка BTCUSDT (15m интервал)")
    print("-" * 80)
    
    btc_data = loader.load_historical_data(
        symbol='BTCUSDT',
        interval='15',
        start_date=start_date,
        end_date=end_date,
        use_cache=True
    )
    
    if btc_data:
        print(f"✅ Загружено {len(btc_data)} свечей для BTCUSDT")
        print(f"   Первая свеча: {btc_data[0]['datetime']} - Цена: ${btc_data[0]['close']:.2f}")
        print(f"   Последняя свеча: {btc_data[-1]['datetime']} - Цена: ${btc_data[-1]['close']:.2f}")
    else:
        print("❌ Не удалось загрузить данные для BTCUSDT")
    
    # Тест 2: Повторная загрузка (проверка кеша)
    print("\n" + "-" * 80)
    print("Тест 2: Повторная загрузка (проверка кеша)")
    print("-" * 80)
    
    btc_data_cached = loader.load_historical_data(
        symbol='BTCUSDT',
        interval='15',
        start_date=start_date,
        end_date=end_date,
        use_cache=True
    )
    
    if btc_data_cached:
        print(f"✅ Загружено {len(btc_data_cached)} свечей из кеша")
        if len(btc_data_cached) == len(btc_data):
            print("✅ Количество свечей совпадает с первой загрузкой")
    else:
        print("❌ Не удалось загрузить данные из кеша")
    
    # Тест 3: Загрузка для нескольких символов
    print("\n" + "-" * 80)
    print("Тест 3: Предзагрузка нескольких символов")
    print("-" * 80)
    
    # Короткий период для быстрого теста (последние 24 часа)
    test_start = end_date - timedelta(days=1)
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    
    all_data = loader.preload_data_for_backtest(
        symbols=symbols,
        interval='15',
        start_date=test_start,
        end_date=end_date
    )
    
    print(f"\n✅ Загружено данных для {len(all_data)} символов:")
    for symbol, klines in all_data.items():
        if klines:
            print(f"   {symbol}: {len(klines)} свечей")
    
    # Тест 4: Проверка покрытия кеша
    print("\n" + "-" * 80)
    print("Тест 4: Проверка покрытия кеша")
    print("-" * 80)
    
    start_ms = int(start_date.timestamp() * 1000)
    end_ms = int(end_date.timestamp() * 1000)
    
    cache_info = loader.db.check_cache_coverage(
        symbol='BTCUSDT',
        interval='15',
        start_timestamp=start_ms,
        end_timestamp=end_ms
    )
    
    print(f"📊 Информация о кеше для BTCUSDT:")
    print(f"   Есть данные: {cache_info.get('has_data', False)}")
    print(f"   Количество свечей: {cache_info.get('cached_count', 0)}")
    if cache_info.get('first_timestamp'):
        first_dt = datetime.fromtimestamp(cache_info['first_timestamp'] / 1000)
        last_dt = datetime.fromtimestamp(cache_info['last_timestamp'] / 1000)
        print(f"   Период: {first_dt.strftime('%Y-%m-%d %H:%M')} - {last_dt.strftime('%Y-%m-%d %H:%M')}")
    
    print("\n" + "=" * 80)
    print("✅ ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
    print("=" * 80)


def test_cache_management():
    """Тест управления кешем"""
    print("\n" + "=" * 80)
    print("🧪 ТЕСТ УПРАВЛЕНИЯ КЕШЕМ")
    print("=" * 80)
    
    loader = DataLoader()
    
    # Информация о кеше
    print("\n📊 Статистика кеша:")
    stats = loader.get_cache_stats()
    if stats:
        print(f"   {stats}")
    else:
        print("   Статистика пока не реализована")
    
    # Очистка старого кеша (не выполняем, только демонстрируем)
    print("\n🗑️  Очистка старых данных (>90 дней):")
    print("   loader.clear_old_cache(days=90)  # Закомментировано для безопасности")
    # loader.clear_old_cache(days=90)  # Раскомментировать для очистки
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    setup_logging()
    
    print("\n")
    print("╔═══════════════════════════════════════════════════════════════════════════════╗")
    print("║                     ТЕСТИРОВАНИЕ DATA LOADER                                  ║")
    print("║                  Загрузка исторических данных с кешированием                  ║")
    print("╚═══════════════════════════════════════════════════════════════════════════════╝")
    print("\n")
    
    try:
        # Основные тесты загрузки
        test_data_loading()
        
        # Тесты управления кешем
        test_cache_management()
        
        print("\n✅ Все тесты выполнены успешно!\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
    except Exception as e:
        print(f"\n\n❌ Ошибка при выполнении тестов: {e}")
        import traceback
        traceback.print_exc()


