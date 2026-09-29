"""Homologação: Postgres dedicado; publicação no Drive vai para a pasta HOMOLOG."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import DATABASES, SECRET_KEY

if "postgresql" not in DATABASES["default"]["ENGINE"]:
    raise ImproperlyConfigured("homologação exige DB_ENGINE=postgres")
if SECRET_KEY.startswith("inseguro"):
    raise ImproperlyConfigured("defina DJANGO_SECRET_KEY em homologação")
