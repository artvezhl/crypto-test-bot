#!/usr/bin/env python3
"""
Скрипт для исправления сделки ID 1047 с некорректной ценой выхода
"""
import sys
sys.path.insert(0, '/app/src')
from database import Database

def fix_trade_1047():
    db = Database()
    
    # Получаем сделку
    query = 'SELECT * FROM virtual_positions WHERE id = 1047'
    result = db._execute_query(query)
    if not result:
        print('❌ Сделка с ID 1047 не найдена')
        return
    
    trade = db._convert_row(result[0]) if hasattr(db, '_convert_row') else result[0]
    
    entry_price = trade.get('entry_price', 0)
    exit_price = trade.get('exit_price', 0)
    stop_loss = trade.get('stop_loss', 0)
    side = trade.get('side', '')
    size = trade.get('size', 0)
    
    print(f'📊 Сделка ID 1047:')
    print(f'  Символ: {trade.get("symbol", "N/A")}')
    print(f'  Направление: {side}')
    print(f'  Цена входа: ${entry_price:,.2f}')
    print(f'  Цена выхода (текущая): ${exit_price:,.2f}')
    print(f'  Stop Loss: ${stop_loss:,.2f}')
    print()
    
    # Для SELL позиции при stop_loss цена выхода должна быть немного выше stop_loss
    # из-за slippage при покупке (закрытие SELL = покупка)
    # Предполагаем slippage 0.1%
    correct_exit_price = stop_loss * 1.001
    
    print(f'✅ Правильная цена выхода (stop_loss + 0.1% slippage): ${correct_exit_price:,.2f}')
    print(f'   Текущая цена: ${exit_price:,.2f}')
    print(f'   Разница: ${exit_price - correct_exit_price:,.2f}')
    print()
    
    # Пересчитываем PnL
    if side == 'SELL':
        pnl_gross = (entry_price - correct_exit_price) * size
        pnl_percent = ((entry_price - correct_exit_price) / entry_price) * 100
    else:
        pnl_gross = (correct_exit_price - entry_price) * size
        pnl_percent = ((correct_exit_price - entry_price) / entry_price) * 100
    
    # Получаем комиссии
    entry_fee = trade.get('entry_fee', 0.0) or 0.0
    exit_fee = trade.get('exit_fee', 0.0) or 0.0
    total_fees = entry_fee + exit_fee
    pnl_net = pnl_gross - total_fees
    pnl_percent_net = (pnl_net / (entry_price * size)) * 100 if (entry_price * size) > 0 else 0
    
    print(f'📊 Правильный PnL:')
    print(f'   PnL (gross): ${pnl_gross:,.2f}')
    print(f'   Комиссии: ${total_fees:,.2f}')
    print(f'   PnL (net): ${pnl_net:,.2f}')
    print(f'   PnL %: {pnl_percent_net:.2f}%')
    print()
    
    # Обновляем сделку
    print('🔧 Обновление сделки...')
    if db.db_type == 'postgresql':
        update_query = """
        UPDATE virtual_positions 
        SET exit_price = %s, realized_pnl = %s, pnl_percent = %s
        WHERE id = 1047
        """
        db._execute_query(update_query, (correct_exit_price, pnl_net, pnl_percent_net))
    else:
        update_query = """
        UPDATE virtual_positions 
        SET exit_price = ?, realized_pnl = ?, pnl_percent = ?
        WHERE id = 1047
        """
        db._execute_query(update_query, (correct_exit_price, pnl_net, pnl_percent_net))
    
    print('✅ Сделка исправлена!')
    
    # Проверяем результат
    result = db._execute_query(query)
    if result:
        updated_trade = db._convert_row(result[0]) if hasattr(db, '_convert_row') else result[0]
        print()
        print('📊 Обновленная сделка:')
        print(f'  Цена выхода: ${updated_trade.get("exit_price", 0):,.2f}')
        print(f'  PnL: ${updated_trade.get("realized_pnl", 0):,.2f}')
        print(f'  PnL %: {updated_trade.get("pnl_percent", 0):.2f}%')

if __name__ == '__main__':
    fix_trade_1047()

