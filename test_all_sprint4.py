#!/usr/bin/env python3
"""
Комплексный тест всех компонентов Спринта 4.

Запускает все тесты последовательно и показывает результаты.
"""

import sys
import subprocess
import time
from datetime import datetime

# Проверка версии Python
if sys.version_info < (3, 11) or sys.version_info >= (3, 12):
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print("=" * 80)
    print("⚠️  ВНИМАНИЕ: Неподдерживаемая версия Python!")
    print("=" * 80)
    print(f"   Текущая версия: {python_version}")
    print(f"   Исполняемый файл: {sys.executable}")
    print()
    print("   💡 Рекомендуется использовать Python 3.11:")
    print("      python3.11 test_all_sprint4.py")
    print()
    print("   Продолжить с текущей версией? (может привести к ошибкам)")
    print("=" * 80)
    print()

def print_header(text):
    """Красивый заголовок"""
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80 + "\n")

def print_section(text):
    """Заголовок секции"""
    print("\n" + "-" * 80)
    print(f"  {text}")
    print("-" * 80 + "\n")

def run_test(name, script_path, description):
    """Запускает тест и показывает результат"""
    print_section(f"🧪 ТЕСТ: {name}")
    print(f"📝 Описание: {description}")
    print(f"📂 Скрипт: {script_path}")
    print(f"⏰ Время запуска: {datetime.now().strftime('%H:%M:%S')}")
    print("\n" + "─" * 80)
    
    start_time = time.time()
    
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=False,
            text=True
        )
        
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            print("\n" + "─" * 80)
            print(f"✅ ТЕСТ ПРОЙДЕН: {name}")
            print(f"⏱️  Время выполнения: {elapsed:.1f} секунд")
            return True
        else:
            print("\n" + "─" * 80)
            print(f"❌ ТЕСТ ПРОВАЛЕН: {name}")
            print(f"⏱️  Время выполнения: {elapsed:.1f} секунд")
            return False
            
    except Exception as e:
        elapsed = time.time() - start_time
        print("\n" + "─" * 80)
        print(f"❌ ОШИБКА ПРИ ЗАПУСКЕ: {name}")
        print(f"   {str(e)}")
        print(f"⏱️  Время до ошибки: {elapsed:.1f} секунд")
        return False

def check_dependencies():
    """Проверяет наличие необходимых зависимостей"""
    print_header("🔍 ПРОВЕРКА ЗАВИСИМОСТЕЙ")
    
    # Показываем версию Python
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    python_executable = sys.executable
    print(f"🐍 Python: {python_version} ({python_executable})")
    
    dependencies = {
        'flask': 'Flask (для Web UI)',
        'numpy': 'NumPy (для метрик)',
        'pandas': 'Pandas (для данных)',
        'pybit': 'Pybit (для Bybit API)',
    }
    
    missing = []
    
    for module, name in dependencies.items():
        try:
            __import__(module)
            print(f"✅ {name}")
        except ImportError:
            print(f"❌ {name} - НЕ УСТАНОВЛЕН")
            missing.append(module)
    
    if missing:
        print(f"\n⚠️  Отсутствуют зависимости: {', '.join(missing)}")
        print(f"   Используется Python: {python_executable}")
        print("   💡 Попробуйте запустить с python3.11:")
        print("      python3.11 test_all_sprint4.py")
        print("   Или установите зависимости:")
        print("      python3.11 -m pip install -r requirements.txt")
        return False
    
    print("\n✅ Все зависимости установлены!")
    return True

def check_env():
    """Проверяет наличие .env файла и ключей"""
    print_header("🔐 ПРОВЕРКА КОНФИГУРАЦИИ")
    
    import os
    from pathlib import Path
    
    env_path = Path('.env')
    
    if not env_path.exists():
        print("❌ Файл .env не найден!")
        print("   Создайте .env файл с API ключами")
        return False
    
    print("✅ Файл .env найден")
    
    # Проверяем ключевые переменные
    from dotenv import load_dotenv
    load_dotenv()
    
    required_vars = {
        'BYBIT_API_KEY': 'Bybit API Key',
        'BYBIT_API_SECRET': 'Bybit API Secret',
    }
    
    missing_vars = []
    
    for var, name in required_vars.items():
        value = os.getenv(var)
        if value:
            # Показываем только первые 10 символов для безопасности
            masked = value[:10] + '...' if len(value) > 10 else value
            print(f"✅ {name}: {masked}")
        else:
            print(f"❌ {name}: НЕ УСТАНОВЛЕН")
            missing_vars.append(var)
    
    if missing_vars:
        print(f"\n⚠️  Отсутствуют переменные: {', '.join(missing_vars)}")
        print("   Добавьте их в .env файл")
        return False
    
    print("\n✅ Конфигурация в порядке!")
    return True

def main():
    """Главная функция"""
    print_header("🚀 КОМПЛЕКСНОЕ ТЕСТИРОВАНИЕ СПРИНТА 4")
    print("Этот скрипт запустит все тесты компонентов бэктестинга")
    print("Ожидаемое время: ~5-10 минут\n")
    
    # Проверки перед запуском
    if not check_dependencies():
        print("\n❌ Пожалуйста, установите недостающие зависимости")
        return 1
    
    if not check_env():
        print("\n❌ Пожалуйста, настройте .env файл")
        return 1
    
    # Список тестов
    tests = [
        {
            'name': 'Базовый бэктест',
            'script': 'src/test_backtest.py',
            'description': 'Проверка основного функционала BacktestEngine'
        },
        {
            'name': 'Загрузка данных',
            'script': 'src/test_data_loader.py',
            'description': 'Тест загрузки и кеширования исторических данных'
        },
        {
            'name': 'Комиссии и Slippage',
            'script': 'src/test_fees_slippage.py',
            'description': 'Сравнение бэктестов с/без комиссий и slippage'
        },
        {
            'name': 'Продвинутые метрики',
            'script': 'src/test_advanced_metrics.py',
            'description': 'Тест всех продвинутых метрик (Sharpe, Sortino и др.)'
        }
    ]
    
    print_header("📋 СПИСОК ТЕСТОВ")
    for i, test in enumerate(tests, 1):
        print(f"{i}. {test['name']}")
        print(f"   {test['description']}")
    
    print("\n" + "=" * 80)
    input("▶️  Нажмите Enter для начала тестирования...")
    
    # Запускаем тесты
    results = []
    total_start = time.time()
    
    for test in tests:
        success = run_test(
            test['name'],
            test['script'],
            test['description']
        )
        results.append((test['name'], success))
        
        if not success:
            print(f"\n⚠️  Тест '{test['name']}' провален, но продолжаем...")
        
        # Небольшая пауза между тестами
        time.sleep(2)
    
    total_time = time.time() - total_start
    
    # Итоговый отчет
    print_header("📊 ИТОГОВЫЙ ОТЧЕТ")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    print(f"Всего тестов: {total}")
    print(f"Пройдено: {passed}")
    print(f"Провалено: {total - passed}")
    print(f"Общее время: {total_time/60:.1f} минут")
    
    print("\nДетали:")
    for name, success in results:
        status = "✅ ПРОЙДЕН" if success else "❌ ПРОВАЛЕН"
        print(f"  {status}: {name}")
    
    print("\n" + "=" * 80)
    
    if passed == total:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("=" * 80)
        print("\n✅ Система бэктестинга готова к использованию!")
        print("\nСледующие шаги:")
        print("  1. Запустите Web UI: python src/web/app.py")
        print("  2. Откройте http://localhost:5000")
        print("  3. Запустите бэктест через веб-интерфейс")
        return 0
    else:
        print("⚠️  НЕКОТОРЫЕ ТЕСТЫ ПРОВАЛЕНЫ")
        print("=" * 80)
        print("\nПроверьте логи выше для деталей")
        print("Убедитесь что:")
        print("  - Все зависимости установлены")
        print("  - .env файл настроен правильно")
        print("  - Есть доступ к интернету (для Bybit API)")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏸️  Тестирование прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

