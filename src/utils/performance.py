"""
Утилиты для мониторинга производительности.

Использование:
    from utils.performance import log_performance, PerformanceTracker

    @log_performance
    def my_slow_function():
        ...

    # Или с порогом
    @log_performance(threshold_seconds=2.0)
    def my_function():
        ...
"""
import time
import functools
import logging
from typing import Optional, Callable, Any
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """Трекер производительности для сбора метрик"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_tracker()
        return cls._instance
    
    def _init_tracker(self):
        """Инициализация трекера"""
        self.metrics = defaultdict(list)
        self.call_counts = defaultdict(int)
        self.total_time = defaultdict(float)
        self.errors = defaultdict(int)
        self.start_time = datetime.now()
    
    def record(self, func_name: str, duration: float, success: bool = True):
        """Записывает метрику выполнения функции"""
        self.metrics[func_name].append({
            'duration': duration,
            'timestamp': datetime.now(),
            'success': success
        })
        self.call_counts[func_name] += 1
        self.total_time[func_name] += duration
        if not success:
            self.errors[func_name] += 1
        
        # Ограничиваем историю последними 1000 записями
        if len(self.metrics[func_name]) > 1000:
            self.metrics[func_name] = self.metrics[func_name][-1000:]
    
    def get_stats(self, func_name: str) -> dict:
        """Возвращает статистику для функции"""
        if func_name not in self.metrics or not self.metrics[func_name]:
            return {}
        
        durations = [m['duration'] for m in self.metrics[func_name]]
        
        return {
            'func_name': func_name,
            'call_count': self.call_counts[func_name],
            'total_time': self.total_time[func_name],
            'avg_time': self.total_time[func_name] / self.call_counts[func_name],
            'min_time': min(durations),
            'max_time': max(durations),
            'error_count': self.errors[func_name],
            'success_rate': (self.call_counts[func_name] - self.errors[func_name]) / self.call_counts[func_name] * 100
        }
    
    def get_all_stats(self) -> dict:
        """Возвращает статистику для всех функций"""
        return {
            'uptime_seconds': (datetime.now() - self.start_time).total_seconds(),
            'functions': {name: self.get_stats(name) for name in self.metrics.keys()}
        }
    
    def get_slow_operations(self, threshold: float = 1.0) -> list:
        """Возвращает список медленных операций"""
        slow_ops = []
        for func_name, records in self.metrics.items():
            slow_calls = [r for r in records if r['duration'] > threshold]
            if slow_calls:
                slow_ops.append({
                    'func_name': func_name,
                    'slow_call_count': len(slow_calls),
                    'avg_slow_duration': sum(r['duration'] for r in slow_calls) / len(slow_calls)
                })
        return slow_ops
    
    def reset(self):
        """Сбрасывает все метрики"""
        self._init_tracker()


# Глобальный экземпляр трекера
_tracker = PerformanceTracker()


def log_performance(func: Optional[Callable] = None, *, 
                    threshold_seconds: float = 1.0,
                    log_all: bool = False,
                    track_metrics: bool = True) -> Callable:
    """
    Декоратор для логирования производительности функций.
    
    Args:
        func: Декорируемая функция
        threshold_seconds: Порог в секундах, выше которого логируется предупреждение
        log_all: Логировать все вызовы (не только медленные)
        track_metrics: Записывать метрики в трекер
    
    Использование:
        @log_performance
        def my_function():
            ...
        
        @log_performance(threshold_seconds=2.0)
        def slow_function():
            ...
        
        @log_performance(log_all=True)
        def important_function():
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.perf_counter()
            success = True
            
            try:
                result = fn(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                logger.error(f"❌ {fn.__name__} failed after {time.perf_counter() - start_time:.3f}s: {e}")
                raise
            finally:
                duration = time.perf_counter() - start_time
                
                # Записываем метрики
                if track_metrics:
                    _tracker.record(fn.__name__, duration, success)
                
                # Логируем
                if duration > threshold_seconds:
                    logger.warning(
                        f"⚠️ SLOW: {fn.__name__} took {duration:.3f}s (threshold: {threshold_seconds}s)"
                    )
                elif log_all:
                    logger.debug(f"⏱️ {fn.__name__} took {duration:.3f}s")
        
        return wrapper
    
    # Поддержка @log_performance и @log_performance()
    if func is not None:
        return decorator(func)
    return decorator


def get_performance_tracker() -> PerformanceTracker:
    """Возвращает глобальный трекер производительности"""
    return _tracker


def get_performance_summary() -> str:
    """Возвращает текстовую сводку производительности"""
    stats = _tracker.get_all_stats()
    
    lines = [
        "📊 Performance Summary",
        f"Uptime: {stats['uptime_seconds']:.1f}s",
        ""
    ]
    
    for func_name, func_stats in stats['functions'].items():
        if func_stats:
            lines.append(
                f"  {func_name}: "
                f"calls={func_stats['call_count']}, "
                f"avg={func_stats['avg_time']:.3f}s, "
                f"max={func_stats['max_time']:.3f}s, "
                f"success={func_stats['success_rate']:.1f}%"
            )
    
    slow_ops = _tracker.get_slow_operations()
    if slow_ops:
        lines.append("")
        lines.append("⚠️ Slow Operations:")
        for op in slow_ops:
            lines.append(f"  - {op['func_name']}: {op['slow_call_count']} slow calls")
    
    return "\n".join(lines)



