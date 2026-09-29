"""Tipos trocados entre executor e handlers das etapas."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from contabilidade_mensal.core.models import Competencia, EtapaExecucao, Execucao, Fundo

from .parametros import Parametros


@dataclass
class ArtefatoNovo:
    """Arquivo produzido por uma etapa. O executor calcula sha256/tamanho a partir de `caminho`."""

    tipo: str
    caminho: Path
    drive_file_id: str = ""
    drive_checksum: str = ""
    verificado_em: dt.datetime | None = None


@dataclass
class ResultadoEtapa:
    artefatos: list[ArtefatoNovo] = field(default_factory=list)
    dados: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextoEtapa:
    etapa_exec: EtapaExecucao
    fundo: Fundo
    competencia: Competencia
    execucao: Execucao
    agora: dt.datetime
    payload: dict[str, Any]  # estado da etapa entre tentativas/pollings; o executor o persiste
    parametros: Parametros


Handler = Callable[[ContextoEtapa], ResultadoEtapa | None]
