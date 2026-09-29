"""Cadastro de carteiras da Britech (`Fundo/BuscaListaFundos`) — porte da parte de cadastro de `monday_ctb_britech2.py`.

Cada linha do cadastro é uma carteira (classe de cotas). Várias carteiras podem compartilhar o CNPJ do fundo.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from ..erros import EstruturaInesperada

_COLUNAS = [
    "ClienteInfo.IdCliente",
    "CarteiraInfo.Nome",
    "CarteiraInfo.CPFCNPJFundo",
    "ClienteInfo.Implantacao",
]


@dataclass(frozen=True)
class ClasseDeCotas:
    id_cliente: str
    nome: str
    cnpj: str
    implantacao: dt.date | None


def normalizar_cnpj(valor) -> str:
    """'12.345.678/0001-90' -> '12345678000190' (vazio/NaN -> '')."""
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)) or valor == "":
        return ""
    return str(valor).replace(".", "").replace("/", "").replace("-", "").strip()


def _texto_id(valor) -> str:
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _data(valor) -> dt.date | None:
    data = pd.to_datetime(valor, errors="coerce")
    return None if pd.isna(data) else data.date()


def ler_cadastro(registros: list[dict]) -> list[ClasseDeCotas]:
    if not registros:
        return []  # administradora sem carteiras cadastradas: válido; quem consulta decide o que fazer
    try:
        df = pd.json_normalize(registros)[_COLUNAS]
    except KeyError as exc:
        raise EstruturaInesperada(f"cadastro da Britech sem as colunas esperadas: {exc}") from exc
    return [
        ClasseDeCotas(
            id_cliente=_texto_id(linha["ClienteInfo.IdCliente"]),
            nome=str(linha["CarteiraInfo.Nome"]),
            cnpj=normalizar_cnpj(linha["CarteiraInfo.CPFCNPJFundo"]),
            implantacao=_data(linha["ClienteInfo.Implantacao"]),
        )
        for _, linha in df.iterrows()
    ]
