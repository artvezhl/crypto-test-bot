// Глобальные переменные для графиков
let balanceChart = null;
let drawdownChart = null;
let pnlChart = null;
let eventSource = null;

// Обработка отправки формы
document.getElementById('backtestForm').addEventListener('submit', async function(e) {
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

// Подключение к SSE для получения прогресса
function connectToProgress() {
    // Закрываем предыдущее соединение если есть
    disconnectFromProgress();
    
    eventSource = new EventSource('/api/progress');
    
    eventSource.onmessage = function(event) {
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
    };
    
    eventSource.onerror = function(error) {
        console.error('SSE Error:', error);
        disconnectFromProgress();
    };
}

// Отключение от SSE
function disconnectFromProgress() {
    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }
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
    displayMetric('roi', results.roi_percent, '%', true);
    displayMetric('total_pnl', results.total_pnl, '$', true);
    displayMetric('win_rate', results.win_rate, '%', false);
    displayMetric('max_drawdown', results.max_drawdown, '%', false, true);
    
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
    const formatted = value.toFixed(2) + suffix;
    element.textContent = formatted;
    
    if (colorize) {
        if ((value > 0 && !inverse) || (value < 0 && inverse)) {
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
        const [balanceData, drawdownData, pnlData] = await Promise.all([
            fetch('/api/chart_data/balance').then(r => r.json()),
            fetch('/api/chart_data/drawdown').then(r => r.json()),
            fetch('/api/chart_data/pnl_distribution').then(r => r.json())
        ]);
        
        // Создаем графики
        createBalanceChart(balanceData);
        createDrawdownChart(drawdownData);
        createPnlChart(pnlData);
        
    } catch (error) {
        console.error('Ошибка загрузки графиков:', error);
    }
}

function createBalanceChart(data) {
    const ctx = document.getElementById('balanceChart').getContext('2d');
    
    // Уничтожаем предыдущий график если есть
    if (balanceChart) {
        balanceChart.destroy();
    }
    
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
    const ctx = document.getElementById('pnlChart').getContext('2d');
    
    if (pnlChart) {
        pnlChart.destroy();
    }
    
    // Раскрашиваем бары в зависимости от прибыли/убытка
    const colors = data.pnls.map(pnl => pnl >= 0 ? 'rgba(16, 185, 129, 0.8)' : 'rgba(239, 68, 68, 0.8)');
    
    pnlChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.trade_numbers,
            datasets: [{
                label: 'PnL ($)',
                data: data.pnls,
                backgroundColor: colors,
                borderColor: colors.map(c => c.replace('0.8', '1')),
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
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
                            return `Сделка #${data.trade_numbers[idx]} (${data.symbols[idx]} ${data.sides[idx]})`;
                        },
                        label: function(context) {
                            return 'PnL: $' + context.parsed.y.toFixed(2);
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return '$' + value.toFixed(0);
                        }
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Номер сделки'
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
        if (settings.symbols) {
            document.getElementById('symbols').value = settings.symbols;
        }
    } catch (error) {
        console.error('Ошибка загрузки настроек:', error);
    }
});


