"""
Тест таблицы сделок в Web UI.
Создаем несколько тестовых сделок вручную для проверки.
"""

import sys
sys.path.append('src')

from database import Database
from datetime import datetime, timedelta
import random

def create_test_trades():
    """Создаем тестовые сделки"""
    db = Database()
    
    print("🧪 Создание тестовых сделок...")
    
    # Очищаем старые тестовые позиции
    db._execute_query("DELETE FROM virtual_positions", fetch=False)
    print("  ✅ Старые позиции очищены")
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT']
    sides = ['BUY', 'SELL']
    
    base_time = datetime.now() - timedelta(days=7)
    
    # Создаем 15 тестовых сделок
    for i in range(15):
        symbol = random.choice(symbols)
        side = random.choice(sides)
        
        # Генерируем реалистичные цены
        if symbol == 'BTCUSDT':
            entry_price = 95000 + random.uniform(-5000, 5000)
        elif symbol == 'ETHUSDT':
            entry_price = 3500 + random.uniform(-500, 500)
        elif symbol == 'SOLUSDT':
            entry_price = 200 + random.uniform(-50, 50)
        else:  # XRPUSDT
            entry_price = 2.5 + random.uniform(-0.5, 0.5)
        
        # Генерируем размер позиции
        size = random.uniform(0.001, 0.1)
        
        # Генерируем выходную цену (±1-5%)
        price_change_percent = random.uniform(-5, 5)
        exit_price = entry_price * (1 + price_change_percent / 100)
        
        # Рассчитываем PnL
        if side == 'BUY':
            pnl_gross = (exit_price - entry_price) * size
        else:
            pnl_gross = (entry_price - exit_price) * size
        
        # Комиссии
        entry_fee = entry_price * size * 0.0006  # 0.06%
        exit_fee = exit_price * size * 0.0006
        total_fees = entry_fee + exit_fee
        
        pnl_net = pnl_gross - total_fees
        pnl_percent = (pnl_net / (entry_price * size)) * 100 if (entry_price * size) > 0 else 0
        
        # Создаем временные метки
        created_at = base_time + timedelta(hours=i * 8)
        closed_at = created_at + timedelta(minutes=random.randint(15, 240))
        
        # Добавляем позицию
        position_id = db.add_virtual_position(
            symbol=symbol,
            side=side,
            size=size,
            entry_price=entry_price,
            leverage=5,
            entry_fee=entry_fee
        )
        
        if position_id and position_id > 0:
            # Закрываем позицию
            db.close_virtual_position(
                position_id=position_id,
                exit_price=exit_price,
                close_reason='test' if i % 2 == 0 else 'take_profit',
                exit_fee=exit_fee
            )
            
            result = "✅ WIN" if pnl_net > 0 else "❌ LOSS"
            print(f"  {result} #{position_id}: {side:4} {symbol:10} PnL: ${pnl_net:+7.2f} ({pnl_percent:+.2f}%)")
        else:
            print(f"  ❌ FAILED to create position: ID={position_id}")
    
    print(f"\n✅ Создано {len(db.get_virtual_closed_positions())} тестовых сделок")
    
    # Показываем статистику
    stats = db.get_virtual_trade_stats(days=30)
    print(f"\n📊 Статистика:")
    print(f"  Всего сделок: {stats.get('total_trades', 0)}")
    print(f"  Закрытых: {stats.get('closed_trades', 0)}")
    print(f"  Прибыльных: {stats.get('winning_trades', 0)}")
    print(f"  Убыточных: {stats.get('losing_trades', 0)}")
    print(f"  Общий PnL: ${stats.get('total_realized_pnl', 0):.2f}")
    print(f"  Win Rate: {(stats.get('winning_trades', 0) / stats.get('closed_trades', 1) * 100):.1f}%")

if __name__ == '__main__':
    print("="*80)
    print("🧪 ТЕСТ ТАБЛИЦЫ СДЕЛОК В WEB UI")
    print("="*80)
    print()
    
    create_test_trades()
    
    print()
    print("="*80)
    print("✅ Тестовые данные созданы!")
    print("  🌐 Откройте http://localhost:5000")
    print("  🔄 Запустите бэктест (любые параметры)")
    print("  📊 Проверьте таблицу сделок внизу страницы")
    print("="*80)

