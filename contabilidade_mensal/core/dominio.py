"""Regras puras de domínio (sem banco): nomes de pasta e exercício.

A regra do exercício foi inferida das pastas reais do Shared Drive (ACELERA CASH,
FII LAZIO II, FII KRONOS, ALPHA FIDC): a pasta `Data Base <mês> <ano>` agrupa as
competências do exercício que TERMINA naquele mês.
"""

from __future__ import annotations

MESES_PT = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


def ano_do_exercicio(exercicio_mes: int, ano: int, mes: int) -> int:
    """Ano em que termina o exercício que contém a competência (ano, mes)."""
    if not 1 <= exercicio_mes <= 12:
        raise ValueError(f"exercicio_mes inválido: {exercicio_mes}")
    return ano if mes <= exercicio_mes else ano + 1


def nome_pasta_exercicio(exercicio_mes: int, ano: int, mes: int) -> str:
    return f"Data Base {MESES_PT[exercicio_mes]} {ano_do_exercicio(exercicio_mes, ano, mes)}"


def nome_pasta_competencia(ano: int, mes: int) -> str:
    return f"{ano:04d}{mes:02d}"


def caminho_relativo_competencia(tipo: str, nome_fundo: str, exercicio_mes: int, ano: int, mes: int) -> tuple[str, ...]:
    """Partes do caminho `<Tipo>/<Fundo>/Data Base <mês> <ano>/<AAAAMM>`."""
    return (tipo, nome_fundo, nome_pasta_exercicio(exercicio_mes, ano, mes), nome_pasta_competencia(ano, mes))
