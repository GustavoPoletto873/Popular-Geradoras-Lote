"""Utilitários compartilhados pelas transformações."""

from __future__ import annotations

import pandas as pd

# strftime('%b') sai em inglês (locale C); o Excel do Simplifica usa abreviações em português.
MESES_EN_PT = {
    "jan": "jan",
    "feb": "fev",
    "mar": "mar",
    "apr": "abr",
    "may": "mai",
    "jun": "jun",
    "jul": "jul",
    "aug": "ago",
    "sep": "set",
    "oct": "out",
    "nov": "nov",
    "dec": "dez",
}


def substituir_mes(datas: pd.Series) -> pd.Series:
    """Série datetime -> 'dd-mmm-aaaa' com mês em português (ex.: 2025-02-01 -> '01-fev-2025')."""
    texto = datas.dt.strftime("%d-%b-%Y").str.lower()
    for en, pt in MESES_EN_PT.items():
        texto = texto.str.replace(en, pt)
    return texto


def eh_texto(serie: pd.Series) -> bool:
    """True para coluna de texto em pandas 2 (object) e em pandas 3 (dtype `str`).

    O código original testava `dtype == 'object'`, que em pandas 3 deixa de ser verdade para
    texto e mudaria o resultado silenciosamente.
    """
    return pd.api.types.is_object_dtype(serie) or pd.api.types.is_string_dtype(serie)
