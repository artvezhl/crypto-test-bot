#!/usr/bin/env python3
"""
Быстрый тест бэктестинга с новой быстрой стратегией.
"""

import sys
import os
from datetime import datetime, timedelta
import logging

# Добавляем директорию src в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtester import BacktestEngine

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_quick_backtest():
    """Быстрый тест с новой стратегией"""
    
    print("\n" + "="*80)
    print("⚡ БЫСТРЫЙ ТЕСТ БЭКТЕСТИНГА")
    print("   Тестирование быстрой стратегии без AI")
    print("="*80 + "\n")
    
    # Создаем движок с быстрой стратегией
    logger.info("🔧 Создание BacktestEngine с быстрой стратегией...")
    engine = BacktestEngine(config={'strategy': 'simple'})
    
    # Параметры теста
    symbols = ['BTCUSDT', 'ETHUSDT']
    interval = '15'  # 15 минут
    days = 3  # Короткий период для быстрого теста
    initial_balance = 10000.0
    
    # Период
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    logger.info(f"📊 Параметры:")
    logger.info(f"   Символы: {', '.join(symbols)}")
    logger.info(f"   Интервал: {interval} минут")
    logger.info(f"   Период: {days} дней ({start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')})")
    logger.info(f"   Баланс: ${initial_balance:.2f}")
    logger.info(f"   Стратегия: Быстрая (Техническая)")
    
    # Включаем комиссии и slippage для реалистичности
    engine.use_fees_in_backtest = True
    engine.use_slippage_in_backtest = True
    
    print("\n🚀 Запуск бэктеста...\n")
    
    import time
    start_time = time.time()
    
    # Запускаем бэктест
    results = engine.run_backtest(
        symbols=symbols,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
        initial_balance=initial_balance
    )
    
    elapsed_time = time.time() - start_time
    
    if not results:
        logger.error("❌ Бэктест не вернул результатов")
        return None
    
    # Выводим результаты
    print("\n" + "="*80)
    print("📊 РЕЗУЛЬТАТЫ БЫСТРОГО ТЕСТА")
    print("="*80)
    
    print(f"\n⏱️  Время выполнения: {elapsed_time:.2f} секунд")
    print(f"📊 Обработано свечей: {results.get('total_candles', 'N/A')}")
    
    print(f"\n💰 ФИНАНСОВЫЕ РЕЗУЛЬТАТЫ:")
    print(f"   Начальный баланс: ${results['initial_balance']:.2f}")
    print(f"   Финальный баланс: ${results['final_balance']:.2f}")
    print(f"   Прибыль/Убыток: ${results['total_pnl']:.2f}")
    print(f"   ROI: {results['roi_percent']:.2f}%")
    
    print(f"\n🎯 СТАТИСТИКА СДЕЛОК:")
    print(f"   Всего сделок: {results['total_trades']}")
    print(f"   Прибыльных: {results['winning_trades']}")
    print(f"   Убыточных: {results['losing_trades']}")
    print(f"   Win Rate: {results['win_rate']:.2f}%")
    
    print(f"\n📉 РИСКИ:")
    print(f"   Max Drawdown: {results['max_drawdown']:.2f}%")
    print(f"   Макс. баланс: ${results.get('max_balance', results['final_balance']):.2f}")
    print(f"   Мин. баланс: ${results.get('min_balance', results['final_balance']):.2f}")
    
    print(f"\n📊 ПРОДВИНУТЫЕ МЕТРИКИ:")
    print(f"   Sharpe Ratio: {results['sharpe_ratio']:.3f}")
    print(f"   Sortino Ratio: {results['sortino_ratio']:.3f}")
    print(f"   Calmar Ratio: {results['calmar_ratio']:.3f}")
    print(f"   Profit Factor: {results['profit_factor']:.2f}")
    print(f"   Expectancy: ${results['expectancy']:.2f} на сделку")
    
    if results['total_trades'] > 0:
        print(f"   Средняя длительность: {results['avg_trade_duration_hours']:.1f} часов")
    
    # Оценка скорости
    print(f"\n⚡ ПРОИЗВОДИТЕЛЬНОСТЬ:")
    if elapsed_time < 30:
        print(f"   ✅ ОТЛИЧНО! Бэктест завершен за {elapsed_time:.1f}s")
    elif elapsed_time < 60:
        print(f"   👍 ХОРОШО! Бэктест завершен за {elapsed_time:.1f}s")
    else:
        print(f"   ⚠️  МЕДЛЕННО: {elapsed_time:.1f}s (ожидалось <60s)")
    
    print("\n" + "="*80)
    
    return results


if __name__ == '__main__':
    try:
        results = test_quick_backtest()
        
        if results:
            print("\n✅ Тест успешно завершен!")
            print("\n💡 Следующие шаги:")
            print("   1. Откройте Web UI: http://localhost:5000")
            print("   2. Запустите бэктест через интерфейс")
            print("   3. Проверьте что прогресс-бар работает")
            print("   4. Посмотрите на графики результатов")
        
    except KeyboardInterrupt:
        logger.info("\n\n⏸️  Тест прерван пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка выполнения теста: {e}")
        import traceback
        traceback.print_exc()




