"""Contrato da camada Britech: DTOs puros (sem Django) e o protocolo dos backends.

A implementação por API, por navegador ou fake é detalhe; o pipeline só enxerga
`BritechGateway` (ver factory.py).
"""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable

from contabilidade_mensal.core.choices import TipoArtefato


@dataclass(frozen=True)
class AdministradoraRef:
    nome: str
    url_adm: str
    segredo_ref: str = ""


@dataclass(frozen=True)
class CarteiraRef:
    codigo_britech: str
    cnpj: str
    nome: str = ""
    exercicio_mes: int | None = None  # mês de encerramento do exercício (1-12); define as datas "inicial"


@dataclass(frozen=True)
class CompetenciaRef:
    ano: int
    mes: int

    @property
    def aaaamm(self) -> str:
        return f"{self.ano:04d}{self.mes:02d}"

    @property
    def data_base(self) -> dt.date:
        return dt.date(self.ano, self.mes, calendar.monthrange(self.ano, self.mes)[1])


class TipoInsumo(str, Enum):
    """Valor = sufixo canônico usado no nome do arquivo (igual ao do downloader do Simplifica)."""

    CARTEIRA_FINAL = "CarteiraFinal"
    CARTEIRA_INICIAL = "CarteiraInicial"
    EXTRATO_CC = "ExtratoCC"
    MOV_COTISTA = "MovCotista"
    POSICAO_COTISTA_FINAL = "SaldoAplicacaoCotistaFinal"
    POSICAO_COTISTA_INICIAL = "SaldoAplicacaoCotistaInicial"
    HISTORICO_COTA = "Histórico de Cota"


TIPO_ARTEFATO_DO_INSUMO: dict[TipoInsumo, TipoArtefato] = {
    TipoInsumo.CARTEIRA_FINAL: TipoArtefato.INSUMO_CARTEIRA_FINAL,
    TipoInsumo.CARTEIRA_INICIAL: TipoArtefato.INSUMO_CARTEIRA_INICIAL,
    TipoInsumo.EXTRATO_CC: TipoArtefato.INSUMO_EXTRATO_CC,
    TipoInsumo.MOV_COTISTA: TipoArtefato.INSUMO_MOV_COTISTA,
    TipoInsumo.POSICAO_COTISTA_FINAL: TipoArtefato.INSUMO_POSICAO_COTISTA_FINAL,
    TipoInsumo.POSICAO_COTISTA_INICIAL: TipoArtefato.INSUMO_POSICAO_COTISTA_INICIAL,
    TipoInsumo.HISTORICO_COTA: TipoArtefato.INSUMO_HISTORICO_COTA,
}

INSUMOS_DO_LOTE: tuple[TipoInsumo, ...] = (
    TipoInsumo.CARTEIRA_FINAL,
    TipoInsumo.CARTEIRA_INICIAL,
    TipoInsumo.EXTRATO_CC,
    TipoInsumo.MOV_COTISTA,
    TipoInsumo.POSICAO_COTISTA_FINAL,
    TipoInsumo.POSICAO_COTISTA_INICIAL,
    TipoInsumo.HISTORICO_COTA,
)


class StatusProcessamento(str, Enum):
    NAO_INICIADO = "nao_iniciado"
    EM_ANDAMENTO = "em_andamento"
    CONCLUIDO = "concluido"
    ERRO = "erro"


@dataclass(frozen=True)
class ArquivoBaixado:
    tipo: TipoArtefato
    caminho: Path
    complementos: tuple["ArquivoBaixado", ...] = ()  # ex.: PDFs de evidência que acompanham o Excel


@dataclass(frozen=True)
class ResultadoDisparo:
    carteiras: tuple[str, ...]
    dry_run: bool  # True = foi só até a seleção; o "Processar" NÃO foi clicado


@dataclass(frozen=True)
class BalanceteBaixado:
    pdf: Path
    xls: Path


@runtime_checkable
class SessaoBritech(Protocol):
    def fechar(self) -> None: ...


class BritechBackend(Protocol):
    """O que cada backend concreto (fake, api, browser) implementa. Pode lançar
    `OperacaoNaoSuportada` nas operações que não cobre."""

    def abrir_sessao(self, administradora: AdministradoraRef) -> SessaoBritech: ...

    def baixar_insumo(
        self,
        sessao: SessaoBritech,
        carteira: CarteiraRef,
        competencia: CompetenciaRef,
        tipo: TipoInsumo,
        destino: Path,
    ) -> ArquivoBaixado: ...

    def processar_contabil(
        self,
        sessao: SessaoBritech,
        carteiras: Sequence[CarteiraRef],
        competencia: CompetenciaRef,
        *,
        dry_run: bool,
    ) -> ResultadoDisparo: ...

    def status_processamento(
        self, sessao: SessaoBritech, carteira: CarteiraRef, competencia: CompetenciaRef
    ) -> StatusProcessamento: ...

    def baixar_balancete(
        self, sessao: SessaoBritech, carteira: CarteiraRef, competencia: CompetenciaRef, destino: Path
    ) -> BalanceteBaixado: ...
