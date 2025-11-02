import pytest
import os
from dotenv import load_dotenv

load_dotenv()


def test_pybit_import():
    """Тест импорта pybit"""
    try:
        from pybit.unified_trading import HTTP
        assert True
    except ImportError as e:
        pytest.fail(f"Failed to import pybit: {e}")


def test_bybit_client_initialization():
    """Тест инициализации клиента Bybit"""
    from bybit_client import BybitClient

    # Это не должен вызывать ошибку, даже без API ключей
    client = BybitClient()
    assert client is not None
    assert hasattr(client, 'session')


def test_config_loading():
    """Тест загрузки конфигурации"""
    from config import Config

    # Проверяем, что конфиг загружается
    assert hasattr(Config, 'BYBIT_TESTNET')
    assert Config.BYBIT_TESTNET in [True, False]
