#!/usr/bin/env python3
"""
Тест комиссий и slippage в системе бэктестинга.

Этот скрипт демонстрирует работу комиссий и slippage при торговле.
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


def test_fees_and_slippage():
    """Тест бэктеста с комиссиями и slippage"""
    
    logger.info("=" * 80)
    logger.info("🧪 ТЕСТ КОМИССИЙ И SLIPPAGE")
    logger.info("=" * 80)
    
    # Создаем два движка бэктестинга
    
    # 1. Без комиссий и slippage (идеальные условия)
    logger.info("\n📊 Тест 1: БЕЗ комиссий и slippage (идеальные условия)")
    logger.info("-" * 80)
    engine_ideal = BacktestEngine()
    engine_ideal.use_fees_in_backtest = False
    engine_ideal.use_slippage_in_backtest = False
    
    # 2. С комиссиями и slippage (реалистичные условия)
    logger.info("\n📊 Тест 2: С комиссиями и slippage (реалистичные условия)")
    logger.info("-" * 80)
    engine_realistic = BacktestEngine()
    engine_realistic.use_fees_in_backtest = True
    engine_realistic.use_slippage_in_backtest = True
    
    # Настройки комиссий (Bybit)
    engine_realistic.maker_fee_percent = 0.055
    engine_realistic.taker_fee_percent = 0.06
    engine_realistic.slippage_percent = 0.05
    
    # Параметры бэктеста
    symbols = ['BTCUSDT', 'ETHUSDT']
    interval = '15'
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    initial_balance = 10000.0
    
    # Запуск бэктеста БЕЗ комиссий и slippage
    logger.info("\n🚀 Запуск идеального бэктеста...")
    results_ideal = engine_ideal.run_backtest(
        symbols=symbols,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
        initial_balance=initial_balance
    )
    
    # Запуск бэктеста С комиссиями и slippage
    logger.info("\n\n🚀 Запуск реалистичного бэктеста...")
    results_realistic = engine_realistic.run_backtest(
        symbols=symbols,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
        initial_balance=initial_balance
    )
    
    # Сравнение результатов
    logger.info("\n" + "=" * 80)
    logger.info("📊 СРАВНЕНИЕ РЕЗУЛЬТАТОВ")
    logger.info("=" * 80)
    
    logger.info("\n🎯 ИДЕАЛЬНЫЕ УСЛОВИЯ (без комиссий и slippage):")
    logger.info(f"   ROI: {results_ideal.get('roi_percent', 0):.2f}%")
    logger.info(f"   PnL: ${results_ideal.get('total_pnl', 0):.2f}")
    logger.info(f"   Сделок: {results_ideal.get('total_trades', 0)}")
    logger.info(f"   Win Rate: {results_ideal.get('win_rate', 0):.2f}%")
    logger.info(f"   Profit Factor: {results_ideal.get('profit_factor', 0):.2f}")
    
    logger.info("\n🎯 РЕАЛИСТИЧНЫЕ УСЛОВИЯ (с комиссиями и slippage):")
    logger.info(f"   ROI: {results_realistic.get('roi_percent', 0):.2f}%")
    logger.info(f"   PnL: ${results_realistic.get('total_pnl', 0):.2f}")
    logger.info(f"   Сделок: {results_realistic.get('total_trades', 0)}")
    logger.info(f"   Win Rate: {results_realistic.get('win_rate', 0):.2f}%")
    logger.info(f"   Profit Factor: {results_realistic.get('profit_factor', 0):.2f}")
    logger.info(f"   Всего комиссий: ${results_realistic.get('total_fees_paid', 0):.4f}")
    
    # Расчет влияния комиссий и slippage
    roi_diff = results_ideal.get('roi_percent', 0) - results_realistic.get('roi_percent', 0)
    pnl_diff = results_ideal.get('total_pnl', 0) - results_realistic.get('total_pnl', 0)
    
    logger.info("\n💡 ВЛИЯНИЕ КОМИССИЙ И SLIPPAGE:")
    logger.info(f"   Снижение ROI: {roi_diff:.2f}%")
    logger.info(f"   Снижение PnL: ${pnl_diff:.2f}")
    if results_ideal.get('total_trades', 0) > 0:
        avg_cost_per_trade = pnl_diff / results_ideal.get('total_trades', 1)
        logger.info(f"   Средние затраты на сделку: ${avg_cost_per_trade:.4f}")
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ Тест завершен!")
    logger.info("=" * 80)
    
    return {
        'ideal': results_ideal,
        'realistic': results_realistic,
        'impact': {
            'roi_diff': roi_diff,
            'pnl_diff': pnl_diff
        }
    }


if __name__ == "__main__":
    try:
        results = test_fees_and_slippage()
        
        # Выводим краткую сводку
        print("\n\n" + "=" * 80)
        print("📝 КРАТКАЯ СВОДКА")
        print("=" * 80)
        print(f"Комиссии и slippage снизили ROI на {results['impact']['roi_diff']:.2f}%")
        print(f"Это важно учитывать при реальной торговле!")
        print("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ Ошибка выполнения теста: {e}")
        import traceback
        traceback.print_exc()

