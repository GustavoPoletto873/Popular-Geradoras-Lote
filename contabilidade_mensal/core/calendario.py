"""Calendário útil brasileiro e datas do exercício.

Porte fiel das regras do downloader do Simplifica (`monday_ctb_britech2.py`):
  - dia útil = segunda a sexta, exceto feriados nacionais + Carnaval (segunda e terça),
    Sexta-feira Santa e Corpus Christi;
  - "fim do exercício anterior" (`MES_EXERCICIO` no Simplifica) = último dia útil do mês de
    encerramento do exercício, no ano em que ele terminou ANTES da data de referência;
  - "início do exercício" (`DATA_INICIO_EXERCICIO`) = o maior entre o dia útil seguinte ao fim
    do exercício anterior e a data de implantação do fundo.
"""

from __future__ import annotations

import calendar
import datetime as dt
from functools import lru_cache

import holidays

MESES_POR_NOME = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


def mes_por_nome(nome: str | None) -> int | None:
    """'Novembro' -> 11 (ignora caixa e espaços); desconhecido/vazio -> None."""
    if not nome:
        return None
    return MESES_POR_NOME.get(nome.strip().lower())


def pascoa(ano: int) -> dt.date:
    """Domingo de Páscoa (mesmo algoritmo do Simplifica)."""
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(ano, mes, dia)


@lru_cache(maxsize=None)
def feriados(ano: int) -> frozenset[dt.date]:
    """Feriados que NÃO são dia útil: nacionais + Carnaval (seg/ter), Sexta Santa e Corpus Christi."""
    p = pascoa(ano)
    extras = {
        p - dt.timedelta(days=48),  # Carnaval (segunda)
        p - dt.timedelta(days=47),  # Carnaval (terça)
        p - dt.timedelta(days=2),  # Sexta-feira Santa
        p + dt.timedelta(days=60),  # Corpus Christi
    }
    return frozenset(set(holidays.Brazil(years=ano, observed=True).keys()) | extras)


def e_dia_util(dia: dt.date) -> bool:
    return dia.weekday() < 5 and dia not in feriados(dia.year)


def ultimo_dia_util(ano: int, mes: int) -> dt.date:
    dia = dt.date(ano, mes, calendar.monthrange(ano, mes)[1])
    while not e_dia_util(dia):
        dia -= dt.timedelta(days=1)
    return dia


def proximo_dia_util(dia: dt.date) -> dt.date:
    proximo = dia + dt.timedelta(days=1)
    while not e_dia_util(proximo):
        proximo += dt.timedelta(days=1)
    return proximo


def data_final_carteira(ano: int, mes: int) -> dt.date:
    """Data da carteira/posição FINAL da competência: último dia útil do mês."""
    return ultimo_dia_util(ano, mes)


def fim_exercicio_anterior(exercicio_mes: int, data_referencia: dt.date) -> dt.date:
    """Último dia útil do mês de encerramento do exercício, no ano em que ele terminou antes da referência.

    É a data da carteira/posição INICIAL. Ex.: exercício em novembro, referência 2026-08-31
    -> último dia útil de novembro/2025 (2025-11-28).
    """
    if not 1 <= exercicio_mes <= 12:
        raise ValueError(f"exercicio_mes inválido: {exercicio_mes}")
    ano_atual = data_referencia.year
    fim_do_mes = dt.date(ano_atual, exercicio_mes, calendar.monthrange(ano_atual, exercicio_mes)[1])
    ano = ano_atual - 1 if fim_do_mes >= data_referencia else ano_atual
    return ultimo_dia_util(ano, exercicio_mes)


def ano_exercicio_proximo(fim_exercicio: dt.date) -> int:
    """Ano do nome da pasta `Data Base <mês> <ano>` (ano em que o exercício em curso termina)."""
    return fim_exercicio.year + 1


def inicio_exercicio(fim_exercicio: dt.date, implantacao: dt.date | None) -> dt.date:
    """`DATA_INICIO_EXERCICIO`: começa no dia útil seguinte ao fim do anterior, ou na implantação se for depois."""
    inicio = proximo_dia_util(fim_exercicio)
    return max(inicio, implantacao) if implantacao else inicio
