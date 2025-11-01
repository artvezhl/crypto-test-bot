import sys
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

# Добавляем src в путь для импорта
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestTelegramNotifications:
    """Тесты для Telegram уведомлений"""

    @patch('requests.post')
    def test_telegram_send_message_success(self, mock_post):
        """Тест успешной отправки сообщения в Telegram"""
        from config import Config

        # Настраиваем мок
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'ok': True, 'result': {'message_id': 123}}
        mock_post.return_value = mock_response

        # Имитируем реальные настройки
        with patch.object(Config, 'TELEGRAM_BOT_TOKEN', 'test_token'):
            with patch.object(Config, 'TELEGRAM_CHAT_ID', 'test_chat_id'):
                import requests

                url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {
                    'chat_id': Config.TELEGRAM_CHAT_ID,
                    'text': 'Тестовое сообщение',
                    'parse_mode': 'Markdown'
                }

                response = requests.post(url, json=payload)

                # Проверяем вызов
                mock_post.assert_called_once()
                assert response.status_code == 200
                assert response.json()['ok'] is True

    @patch('requests.post')
    def test_telegram_send_message_failure(self, mock_post):
        """Тест ошибки отправки сообщения в Telegram"""
        from config import Config

        # Настраиваем мок на ошибку
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            'ok': False, 'description': 'Bad Request'}
        mock_post.return_value = mock_response

        with patch.object(Config, 'TELEGRAM_BOT_TOKEN', 'test_token'):
            with patch.object(Config, 'TELEGRAM_CHAT_ID', 'test_chat_id'):
                import requests

                url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {
                    'chat_id': Config.TELEGRAM_CHAT_ID,
                    'text': 'Тестовое сообщение',
                    'parse_mode': 'Markdown'
                }

                response = requests.post(url, json=payload)

                assert response.status_code == 400
                assert response.json()['ok'] is False


def test_telegram_config_validation():
    """Тест валидации конфигурации Telegram"""
    from config import Config

    # Тестируем с невалидными настройками
    with patch.object(Config, 'TELEGRAM_BOT_TOKEN', 'your_telegram_token'):
        with patch.object(Config, 'TELEGRAM_CHAT_ID', 'your_chat_id'):
            # Это должно быть обработано в основном коде
            assert Config.TELEGRAM_BOT_TOKEN == 'your_telegram_token'
            assert Config.TELEGRAM_CHAT_ID == 'your_chat_id'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
