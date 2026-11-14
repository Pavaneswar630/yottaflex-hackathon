import pytest

from src.config import Scale
from src.generator import generate


@pytest.fixture(scope="module")
def small_data():
    return generate(20261022, Scale(skus=12, machines=8, orders=40, materials=24, horizon_days=90))
