import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


def pytest_addoption(parser):
    parser.addoption(
        "--run-browser",
        action="store_true",
        default=False,
        help="executa os testes marcados com @pytest.mark.browser (abrem o navegador)",
    )
    parser.addoption(
        "--run-excel",
        action="store_true",
        default=False,
        help="executa os testes marcados com @pytest.mark.excel (abrem o Excel real via COM)",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-excel"):
        pular_excel = pytest.mark.skip(reason="teste com Excel real: use --run-excel")
        for item in items:
            if item.get_closest_marker("excel"):
                item.add_marker(pular_excel)
    if not config.getoption("--run-browser"):
        pular = pytest.mark.skip(reason="teste de navegador: use --run-browser")
        for item in items:
            if item.get_closest_marker("browser"):
                item.add_marker(pular)

    from django.conf import settings

    if "postgresql" not in settings.DATABASES["default"]["ENGINE"]:
        pular_pg = pytest.mark.skip(reason="exige Postgres: rode com DB_ENGINE=postgres")
        for item in items:
            if item.get_closest_marker("postgres"):
                item.add_marker(pular_pg)
