#!/usr/bin/env python3
"""
Web UI для системы бэктестинга.

Предоставляет веб-интерфейс для:
- Запуска бэктестов
- Визуализации результатов
- Анализа метрик
"""

from flask import Flask, render_template, request, jsonify, Response
from datetime import datetime, timedelta
import sys
import os
import logging
import json
from queue import Queue
import threading

# Добавляем родительскую директорию в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtester import BacktestEngine
from database import Database

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создание Flask приложения
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # В production использовать переменную окружения

# Глобальные переменные для хранения последних результатов
last_backtest_results = None
last_backtest_engine = None
progress_queue = Queue()
backtest_running = False


@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')


@app.route('/api/progress')
def progress():
    """
    SSE endpoint для отправки прогресса бэктеста в реальном времени.
    """
    def generate():
        while True:
            # Получаем сообщение из очереди (блокируется до получения)
            message = progress_queue.get()
            
            # Если получили None, значит бэктест завершен
            if message is None:
                yield f"data: {json.dumps({'status': 'done'})}\n\n"
                break
                
            # Отправляем прогресс клиенту
            yield f"data: {json.dumps(message)}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')


def run_backtest_async(symbols, interval, days, initial_balance, strategy, use_fees, use_slippage):
    """
    Запуск бэктеста в отдельном потоке с отправкой прогресса.
    """
    global last_backtest_results, last_backtest_engine, backtest_running
    
    try:
        backtest_running = True
        
        # Создаем движок бэктестинга с выбранной стратегией
        config = {'strategy': strategy}
        engine = BacktestEngine(config=config)
        engine.use_fees_in_backtest = use_fees
        engine.use_slippage_in_backtest = use_slippage
        
        # Определяем период
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Отправляем начальный статус
        progress_queue.put({
            'status': 'running',
            'progress': 0,
            'message': 'Загрузка данных...'
        })
        
        # Запускаем бэктест
        results = engine.run_backtest(
            symbols=symbols,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
            initial_balance=initial_balance,
            progress_callback=lambda p, msg: progress_queue.put({
                'status': 'running',
                'progress': p,
                'message': msg
            })
        )
        
        if results:
            # Добавляем дополнительную информацию
            results['start_date'] = start_date.strftime('%Y-%m-%d %H:%M')
            results['end_date'] = end_date.strftime('%Y-%m-%d %H:%M')
            results['symbols'] = symbols
            results['interval'] = interval
            
            # Сохраняем результаты глобально
            last_backtest_results = results
            last_backtest_engine = engine
            
            # Отправляем финальный статус
            progress_queue.put({
                'status': 'completed',
                'progress': 100,
                'message': 'Бэктест завершен!',
                'results': results
            })
        else:
            progress_queue.put({
                'status': 'error',
                'message': 'Бэктест не вернул результатов'
            })
            
    except Exception as e:
        logger.error(f"Ошибка выполнения бэктеста: {e}")
        import traceback
        traceback.print_exc()
        progress_queue.put({
            'status': 'error',
            'message': str(e)
        })
    finally:
        # Сигнализируем о завершении
        progress_queue.put(None)
        backtest_running = False


@app.route('/api/run_backtest', methods=['POST'])
def run_backtest():
    """
    API endpoint для запуска бэктеста.
    
    Ожидает JSON с параметрами:
    - symbols: список символов
    - interval: таймфрейм
    - days: количество дней для тестирования
    - initial_balance: начальный баланс
    """
    global backtest_running
    
    try:
        # Проверяем, не запущен ли уже бэктест
        if backtest_running:
            return jsonify({'error': 'Бэктест уже выполняется'}), 400
        
        data = request.get_json()
        
        # Парсим параметры
        symbols_input = data.get('symbols', 'BTCUSDT,ETHUSDT')
        if isinstance(symbols_input, str):
            # Разделяем по запятым, переносам строк и пробелам
            symbols = [s.strip() for s in symbols_input.replace('\n', ',').replace(' ', ',').split(',') if s.strip()]
        else:
            symbols = symbols_input
        
        interval = data.get('interval', '15')
        days = int(data.get('days', 7))
        initial_balance = float(data.get('initial_balance', 10000))
        
        # Стратегия бэктестинга
        strategy = data.get('strategy', 'simple')
        
        # Настройки комиссий и slippage
        use_fees = data.get('use_fees', True)
        use_slippage = data.get('use_slippage', True)
        
        logger.info(f"Запуск бэктеста: symbols={symbols}, interval={interval}, days={days}, strategy={strategy}")
        
        # Очищаем очередь прогресса
        while not progress_queue.empty():
            progress_queue.get()
        
        # Запускаем бэктест в отдельном потоке
        thread = threading.Thread(
            target=run_backtest_async,
            args=(symbols, interval, days, initial_balance, strategy, use_fees, use_slippage)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Бэктест запущен'
        })
        
    except Exception as e:
        logger.error(f"Ошибка запуска бэктеста: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/chart_data/balance')
def get_balance_chart_data():
    """Получить данные для графика баланса"""
    global last_backtest_engine
    
    if not last_backtest_engine or not last_backtest_engine.balance_history:
        return jsonify({'error': 'Нет данных бэктеста'}), 404
    
    try:
        # Формируем данные для графика
        timestamps = []
        balances = []
        
        for entry in last_backtest_engine.balance_history:
            timestamps.append(entry['datetime'].strftime('%Y-%m-%d %H:%M'))
            balances.append(entry['balance'])
        
        return jsonify({
            'timestamps': timestamps,
            'balances': balances,
            'initial_balance': last_backtest_engine.initial_balance
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения данных графика: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chart_data/drawdown')
def get_drawdown_chart_data():
    """Получить данные для графика просадки"""
    global last_backtest_engine
    
    if not last_backtest_engine or not last_backtest_engine.balance_history:
        return jsonify({'error': 'Нет данных бэктеста'}), 404
    
    try:
        timestamps = []
        drawdowns = []
        peak = last_backtest_engine.initial_balance
        
        for entry in last_backtest_engine.balance_history:
            balance = entry['balance']
            
            # Обновляем пик
            if balance > peak:
                peak = balance
            
            # Рассчитываем текущую просадку
            if peak > 0:
                drawdown = ((peak - balance) / peak) * 100
            else:
                drawdown = 0
            
            timestamps.append(entry['datetime'].strftime('%Y-%m-%d %H:%M'))
            drawdowns.append(drawdown)
        
        return jsonify({
            'timestamps': timestamps,
            'drawdowns': drawdowns
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения данных просадки: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chart_data/pnl_distribution')
def get_pnl_distribution():
    """Получить данные распределения PnL по сделкам"""
    global last_backtest_engine
    
    if not last_backtest_engine:
        return jsonify({'error': 'Нет данных бэктеста'}), 404
    
    try:
        db = last_backtest_engine.db
        
        # Получаем все закрытые позиции
        if db.db_type == 'postgresql':
            query = """
            SELECT realized_pnl, pnl_percent, symbol, side, created_at, closed_at
            FROM virtual_positions
            WHERE status = 'closed'
            ORDER BY closed_at
            """
        else:
            query = """
            SELECT realized_pnl, pnl_percent, symbol, side, created_at, closed_at
            FROM virtual_positions
            WHERE status = 'closed'
            ORDER BY closed_at
            """
        
        positions = db._execute_query(query)
        
        if not positions:
            return jsonify({'error': 'Нет закрытых позиций'}), 404
        
        # Формируем данные
        trade_numbers = []
        pnls = []
        symbols = []
        sides = []
        
        for i, pos in enumerate(positions, 1):
            trade_numbers.append(i)
            pnls.append(float(pos.get('realized_pnl', 0)))
            symbols.append(pos.get('symbol', 'N/A'))
            sides.append(pos.get('side', 'N/A'))
        
        return jsonify({
            'trade_numbers': trade_numbers,
            'pnls': pnls,
            'symbols': symbols,
            'sides': sides
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения распределения PnL: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings')
def get_settings():
    """Получить текущие настройки из БД"""
    try:
        db = Database()
        
        settings = {
            'symbols': db.get_setting('trading_symbols', 'BTCUSDT,ETHUSDT'),
            'min_confidence': db.get_setting('min_confidence', '0.68'),
            'leverage': db.get_setting('leverage', '5'),
            'risk_percent': db.get_setting('risk_percent', '2.0'),
            'stop_loss_percent': db.get_setting('stop_loss_percent', '2.0'),
            'take_profit_percent': db.get_setting('take_profit_percent', '4.0'),
            'maker_fee_percent': db.get_setting('maker_fee_percent', '0.055'),
            'taker_fee_percent': db.get_setting('taker_fee_percent', '0.06'),
            'slippage_percent': db.get_setting('slippage_percent', '0.05'),
        }
        
        return jsonify(settings)
        
    except Exception as e:
        logger.error(f"Ошибка получения настроек: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 80)
    print("🌐 ЗАПУСК WEB UI ДЛЯ БЭКТЕСТИНГА")
    print("=" * 80)
    print()
    print("📊 Веб-интерфейс доступен по адресу: http://localhost:5000")
    print()
    print("Возможности:")
    print("  ✅ Запуск бэктестов через веб-интерфейс")
    print("  ✅ Интерактивные графики результатов")
    print("  ✅ Детальная статистика метрик")
    print()
    print("Для остановки нажмите Ctrl+C")
    print("=" * 80)
    print()
    
    # Запускаем сервер
    app.run(debug=True, host='0.0.0.0', port=5000)


