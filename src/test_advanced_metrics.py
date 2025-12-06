#!/usr/bin/env python3
"""
Тест продвинутых метрик бэктестинга.

Этот скрипт демонстрирует работу улучшенных метрик:
- Sharpe Ratio
- Sortino Ratio
- Calmar Ratio
- Expectancy
- Average Trade Duration
"""

import logging
from datetime import datetime, timedelta
from backtester import BacktestEngine

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def explain_metrics():
    """Объясняет значение каждой метрики"""
    logger.info("=" * 80)
    logger.info("📚 СПРАВКА ПО МЕТРИКАМ")
    logger.info("=" * 80)
    
    logger.info("\n📊 SHARPE RATIO (Коэффициент Шарпа)")
    logger.info("   Что показывает: Риск-скорректированную доходность")
    logger.info("   Формула: (Средняя доходность - Безрисковая ставка) / Стандартное отклонение")
    logger.info("   Оценка:")
    logger.info("      > 3.0  - 🌟 Отлично (профессиональный уровень)")
    logger.info("      2.0-3.0 - ✅ Очень хорошо")
    logger.info("      1.0-2.0 - 👍 Хорошо")
    logger.info("      0.5-1.0 - 🟡 Приемлемо")
    logger.info("      < 0.5  - 🔴 Плохо")
    
    logger.info("\n📊 SORTINO RATIO (Коэффициент Сортино)")
    logger.info("   Что показывает: Риск-скорректированную доходность (только негативная волатильность)")
    logger.info("   Отличие от Sharpe: Учитывает только убыточные периоды")
    logger.info("   Почему важно: Более точная оценка для асимметричных стратегий")
    logger.info("   Оценка: Аналогична Sharpe Ratio, но обычно выше")
    
    logger.info("\n📊 CALMAR RATIO (Коэффициент Кальмара)")
    logger.info("   Что показывает: Соотношение доходности к максимальной просадке")
    logger.info("   Формула: Годовая доходность / Максимальная просадка")
    logger.info("   Оценка:")
    logger.info("      > 3.0  - Отлично")
    logger.info("      1.0-3.0 - Хорошо")
    logger.info("      < 1.0  - Риск превышает доходность")
    
    logger.info("\n📊 EXPECTANCY (Математическое ожидание)")
    logger.info("   Что показывает: Ожидаемую прибыль на одну сделку")
    logger.info("   Формула: (Win Rate × Avg Win) - (Loss Rate × Avg Loss)")
    logger.info("   Оценка:")
    logger.info("      > $10  - Отлично для большинства стратегий")
    logger.info("      > $0   - Прибыльная стратегия")
    logger.info("      < $0   - Убыточная стратегия")
    
    logger.info("\n📊 PROFIT FACTOR (Фактор прибыли)")
    logger.info("   Что показывает: Отношение общей прибыли к общим убыткам")
    logger.info("   Формула: Сумма прибылей / Сумма убытков")
    logger.info("   Оценка:")
    logger.info("      > 2.0  - Отлично")
    logger.info("      1.5-2.0 - Хорошо")
    logger.info("      1.0-1.5 - Приемлемо")
    logger.info("      < 1.0  - Убыточная стратегия")
    
    logger.info("\n" + "=" * 80)


def test_advanced_metrics():
    """Тест бэктеста с продвинутыми метриками"""
    
    logger.info("=" * 80)
    logger.info("🧪 ТЕСТ ПРОДВИНУТЫХ МЕТРИК БЭКТЕСТИНГА")
    logger.info("=" * 80)
    
    # Создаем движок бэктестинга
    engine = BacktestEngine()
    
    # Настройки для реалистичного бэктеста
    engine.use_fees_in_backtest = True
    engine.use_slippage_in_backtest = True
    
    # Параметры бэктеста
    symbols = ['BTCUSDT', 'ETHUSDT']
    interval = '15'
    end_date = datetime.now()
    start_date = end_date - timedelta(days=14)  # 2 недели для достаточной статистики
    initial_balance = 10000.0
    
    logger.info(f"\n⚙️ ПАРАМЕТРЫ БЭКТЕСТА:")
    logger.info(f"   Символы: {', '.join(symbols)}")
    logger.info(f"   Период: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    logger.info(f"   Таймфрейм: {interval} минут")
    logger.info(f"   Начальный баланс: ${initial_balance:.2f}")
    logger.info(f"   Комиссии: Включены (Bybit: 0.055%/0.06%)")
    logger.info(f"   Slippage: Включен (0.05%)")
    
    # Запуск бэктеста
    logger.info("\n🚀 Запуск бэктеста...")
    results = engine.run_backtest(
        symbols=symbols,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
        initial_balance=initial_balance
    )
    
    if not results:
        logger.error("❌ Бэктест не вернул результатов")
        return None
    
    # Детальный анализ метрик
    logger.info("\n" + "=" * 80)
    logger.info("🔍 ДЕТАЛЬНЫЙ АНАЛИЗ МЕТРИК")
    logger.info("=" * 80)
    
    # Базовые метрики
    logger.info("\n💰 БАЗОВЫЕ ПОКАЗАТЕЛИ:")
    logger.info(f"   ROI: {results['roi_percent']:.2f}%")
    logger.info(f"   Прибыль: ${results['total_pnl']:.2f}")
    logger.info(f"   Сделок: {results['total_trades']}")
    logger.info(f"   Win Rate: {results['win_rate']:.2f}%")
    
    # Риск-метрики
    logger.info("\n📉 РИСК-МЕТРИКИ:")
    logger.info(f"   Max Drawdown: {results['max_drawdown']:.2f}%")
    
    sharpe = results['sharpe_ratio']
    sortino = results['sortino_ratio']
    calmar = results['calmar_ratio']
    
    logger.info(f"   Sharpe Ratio: {sharpe:.3f}")
    if sharpe >= 2.0:
        logger.info("      ✅ Отличный результат! Стратегия эффективна с учетом риска.")
    elif sharpe >= 1.0:
        logger.info("      👍 Хороший результат. Доходность оправдывает риск.")
    elif sharpe >= 0.5:
        logger.info("      🟡 Приемлемо, но есть потенциал для улучшения.")
    else:
        logger.info("      ⚠️ Низкий Sharpe Ratio. Риск слишком высок для такой доходности.")
    
    logger.info(f"   Sortino Ratio: {sortino:.3f}")
    if sortino > sharpe:
        logger.info("      💡 Sortino выше Sharpe - стратегия лучше защищена от просадок")
    
    logger.info(f"   Calmar Ratio: {calmar:.3f}")
    if calmar >= 1.0:
        logger.info("      ✅ Доходность превышает максимальную просадку")
    else:
        logger.info("      ⚠️ Просадка больше годовой доходности - высокий риск")
    
    # Торговые метрики
    logger.info("\n💹 ТОРГОВЫЕ МЕТРИКИ:")
    
    pf = results['profit_factor']
    logger.info(f"   Profit Factor: {pf:.2f}")
    if pf >= 2.0:
        logger.info("      ✅ Отлично! Прибыли вдвое превышают убытки.")
    elif pf >= 1.5:
        logger.info("      👍 Хорошо. Стратегия стабильно прибыльна.")
    elif pf >= 1.0:
        logger.info("      🟡 Приемлемо, но есть риск.")
    else:
        logger.info("      🔴 Стратегия убыточна!")
    
    exp = results['expectancy']
    logger.info(f"   Expectancy: ${exp:.2f} на сделку")
    if exp > 0:
        total_expected = exp * results['total_trades']
        logger.info(f"      💰 При {results['total_trades']} сделках ожидается: ${total_expected:.2f}")
    else:
        logger.info("      ⚠️ Отрицательное ожидание - стратегия убыточна")
    
    avg_duration = results['avg_trade_duration_hours']
    if avg_duration > 0:
        if avg_duration < 1:
            logger.info(f"   Средняя длительность: {avg_duration * 60:.1f} минут (скальпинг)")
        elif avg_duration < 24:
            logger.info(f"   Средняя длительность: {avg_duration:.1f} часов (дневная торговля)")
        else:
            logger.info(f"   Средняя длительность: {avg_duration / 24:.1f} дней (свинг-трейдинг)")
    
    # Комиссии
    logger.info("\n💸 ВЛИЯНИЕ КОМИССИЙ:")
    fees = results['total_fees_paid']
    if fees > 0:
        fee_impact = (fees / initial_balance) * 100
        logger.info(f"   Всего комиссий: ${fees:.4f} ({fee_impact:.3f}% от баланса)")
        if results['total_trades'] > 0:
            avg_fee = fees / results['total_trades']
            logger.info(f"   Средняя комиссия на сделку: ${avg_fee:.4f}")
    
    # Итоговая оценка
    logger.info("\n" + "=" * 80)
    logger.info("🏆 ИТОГОВАЯ ОЦЕНКА СТРАТЕГИИ")
    logger.info("=" * 80)
    
    score = 0
    max_score = 5
    
    if results['roi_percent'] > 0:
        score += 1
        logger.info("✅ ROI положительный")
    else:
        logger.info("❌ ROI отрицательный")
    
    if sharpe >= 1.0:
        score += 1
        logger.info("✅ Sharpe Ratio хороший (≥ 1.0)")
    else:
        logger.info("❌ Sharpe Ratio низкий (< 1.0)")
    
    if pf >= 1.5:
        score += 1
        logger.info("✅ Profit Factor хороший (≥ 1.5)")
    else:
        logger.info("❌ Profit Factor низкий (< 1.5)")
    
    if exp > 0:
        score += 1
        logger.info("✅ Expectancy положительное")
    else:
        logger.info("❌ Expectancy отрицательное")
    
    if results['max_drawdown'] < 20:
        score += 1
        logger.info("✅ Max Drawdown приемлемый (< 20%)")
    else:
        logger.info("❌ Max Drawdown высокий (≥ 20%)")
    
    logger.info(f"\n📊 ОБЩИЙ БАЛЛ: {score}/{max_score}")
    
    if score >= 4:
        logger.info("🌟 ОТЛИЧНО! Стратегия показывает сильные результаты.")
    elif score >= 3:
        logger.info("👍 ХОРОШО. Стратегия работает, но есть потенциал для улучшения.")
    elif score >= 2:
        logger.info("🟡 ПРИЕМЛЕМО. Требуется оптимизация параметров.")
    else:
        logger.info("🔴 ПЛОХО. Стратегия нуждается в серьезной доработке.")
    
    logger.info("\n" + "=" * 80)
    
    return results


if __name__ == "__main__":
    try:
        # Сначала объясняем метрики
        explain_metrics()
        
        input("\n\n▶️  Нажмите Enter для запуска бэктеста...")
        
        # Затем запускаем тест
        results = test_advanced_metrics()
        
        if results:
            logger.info("\n✅ Тест успешно завершен!")
            logger.info("📝 Все метрики рассчитаны и отображены выше.")
        
    except KeyboardInterrupt:
        logger.info("\n\n⏸️  Тест прерван пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка выполнения теста: {e}")
        import traceback
        traceback.print_exc()

