import requests
import json
import re
from config import Config
from database import Database
import logging
from typing import Dict, Any
import time


class DeepSeekClient:
    def __init__(self, db: Database | None = None):
        self.db = db or Database()
        self.logger = logging.getLogger(__name__)
        self.base_url = "https://api.deepseek.com/chat/completions"
        self._load_settings()
        self.request_timeout = 300  # 5 минут для сложных анализов

    def _load_settings(self):
        """Загрузка настроек из базы данных"""
        try:
            self.api_key = Config.DEEPSEEK_API_KEY
            self.model = self.db.get_setting(
                'deepseek_model', 'deepseek-reasoner')
            self.max_tokens = int(self.db.get_setting(
                'deepseek_max_tokens', '5000'))
            self.temperature = float(
                self.db.get_setting('deepseek_temperature', '1.0'))
            self.enable_reasoning = self.db.get_setting(
                'enable_deepseek_reasoning', 'true').lower() == 'true'

            self.logger.info("✅ Настройки DeepSeek загружены из БД")
        except Exception as e:
            self.logger.error(f"❌ Ошибка загрузки настроек DeepSeek: {e}")
            # Значения по умолчанию
            self.api_key = ''
            self.model = 'deepseek-reasoner'
            self.max_tokens = 5000
            self.temperature = 1.0
            self.enable_reasoning = True

    def get_trading_signal(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Получаем торговый сигнал от DeepSeek на основе рыночных данных"""

        # Обновляем настройки перед каждым запросом
        self._load_settings()

        # Проверяем наличие API ключа
        if not self.api_key or self.api_key == "your_deepseek_api_key_here":
            self.logger.warning("⚠️ DeepSeek API ключ не настроен")
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "reason": "API ключ не настроен",
                "error": "missing_api_key"
            }

        prompt = self._build_detailed_prompt(market_data)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": self._get_system_prompt()
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"}
        }

        # Добавляем reasoning для соответствующих моделей
        if self.enable_reasoning and "reason" in self.model.lower():
            payload["reasoning"] = True

        try:
            self.logger.info(
                f"🔗 Отправляем запрос к DeepSeek API (модель: {self.model})...")
            start_time = time.time()

            response = requests.post(
                self.base_url,
                json=payload,
                headers=headers,
                timeout=self.request_timeout
            )

            response_time = time.time() - start_time
            self.logger.info(
                f"📨 Ответ получен за {response_time:.2f}с, статус: {response.status_code}")

            if response.status_code != 200:
                self.logger.error(f"❌ HTTP ошибка: {response.status_code}")
                self.logger.error(f"📄 Текст ответа: {response.text}")

                # Логируем ошибку в БД
                self._log_api_error(response.status_code,
                                    response.text, market_data.get('symbol'))

                return {
                    "action": "HOLD",
                    "confidence": 0.0,
                    "reason": f"HTTP ошибка: {response.status_code}",
                    "error": f"http_{response.status_code}"
                }

            result = response.json()
            self.logger.debug(
                f"📦 Полный ответ API: {json.dumps(result, indent=2)}")

            if 'choices' in result and len(result['choices']) > 0:
                signal_text = result['choices'][0]['message']['content']
                self.logger.info(f"📝 Ответ модели: {signal_text}")

                # Логируем успешный запрос
                self._log_successful_request(
                    market_data.get('symbol'), response_time)

                # Обрабатываем ответ
                return self._process_ai_response(signal_text, market_data)
            else:
                self.logger.error("❌ Неожиданная структура ответа API")
                return {
                    "action": "HOLD",
                    "confidence": 0.0,
                    "reason": "Неожиданная структура ответа",
                    "error": "invalid_response_structure"
                }

        except requests.exceptions.Timeout:
            self.logger.error("❌ Таймаут запроса к DeepSeek API")
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "reason": "Таймаут анализа",
                "error": "timeout"
            }
        except json.JSONDecodeError as e:
            self.logger.error(f"❌ Ошибка декодирования JSON: {e}")
            response_text = response.text if 'response' in locals() else 'Нет ответа'
            self.logger.error(f"📄 Сырой ответ: {response_text}")
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "reason": "Ошибка формата JSON",
                "error": "json_decode_error"
            }
        except Exception as e:
            self.logger.error(f"❌ Ошибка при запросе к DeepSeek: {e}")
            import traceback
            traceback.print_exc()
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "reason": "Ошибка анализа",
                "error": "request_exception"
            }

    def _get_system_prompt(self) -> str:
        """Возвращает системный промпт для AI"""
        return """Ты опытный трейдер криптовалют с 10+ летним опытом. 
Анализируй предоставленные рыночные данные и давай торговые рекомендации на основе:
1. Технического анализа (тренды, уровни поддержки/сопротивления, индикаторы)
2. Объема торгов и волатильности
3. Рыночного контекста и общего настроения
4. Управления рисками

Отвечай СТРОГО в формате JSON:
{
    "action": "BUY/SELL/HOLD",
    "confidence": число от 0.0 до 1.0,
    "reason": "краткое обоснование на русском языке",
    "timeframe": "краткосрочный/среднесрочный/долгосрочный",
    "risk_level": "низкий/средний/высокий"
}

Не добавляй никакого дополнительного текста, не используй markdown блоки кода."""

    def _build_detailed_prompt(self, market_data: Dict[str, Any]) -> str:
        """Строим детальный промпт для DeepSeek на основе рыночных данных"""
        symbol = market_data.get('symbol', 'Unknown')
        current_price = market_data.get('price', 0)
        price_change_24h = market_data.get('price_change_24h', 0)
        volume_24h = market_data.get('volume_24h', 0)

        # Исторические данные
        historical_prices = market_data.get('historical_prices', [])
        if historical_prices:
            price_1h_ago = historical_prices[-1] if len(
                historical_prices) > 0 else current_price
            price_4h_ago = historical_prices[-4] if len(
                historical_prices) > 3 else current_price
            price_24h_ago = historical_prices[-24] if len(
                historical_prices) > 23 else current_price

            change_1h = ((current_price - price_1h_ago) /
                         price_1h_ago) * 100 if price_1h_ago else 0
            change_4h = ((current_price - price_4h_ago) /
                         price_4h_ago) * 100 if price_4h_ago else 0
            change_24h = ((current_price - price_24h_ago) /
                          price_24h_ago) * 100 if price_24h_ago else 0
        else:
            change_1h = change_4h = change_24h = 0

        # Индикаторы (если доступны)
        rsi = market_data.get('rsi', 'N/A')
        macd = market_data.get('macd', 'N/A')
        trend = market_data.get('trend', 'N/A')
        support_level = market_data.get('support_level', 'N/A')
        resistance_level = market_data.get('resistance_level', 'N/A')

        prompt = f"""
Детальный анализ торговой пары: {symbol}

ТЕКУЩИЕ ДАННЫЕ:
- Текущая цена: ${current_price:.2f}
- Изменение за 24ч: {price_change_24h:.2f}%
- Объем за 24ч: {volume_24h:,.0f} USDT

ИСТОРИЧЕСКИЕ ИЗМЕНЕНИЯ:
- Изменение за 1ч: {change_1h:+.2f}%
- Изменение за 4ч: {change_4h:+.2f}% 
- Изменение за 24ч: {change_24h:+.2f}%

ТЕХНИЧЕСКИЕ ИНДИКАТОРЫ:
- RSI: {rsi}
- MACD: {macd}
- Тренд: {trend}
- Уровень поддержки: {support_level}
- Уровень сопротивления: {resistance_level}

ИСТОРИЧЕСКИЙ КОНТЕКСТ (последние 24 часа):
Цены менялись в диапазоне от ${min(historical_prices) if historical_prices else current_price:.2f} до ${max(historical_prices) if historical_prices else current_price:.2f}

ПРОСЬБА:
Проанализируй эти данные и дай торговую рекомендацию с обоснованием. Учти:
1. Силу тренда и моментум
2. Уровни поддержки и сопротивления  
3. Показатели перекупленности/перепроданности
4. Объемы и волатильность
5. Общий рыночный контекст

Ответ предоставь в указанном JSON формате.
"""

        return prompt

    def _process_ai_response(self, signal_text: str, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Обрабатывает ответ от AI"""
        try:
            # Извлекаем JSON из markdown блока кода, если он есть
            cleaned_json = self._extract_json_from_markdown(signal_text)

            # Парсим JSON
            signal_data = json.loads(cleaned_json)
            self.logger.info("✅ Успешно распарсен JSON ответ")

            # Валидация и нормализация ответа
            return self._validate_and_normalize_signal(signal_data, market_data)

        except json.JSONDecodeError as e:
            self.logger.error(f"❌ Ошибка декодирования JSON: {e}")
            self.logger.error(f"📄 Исходный текст: {signal_text}")

            # Логируем ошибку парсинга
            self._log_parsing_error(signal_text, market_data.get('symbol'))

            return {
                "action": "HOLD",
                "confidence": 0.0,
                "reason": "Ошибка формата JSON в ответе AI",
                "error": "ai_json_error",
                "raw_response": signal_text
            }
        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки ответа AI: {e}")
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "reason": f"Ошибка обработки: {str(e)}",
                "error": "processing_error",
                "raw_response": signal_text
            }

    def _extract_json_from_markdown(self, text: str) -> str:
        """Извлекает JSON из markdown блока кода"""
        text = text.strip()

        # Если текст уже чистый JSON, возвращаем как есть
        if text.startswith('{') and text.endswith('}'):
            return text

        # Пытаемся найти JSON в markdown блоке кода
        json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        match = re.search(json_pattern, text, re.DOTALL)

        if match:
            self.logger.info("🔍 Найден JSON в markdown блоке, извлекаем...")
            return match.group(1)
        else:
            # Если не нашли в блоке кода, пытаемся найти любой JSON в тексте
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                self.logger.info("🔍 Найден JSON в тексте, извлекаем...")
                return json_match.group(0)
            else:
                self.logger.error("❌ Не удалось найти JSON в ответе")
                raise json.JSONDecodeError("No JSON found", text, 0)

    def _validate_and_normalize_signal(self, signal_data: Dict[str, Any], market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Валидирует и нормализует сигнал от AI"""
        # Обязательные поля
        action = signal_data.get('action', 'HOLD').upper()
        confidence = float(signal_data.get('confidence', 0.0))
        reason = signal_data.get('reason', 'Нет обоснования')

        # Нормализуем действие
        if action not in ['BUY', 'SELL', 'HOLD']:
            self.logger.warning(
                f"⚠️ Некорректное действие: {action}, заменяем на HOLD")
            action = 'HOLD'
            # Снижаем уверенность при некорректном действии
            confidence = min(confidence, 0.3)

        # Ограничиваем уверенность в диапазоне 0-1
        confidence = max(0.0, min(1.0, confidence))

        # Дополнительные поля
        timeframe = signal_data.get('timeframe', 'не указан')
        risk_level = signal_data.get('risk_level', 'не указан')

        # Логируем успешный сигнал
        self._log_successful_signal(
            action, confidence, market_data.get('symbol'))

        return {
            "action": action,
            "confidence": confidence,
            "reason": reason,
            "timeframe": timeframe,
            "risk_level": risk_level,
            "symbol": market_data.get('symbol'),
            "timestamp": time.time(),
            "error": None
        }

    def _log_api_error(self, status_code: int, response_text: str, symbol: str | None):
        """Логирует ошибки API в БД"""
        try:
            self.db.log_trade_event(
                level='ERROR',
                message=f"DeepSeek API error: {status_code}",
                symbol=symbol,
                trade_action='API_ERROR',
                error_details=response_text[:500]
            )
        except Exception as e:
            self.logger.error(f"❌ Ошибка логирования API error: {e}")

    def _log_successful_request(self, symbol: str | None, response_time: float):
        """Логирует успешный запрос к API"""
        try:
            self.db.log_trade_event(
                level='INFO',
                message=f"DeepSeek request successful, time: {response_time:.2f}s",
                symbol=symbol,
                trade_action='API_REQUEST',
                response_time=response_time
            )
        except Exception as e:
            self.logger.error(f"❌ Ошибка логирования успешного запроса: {e}")

    def _log_parsing_error(self, raw_response: str, symbol: str | None):
        """Логирует ошибки парсинга"""
        try:
            self.db.log_trade_event(
                level='ERROR',
                message="DeepSeek response parsing error",
                symbol=symbol,
                trade_action='PARSING_ERROR',
                error_details=raw_response[:500]
            )

        except Exception as e:
            self.logger.error(f"❌ Ошибка логирования parsing error: {e}")

    def _log_successful_signal(self, action: str, confidence: float, symbol: str | None):
        """Логирует успешно полученный сигнал"""
        try:
            self.db.log_trade_event(
                level='INFO',
                message=f"DeepSeek signal: {action} (confidence: {confidence:.2f})",
                symbol=symbol,
                trade_action=f'SIGNAL_{action}',
                confidence=confidence
            )
        except Exception as e:
            self.logger.error(f"❌ Ошибка логирования сигнала: {e}")

    def update_settings(self, settings: Dict[str, str]):
        """Обновляет настройки DeepSeek"""
        try:
            for key, value in settings.items():
                if key.startswith('deepseek_'):
                    self.db.set_setting(key, value)

            # Перезагружаем настройки
            self._load_settings()
            self.logger.info("✅ Настройки DeepSeek обновлены")

        except Exception as e:
            self.logger.error(f"❌ Ошибка обновления настроек DeepSeek: {e}")

    def get_current_settings(self) -> Dict[str, Any]:
        """Возвращает текущие настройки"""
        return {
            'model': self.model,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
            'enable_reasoning': self.enable_reasoning,
            'api_key_configured': bool(self.api_key and self.api_key != "your_deepseek_api_key_here")
        }
