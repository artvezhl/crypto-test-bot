#!/usr/bin/env python3
"""
Скрипт для исправления неправильных причин закрытия позиций.

Исправляет случаи когда:
- Убыточные сделки помечены как 'take_profit'
- Прибыльные сделки помечены как 'stop_loss' (когда достигнут тейк-профит)
"""

import sys
sys.path.append('src')

from database import Database
from datetime import datetime

def fix_close_reasons():
    """Исправляет неправильные причины закрытия позиций"""
    db = Database()
    
    print("=" * 80)
    print("🔧 ИСПРАВЛЕНИЕ ПРИЧИН ЗАКРЫТИЯ ПОЗИЦИЙ")
    print("=" * 80)
    print()
    
    # Получаем все закрытые позиции
    if db.db_type == 'postgresql':
        query = """
        SELECT id, symbol, side, entry_price, exit_price, stop_loss, take_profit, 
               realized_pnl, close_reason
        FROM virtual_positions
        WHERE status = 'closed'
        ORDER BY id
        """
    else:
        query = """
        SELECT id, symbol, side, entry_price, exit_price, stop_loss, take_profit, 
               realized_pnl, close_reason
        FROM virtual_positions
        WHERE status = 'closed'
        ORDER BY id
        """
    
    positions = db._execute_query(query)
    
    if not positions:
        print("Нет закрытых позиций для проверки")
        return
    
    print(f"📊 Найдено {len(positions)} закрытых позиций")
    print()
    
    fixed_count = 0
    issues = []
    
    for row in positions:
        pos = db._convert_row(row)
        
        # Определяем правильную причину на основе PnL и цен
        side = pos['side']
        entry_price = pos['entry_price']
        exit_price = pos.get('exit_price', 0)
        realized_pnl = pos.get('realized_pnl', 0)
        current_reason = pos.get('close_reason', 'manual')
        stop_loss = pos.get('stop_loss')
        take_profit = pos.get('take_profit')
        
        # Определяем правильную причину
        correct_reason = None
        
        if side == 'SELL':  # SHORT
            # Для SHORT: убыток если exit > entry
            if exit_price > entry_price:
                # Это убыток
                if stop_loss and exit_price >= stop_loss:
                    correct_reason = 'stop_loss'
                else:
                    correct_reason = 'stop_loss'  # Убыток = стоп-лосс
            else:
                # Это прибыль
                if take_profit and exit_price <= take_profit:
                    correct_reason = 'take_profit'
                else:
                    correct_reason = 'take_profit' if realized_pnl > 0 else 'stop_loss'
        else:  # BUY (LONG)
            # Для LONG: убыток если exit < entry
            if exit_price < entry_price:
                # Это убыток
                if stop_loss and exit_price <= stop_loss:
                    correct_reason = 'stop_loss'
                else:
                    correct_reason = 'stop_loss'  # Убыток = стоп-лосс
            else:
                # Это прибыль
                if take_profit and exit_price >= take_profit:
                    correct_reason = 'take_profit'
                else:
                    correct_reason = 'take_profit' if realized_pnl > 0 else 'stop_loss'
        
        # Если причина неправильная, исправляем
        if current_reason != correct_reason:
            # Особые случаи: manual и test оставляем как есть
            if current_reason in ['manual', 'test']:
                continue
            
            issues.append({
                'id': pos['id'],
                'symbol': pos['symbol'],
                'side': side,
                'entry': entry_price,
                'exit': exit_price,
                'pnl': realized_pnl,
                'old_reason': current_reason,
                'new_reason': correct_reason
            })
            
            # Обновляем в БД
            if db.db_type == 'postgresql':
                update_query = """
                UPDATE virtual_positions
                SET close_reason = %s
                WHERE id = %s
                """
            else:
                update_query = """
                UPDATE virtual_positions
                SET close_reason = ?
                WHERE id = ?
                """
            
            db._execute_query(update_query, (correct_reason, pos['id']), fetch=False)
            fixed_count += 1
    
    # Выводим результаты
    print(f"✅ Исправлено позиций: {fixed_count}")
    print()
    
    if issues:
        print("📋 Детали исправлений:")
        print("-" * 80)
        for issue in issues:
            side_text = "LONG" if issue['side'] == 'BUY' else "SHORT"
            pnl_sign = "+" if issue['pnl'] >= 0 else ""
            print(f"  #{issue['id']}: {issue['symbol']} {side_text}")
            print(f"    Entry: ${issue['entry']:.2f} → Exit: ${issue['exit']:.2f}")
            print(f"    PnL: ${pnl_sign}{issue['pnl']:.2f}")
            print(f"    {issue['old_reason']} → {issue['new_reason']}")
            print()
    
    print("=" * 80)
    print("✅ Исправление завершено!")
    print("=" * 80)

if __name__ == '__main__':
    try:
        fix_close_reasons()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


