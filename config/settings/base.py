"""Configuração base. Ambientes específicos (dev/homolog/prod/test) importam daqui.

Nada aqui lê segredos de arquivo: tudo vem de variáveis de ambiente (ver .env.example).
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(nome: str, padrao: str | None = None) -> str | None:
    return os.environ.get(nome, padrao)


def env_bool(nome: str, padrao: bool = False) -> bool:
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in {"1", "true", "yes", "sim", "on"}


def env_lista(nome: str, padrao: tuple[str, ...] = ()) -> tuple[str, ...]:
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return tuple(item.strip() for item in valor.split(",") if item.strip())


SECRET_KEY = env("DJANGO_SECRET_KEY") or "inseguro-apenas-para-desenvolvimento-local"
DEBUG = False
ALLOWED_HOSTS = list(env_lista("DJANGO_ALLOWED_HOSTS", ("localhost", "127.0.0.1")))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "contabilidade_mensal.core",
    "contabilidade_mensal.pipeline",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

# --- Banco ------------------------------------------------------------------
# sqlite (padrão em dev/teste) ou postgres. A fila do pipeline é a própria tabela
# EtapaExecucao; em Postgres ela usa as mesmas operações compare-and-set do SQLite.
VAR_DIR = Path(env("CM_VAR_DIR") or BASE_DIR / "var")


def _banco() -> dict:
    if (env("DB_ENGINE") or "sqlite").lower() in {"postgres", "postgresql"}:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", "contabilidade_mensal"),
            "USER": env("DB_USER", ""),
            "PASSWORD": env("DB_PASSWORD", ""),
            "HOST": env("DB_HOST", "localhost"),
            "PORT": env("DB_PORT", "5432"),
        }
    VAR_DIR.mkdir(parents=True, exist_ok=True)
    return {"ENGINE": "django.db.backends.sqlite3", "NAME": VAR_DIR / "db.sqlite3"}


DATABASES = {"default": _banco()}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"

# --- Feature flags por operação (troca de backend sem deploy de código) -------
OPERACOES_BRITECH = (
    "baixar_insumo",
    "processar_contabil",
    "status_processamento",
    "baixar_balancete",
)
BRITECH_BACKENDS = {
    op: (env(f"BRITECH_BACKEND_{op.upper()}") or "fake") for op in OPERACOES_BRITECH
}

# Operações que ALTERAM algo fora do nosso sistema. Ficam em dry-run por padrão e
# o "Processar" só é clicado de verdade para carteiras da allowlist.
OPERACOES_QUE_ALTERAM = ("processar_contabil", "publicar_drive")
DRY_RUN_PROCESSAR_CONTABIL = env_bool("DRY_RUN_PROCESSAR_CONTABIL", True)
DRY_RUN_PUBLICAR_DRIVE = env_bool("DRY_RUN_PUBLICAR_DRIVE", True)
ALLOWLIST_PROCESSAR_CONTABIL = env_lista("ALLOWLIST_PROCESSAR_CONTABIL")

STORAGE_ROOT = Path(env("STORAGE_ROOT") or VAR_DIR / "staging")

# --- Navegador (Playwright). Evidências (screenshot/trace) são dados SENSÍVEIS: pasta restrita, retenção curta. ---
BROWSER = {
    "headless": env_bool("BROWSER_HEADLESS", True),
    "timeout_ms": int(env("BROWSER_TIMEOUT_MS") or 30_000),
    "pasta_evidencias": Path(env("BROWSER_EVIDENCIAS") or VAR_DIR / "evidencias"),
}

# --- Monday (cadastro mestre de fundos) --------------------------------------------------------------
# IDs de board/grupo/coluna não são segredos; o token (MONDAY_API_TOKEN) só é lido do ambiente, na hora do uso.
MONDAY = {
    "board_id": env("MONDAY_BOARD_ID") or "6799176339",
    "grupos": {  # id do grupo -> tipo do fundo
        "novo_grupo72711": "FIF",
        "novo_grupo": "FIDC",
        "new_group": "FII",
        "novo_grupo68489": "FIP",
    },
    "colunas": {
        "cnpj": "texto",
        "administrador": "status8__1",
        "carteira": "texto3",
        "exercicio": "exerc_cio_social__1",
        "sistema": "dup__of_administrador_mkkz14qe",
    },
}

# --- Parâmetros do pipeline (ver contabilidade_mensal/pipeline/parametros.py) ---
PIPELINE: dict = {}

# --- Logging estruturado (JSON) ---------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "contabilidade_mensal.observability.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "loggers": {
        "contabilidade_mensal": {
            "handlers": ["console"],
            "level": env("CM_LOG_LEVEL") or "INFO",
            "propagate": False,
        },
    },
}
