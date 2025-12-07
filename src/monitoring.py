"""
Мониторинг торгового бота.

Включает:
- Health check для проверки состояния компонентов
- Метрики производительности
- Статистика торговли
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Статус здоровья компонента"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Состояние здоровья компонента"""
    name: str
    status: HealthStatus
    message: str = ""
    last_check: datetime = field(default_factory=datetime.now)
    response_time_ms: float = 0.0
    details: Dict = field(default_factory=dict)


class HealthChecker:
    """Проверка здоровья всех компонентов системы"""
    
    def __init__(self, db=None, bybit=None, deepseek=None):
        self.db = db
        self.bybit = bybit
        self.deepseek = deepseek
        self.last_full_check: Optional[datetime] = None
        self.components_health: Dict[str, ComponentHealth] = {}
    
    def check_database(self) -> ComponentHealth:
        """Проверка здоровья базы данных"""
        import time
        start = time.perf_counter()
        
        try:
            if self.db is None:
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.UNKNOWN,
                    message="Database not configured"
                )
            
            # Простой запрос для проверки
            result = self.db.get_setting('leverage', '10')
            response_time = (time.perf_counter() - start) * 1000
            
            if result:
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    message="Database connection OK",
                    response_time_ms=response_time,
                    details={"db_type": self.db.db_type}
                )
            else:
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.DEGRADED,
                    message="Database query returned empty",
                    response_time_ms=response_time
                )
                
        except Exception as e:
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database error: {str(e)}",
                response_time_ms=(time.perf_counter() - start) * 1000
            )
    
    def check_bybit(self) -> ComponentHealth:
        """Проверка здоровья Bybit API"""
        import time
        start = time.perf_counter()
        
        try:
            if self.bybit is None:
                return ComponentHealth(
                    name="bybit_api",
                    status=HealthStatus.UNKNOWN,
                    message="Bybit client not configured"
                )
            
            # Получаем рыночные данные как проверку
            market_data = self.bybit.get_market_data("BTCUSDT")
            response_time = (time.perf_counter() - start) * 1000
            
            if market_data and 'price' in market_data:
                return ComponentHealth(
                    name="bybit_api",
                    status=HealthStatus.HEALTHY,
                    message="Bybit API connection OK",
                    response_time_ms=response_time,
                    details={"btc_price": market_data.get('price')}
                )
            else:
                return ComponentHealth(
                    name="bybit_api",
                    status=HealthStatus.DEGRADED,
                    message="Bybit API returned incomplete data",
                    response_time_ms=response_time
                )
                
        except Exception as e:
            return ComponentHealth(
                name="bybit_api",
                status=HealthStatus.UNHEALTHY,
                message=f"Bybit API error: {str(e)}",
                response_time_ms=(time.perf_counter() - start) * 1000
            )
    
    def check_deepseek(self) -> ComponentHealth:
        """Проверка здоровья DeepSeek API (лёгкая проверка)"""
        try:
            if self.deepseek is None:
                return ComponentHealth(
                    name="deepseek_api",
                    status=HealthStatus.UNKNOWN,
                    message="DeepSeek client not configured"
                )
            
            # Проверяем только наличие API ключа, не делаем запрос
            if hasattr(self.deepseek, 'api_key') and self.deepseek.api_key:
                return ComponentHealth(
                    name="deepseek_api",
                    status=HealthStatus.HEALTHY,
                    message="DeepSeek API key configured"
                )
            else:
                return ComponentHealth(
                    name="deepseek_api",
                    status=HealthStatus.DEGRADED,
                    message="DeepSeek API key not configured"
                )
                
        except Exception as e:
            return ComponentHealth(
                name="deepseek_api",
                status=HealthStatus.UNHEALTHY,
                message=f"DeepSeek error: {str(e)}"
            )
    
    def check_all(self) -> Dict:
        """Полная проверка всех компонентов"""
        self.last_full_check = datetime.now()
        
        checks = {
            'database': self.check_database(),
            'bybit_api': self.check_bybit(),
            'deepseek_api': self.check_deepseek()
        }
        
        self.components_health = checks
        
        # Определяем общий статус
        statuses = [c.status for c in checks.values()]
        
        if all(s == HealthStatus.HEALTHY for s in statuses):
            overall_status = HealthStatus.HEALTHY
        elif any(s == HealthStatus.UNHEALTHY for s in statuses):
            overall_status = HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.UNKNOWN
        
        return {
            'status': overall_status.value,
            'timestamp': self.last_full_check.isoformat(),
            'components': {
                name: {
                    'status': comp.status.value,
                    'message': comp.message,
                    'response_time_ms': comp.response_time_ms,
                    'details': comp.details
                }
                for name, comp in checks.items()
            }
        }
    
    def get_health_summary(self) -> str:
        """Возвращает текстовую сводку здоровья"""
        health = self.check_all()
        
        status_emoji = {
            'healthy': '🟢',
            'degraded': '🟡',
            'unhealthy': '🔴',
            'unknown': '⚪'
        }
        
        lines = [
            f"🏥 Health Check: {status_emoji.get(health['status'], '⚪')} {health['status'].upper()}",
            f"📅 Timestamp: {health['timestamp']}",
            ""
        ]
        
        for name, comp in health['components'].items():
            emoji = status_emoji.get(comp['status'], '⚪')
            lines.append(f"  {emoji} {name}: {comp['message']}")
            if comp['response_time_ms'] > 0:
                lines.append(f"     ⏱️ Response: {comp['response_time_ms']:.1f}ms")
        
        return "\n".join(lines)


class TradingMetrics:
    """Метрики торговли"""
    
    def __init__(self, db=None):
        self.db = db
        self.start_time = datetime.now()
        
        # Счётчики
        self.signals_received = 0
        self.trades_executed = 0
        self.errors_count = 0
        self.api_calls = 0
        
    def increment_signals(self):
        """Увеличивает счётчик полученных сигналов"""
        self.signals_received += 1
    
    def increment_trades(self):
        """Увеличивает счётчик выполненных сделок"""
        self.trades_executed += 1
    
    def increment_errors(self):
        """Увеличивает счётчик ошибок"""
        self.errors_count += 1
    
    def increment_api_calls(self):
        """Увеличивает счётчик API вызовов"""
        self.api_calls += 1
    
    def get_trading_stats(self, days: int = 7) -> Dict:
        """Получает статистику торговли из БД"""
        if not self.db:
            return {}
        
        try:
            return self.db.get_virtual_trade_stats(days)
        except Exception as e:
            logger.error(f"Error getting trading stats: {e}")
            return {}
    
    def get_metrics(self) -> Dict:
        """Возвращает все метрики"""
        uptime = datetime.now() - self.start_time
        trading_stats = self.get_trading_stats(7)
        
        return {
            'uptime_seconds': uptime.total_seconds(),
            'uptime_human': str(uptime).split('.')[0],
            'counters': {
                'signals_received': self.signals_received,
                'trades_executed': self.trades_executed,
                'errors_count': self.errors_count,
                'api_calls': self.api_calls
            },
            'trading_stats_7d': trading_stats,
            'rates': {
                'signals_per_hour': self.signals_received / (uptime.total_seconds() / 3600) if uptime.total_seconds() > 0 else 0,
                'trades_per_hour': self.trades_executed / (uptime.total_seconds() / 3600) if uptime.total_seconds() > 0 else 0,
                'error_rate_percent': (self.errors_count / max(self.signals_received, 1)) * 100
            }
        }
    
    def get_metrics_summary(self) -> str:
        """Возвращает текстовую сводку метрик"""
        metrics = self.get_metrics()
        
        lines = [
            "📊 Trading Metrics",
            f"⏱️ Uptime: {metrics['uptime_human']}",
            "",
            "📈 Counters:",
            f"  • Signals received: {metrics['counters']['signals_received']}",
            f"  • Trades executed: {metrics['counters']['trades_executed']}",
            f"  • Errors: {metrics['counters']['errors_count']}",
            f"  • API calls: {metrics['counters']['api_calls']}",
            "",
            "📉 Rates:",
            f"  • Signals/hour: {metrics['rates']['signals_per_hour']:.2f}",
            f"  • Trades/hour: {metrics['rates']['trades_per_hour']:.2f}",
            f"  • Error rate: {metrics['rates']['error_rate_percent']:.2f}%",
        ]
        
        if metrics.get('trading_stats_7d'):
            stats = metrics['trading_stats_7d']
            lines.extend([
                "",
                "💰 Trading Stats (7 days):",
                f"  • Total trades: {stats.get('total_trades', 0)}",
                f"  • Winning: {stats.get('winning_trades', 0)}",
                f"  • Losing: {stats.get('losing_trades', 0)}",
                f"  • Total PnL: {stats.get('total_realized_pnl', 0):.2f} USDT"
            ])
        
        return "\n".join(lines)


class BotMonitor:
    """Главный класс мониторинга бота"""
    
    def __init__(self, db=None, bybit=None, deepseek=None):
        self.health_checker = HealthChecker(db, bybit, deepseek)
        self.metrics = TradingMetrics(db)
        self.alerts: List[Dict] = []
        self.max_alerts = 100
    
    def add_alert(self, level: str, message: str, component: str = "system"):
        """Добавляет алерт"""
        alert = {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'component': component,
            'message': message
        }
        self.alerts.append(alert)
        
        # Ограничиваем количество алертов
        if len(self.alerts) > self.max_alerts:
            self.alerts = self.alerts[-self.max_alerts:]
        
        # Логируем
        if level == 'critical':
            logger.critical(f"[{component}] {message}")
        elif level == 'error':
            logger.error(f"[{component}] {message}")
        elif level == 'warning':
            logger.warning(f"[{component}] {message}")
        else:
            logger.info(f"[{component}] {message}")
    
    def get_recent_alerts(self, count: int = 10) -> List[Dict]:
        """Возвращает последние алерты"""
        return self.alerts[-count:]
    
    def get_full_status(self) -> Dict:
        """Возвращает полный статус бота"""
        return {
            'health': self.health_checker.check_all(),
            'metrics': self.metrics.get_metrics(),
            'recent_alerts': self.get_recent_alerts(5)
        }
    
    def get_status_summary(self) -> str:
        """Возвращает текстовую сводку статуса"""
        lines = [
            "=" * 50,
            "🤖 TRADING BOT STATUS",
            "=" * 50,
            "",
            self.health_checker.get_health_summary(),
            "",
            "-" * 50,
            "",
            self.metrics.get_metrics_summary(),
        ]
        
        recent_alerts = self.get_recent_alerts(3)
        if recent_alerts:
            lines.extend([
                "",
                "-" * 50,
                "",
                "🚨 Recent Alerts:"
            ])
            for alert in recent_alerts:
                lines.append(f"  [{alert['level'].upper()}] {alert['message']}")
        
        lines.append("")
        lines.append("=" * 50)
        
        return "\n".join(lines)


