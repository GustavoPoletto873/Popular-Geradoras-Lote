"""Logging estruturado (JSON) com contexto propagado por `contextvars`.

Uso:
    with contexto(execucao_id=7, fundo="FII X", etapa="baixar_insumos"):
        logger.info("iniciando")     # a linha JSON já sai com esses campos
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_contexto: ContextVar[dict[str, Any]] = ContextVar("cm_log_contexto", default={})

CHAVES_SENSIVEIS = ("senha", "password", "token", "secret", "authorization", "cookie")

_CAMPOS_PADRAO_DO_LOGRECORD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


@contextmanager
def contexto(**campos: Any) -> Iterator[None]:
    """Acrescenta campos ao contexto de log dentro do bloco (campos None são ignorados)."""
    atual = dict(_contexto.get())
    atual.update({chave: valor for chave, valor in campos.items() if valor is not None})
    token = _contexto.set(atual)
    try:
        yield
    finally:
        _contexto.reset(token)


def contexto_atual() -> dict[str, Any]:
    return dict(_contexto.get())


def _mascarar(campos: dict[str, Any]) -> dict[str, Any]:
    return {
        chave: ("***" if any(s in chave.lower() for s in CHAVES_SENSIVEIS) else valor)
        for chave, valor in campos.items()
    }


class JsonFormatter(logging.Formatter):
    """Uma linha JSON por registro: campos fixos + contexto + `extra=` (valores sensíveis mascarados)."""

    def format(self, record: logging.LogRecord) -> str:
        carga: dict[str, Any] = {
            "ts": dt.datetime.fromtimestamp(record.created, dt.timezone.utc).isoformat(timespec="milliseconds"),
            "nivel": record.levelname,
            "logger": record.name,
            "mensagem": record.getMessage(),
        }
        carga.update(contexto_atual())
        carga.update({k: v for k, v in record.__dict__.items() if k not in _CAMPOS_PADRAO_DO_LOGRECORD})
        if record.exc_info:
            carga["excecao"] = self.formatException(record.exc_info)
        # ensure_ascii=True: seguro em qualquer console/arquivo (o console do Windows é cp1252)
        return json.dumps(_mascarar(carga), ensure_ascii=True, default=str)
