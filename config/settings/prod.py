"""Produção.

Recusa subir com backend "fake" (o pipeline "teria sucesso" com dados falsos) ou
com dry-run ligado nas operações que alteram dados sem decisão explícita.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import BRITECH_BACKENDS, DATABASES, SECRET_KEY, env_bool

if "postgresql" not in DATABASES["default"]["ENGINE"]:
    raise ImproperlyConfigured("produção exige DB_ENGINE=postgres")
if SECRET_KEY.startswith("inseguro"):
    raise ImproperlyConfigured("defina DJANGO_SECRET_KEY em produção")
if "fake" in BRITECH_BACKENDS.values() and not env_bool("PERMITIR_BACKEND_FAKE_EM_PRODUCAO"):
    raise ImproperlyConfigured(
        "backend 'fake' configurado em produção: defina BRITECH_BACKEND_<OPERACAO>=api|browser"
    )
