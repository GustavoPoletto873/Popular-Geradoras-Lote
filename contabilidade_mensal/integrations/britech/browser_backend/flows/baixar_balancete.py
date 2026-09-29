"""Fluxo "Balancete": uma carteira, um período (datas vêm da competência — fim das datas fixas do projeto original)."""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

from playwright.sync_api import Page

from ...interface import BalanceteBaixado, CompetenciaRef
from ...nomes import nome_balancete_canonico
from ..pages.balancete_page import BalanceteContabilPage

logger = logging.getLogger(__name__)


def periodo_da_competencia(competencia: CompetenciaRef) -> tuple[dt.date, dt.date]:
    """Mês fechado: do dia 1º ao último dia. (Q7: falta confirmar com o contador se o balancete é do mês ou acumulado.)"""
    return dt.date(competencia.ano, competencia.mes, 1), competencia.data_base


def _br(dia: dt.date) -> str:
    return dia.strftime("%d/%m/%Y")


def baixar_balancete(
    page: Page,
    base_url: str,
    *,
    codigo_carteira: str,
    cnpj: str,
    competencia: CompetenciaRef,
    destino: Path,
    timeout_ms: int,
    timeout_download_ms: int,
) -> BalanceteBaixado:
    inicio, fim = periodo_da_competencia(competencia)
    destino.mkdir(parents=True, exist_ok=True)
    pagina = BalanceteContabilPage(page, base_url, timeout_ms=timeout_ms, timeout_download_ms=timeout_download_ms)
    pagina.abrir()
    pagina.selecionar_carteira(codigo_carteira)
    pagina.preencher_periodo(_br(inicio), _br(fim))
    pdf = pagina.baixar_pdf(destino / nome_balancete_canonico(competencia, cnpj, "pdf"))
    xls = pagina.baixar_excel(destino / nome_balancete_canonico(competencia, cnpj, "xls"))
    logger.info("balancete baixado (%s a %s)", _br(inicio), _br(fim))
    return BalanceteBaixado(pdf=pdf, xls=xls)
