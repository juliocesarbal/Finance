import pytest

from market.providers import set_provider


@pytest.fixture(autouse=True)
def _reset_market_provider():
    """Cada test parte sin proveedor inyectado y limpia el que haya dejado."""
    set_provider(None)
    yield
    set_provider(None)


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
