"""Produção.

Recusa subir com backend "fake" (o pipeline "teria sucesso" com dados falsos) ou
com dry-run ligado nas operações que alteram dados sem decisão explícita.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import BRITECH_BACKENDS, DATABASES, DRIVE_BACKEND, EXCEL_BACKEND, SECRET_KEY, env_bool

if "postgresql" not in DATABASES["default"]["ENGINE"]:
    raise ImproperlyConfigured("produção exige DB_ENGINE=postgres")
if SECRET_KEY.startswith("inseguro"):
    raise ImproperlyConfigured("defina DJANGO_SECRET_KEY em produção")
if "fake" in BRITECH_BACKENDS.values() and not env_bool("PERMITIR_BACKEND_FAKE_EM_PRODUCAO"):
    raise ImproperlyConfigured(
        "backend 'fake' configurado em produção: defina BRITECH_BACKEND_<OPERACAO>=api|browser"
    )
if os.environ.get("PERMITIR_STUBS_EXCEL_DRIVE", "").lower() in ("1", "true", "yes", "sim"):
    raise ImproperlyConfigured("PERMITIR_STUBS_EXCEL_DRIVE não é aceito em produção")
if EXCEL_BACKEND != "com" or DRIVE_BACKEND != "api":
    raise ImproperlyConfigured("produção exige EXCEL_BACKEND=com e DRIVE_BACKEND=api (stubs só em homologação)")
