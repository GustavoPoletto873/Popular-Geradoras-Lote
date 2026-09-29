"""Parâmetros do pipeline, com padrões sensatos e override por `settings.PIPELINE`."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field

from django.conf import settings


def _limites_padrao() -> dict[str, int]:
    return {"autenticacao_falhou": 1, "tela_mudou": 3, "sessao_bloqueada": 2, "default": 5}


@dataclass(frozen=True)
class Parametros:
    lease_segundos: int = 300
    max_tentativas: int = 3
    backoff_base_s: float = 30.0
    backoff_teto_s: float = 900.0
    backoff_jitter: float = 0.2
    polling_intervalo_s: float = 60.0
    polling_timeout_s: float = 1800.0
    disjuntor_limites: Mapping[str, int] = field(default_factory=_limites_padrao)
    disjuntor_resfriamento_s: float = 900.0


def obter() -> Parametros:
    """Parâmetros vigentes (relidos a cada chamada, para os testes poderem alterar `settings`)."""
    overrides = dict(getattr(settings, "PIPELINE", {}) or {})
    limites = _limites_padrao()
    limites.update(overrides.pop("disjuntor_limites", {}))
    campos_validos = {f.name for f in dataclasses.fields(Parametros)}
    desconhecidos = set(overrides) - campos_validos
    if desconhecidos:
        raise ValueError(f"settings.PIPELINE com chaves desconhecidas: {sorted(desconhecidos)}")
    return Parametros(disjuntor_limites=limites, **overrides)
