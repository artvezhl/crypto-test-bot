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


@app.route('/api/backtest_status')
def backtest_status():
    """Проверка статуса бэктеста"""
    global backtest_running
    return jsonify({'running': backtest_running})


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
            # Явно сохраняем символы и период в движок для фильтрации
            engine.symbols = symbols
            engine.backtest_start_date = start_date
            engine.backtest_end_date = end_date
            logger.info(f"💾 Сохранены параметры бэктеста: символы={symbols}, период={start_date} - {end_date}")
            
            # Пересчитываем метрики только для выбранных символов и периода
            # Используем balance_history из engine, если он есть
            balance_history_for_metrics = getattr(engine, 'balance_history', [])
            logger.info(f"📊 Используем balance_history: {len(balance_history_for_metrics)} записей для расчета метрик")
            
            filtered_metrics = recalculate_metrics_for_symbols(
                engine.db, symbols, initial_balance, balance_history_for_metrics, start_date, end_date
            )
            
            # Если есть отфильтрованные метрики, обновляем results
            if filtered_metrics:
                logger.info(f"📊 Пересчитаны метрики для символов {symbols}: {filtered_metrics.get('total_trades', 0)} сделок, PnL: ${filtered_metrics.get('total_pnl', 0):.2f}, Max DD: {filtered_metrics.get('max_drawdown', 0):.2f}%")
                results.update(filtered_metrics)
            else:
                logger.warning(f"⚠️ Не удалось пересчитать метрики для символов {symbols}")
            
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
    
    try:
        # Если нет данных бэктеста, используем последние сделки из БД
        if not last_backtest_engine:
            db = Database()
            if db.db_type == 'postgresql':
                query = """
                SELECT realized_pnl, pnl_percent, symbol, side, created_at, closed_at
                FROM virtual_positions
                WHERE status = 'closed'
                    ORDER BY closed_at DESC
                    LIMIT 100
                """
            else:
                query = """
                SELECT realized_pnl, pnl_percent, symbol, side, created_at, closed_at
                FROM virtual_positions
                WHERE status = 'closed'
                    ORDER BY closed_at DESC
                    LIMIT 100
                """
            positions = db._execute_query(query)
            if positions:
                positions = [db._convert_row(row) for row in positions]
            else:
                positions = []
            
            # Формируем данные для графика
            pnls = [float(p.get('realized_pnl', 0)) for p in positions]
            return jsonify({'pnls': pnls})
        else:
            db = last_backtest_engine.db
            
            # Получаем параметры последнего бэктеста для фильтрации
            backtest_symbols = getattr(last_backtest_engine, 'symbols', [])
            # Не фильтруем по времени, так как старые сделки уже очищены
            backtest_start_date = None
            backtest_end_date = None
            
            # Получаем последние 100 закрытых позиций с фильтрацией по символам и времени
            if db.db_type == 'postgresql':
                if backtest_symbols:
                    if len(backtest_symbols) == 1:
                        if backtest_start_date and backtest_end_date:
                            query = """
                            SELECT realized_pnl, pnl_percent, symbol, side, created_at, closed_at
                            FROM virtual_positions
                            WHERE status = 'closed' 
                              AND symbol = %s
                              AND created_at >= %s
                              AND closed_at <= %s
                            ORDER BY closed_at DESC
                            LIMIT 100
                            """
                            positions = db._execute_query(query, (backtest_symbols[0], backtest_start_date, backtest_end_date))
                        else:
                            query = """
                            SELECT realized_pnl, pnl_percent, symbol, side, created_at, closed_at
                            FROM virtual_positions
                            WHERE status = 'closed' AND symbol = %s
                            ORDER BY closed_at DESC
                            LIMIT 100
                            """
                            positions = db._execute_query(query, (backtest_symbols[0],))
                    else:
                        symbols_placeholders = ','.join(['%s'] * len(backtest_symbols))
                        if backtest_start_date and backtest_end_date:
                            query = f"""
                            SELECT realized_pnl, pnl_percent, symbol, side, created_at, closed_at
                            FROM virtual_positions
                            WHERE status = 'closed' 
                              AND symbol IN ({symbols_placeholders})
                              AND created_at >= %s
                              AND closed_at <= %s
                            ORDER BY closed_at DESC
                            LIMIT 100
                            """
                            positions = db._execute_query(query, tuple(backtest_symbols) + (backtest_start_date, backtest_end_date))
                        else:
                            query = f"""
                            SELECT realized_pnl, pnl_percent, symbol, side, created_at, closed_at
                            FROM virtual_positions
                            WHERE status = 'closed' AND symbol IN ({symbols_placeholders})
                            ORDER BY closed_at DESC
                            LIMIT 100
                            """
                            positions = db._execute_query(query, tuple(backtest_symbols))
                else:
                    query = """
                    SELECT realized_pnl, pnl_percent, symbol, side, created_at, closed_at
                    FROM virtual_positions
                    WHERE status = 'closed'
                    ORDER BY closed_at DESC
                    LIMIT 100
                    """
                    positions = db._execute_query(query)
            else:
                if backtest_symbols:
                    if len(backtest_symbols) == 1:
                        if backtest_start_date and backtest_end_date:
                            query = """
                            SELECT realized_pnl, pnl_percent, symbol, side, created_at, closed_at
                            FROM virtual_positions
                            WHERE status = 'closed' 
                              AND symbol = ?
                              AND created_at >= ?
                              AND closed_at <= ?
                            ORDER BY closed_at DESC
                            LIMIT 100
                            """
                            positions = db._execute_query(query, (backtest_symbols[0], backtest_start_date, backtest_end_date))
                        else:
                            query = """
                            SELECT realized_pnl, pnl_percent, symbol, side, created_at, closed_at
                            FROM virtual_positions
                            WHERE status = 'closed' AND symbol = ?
                            ORDER BY closed_at DESC
                            LIMIT 100
                            """
                            positions = db._execute_query(query, (backtest_symbols[0],))
                    else:
                        symbols_placeholders = ','.join(['?'] * len(backtest_symbols))
                        if backtest_start_date and backtest_end_date:
                            query = f"""
                            SELECT realized_pnl, pnl_percent, symbol, side, created_at, closed_at
                            FROM virtual_positions
                            WHERE status = 'closed' 
                              AND symbol IN ({symbols_placeholders})
                              AND created_at >= ?
                              AND closed_at <= ?
                            ORDER BY closed_at DESC
                            LIMIT 100
                            """
                            positions = db._execute_query(query, tuple(backtest_symbols) + (backtest_start_date, backtest_end_date))
                        else:
                            query = f"""
                            SELECT realized_pnl, pnl_percent, symbol, side, created_at, closed_at
                            FROM virtual_positions
                            WHERE status = 'closed' AND symbol IN ({symbols_placeholders})
                            ORDER BY closed_at DESC
                            LIMIT 100
                            """
                            positions = db._execute_query(query, tuple(backtest_symbols))
                else:
                    query = """
                    SELECT realized_pnl, pnl_percent, symbol, side, created_at, closed_at
                    FROM virtual_positions
                    WHERE status = 'closed'
                    ORDER BY closed_at DESC
                    LIMIT 100
                    """
                    positions = db._execute_query(query)
        
        if not positions:
            logger.warning("⚠️ Нет позиций для графика PnL")
            return jsonify({
                'trade_numbers': [],
                'pnls': [],
                'symbols': [],
                'sides': []
            })
        
        logger.info(f"📊 Получено {len(positions)} позиций для графика PnL")
        
        # Переворачиваем чтобы показать в хронологическом порядке
        positions = list(reversed(positions))
        
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


def format_duration(delta):
    """Форматирует timedelta в читаемый формат"""
    if not delta:
        return 'N/A'
    
    total_seconds = delta.total_seconds()
    
    # Меньше секунды - показываем миллисекунды
    if total_seconds < 1:
        milliseconds = int(total_seconds * 1000)
        return f"{milliseconds} мс"
    
    # Меньше минуты - показываем секунды
    if total_seconds < 60:
        seconds = int(total_seconds)
        return f"{seconds} сек"
    
    # Меньше часа - показываем минуты и секунды
    if total_seconds < 3600:
        minutes = int(total_seconds // 60)
        seconds = int(total_seconds % 60)
        if seconds > 0:
            return f"{minutes} мин {seconds} сек"
        return f"{minutes} мин"
    
    # Меньше дня - показываем часы и минуты
    if total_seconds < 86400:
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        if minutes > 0:
            return f"{hours} ч {minutes} мин"
        return f"{hours} ч"
    
    # Больше дня - показываем дни, часы и минуты
    days = int(total_seconds // 86400)
    hours = int((total_seconds % 86400) // 3600)
    minutes = int((total_seconds % 3600) // 60)
    
    parts = [f"{days} дн"]
    if hours > 0:
        parts.append(f"{hours} ч")
    if minutes > 0 and days < 7:  # Показываем минуты только если меньше недели
        parts.append(f"{minutes} мин")
    
    return " ".join(parts)


def translate_close_reason(reason):
    """Переводит причину закрытия на русский язык"""
    translations = {
        'stop_loss': 'Стоп-лосс',
        'take_profit': 'Тейк-профит',
        'manual': 'Ручное',
        'test': 'Тест',
        'signal': 'Сигнал',
        'timeout': 'Таймаут',
        'N/A': 'N/A'
    }
    return translations.get(reason, reason.capitalize() if reason else 'N/A')


def recalculate_metrics_for_symbols(db, symbols, initial_balance, balance_history, start_date=None, end_date=None):
    """Пересчитывает метрики только для указанных символов и периода"""
    if not symbols:
        return None
    
    try:
        # Получаем сделки только для указанных символов и периода
        if db.db_type == 'postgresql':
            if len(symbols) == 1:
                if start_date and end_date:
                    query = """
                    SELECT realized_pnl, pnl_percent, created_at, closed_at, entry_price, exit_price
                    FROM virtual_positions
                    WHERE status = 'closed' 
                      AND symbol = %s
                      AND created_at >= %s
                      AND closed_at <= %s
                    ORDER BY closed_at
                    """
                    trades = db._execute_query(query, (symbols[0], start_date, end_date))
                else:
                    query = """
                    SELECT realized_pnl, pnl_percent, created_at, closed_at, entry_price, exit_price
                    FROM virtual_positions
                    WHERE status = 'closed' AND symbol = %s
                    ORDER BY closed_at
                    """
                    trades = db._execute_query(query, (symbols[0],))
            else:
                symbols_placeholders = ','.join(['%s'] * len(symbols))
                if start_date and end_date:
                    query = f"""
                    SELECT realized_pnl, pnl_percent, created_at, closed_at, entry_price, exit_price
                    FROM virtual_positions
                    WHERE status = 'closed' 
                      AND symbol IN ({symbols_placeholders})
                      AND created_at >= %s
                      AND closed_at <= %s
                    ORDER BY closed_at
                    """
                    trades = db._execute_query(query, tuple(symbols) + (start_date, end_date))
                else:
                    query = f"""
                    SELECT realized_pnl, pnl_percent, created_at, closed_at, entry_price, exit_price
                    FROM virtual_positions
                    WHERE status = 'closed' AND symbol IN ({symbols_placeholders})
                    ORDER BY closed_at
                    """
                    trades = db._execute_query(query, tuple(symbols))
        else:
            if len(symbols) == 1:
                if start_date and end_date:
                    query = """
                    SELECT realized_pnl, pnl_percent, created_at, closed_at, entry_price, exit_price
                    FROM virtual_positions
                    WHERE status = 'closed' 
                      AND symbol = ?
                      AND created_at >= ?
                      AND closed_at <= ?
                    ORDER BY closed_at
                    """
                    trades = db._execute_query(query, (symbols[0], start_date, end_date))
                else:
                    query = """
                    SELECT realized_pnl, pnl_percent, created_at, closed_at, entry_price, exit_price
                    FROM virtual_positions
                    WHERE status = 'closed' AND symbol = ?
                    ORDER BY closed_at
                    """
                    trades = db._execute_query(query, (symbols[0],))
            else:
                symbols_placeholders = ','.join(['?'] * len(symbols))
                if start_date and end_date:
                    query = f"""
                    SELECT realized_pnl, pnl_percent, created_at, closed_at, entry_price, exit_price
                    FROM virtual_positions
                    WHERE status = 'closed' 
                      AND symbol IN ({symbols_placeholders})
                      AND created_at >= ?
                      AND closed_at <= ?
                    ORDER BY closed_at
                    """
                    trades = db._execute_query(query, tuple(symbols) + (start_date, end_date))
                else:
                    query = f"""
                    SELECT realized_pnl, pnl_percent, created_at, closed_at, entry_price, exit_price
                    FROM virtual_positions
                    WHERE status = 'closed' AND symbol IN ({symbols_placeholders})
                    ORDER BY closed_at
                    """
                    trades = db._execute_query(query, tuple(symbols))
        
        if not trades:
            return None
        
        # Пересчитываем метрики
        total_pnl = sum(float(t.get('realized_pnl', 0) or 0) for t in trades)
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if float(t.get('realized_pnl', 0) or 0) > 0)
        losing_trades = sum(1 for t in trades if float(t.get('realized_pnl', 0) or 0) < 0)
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        roi = (total_pnl / initial_balance * 100) if initial_balance > 0 else 0
        
        # Рассчитываем max drawdown из balance_history
        max_drawdown = 0
        logger.info(f"🔍 Расчет Max Drawdown: balance_history={balance_history is not None}, len={len(balance_history) if balance_history else 0}, initial_balance={initial_balance}")
        
        if balance_history and len(balance_history) > 0:
            try:
                # Извлекаем балансы из истории
                balances = []
                for e in balance_history:
                    if isinstance(e, dict):
                        balance = float(e.get('balance', initial_balance))
                    else:
                        balance = float(initial_balance)
                    balances.append(balance)
                
                logger.info(f"🔍 Извлечено {len(balances)} балансов: min=${min(balances):.2f}, max=${max(balances):.2f}, первый=${balances[0]:.2f}, последний=${balances[-1]:.2f}")
                
                if len(balances) > 0:
                    peak = float(initial_balance)
                    min_balance = float(initial_balance)
                    for balance in balances:
                        if balance > peak:
                            peak = balance
                        if balance < min_balance:
                            min_balance = balance
                        if peak > 0:
                            drawdown = ((peak - balance) / peak) * 100
                            if drawdown > max_drawdown:
                                max_drawdown = drawdown
                    
                    # Если все балансы одинаковые, max_drawdown будет 0
                    if max(balances) == min(balances):
                        logger.warning(f"⚠️ Все балансы одинаковые: ${max(balances):.2f}, Max Drawdown = 0%")
                    else:
                        logger.info(f"📉 Max Drawdown рассчитан: {max_drawdown:.2f}% (пик: ${peak:.2f}, минимум: ${min_balance:.2f}, начальный: ${initial_balance:.2f})")
            except Exception as e:
                logger.warning(f"Ошибка расчета max_drawdown: {e}")
                import traceback
                traceback.print_exc()
                max_drawdown = 0
        else:
            logger.warning(f"⚠️ balance_history пуст или отсутствует: {balance_history}")
        
        # Простые метрики (без продвинутых расчетов)
        return {
            'total_pnl': total_pnl,
            'roi_percent': roi,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': 0.0,  # Упрощенная версия
            'sortino_ratio': 0.0,
            'calmar_ratio': 0.0,
            'profit_factor': 0.0,
            'expectancy': 0.0,
            'avg_trade_duration_hours': 0.0
        }
    except Exception as e:
        logger.error(f"Ошибка пересчета метрик: {e}")
        return None


@app.route('/api/trades')
def get_trades():
    """Получить список закрытых сделок"""
    global last_backtest_engine
    
    try:
        # Всегда используем последние сделки из БД
        # Если есть last_backtest_engine, фильтруем по символам, иначе показываем все
        closed_positions = []
        
        if not last_backtest_engine:
            db = Database()
            closed_positions = db.get_virtual_closed_positions(limit=200)
            logger.info(f"📊 Получено {len(closed_positions)} сделок из БД (без фильтрации, last_backtest_engine отсутствует)")
        else:
            db = last_backtest_engine.db
            
            # Получаем параметры последнего бэктеста для фильтрации
            backtest_symbols = getattr(last_backtest_engine, 'symbols', [])
            logger.info(f"📊 Фильтрация сделок по символам: {backtest_symbols}")
            
            # Получаем закрытые позиции с фильтрацией только по символам
            # (время не фильтруем, так как старые сделки уже очищены перед новым бэктестом)
            if backtest_symbols:
                if db.db_type == 'postgresql':
                    if len(backtest_symbols) == 1:
                        query = """
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' AND symbol = %s
                        ORDER BY closed_at DESC
                        LIMIT 200
                        """
                        closed_positions_raw = db._execute_query(query, (backtest_symbols[0],))
                    else:
                        symbols_placeholders = ','.join(['%s'] * len(backtest_symbols))
                        query = f"""
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' AND symbol IN ({symbols_placeholders})
                        ORDER BY closed_at DESC
                        LIMIT 200
                        """
                        closed_positions_raw = db._execute_query(query, tuple(backtest_symbols))
                else:
                    # SQLite
                    if len(backtest_symbols) == 1:
                        query = """
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' AND symbol = ?
                        ORDER BY closed_at DESC
                        LIMIT 200
                        """
                        closed_positions_raw = db._execute_query(query, (backtest_symbols[0],))
                    else:
                        symbols_placeholders = ','.join(['?'] * len(backtest_symbols))
                        query = f"""
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' AND symbol IN ({symbols_placeholders})
                        ORDER BY closed_at DESC
                        LIMIT 200
                        """
                        closed_positions_raw = db._execute_query(query, tuple(backtest_symbols))
                
                # Конвертируем в словари (для обоих типов БД)
                closed_positions = [db._convert_row(row) for row in closed_positions_raw] if closed_positions_raw else []
                logger.info(f"📊 Получено {len(closed_positions)} сделок с фильтрацией по символам")
            else:
                # Если нет символов, получаем все сделки (fallback)
                closed_positions = db.get_virtual_closed_positions(limit=200)
                logger.info(f"📊 Получено {len(closed_positions)} сделок без фильтрации (backtest_symbols пустой)")
        
        # Финальная проверка: если все еще пусто, пробуем получить все сделки напрямую
        if not closed_positions:
            logger.warning("⚠️ Сделки не найдены через фильтрацию, пробуем получить все сделки напрямую из БД")
            try:
                db_fallback = Database()
                closed_positions = db_fallback.get_virtual_closed_positions(limit=200)
                logger.info(f"📊 Fallback: получено {len(closed_positions)} сделок из БД")
            except Exception as e:
                logger.error(f"❌ Ошибка при fallback получении сделок: {e}")
                closed_positions = []
        
        if not closed_positions:
            logger.warning("⚠️ Нет закрытых позиций в БД после всех попыток")
            return jsonify({
                'trades': [], 
                'tradesCount': 0,
                'summary': {'total': 0, 'winning': 0, 'losing': 0, 'win_rate': 0}
            })
        
        # Форматируем данные для фронтенда
        trades = []
        winning_count = 0
        losing_count = 0
        
        for pos in closed_positions:
            # Вычисляем длительность
            duration_str = 'N/A'
            if pos['closed_at'] and pos['created_at']:
                duration_delta = pos['closed_at'] - pos['created_at']
                duration_str = format_duration(duration_delta)
            
            trade = {
                'id': pos['id'],
                'symbol': pos['symbol'],
                'side': pos['side'],
                'size': float(pos['size']),
                'entry_price': float(pos['entry_price']),
                'exit_price': float(pos['exit_price']) if pos['exit_price'] else 0,
                'realized_pnl': float(pos['realized_pnl']) if pos['realized_pnl'] else 0,
                'pnl_percent': float(pos['pnl_percent']) if pos['pnl_percent'] else 0,
                'leverage': pos.get('leverage', 1),
                'entry_fee': float(pos.get('entry_fee', 0) or 0),
                'exit_fee': float(pos.get('exit_fee', 0) or 0),
                'total_fees': float(pos.get('total_fees', 0) or 0),
                'close_reason': translate_close_reason(pos.get('close_reason', 'N/A')),
                'close_reason_raw': pos.get('close_reason', 'N/A'),  # Оригинальное значение для экспорта
                'created_at': pos['created_at'].strftime('%Y-%m-%d %H:%M:%S') if pos['created_at'] else 'N/A',
                'created_at_date': pos['created_at'].strftime('%Y-%m-%d') if pos['created_at'] else 'N/A',  # Дата
                'created_at_short': pos['created_at'].strftime('%H:%M:%S') if pos['created_at'] else 'N/A',  # Только время
                'closed_at': pos['closed_at'].strftime('%Y-%m-%d %H:%M:%S') if pos['closed_at'] else 'N/A',
                'closed_at_date': pos['closed_at'].strftime('%Y-%m-%d') if pos['closed_at'] else 'N/A',  # Дата
                'closed_at_short': pos['closed_at'].strftime('%H:%M:%S') if pos['closed_at'] else 'N/A',  # Только время
                'duration': duration_str
            }
            trades.append(trade)
            
            if trade['realized_pnl'] > 0:
                winning_count += 1
            elif trade['realized_pnl'] < 0:
                losing_count += 1
        
        summary = {
            'total': len(trades),
            'winning': winning_count,
            'losing': losing_count,
            'win_rate': (winning_count / len(trades) * 100) if len(trades) > 0 else 0
        }
        
        logger.info(f"✅ Возвращаем {len(trades)} сделок в API ответе")
        
        return jsonify({
            'trades': trades,
            'tradesCount': len(trades),  # Добавляем для совместимости с фронтендом
            'summary': summary
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения сделок: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/export/trades/csv')
def export_trades_csv():
    """Экспорт сделок в CSV"""
    global last_backtest_engine
    
    if not last_backtest_engine:
        return jsonify({'error': 'Нет данных бэктеста'}), 404
    
    try:
        import csv
        import io
        from flask import make_response
        
        db = last_backtest_engine.db
        
        # Получаем параметры последнего бэктеста для фильтрации
        backtest_symbols = getattr(last_backtest_engine, 'symbols', [])
        backtest_start_date = getattr(last_backtest_engine, 'backtest_start_date', None)
        backtest_end_date = getattr(last_backtest_engine, 'backtest_end_date', None)
        
        # Получаем сделки с фильтрацией по символам и времени
        if backtest_symbols:
            if db.db_type == 'postgresql':
                if len(backtest_symbols) == 1:
                    if backtest_start_date and backtest_end_date:
                        query = """
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' 
                          AND symbol = %s
                          AND created_at >= %s
                          AND closed_at <= %s
                        ORDER BY closed_at DESC
                        LIMIT 1000
                        """
                        closed_positions_raw = db._execute_query(query, (backtest_symbols[0], backtest_start_date, backtest_end_date))
                    else:
                        query = """
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' AND symbol = %s
                        ORDER BY closed_at DESC
                        LIMIT 1000
                        """
                        closed_positions_raw = db._execute_query(query, (backtest_symbols[0],))
                else:
                    symbols_placeholders = ','.join(['%s'] * len(backtest_symbols))
                    if backtest_start_date and backtest_end_date:
                        query = f"""
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' 
                          AND symbol IN ({symbols_placeholders})
                          AND created_at >= %s
                          AND closed_at <= %s
                        ORDER BY closed_at DESC
                        LIMIT 1000
                        """
                        closed_positions_raw = db._execute_query(query, tuple(backtest_symbols) + (backtest_start_date, backtest_end_date))
                    else:
                        query = f"""
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' AND symbol IN ({symbols_placeholders})
                        ORDER BY closed_at DESC
                        LIMIT 1000
                        """
                        closed_positions_raw = db._execute_query(query, tuple(backtest_symbols))
            else:
                # SQLite
                if len(backtest_symbols) == 1:
                    if backtest_start_date and backtest_end_date:
                        query = """
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' 
                          AND symbol = ?
                          AND created_at >= ?
                          AND closed_at <= ?
                        ORDER BY closed_at DESC
                        LIMIT 1000
                        """
                        closed_positions_raw = db._execute_query(query, (backtest_symbols[0], backtest_start_date, backtest_end_date))
                    else:
                        query = """
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' AND symbol = ?
                        ORDER BY closed_at DESC
                        LIMIT 1000
                        """
                        closed_positions_raw = db._execute_query(query, (backtest_symbols[0],))
                else:
                    symbols_placeholders = ','.join(['?'] * len(backtest_symbols))
                    if backtest_start_date and backtest_end_date:
                        query = f"""
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' 
                          AND symbol IN ({symbols_placeholders})
                          AND created_at >= ?
                          AND closed_at <= ?
                        ORDER BY closed_at DESC
                        LIMIT 1000
                        """
                        closed_positions_raw = db._execute_query(query, tuple(backtest_symbols) + (backtest_start_date, backtest_end_date))
                    else:
                        query = f"""
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' AND symbol IN ({symbols_placeholders})
                        ORDER BY closed_at DESC
                        LIMIT 1000
                        """
                        closed_positions_raw = db._execute_query(query, tuple(backtest_symbols))
            
            closed_positions = [db._convert_row(row) for row in closed_positions_raw] if closed_positions_raw else []
        else:
            closed_positions = db.get_virtual_closed_positions(limit=1000)
        
        if not closed_positions:
            return jsonify({'error': 'Нет сделок для экспорта'}), 404
        
        # Создаем CSV в памяти
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Заголовки
        writer.writerow([
            'ID', 'Symbol', 'Side', 'Size', 'Entry Price', 'Exit Price',
            'Entry Time', 'Exit Time', 'Realized PnL', 'PnL %', 'Leverage', 
            'Entry Fee', 'Exit Fee', 'Total Fees', 'Close Reason', 'Duration'
        ])
        
        # Данные
        for pos in closed_positions:
            # Форматируем длительность
            duration_str = 'N/A'
            if pos['closed_at'] and pos['created_at']:
                duration_delta = pos['closed_at'] - pos['created_at']
                duration_str = format_duration(duration_delta)
            
            writer.writerow([
                pos['id'],
                pos['symbol'],
                pos['side'],
                pos['size'],
                pos['entry_price'],
                pos.get('exit_price', 0),
                pos['created_at'].strftime('%Y-%m-%d %H:%M:%S') if pos['created_at'] else 'N/A',
                pos['closed_at'].strftime('%Y-%m-%d %H:%M:%S') if pos['closed_at'] else 'N/A',
                pos.get('realized_pnl', 0),
                pos.get('pnl_percent', 0),
                pos.get('leverage', 1),
                pos.get('entry_fee', 0),
                pos.get('exit_fee', 0),
                pos.get('total_fees', 0),
                translate_close_reason(pos.get('close_reason', 'N/A')),
                duration_str
            ])
        
        # Создаем ответ
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = 'attachment; filename=backtest_trades.csv'
        return response
        
    except Exception as e:
        logger.error(f"Ошибка экспорта CSV: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/export/results/json')
def export_results_json():
    """Экспорт полных результатов бэктеста в JSON"""
    global last_backtest_engine
    
    if not last_backtest_engine:
        return jsonify({'error': 'Нет данных бэктеста'}), 404
    
    try:
        from flask import make_response
        import json
        
        db = last_backtest_engine.db
        
        # Собираем полные результаты
        results = {
            'backtest_info': {
                'symbols': getattr(last_backtest_engine, 'symbols', []),
                'initial_balance': last_backtest_engine.initial_balance,
                'strategy': getattr(last_backtest_engine, 'backtest_strategy', 'simple'),
                'use_fees': getattr(last_backtest_engine, 'use_fees', True),
                'use_slippage': getattr(last_backtest_engine, 'use_slippage', True)
            },
            'metrics': last_backtest_engine.metrics,
            'trades': [],
            'balance_history': []
        }
        
        # Получаем параметры последнего бэктеста для фильтрации
        backtest_symbols = getattr(last_backtest_engine, 'symbols', [])
        backtest_start_date = getattr(last_backtest_engine, 'backtest_start_date', None)
        backtest_end_date = getattr(last_backtest_engine, 'backtest_end_date', None)
        
        # Получаем сделки с фильтрацией по символам и времени
        if backtest_symbols:
            if db.db_type == 'postgresql':
                if len(backtest_symbols) == 1:
                    if backtest_start_date and backtest_end_date:
                        query = """
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' 
                          AND symbol = %s
                          AND created_at >= %s
                          AND closed_at <= %s
                        ORDER BY closed_at DESC
                        LIMIT 1000
                        """
                        closed_positions_raw = db._execute_query(query, (backtest_symbols[0], backtest_start_date, backtest_end_date))
                    else:
                        query = """
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' AND symbol = %s
                        ORDER BY closed_at DESC
                        LIMIT 1000
                        """
                        closed_positions_raw = db._execute_query(query, (backtest_symbols[0],))
                else:
                    symbols_placeholders = ','.join(['%s'] * len(backtest_symbols))
                    if backtest_start_date and backtest_end_date:
                        query = f"""
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' 
                          AND symbol IN ({symbols_placeholders})
                          AND created_at >= %s
                          AND closed_at <= %s
                        ORDER BY closed_at DESC
                        LIMIT 1000
                        """
                        closed_positions_raw = db._execute_query(query, tuple(backtest_symbols) + (backtest_start_date, backtest_end_date))
                    else:
                        query = f"""
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' AND symbol IN ({symbols_placeholders})
                        ORDER BY closed_at DESC
                        LIMIT 1000
                        """
                        closed_positions_raw = db._execute_query(query, tuple(backtest_symbols))
            else:
                # SQLite
                if len(backtest_symbols) == 1:
                    if backtest_start_date and backtest_end_date:
                        query = """
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' 
                          AND symbol = ?
                          AND created_at >= ?
                          AND closed_at <= ?
                        ORDER BY closed_at DESC
                        LIMIT 1000
                        """
                        closed_positions_raw = db._execute_query(query, (backtest_symbols[0], backtest_start_date, backtest_end_date))
                    else:
                        query = """
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' AND symbol = ?
                        ORDER BY closed_at DESC
                        LIMIT 1000
                        """
                        closed_positions_raw = db._execute_query(query, (backtest_symbols[0],))
                else:
                    symbols_placeholders = ','.join(['?'] * len(backtest_symbols))
                    if backtest_start_date and backtest_end_date:
                        query = f"""
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' 
                          AND symbol IN ({symbols_placeholders})
                          AND created_at >= ?
                          AND closed_at <= ?
                        ORDER BY closed_at DESC
                        LIMIT 1000
                        """
                        closed_positions_raw = db._execute_query(query, tuple(backtest_symbols) + (backtest_start_date, backtest_end_date))
                    else:
                        query = f"""
                        SELECT *
                        FROM virtual_positions
                        WHERE status = 'closed' AND symbol IN ({symbols_placeholders})
                        ORDER BY closed_at DESC
                        LIMIT 1000
                        """
                        closed_positions_raw = db._execute_query(query, tuple(backtest_symbols))
            
            closed_positions = [db._convert_row(row) for row in closed_positions_raw] if closed_positions_raw else []
        else:
            closed_positions = db.get_virtual_closed_positions(limit=1000)
        
        for pos in closed_positions:
            trade = {
                'id': pos['id'],
                'symbol': pos['symbol'],
                'side': pos['side'],
                'size': float(pos['size']),
                'entry_price': float(pos['entry_price']),
                'exit_price': float(pos.get('exit_price', 0)),
                'realized_pnl': float(pos.get('realized_pnl', 0)),
                'pnl_percent': float(pos.get('pnl_percent', 0)),
                'leverage': pos.get('leverage', 1),
                'entry_fee': float(pos.get('entry_fee', 0)),
                'exit_fee': float(pos.get('exit_fee', 0)),
                'total_fees': float(pos.get('total_fees', 0)),
                'close_reason': pos.get('close_reason', 'N/A'),
                'created_at': pos['created_at'].isoformat() if pos['created_at'] else None,
                'closed_at': pos['closed_at'].isoformat() if pos['closed_at'] else None
            }
            results['trades'].append(trade)
        
        # Добавляем историю баланса
        for entry in last_backtest_engine.balance_history:
            results['balance_history'].append({
                'datetime': entry['datetime'].isoformat(),
                'balance': entry['balance']
            })
        
        # Создаем ответ
        response = make_response(json.dumps(results, indent=2))
        response.headers['Content-Type'] = 'application/json'
        response.headers['Content-Disposition'] = 'attachment; filename=backtest_results.json'
        return response
        
    except Exception as e:
        logger.error(f"Ошибка экспорта JSON: {e}")
        import traceback
        traceback.print_exc()
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
    # Отключаем auto-reload чтобы не разрывать SSE соединения
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)



