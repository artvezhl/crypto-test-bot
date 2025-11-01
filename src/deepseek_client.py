import requests
import json
import re
from config import Config


class DeepSeekClient:
    def __init__(self):
        self.api_key = Config.DEEPSEEK_API_KEY
        self.base_url = "https://api.deepseek.com/chat/completions"

    def get_trading_signal(self, market_data):
        """Получаем торговый сигнал от DeepSeek на основе рыночных данных"""

        # Проверяем наличие API ключа
        if not self.api_key or self.api_key == "your_deepseek_api_key_here":
            print("⚠️ DeepSeek API ключ не настроен")
            return {"action": "HOLD", "confidence": 0.0, "reason": "API ключ не настроен"}

        prompt = self._build_prompt(market_data)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": "Ты опытный трейдер криптовалют. Анализируй предоставленные рыночные данные и давай торговые рекомендации. Отвечай ТОЛЬКО в формате JSON: {'action': 'BUY/SELL/HOLD', 'confidence': число от 0.0 до 1.0, 'reason': 'краткое обоснование'}. Не добавляй никакого дополнительного текста, не используй markdown блоки кода."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,
            "max_tokens": 500,
            # Запрашиваем чистый JSON
            "response_format": {"type": "json_object"}
        }

        try:
            print(f"🔗 Отправляем запрос к DeepSeek API...")
            response = requests.post(
                self.base_url, json=payload, headers=headers, timeout=30)

            print(f"📨 Статус ответа: {response.status_code}")

            if response.status_code != 200:
                print(f"❌ HTTP ошибка: {response.status_code}")
                print(f"📄 Текст ответа: {response.text}")
                return {"action": "HOLD", "confidence": 0.0, "reason": f"HTTP ошибка: {response.status_code}"}

            result = response.json()
            print(f"📦 Полный ответ API: {json.dumps(result, indent=2)}")

            if 'choices' in result and len(result['choices']) > 0:
                signal_text = result['choices'][0]['message']['content']
                print(f"📝 Ответ модели: {signal_text}")

                # Извлекаем JSON из markdown блока кода, если он есть
                cleaned_json = self._extract_json_from_markdown(signal_text)

                # Парсим JSON
                signal_data = json.loads(cleaned_json)
                print("✅ Успешно распарсен JSON ответ")
                return signal_data
            else:
                print("❌ Неожиданная структура ответа API")
                return {"action": "HOLD", "confidence": 0.0, "reason": "Неожиданная структура ответа"}

        except json.JSONDecodeError as e:
            print(f"❌ Ошибка декодирования JSON: {e}")
            print(
                f"📄 Сырой ответ: {response.text if 'response' in locals() else 'Нет ответа'}")
            return {"action": "HOLD", "confidence": 0.0, "reason": "Ошибка формата JSON"}
        except Exception as e:
            print(f"❌ Ошибка при запросе к DeepSeek: {e}")
            import traceback
            traceback.print_exc()
            return {"action": "HOLD", "confidence": 0.0, "reason": "Ошибка анализа"}

    def _extract_json_from_markdown(self, text):
        """Извлекает JSON из markdown блока кода"""
        # Если текст уже чистый JSON, возвращаем как есть
        text = text.strip()
        if text.startswith('{') and text.endswith('}'):
            return text

        # Пытаемся найти JSON в markdown блоке кода
        json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        match = re.search(json_pattern, text, re.DOTALL)

        if match:
            print("🔍 Найден JSON в markdown блоке, извлекаем...")
            return match.group(1)
        else:
            # Если не нашли в блоке кода, пытаемся найти любой JSON в тексте
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                print("🔍 Найден JSON в тексте, извлекаем...")
                return json_match.group(0)
            else:
                print("❌ Не удалось найти JSON в ответе")
                raise json.JSONDecodeError("No JSON found", text, 0)

    def _build_prompt(self, market_data):
        """Строим промпт для DeepSeek на основе рыночных данных"""
        return f"""
        Проанализируй следующие рыночные данные и дай торговую рекомендацию для криптовалюты:
        
        Пара: {market_data['symbol']}
        Текущая цена: {market_data['price']}
        24h изменение: {market_data['price_change_24h']}%
        24h объем: {market_data['volume_24h']}
        RSI: {market_data.get('rsi', 'N/A')}
        MACD: {market_data.get('macd', 'N/A')}
        Тренд: {market_data.get('trend', 'N/A')}
        
        Прошлые данные:
        {market_data.get('historical', '')}
        
        Дай рекомендацию в формате JSON: BUY, SELL или HOLD с уверенностью (0.0-1.0) и кратким обоснованием.
        """
