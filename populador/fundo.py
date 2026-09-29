"""
Biblioteca: popular UM fundo, sem Painel.

É o miolo que `runner.processar_fundo` (CLI/Painel) e o adapter do pipeline
(`contabilidade_mensal.integrations.excel`) compartilham: copia o arquivo do período
anterior, limpa as abas de dados, popula a partir dos insumos e salva.

Não lê nem escreve a aba Painel e não decide se a saída "já existe" — quem chama decide.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from . import config, populate
from .copiar import copiar_arquivo_origem
from .excel_app import ExcelSession

logger = logging.getLogger(__name__)


@dataclass
class ResultadoPopulacao:
    status: str  # um dos config.STATUS_* (o mesmo texto que o VBA/Painel usa)
    caminho: Path | None = None  # arquivo gerado (só quando status == STATUS_SALVO)
    avisos: list[str] = field(default_factory=list)
    erro: str | None = None

    @property
    def sucesso(self) -> bool:
        return self.status == config.STATUS_SALVO


def popular_arquivo(
    session: ExcelSession,
    *,
    fundo: str,
    periodo_destino: str,
    pasta_origem: Path,
    pasta_insumos: Path,
    pasta_saida: Path,
    resolver_ambiguidade: "populate.ResolverAmbiguidade | None" = None,
) -> ResultadoPopulacao:
    copia = copiar_arquivo_origem(session, pasta_origem, fundo, pasta_saida, periodo_destino)
    if not copia.sucesso:
        return ResultadoPopulacao(status=config.STATUS_NAO_PROCESSADO, erro=copia.mensagem)

    if not pasta_insumos.exists():
        return ResultadoPopulacao(status=config.STATUS_PASTA_NAO_ENCONTRADA)

    wb_destino = None
    try:
        wb_destino = session.open_workbook(copia.caminho_arquivo, read_only=False)
        avisos = populate.executar_batch_steps(
            session, wb_destino, pasta_insumos, resolver_ambiguidade=resolver_ambiguidade
        )
        try:
            wb_destino.Sheets(config.ABA_MAPA_CONTABIL).Activate()
        except Exception:
            logger.warning(
                "Aba %r não encontrada em %s para ativar (não impede o salvamento).",
                config.ABA_MAPA_CONTABIL,
                copia.caminho_arquivo,
            )
        wb_destino.Close(SaveChanges=True)
        wb_destino = None
        return ResultadoPopulacao(status=config.STATUS_SALVO, caminho=copia.caminho_arquivo, avisos=avisos)
    except Exception as exc:
        logger.exception("Erro populando fundo %s", fundo)
        if wb_destino is not None:
            try:
                wb_destino.Close(SaveChanges=False)
            except Exception:
                logger.warning("Falha ao fechar workbook de destino após erro.", exc_info=True)
        return ResultadoPopulacao(status=config.STATUS_ERRO, erro=str(exc))
