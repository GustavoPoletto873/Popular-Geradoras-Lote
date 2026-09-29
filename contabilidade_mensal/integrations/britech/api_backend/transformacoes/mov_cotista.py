"""Movimentação de cotistas (`Fundo/OperacaoCotistaAnalitico_PorCarteiraCotista`, JSON).

Porte de `mov_cotista_ctb_britech.py`. Uma chamada por carteira (classe de cotas); o empilhamento
das classes é feito depois (transformacoes/empilhar.py).
"""

from __future__ import annotations

import pandas as pd

from ...erros import EstruturaInesperada
from .comum import substituir_mes

TIPO_OPERACAO = {
    80: "Amortização",
    82: "Juros",
    3: "Resgate Líquido",
    1: "Aplicação",
    10: "Aplicação Cotas Especial",
    12: "Resgate Cotas Especial",
    102: "Retirada",
    5: "Resgate Total",
    103: "Depósito",
    123: "Alienação – Venda em Quantidade de Cotas",
    121: "Alienação – Compra em Quantidade de Cotas",
    20: "Come Cotas",
    141: "Cisão Aplicação",
    4: "Resgate Cotas",
    100: "Incorporação Resgate",
    2: "Resgate Bruto",
    101: "Incorp. Aplicação",
    122: "Alienação – Compra em Valor de Cotas",
    140: "Cisão Resgate",
    112: "Dividendo",
    110: "Aplicação Cotas",
}

COLUNAS_SAIDA = [
    "NomeFundo", "DataOperacao", "NomeCotista", "DataConversao", "DataLiquidacao", "TipoOperacao", "Tipo Cotista Mov",
    "Quantidade", "CotaOperacao", "ValorBruto", "Vl Penalty Fee", "Valor IR", "Valor IOF", "Rend. Trib.", "ValorLiquido",
]  # fmt: skip


def _sem_movimentacao(id_carteira, nome_classe) -> pd.DataFrame:
    return pd.DataFrame(
        {"NomeFundo": [f"{id_carteira} - {nome_classe}"], "TipoOperacao": ["Sem movimentação"]}
    )


def transformar_mov_cotista(
    registros: list[dict], *, id_carteira, nome_classe: str, data_inicio: str, data_fim: str
) -> pd.DataFrame:
    """`registros` = JSON da API. Datas 'AAAA-MM-DD'. Sem operações no período → linha "Sem movimentação"."""
    try:
        df_mov = pd.DataFrame(registros)
        inicio = pd.to_datetime(data_inicio)
        fim = pd.to_datetime(data_fim)

        try:
            df_mov["DataOperacao"] = pd.to_datetime(df_mov["DataOperacao"])
        except Exception:  # noqa: BLE001 - sem a coluna (lista vazia) equivale a "sem movimentação"
            return _sem_movimentacao(id_carteira, nome_classe)

        df = df_mov[(df_mov["DataOperacao"] >= inicio) & (df_mov["DataOperacao"] <= fim)].copy()
        if df.empty:
            return _sem_movimentacao(id_carteira, nome_classe)

        df["TipoOperacao"] = df["TipoOperacao"].map(TIPO_OPERACAO)
        df["NomeFundo"] = str(id_carteira) + " - " + df["NomeFundo"]
        df["Tipo Cotista Mov"] = None
        df["Vl Penalty Fee"] = None
        df["Valor IR"] = None
        df["Valor IOF"] = None
        df["Rend. Trib."] = None

        df = df[COLUNAS_SAIDA]
        df = df.sort_values(by="DataOperacao")

        colunas_data = ["DataOperacao", "DataConversao", "DataLiquidacao"]
        df[colunas_data] = df[colunas_data].apply(pd.to_datetime)
        df[colunas_data] = df[colunas_data].apply(substituir_mes)

        colunas = ["Quantidade", "CotaOperacao", "ValorBruto", "ValorLiquido"]
        df[colunas] = df[colunas].astype(float).map(lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        for col in colunas:
            df[col] = df[col].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
        df[colunas] = df[colunas].astype(float)
        return df
    except (KeyError, IndexError, ValueError, TypeError, AttributeError) as exc:
        raise EstruturaInesperada(
            f"movimentação de cotistas da carteira {id_carteira} fora do formato esperado: {type(exc).__name__}: {exc}"
        ) from exc
