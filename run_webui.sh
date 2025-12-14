#!/bin/bash
# Скрипт для запуска Web UI

cd "$(dirname "$0")"
export PYTHONPATH="${PWD}/src:${PWD}"
export FLASK_APP="src/web/app.py"
export FLASK_ENV="development"
export FLASK_DEBUG="1"

echo "🚀 Запуск Web UI..."
echo "📁 Рабочая директория: ${PWD}"
echo "🐍 Python: $(which python3.11)"
echo "🌐 Приложение будет доступно на: http://localhost:5000"
echo ""
echo "Для остановки нажмите Ctrl+C"
echo "=" * 80
echo ""

python3.11 src/web/app.py

