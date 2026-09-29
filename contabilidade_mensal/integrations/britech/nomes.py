"""Nomes canônicos dos arquivos que o pipeline produz nos `Insumos/` do fundo/mês.

Insumos por API: mesmo padrão do downloader do Simplifica nos Insumos recentes
(ex.: `202608_46557432000107_CarteiraFinal.xlsx`) — o arquivo empilhado por CNPJ,
sem id de classe. O balancete usa `BalanceteContabilFinal` (proposta desta migração,
coerente com CarteiraFinal/SaldoAplicacaoCotistaFinal) em vez do nome sugerido pela
Britech, que varia (`BalanceteContabil_<id>_<cnpj>_.xls`, com sufixo "(3)" em repetições).
"""

from __future__ import annotations

from .interface import CompetenciaRef, TipoInsumo


def nome_insumo_canonico(tipo: TipoInsumo, competencia: CompetenciaRef, cnpj: str) -> str:
    return f"{competencia.aaaamm}_{cnpj}_{tipo.value}.xlsx"


def nome_balancete_canonico(competencia: CompetenciaRef, cnpj: str, extensao: str) -> str:
    return f"{competencia.aaaamm}_{cnpj}_BalanceteContabilFinal.{extensao.lstrip('.')}"
