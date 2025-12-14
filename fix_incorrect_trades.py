#!/usr/bin/env python3
"""
Скрипт для поиска и исправления всех сделок с некорректной ценой выхода
"""
import sys
sys.path.insert(0, '/app/src')
from database import Database

def find_and_fix_incorrect_trades():
    db = Database()
    
    # Находим все закрытые сделки с подозрительными ценами выхода
    if db.db_type == 'postgresql':
        query = """
        SELECT * FROM virtual_positions 
        WHERE status = 'closed' 
          AND exit_price IS NOT NULL
          AND entry_price IS NOT NULL
        ORDER BY id DESC
        """
    else:
        query = """
        SELECT * FROM virtual_positions 
        WHERE status = 'closed' 
          AND exit_price IS NOT NULL
          AND entry_price IS NOT NULL
        ORDER BY id DESC
        """
    
    result = db._execute_query(query)
    if not result:
        print('❌ Не найдено закрытых сделок')
        return
    
    trades = [db._convert_row(row) if hasattr(db, '_convert_row') else row for row in result]
    
    print(f'📊 Проверка {len(trades)} закрытых сделок...\n')
    
    incorrect_trades = []
    
    for trade in trades:
        entry_price = trade.get('entry_price', 0)
        exit_price = trade.get('exit_price', 0)
        stop_loss = trade.get('stop_loss', 0)
        take_profit = trade.get('take_profit', 0)
        side = trade.get('side', '')
        trade_id = trade.get('id', 0)
        
        if entry_price <= 0 or exit_price <= 0:
            continue
        
        # Проверяем на некорректность
        is_incorrect = False
        reason = ""
        
        if side == 'SELL':
            # Для SELL цена выхода не должна быть намного выше entry_price или stop_loss
            if exit_price > entry_price * 1.5:
                is_incorrect = True
                reason = f"Цена выхода ({exit_price:,.2f}) в {exit_price/entry_price:.2f}x больше цены входа ({entry_price:,.2f})"
            elif stop_loss > 0 and exit_price > stop_loss * 1.5:
                is_incorrect = True
                reason = f"Цена выхода ({exit_price:,.2f}) в {exit_price/stop_loss:.2f}x больше stop_loss ({stop_loss:,.2f})"
        elif side == 'BUY':
            # Для BUY цена выхода не должна быть намного ниже entry_price или stop_loss
            if exit_price < entry_price * 0.5:
                is_incorrect = True
                reason = f"Цена выхода ({exit_price:,.2f}) в {entry_price/exit_price:.2f}x меньше цены входа ({entry_price:,.2f})"
            elif stop_loss > 0 and exit_price < stop_loss * 0.5:
                is_incorrect = True
                reason = f"Цена выхода ({exit_price:,.2f}) в {stop_loss/exit_price:.2f}x меньше stop_loss ({stop_loss:,.2f})"
        
        if is_incorrect:
            incorrect_trades.append((trade, reason))
            print(f'❌ ID {trade_id}: {reason}')
    
    print(f'\n📊 Найдено {len(incorrect_trades)} некорректных сделок\n')
    
    if not incorrect_trades:
        print('✅ Все сделки корректны!')
        return
    
    # Исправляем найденные сделки
    for trade, reason in incorrect_trades:
        fix_trade(db, trade)

def fix_trade(db, trade):
    """Исправление одной сделки"""
    trade_id = trade.get('id', 0)
    entry_price = trade.get('entry_price', 0)
    exit_price = trade.get('exit_price', 0)
    stop_loss = trade.get('stop_loss', 0)
    take_profit = trade.get('take_profit', 0)
    side = trade.get('side', '')
    size = trade.get('size', 0)
    close_reason = trade.get('close_reason', 'stop_loss')
    
    print(f'\n🔧 Исправление сделки ID {trade_id}:')
    print(f'  Символ: {trade.get("symbol", "N/A")}')
    print(f'  Направление: {side}')
    print(f'  Цена входа: ${entry_price:,.2f}')
    print(f'  Цена выхода (текущая): ${exit_price:,.2f}')
    print(f'  Stop Loss: ${stop_loss:,.2f}')
    print(f'  Take Profit: ${take_profit:,.2f}')
    print(f'  Причина закрытия: {close_reason}')
    
    # Определяем правильную цену выхода
    if close_reason == 'stop_loss' and stop_loss > 0:
        # Для stop_loss цена выхода должна быть около stop_loss с учетом slippage
        if side == 'SELL':
            # Закрытие SELL = покупка, slippage увеличивает цену
            correct_exit_price = stop_loss * 1.001  # +0.1% slippage
        else:  # BUY
            # Закрытие BUY = продажа, slippage уменьшает цену
            correct_exit_price = stop_loss * 0.999  # -0.1% slippage
    elif close_reason == 'take_profit' and take_profit > 0:
        # Для take_profit цена выхода должна быть около take_profit с учетом slippage
        if side == 'SELL':
            # Закрытие SELL = покупка, slippage увеличивает цену
            correct_exit_price = take_profit * 1.001  # +0.1% slippage
        else:  # BUY
            # Закрытие BUY = продажа, slippage уменьшает цену
            correct_exit_price = take_profit * 0.999  # -0.1% slippage
    else:
        # Если нет stop_loss/take_profit, используем текущую цену (но это странно)
        print(f'  ⚠️ Нет stop_loss/take_profit, используем текущую цену')
        correct_exit_price = exit_price
    
    print(f'  ✅ Правильная цена выхода: ${correct_exit_price:,.2f}')
    
    # Пересчитываем PnL
    if side == 'SELL':
        pnl_gross = (entry_price - correct_exit_price) * size
        pnl_percent = ((entry_price - correct_exit_price) / entry_price) * 100
    else:  # BUY
        pnl_gross = (correct_exit_price - entry_price) * size
        pnl_percent = ((correct_exit_price - entry_price) / entry_price) * 100
    
    # Получаем комиссии
    entry_fee = trade.get('entry_fee', 0.0) or 0.0
    exit_fee = trade.get('exit_fee', 0.0) or 0.0
    total_fees = entry_fee + exit_fee
    pnl_net = pnl_gross - total_fees
    pnl_percent_net = (pnl_net / (entry_price * size)) * 100 if (entry_price * size) > 0 else 0
    
    print(f'  📊 Правильный PnL:')
    print(f'     PnL (gross): ${pnl_gross:,.2f}')
    print(f'     Комиссии: ${total_fees:,.2f}')
    print(f'     PnL (net): ${pnl_net:,.2f}')
    print(f'     PnL %: {pnl_percent_net:.2f}%')
    
    # Обновляем сделку
    if db.db_type == 'postgresql':
        update_query = """
        UPDATE virtual_positions 
        SET exit_price = %s, realized_pnl = %s, pnl_percent = %s
        WHERE id = %s
        """
        db._execute_query(update_query, (correct_exit_price, pnl_net, pnl_percent_net, trade_id))
    else:
        update_query = """
        UPDATE virtual_positions 
        SET exit_price = ?, realized_pnl = ?, pnl_percent = ?
        WHERE id = ?
        """
        db._execute_query(update_query, (correct_exit_price, pnl_net, pnl_percent_net, trade_id))
    
    print(f'  ✅ Сделка ID {trade_id} исправлена!')

if __name__ == '__main__':
    find_and_fix_incorrect_trades()

