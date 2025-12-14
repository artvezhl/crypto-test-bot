// Глобальные переменные для графиков
let balanceChart = null;
let drawdownChart = null;
let pnlChart = null;
let eventSource = null;

// Пагинация таблицы сделок
let allTrades = [];
let currentTradesPage = 1;
const tradesPerPage = 50;

// Переподключение SSE
let reconnectAttempts = 0;
const maxReconnectAttempts = 10;
let reconnectTimeout = null;

// Инициализация при загрузке DOM
window.addEventListener('DOMContentLoaded', function() {
    // Обработка отправки формы
    const backtestForm = document.getElementById('backtestForm');
    if (!backtestForm) {
        console.error('❌ Форма backtestForm не найдена');
        return;
    }
    
    backtestForm.addEventListener('submit', async function(e) {
    e.preventDefault();
    
    // Дизейблим кнопку
    const runButton = document.getElementById('runButton');
    const buttonText = document.getElementById('buttonText');
    runButton.disabled = true;
    buttonText.textContent = 'Выполняется...';
    
    // Показываем прогресс-бар
    document.getElementById('progressContainer').classList.remove('hidden');
    document.getElementById('results').classList.add('hidden');
    document.getElementById('loading').classList.add('hidden');
    
    // Сбрасываем прогресс
    updateProgress(0, 'Инициализация...');
    
    // Собираем параметры
    const params = {
        symbols: document.getElementById('symbols').value,
        interval: document.getElementById('interval').value,
        days: parseInt(document.getElementById('days').value),
        initial_balance: parseFloat(document.getElementById('initial_balance').value),
        strategy: document.getElementById('strategy').value,
        use_fees: document.getElementById('use_fees').checked,
        use_slippage: document.getElementById('use_slippage').checked
    };
    
    try {
        // Подключаемся к SSE для получения прогресса
        connectToProgress();
        
        // Запускаем бэктест
        const response = await fetch('/api/run_backtest', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(params)
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Ошибка выполнения бэктеста');
            disconnectFromProgress();
            resetUI();
        }
        
    } catch (error) {
        console.error('Ошибка:', error);
        alert('Ошибка: ' + error.message);
        disconnectFromProgress();
        resetUI();
    }
    });
}); // Конец DOMContentLoaded

// Подключение к SSE для получения прогресса
function connectToProgress() {
    // Закрываем предыдущее соединение если есть
    disconnectFromProgress();
    
    if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
    }
    
    reconnectAttempts = 0;
    
    eventSource = new EventSource('/api/progress');
    
    eventSource.onopen = function() {
        console.log('SSE соединение установлено');
        reconnectAttempts = 0; // Сбрасываем счетчик при успешном подключении
    };
    
    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            
            if (data.status === 'running') {
                updateProgress(data.progress, data.message);
            } else if (data.status === 'completed') {
                updateProgress(100, 'Готово!');
                displayResults(data.results);
                loadCharts();
                disconnectFromProgress();
                resetUI();
            } else if (data.status === 'error') {
                alert('Ошибка: ' + data.message);
                disconnectFromProgress();
                resetUI();
            } else if (data.status === 'done') {
                disconnectFromProgress();
            }
        } catch (e) {
            console.error('Ошибка парсинга SSE данных:', e);
        }
    };
    
    eventSource.onerror = function(error) {
        console.error('SSE Error:', error);
        
        // Проверяем состояние соединения
        if (eventSource && eventSource.readyState === EventSource.CLOSED) {
            // Соединение закрыто - пытаемся переподключиться
            if (reconnectAttempts < maxReconnectAttempts) {
                reconnectAttempts++;
                const delay = Math.min(1000 * reconnectAttempts, 5000); // Максимум 5 секунд
                
                console.log(`Попытка переподключения ${reconnectAttempts}/${maxReconnectAttempts} через ${delay}ms...`);
                
                // Проверяем состояние бэктеста перед переподключением
                checkBacktestStatus().then(isRunning => {
                    if (isRunning) {
                        reconnectTimeout = setTimeout(() => {
                            connectToProgress();
                        }, delay);
                    } else {
                        console.log('Бэктест завершен, переподключение не требуется');
                        disconnectFromProgress();
                    }
                });
            } else {
                console.error('Превышено максимальное количество попыток переподключения');
                updateProgress(0, 'Ошибка соединения. Проверьте состояние бэктеста.');
                disconnectFromProgress();
            }
        }
    };
}

// Проверка состояния бэктеста
async function checkBacktestStatus() {
    try {
        const response = await fetch('/api/backtest_status');
        const data = await response.json();
        return data.running === true;
    } catch (error) {
        console.error('Ошибка проверки статуса:', error);
        return false;
    }
}

// Отключение от SSE
function disconnectFromProgress() {
    if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
    }
    
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
    
    reconnectAttempts = 0;
}

// Обновление прогресс-бара
function updateProgress(percent, message) {
    document.getElementById('progressBar').style.width = percent + '%';
    document.getElementById('progressPercent').textContent = Math.round(percent) + '%';
    document.getElementById('progressMessage').textContent = message;
}

// Сброс UI после завершения
function resetUI() {
    const runButton = document.getElementById('runButton');
    const buttonText = document.getElementById('buttonText');
    runButton.disabled = false;
    buttonText.textContent = 'Запустить бэктест';
    
    // Скрываем прогресс-бар через 2 секунды
    setTimeout(() => {
        document.getElementById('progressContainer').classList.add('hidden');
    }, 2000);
}

function displayResults(results) {
    // Показываем блок с результатами
    document.getElementById('results').classList.remove('hidden');
    
    // Базовые метрики
    console.log('📊 Результаты бэктеста:', {
        roi_percent: results.roi_percent,
        total_pnl: results.total_pnl,
        win_rate: results.win_rate,
        max_drawdown: results.max_drawdown,
        winning_trades: results.winning_trades,
        total_trades: results.total_trades
    });
    displayMetric('roi', results.roi_percent, '%', true);
    displayMetric('total_pnl', results.total_pnl, '$', true);
    
    // Win Rate - проверяем что значение есть
    const winRateValue = results.win_rate || 0;
    const winRateElement = document.getElementById('win_rate');
    console.log('🎯 Обновление Win Rate:', { 
        winRateValue, 
        element: winRateElement,
        elementTextBefore: winRateElement?.textContent,
        elementVisible: winRateElement ? window.getComputedStyle(winRateElement).display !== 'none' : false
    });
    displayMetric('win_rate', winRateValue, '%');
    
    // Убеждаемся что win_rate имеет видимый цвет (не белый)
    const winRateEl = document.getElementById('win_rate');
    if (winRateEl) {
        winRateEl.style.color = '#111827'; // Темно-серый цвет (gray-900)
        winRateEl.classList.remove('metric-positive', 'metric-negative', 'text-white');
    }
    
    // Проверяем после обновления
    setTimeout(() => {
        const afterElement = document.getElementById('win_rate');
        console.log('🔍 Win Rate после обновления:', {
            textContent: afterElement?.textContent,
            innerHTML: afterElement?.innerHTML,
            visible: afterElement ? window.getComputedStyle(afterElement).display !== 'none' : false
        });
    }, 100);
    
    // Max Drawdown - не используем colorize, чтобы текст был виден
    displayMetric('max_drawdown', results.max_drawdown || 0, '%', false);
    
    // Win ratio
    document.getElementById('win_ratio').textContent = 
        `${results.winning_trades}/${results.total_trades} сделок`;
    
    // Продвинутые метрики
    document.getElementById('sharpe_ratio').textContent = results.sharpe_ratio.toFixed(3);
    document.getElementById('sortino_ratio').textContent = results.sortino_ratio.toFixed(3);
    document.getElementById('calmar_ratio').textContent = results.calmar_ratio.toFixed(3);
    document.getElementById('profit_factor').textContent = results.profit_factor.toFixed(2);
    document.getElementById('expectancy').textContent = '$' + results.expectancy.toFixed(2);
    
    // Average duration
    const hours = results.avg_trade_duration_hours;
    let durationText;
    if (hours < 1) {
        durationText = (hours * 60).toFixed(0) + 'мин';
    } else if (hours < 24) {
        durationText = hours.toFixed(1) + 'ч';
    } else {
        durationText = (hours / 24).toFixed(1) + 'д';
    }
    document.getElementById('avg_duration').textContent = durationText;
    
    // Применяем цветовое кодирование к продвинутым метрикам
    colorizeMetric('sharpe_ratio', results.sharpe_ratio, 1.0, 2.0);
    colorizeMetric('sortino_ratio', results.sortino_ratio, 1.0, 2.0);
    colorizeMetric('calmar_ratio', results.calmar_ratio, 1.0, 2.0);
    colorizeMetric('profit_factor', results.profit_factor, 1.5, 2.0);
}

function displayMetric(id, value, suffix = '', colorize = false, inverse = false) {
    const element = document.getElementById(id);
    if (!element) {
        console.warn(`⚠️ Элемент с ID "${id}" не найден в DOM`);
        return;
    }
    
    // Проверяем, что значение существует и является числом
    if (value === undefined || value === null || isNaN(value)) {
        console.warn(`⚠️ Значение для "${id}" невалидно:`, value);
        element.textContent = '-';
        return;
    }
    
    const numValue = Number(value);
    if (isNaN(numValue)) {
        console.warn(`⚠️ Не удалось преобразовать значение для "${id}" в число:`, value);
        element.textContent = '-';
        return;
    }
    
    const formatted = numValue.toFixed(2) + suffix;
    element.textContent = formatted;
    
    // Для win_rate и max_drawdown устанавливаем явный темный цвет текста
    if (id === 'win_rate' || id === 'max_drawdown') {
        element.style.color = '#111827'; // Темно-серый цвет (gray-900)
        element.classList.remove('metric-positive', 'metric-negative', 'text-white');
        if (id === 'win_rate') {
            console.log(`✅ Обновлен ${id}: ${formatted} (значение: ${numValue})`);
        }
    }
    
    if (colorize) {
        if ((numValue > 0 && !inverse) || (numValue < 0 && inverse)) {
            element.classList.add('metric-positive');
            element.classList.remove('metric-negative');
        } else {
            element.classList.add('metric-negative');
            element.classList.remove('metric-positive');
        }
    }
}

function colorizeMetric(id, value, goodThreshold, excellentThreshold) {
    const element = document.getElementById(id);
    
    if (value >= excellentThreshold) {
        element.style.color = '#10b981'; // green
    } else if (value >= goodThreshold) {
        element.style.color = '#f59e0b'; // yellow
    } else {
        element.style.color = '#ef4444'; // red
    }
}

async function loadCharts() {
    try {
        // Загружаем данные для всех графиков параллельно
        const balancePromise = fetch('/api/chart_data/balance')
            .then(r => r.ok ? r.json() : { error: 'Нет данных' })
            .catch(() => ({ error: 'Ошибка загрузки' }));
        const drawdownPromise = fetch('/api/chart_data/drawdown')
            .then(r => r.ok ? r.json() : { error: 'Нет данных' })
            .catch(() => ({ error: 'Ошибка загрузки' }));
        const pnlPromise = fetch('/api/chart_data/pnl_distribution')
            .then(r => r.ok ? r.json() : { pnls: [] })
            .catch(() => ({ pnls: [] }));
        
        const [balanceData, drawdownData, pnlData] = await Promise.all([
            balancePromise,
            drawdownPromise,
            pnlPromise
        ]);
        
        console.log('📊 Данные графиков:', {
            balance: balanceData.error ? 'Ошибка' : `OK (${balanceData.timestamps?.length || 0} точек)`,
            drawdown: drawdownData.error ? 'Ошибка' : 'OK',
            pnl: pnlData.pnls?.length || 0
        });
        
        // Создаем графики
        if (!balanceData.error) {
        createBalanceChart(balanceData);
        } else {
            console.log('⏸️ График баланса недоступен:', balanceData.error);
        }
        if (!drawdownData.error) {
        createDrawdownChart(drawdownData);
        } else {
            console.log('⏸️ График просадки недоступен:', drawdownData.error);
        }
        
        // Создаем график PnL (с проверкой данных внутри функции)
        createPnlChart(pnlData);
        
        // Загружаем таблицу сделок
        await loadTrades();
        
    } catch (error) {
        console.error('Ошибка загрузки графиков:', error);
    }
}

async function loadTrades() {
    try {
        console.log('🔄 Загрузка сделок...');
        const response = await fetch('/api/trades');
        const data = await response.json();
        
        console.log('📊 Данные сделок:', { 
            tradesCount: data.trades?.length || 0, 
            summary: data.summary,
            error: data.error 
        });
        
        if (data.error) {
            console.error('Ошибка загрузки сделок:', data.error);
            return;
        }
        
        const tradesContainer = document.getElementById('tradesTableContainer');
        const tradesTableBody = document.getElementById('tradesTableBody');
        const tradesSummary = document.getElementById('tradesSummary');
        
        if (!tradesContainer || !tradesTableBody) {
            console.error('❌ Элементы таблицы сделок не найдены в DOM');
            return;
        }
        
        if (!data.trades || data.trades.length === 0) {
            console.log('⏸️ Нет сделок для отображения');
            tradesContainer.style.display = 'none';
            return;
        }
        
        // Сохраняем все сделки для пагинации
        allTrades = data.trades;
        currentTradesPage = 1;
        
        // Показываем контейнер
        tradesContainer.style.display = 'block';
        // Убеждаемся, что контейнер виден
        tradesContainer.classList.remove('hidden');
        console.log('✅ Контейнер таблицы сделок показан', {
            container: tradesContainer,
            display: tradesContainer.style.display,
            allTradesCount: allTrades.length,
            classList: tradesContainer.classList.toString()
        });
        
        // Обновляем summary
        const summary = data.summary;
        if (tradesSummary) {
            tradesSummary.innerHTML = `
                Всего: <span class="font-semibold">${summary.total}</span> | 
                Прибыльных: <span class="font-semibold text-green-600">${summary.winning}</span> | 
                Убыточных: <span class="font-semibold text-red-600">${summary.losing}</span> | 
                Win Rate: <span class="font-semibold">${summary.win_rate.toFixed(1)}%</span>
            `;
        }
        
        // Отображаем первую страницу
        console.log('📋 Рендеринг таблицы сделок...');
        renderTradesPage();
        console.log('✅ Таблица сделок отображена');
        
    } catch (error) {
        console.error('Ошибка загрузки таблицы сделок:', error);
    }
}

function renderTradesPage() {
    console.log('🔄 renderTradesPage вызвана', { allTradesLength: allTrades?.length, currentPage: currentTradesPage });
    
    const tradesTableBody = document.getElementById('tradesTableBody');
    const tradesPagination = document.getElementById('tradesPagination');
    const tradesShown = document.getElementById('tradesShown');
    const tradesTotal = document.getElementById('tradesTotal');
    const tradesPageInfo = document.getElementById('tradesPageInfo');
    const tradesPrevBtn = document.getElementById('tradesPrevBtn');
    const tradesNextBtn = document.getElementById('tradesNextBtn');
    
    if (!tradesTableBody) {
        console.error('❌ tradesTableBody не найден');
        return;
    }
    
    if (!allTrades || allTrades.length === 0) {
        console.log('⏸️ Нет сделок для рендеринга');
        if (tradesPagination) {
            tradesPagination.style.display = 'none';
        }
        return;
    }
    
    // Вычисляем пагинацию
    const totalPages = Math.ceil(allTrades.length / tradesPerPage);
    const startIdx = (currentTradesPage - 1) * tradesPerPage;
    const endIdx = Math.min(startIdx + tradesPerPage, allTrades.length);
    const pageTrades = allTrades.slice(startIdx, endIdx);
    
    // Очищаем таблицу
    tradesTableBody.innerHTML = '';
    console.log(`📋 Рендеринг ${pageTrades.length} сделок (страница ${currentTradesPage} из ${totalPages})`);
    
    // Заполняем таблицу только текущей страницей
    pageTrades.forEach((trade, index) => {
        if (index === 0) {
            console.log('📊 Пример сделки:', trade);
        }
        const row = document.createElement('tr');
        row.className = 'hover:bg-gray-50';
        
        // Определяем цвет для PnL
        const pnlColor = trade.realized_pnl > 0 ? 'text-green-600 font-semibold' : 
                       trade.realized_pnl < 0 ? 'text-red-600 font-semibold' : 
                       'text-gray-600';
        
        // Направление
        const sideClass = trade.side === 'BUY' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800';
        const sideText = trade.side === 'BUY' ? 'LONG' : 'SHORT';
        
        row.innerHTML = `
            <td class="px-4 py-3 text-sm text-gray-900">#${trade.id}</td>
            <td class="px-4 py-3 text-sm font-medium text-gray-900">${trade.symbol}</td>
            <td class="px-4 py-3 text-sm">
                <span class="px-2 py-1 text-xs font-semibold rounded ${sideClass}">${sideText}</span>
            </td>
            <td class="px-4 py-3 text-sm text-right text-gray-900">${trade.size.toFixed(6)}</td>
            <td class="px-4 py-3 text-sm text-right text-gray-900">$${trade.entry_price.toFixed(2)}</td>
            <td class="px-4 py-3 text-sm text-right text-gray-900">$${trade.exit_price.toFixed(2)}</td>
            <td class="px-4 py-3 text-sm text-gray-600">${trade.created_at_date || 'N/A'}</td>
            <td class="px-4 py-3 text-sm text-gray-600" title="${trade.created_at || 'N/A'}">${trade.created_at_short || 'N/A'}</td>
            <td class="px-4 py-3 text-sm text-gray-600">${trade.closed_at_date || 'N/A'}</td>
            <td class="px-4 py-3 text-sm text-gray-600" title="${trade.closed_at || 'N/A'}">${trade.closed_at_short || 'N/A'}</td>
            <td class="px-4 py-3 text-sm text-right ${pnlColor}">$${trade.realized_pnl.toFixed(2)}</td>
            <td class="px-4 py-3 text-sm text-right ${pnlColor}">${trade.pnl_percent.toFixed(2)}%</td>
            <td class="px-4 py-3 text-sm text-right text-gray-600">$${trade.total_fees.toFixed(4)}</td>
            <td class="px-4 py-3 text-sm text-gray-600">${trade.duration}</td>
            <td class="px-4 py-3 text-sm text-gray-600">${trade.close_reason}</td>
        `;
        
        tradesTableBody.appendChild(row);
    });
    
    // Обновляем пагинацию
    if (totalPages > 1) {
        tradesPagination.style.display = 'flex';
        tradesShown.textContent = `${startIdx + 1}-${endIdx}`;
        tradesTotal.textContent = allTrades.length;
        tradesPageInfo.textContent = `Страница ${currentTradesPage} из ${totalPages}`;
        
        tradesPrevBtn.disabled = currentTradesPage === 1;
        tradesNextBtn.disabled = currentTradesPage === totalPages;
    } else {
        tradesPagination.style.display = 'none';
    }
}

function changeTradesPage(direction) {
    const totalPages = Math.ceil(allTrades.length / tradesPerPage);
    const newPage = currentTradesPage + direction;
    
    if (newPage >= 1 && newPage <= totalPages) {
        currentTradesPage = newPage;
        renderTradesPage();
    }
}

function createBalanceChart(data) {
    if (!data || !data.timestamps || !data.balances || data.timestamps.length === 0) {
        console.log('⏸️ Нет данных для графика баланса');
        return;
    }
    
    const balanceChartElement = document.getElementById('balanceChart');
    if (!balanceChartElement) {
        console.error('❌ Элемент balanceChart не найден');
        return;
    }
    
    const ctx = balanceChartElement.getContext('2d');
    
    // Уничтожаем предыдущий график если есть
    if (balanceChart) {
        balanceChart.destroy();
    }
    
    console.log('📊 Создание графика баланса:', {
        timestampsCount: data.timestamps.length,
        balancesCount: data.balances.length,
        initialBalance: data.initial_balance
    });
    
    balanceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.timestamps,
            datasets: [{
                label: 'Баланс ($)',
                data: data.balances,
                borderColor: 'rgb(102, 126, 234)',
                backgroundColor: 'rgba(102, 126, 234, 0.1)',
                fill: true,
                tension: 0.4
            }, {
                label: 'Начальный баланс',
                data: new Array(data.timestamps.length).fill(data.initial_balance),
                borderColor: 'rgb(156, 163, 175)',
                borderDash: [5, 5],
                borderWidth: 1,
                fill: false,
                pointRadius: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': $' + context.parsed.y.toFixed(2);
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    ticks: {
                        callback: function(value) {
                            return '$' + value.toFixed(0);
                        }
                    }
                }
            }
        }
    });
}

function createDrawdownChart(data) {
    const ctx = document.getElementById('drawdownChart').getContext('2d');
    
    if (drawdownChart) {
        drawdownChart.destroy();
    }
    
    drawdownChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.timestamps,
            datasets: [{
                label: 'Просадка (%)',
                data: data.drawdowns,
                borderColor: 'rgb(239, 68, 68)',
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return 'Просадка: ' + context.parsed.y.toFixed(2) + '%';
                        }
                    }
                }
            },
            scales: {
                y: {
                    reverse: true,
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return value.toFixed(1) + '%';
                        }
                    }
                }
            }
        }
    });
}

function createPnlChart(data) {
    const pnlChartCard = document.getElementById('pnlChartCard');
    
    if (!data || !data.pnls || data.pnls.length === 0) {
        console.log('⏸️ Нет данных для графика PnL');
        // Скрываем контейнер графика, если нет данных
        if (pnlChartCard) {
            pnlChartCard.style.display = 'none';
        }
        if (pnlChart) {
            pnlChart.destroy();
            pnlChart = null;
        }
        return;
    }
    
    // Показываем контейнер, если есть данные
    if (pnlChartCard) {
        pnlChartCard.style.display = 'block';
    }
    
    const ctx = document.getElementById('pnlChart').getContext('2d');
    
    if (pnlChart) {
        pnlChart.destroy();
    }
    
    // Ограничиваем количество данных для производительности (максимум 100)
    const maxBars = 100;
    let displayData = data;
    if (data.pnls.length > maxBars) {
        // Берем последние maxBars сделок
        const startIdx = data.pnls.length - maxBars;
        displayData = {
            trade_numbers: data.trade_numbers.slice(startIdx),
            pnls: data.pnls.slice(startIdx),
            symbols: data.symbols.slice(startIdx),
            sides: data.sides.slice(startIdx)
        };
    }
    
    // Раскрашиваем бары в зависимости от прибыли/убытка
    const colors = displayData.pnls.map(pnl => pnl >= 0 ? 'rgba(16, 185, 129, 0.8)' : 'rgba(239, 68, 68, 0.8)');
    
    // Вычисляем разумные границы для масштабирования
    const minPnL = Math.min(...displayData.pnls);
    const maxPnL = Math.max(...displayData.pnls);
    const range = maxPnL - minPnL;
    const padding = range * 0.1; // 10% отступ
    
    pnlChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: displayData.trade_numbers,
            datasets: [{
                label: 'PnL ($)',
                data: displayData.pnls,
                backgroundColor: colors,
                borderColor: colors.map(c => c.replace('0.8', '1')),
                borderWidth: 1,
                maxBarThickness: 50 // Ограничиваем ширину баров
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: {
                    top: 10,
                    bottom: 10
                }
            },
            animation: {
                duration: 0 // Отключаем анимацию для производительности
            },
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        title: function(context) {
                            const idx = context[0].dataIndex;
                            return `Сделка #${displayData.trade_numbers[idx]} (${displayData.symbols[idx]} ${displayData.sides[idx]})`;
                        },
                        label: function(context) {
                            return 'PnL: $' + context.parsed.y.toFixed(2);
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: false, // Не начинаем с нуля для лучшего масштабирования
                    suggestedMin: minPnL - padding,
                    suggestedMax: maxPnL + padding,
                    ticks: {
                        callback: function(value) {
                            return '$' + value.toFixed(0);
                        },
                        maxTicksLimit: 10 // Ограничиваем количество меток
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Номер сделки'
                    },
                    ticks: {
                        maxTicksLimit: 20 // Ограничиваем количество меток на оси X
                    }
                }
            }
        }
    });
}

// Автоматически подгружаем настройки при загрузке страницы
window.addEventListener('DOMContentLoaded', async function() {
    try {
        const response = await fetch('/api/settings');
        const settings = await response.json();
        
        // Заполняем форму настройками из БД
        
        // Пытаемся загрузить сделки, если бэктест уже был выполнен
        try {
            await loadTrades();
        } catch (e) {
            console.log('Бэктест еще не выполнен или нет сделок');
        }
        if (settings.symbols) {
            document.getElementById('symbols').value = settings.symbols;
        }
    } catch (error) {
        console.error('Ошибка загрузки настроек:', error);
    }
});

// Экспорт сделок в CSV
function exportTradesCSV() {
    window.location.href = '/api/export/trades/csv';
}

// Экспорт результатов в JSON
function exportResultsJSON() {
    window.location.href = '/api/export/results/json';
}



