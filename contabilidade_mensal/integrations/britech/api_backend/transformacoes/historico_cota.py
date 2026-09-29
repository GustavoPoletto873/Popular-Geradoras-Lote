"""Histórico de cota (`Fundo/BuscaHistoricoCotaRentabilidade`, JSON). Porte de `histórico_cota_ctb_britech.py`."""

from __future__ import annotations

import pandas as pd

from ...erros import EstruturaInesperada
from .comum import substituir_mes

COLUNAS_SAIDA = [
    "data", "Entrada", "Saida", "PLFechamento", "QtdCotas", "CotaFechamento", "Dia", "Mes", "Ano", "DozeMeses", "Carteira",
]  # fmt: skip
COLUNAS_NUMERICAS = ["PLFechamento", "QtdCotas", "CotaFechamento", "Dia", "Mes", "Ano", "DozeMeses"]


def _sem_movimentacao(id_carteira, nome_classe, status: str) -> pd.DataFrame:
    return pd.DataFrame({"Carteira": [f"{id_carteira} - {nome_classe}"], "Status": [status]})


def transformar_historico_cota(registros: list[dict], *, id_carteira, nome_classe: str) -> pd.DataFrame:
    try:
        df = pd.DataFrame(registros)
        if df.empty:
            return _sem_movimentacao(id_carteira, nome_classe, "Sem movimentação")

        try:
            df["data"] = pd.to_datetime(df["data"])
        except Exception:  # noqa: BLE001
            return _sem_movimentacao(id_carteira, nome_classe, "Sem movimentação - Erro na conversão de data")

        df["Carteira"] = id_carteira
        df["Carteira"] = df["Carteira"].astype(str) + " - " + nome_classe
        df = df.loc[:, COLUNAS_SAIDA]

        df[["data"]] = df[["data"]].apply(pd.to_datetime)
        df[["data"]] = df[["data"]].apply(substituir_mes)

        df[COLUNAS_NUMERICAS] = df[COLUNAS_NUMERICAS].astype(float).map(
            lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        for col in COLUNAS_NUMERICAS:
            df[col] = df[col].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
        df[COLUNAS_NUMERICAS] = df[COLUNAS_NUMERICAS].astype(float)
        return df
    except (KeyError, IndexError, ValueError, TypeError, AttributeError) as exc:
        raise EstruturaInesperada(
            f"histórico de cota da carteira {id_carteira} fora do formato esperado: {type(exc).__name__}: {exc}"
        ) from exc
