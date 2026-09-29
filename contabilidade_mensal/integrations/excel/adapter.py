"""Adapter do populador Excel para o pipeline (Windows + Excel, via COM).

Monta uma pasta de trabalho por fundo/execução:
    <trabalho>/Origem/   boleta do mês anterior (vinda da `OrigemBoleta`)
    <trabalho>/Insumos/  cópia dos insumos e do balancete vigentes (nomes canônicos)
    <trabalho>/Saida/    onde o populador grava `<fundo> AAAAMM.<ext>`
e chama `populador.fundo.popular_arquivo` — a MESMA rotina que o CLI do Painel usa.

Uma instância do Excel por chamada (abre e fecha): mais lento que reaproveitar, mas sem estado que vaze entre
fundos; a concorrência é 1 por host garantida pela fila `excel`.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path

from contabilidade_mensal.core.models import Competencia, Fundo

from ..britech.erros import BritechErro
from .origem import OrigemBoleta

logger = logging.getLogger(__name__)


class ErroExcel(BritechErro):
    """O Excel/COM falhou ao popular (instância travada, arquivo bloqueado…). Vale tentar de novo."""

    codigo = "erro_excel"
    retentavel = True


class PopulacaoRecusada(BritechErro):
    """O populador não conseguiu produzir a boleta por motivo do conteúdo (ex.: não copiou o modelo)."""

    codigo = "populacao_recusada"


@dataclass
class BoletaGerada:
    caminho: Path
    avisos: list[str] = field(default_factory=list)


class PopuladorExcel:
    def __init__(
        self,
        origem: OrigemBoleta,
        *,
        visivel: bool = False,
        sessao: Callable[[], AbstractContextManager] | None = None,
        popular=None,
    ) -> None:
        self._origem = origem
        self._visivel = visivel
        self._sessao = sessao
        self._popular = popular

    def _sessao_excel(self):
        if self._sessao is not None:
            return self._sessao()
        from populador.excel_app import ExcelSession  # import tardio: só existe/serve em Windows com Excel

        return ExcelSession(visible=self._visivel)

    def popular(
        self, *, fundo: Fundo, competencia: Competencia, arquivos: Sequence[Path], pasta_trabalho: Path
    ) -> BoletaGerada:
        from populador import config as cfg_pop
        from populador.fundo import popular_arquivo

        popular_fn = self._popular or popular_arquivo
        origem_dir, insumos_dir, saida_dir = (pasta_trabalho / n for n in ("Origem", "Insumos", "Saida"))
        for pasta in (insumos_dir, saida_dir):
            if pasta.exists():
                shutil.rmtree(pasta)  # reexecução começa limpa: nunca herda arquivo de tentativa anterior
            pasta.mkdir(parents=True)
        if origem_dir.exists():
            shutil.rmtree(origem_dir)
        for arquivo in arquivos:
            shutil.copy2(arquivo, insumos_dir / Path(arquivo).name)
        self._origem.obter(fundo, competencia, origem_dir)  # BoletaAnteriorAusente sobe daqui

        with self._sessao_excel() as sessao:
            resultado = popular_fn(
                sessao,
                fundo=fundo.nome,
                periodo_destino=competencia.aaaamm,
                pasta_origem=origem_dir,
                pasta_insumos=insumos_dir,
                pasta_saida=saida_dir,
            )
        if resultado.status == cfg_pop.STATUS_SALVO:
            return BoletaGerada(resultado.caminho, list(resultado.avisos))
        if resultado.status == cfg_pop.STATUS_ERRO:
            raise ErroExcel(resultado.erro or "erro do Excel ao popular")
        raise PopulacaoRecusada(f"{resultado.status}: {resultado.erro or 'sem detalhe'}")
