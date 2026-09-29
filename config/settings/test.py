"""Testes: SQLite em memória por padrão; DB_ENGINE=postgres liga os testes marcados `postgres`."""

from .base import *  # noqa: F401,F403
from .base import DATABASES

if "postgresql" not in DATABASES["default"]["ENGINE"]:
    DATABASES["default"] = {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
BRITECH_BACKENDS = {  # testes nunca falam com a Britech
    "baixar_insumo": "fake",
    "processar_contabil": "fake",
    "status_processamento": "fake",
    "baixar_balancete": "fake",
}
LOGGING["loggers"]["contabilidade_mensal"]["level"] = "WARNING"  # noqa: F405
