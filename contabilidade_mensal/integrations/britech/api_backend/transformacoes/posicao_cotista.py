"""Posição (saldo de aplicações) por cotista (`Relatorio/RelatorioSaldoAplicacoesCotista`, `TipoArquivo=Excel`).

Porte de `posição_cotista_ctb_britech1.py`. Diferenças sem efeito no resultado:
`df.columns.values[i] = …` (mutação in-place de Index, proibida no pandas 3) → reatribuição de `columns`.
"""

from __future__ import annotations

import pandas as pd

from ...erros import EstruturaInesperada
from .comum import substituir_mes

COLUNAS_SAIDA = [
    "Data Aplicação", "Valor da Cota na Aplicação", "Valor Aplicado", "Qtd. Cotas", "Saldo Bruto", "Valor IR", "Valor IOF",
    "Saldo Líquido", "Valor Pfee.", "Particip.", "Qtde Pendente Liquidação", "Valor Pendente Liquidação",
    "NomeFundo", "Cotista", "Data Posicao",
]  # fmt: skip


def _sem_dados(id_carteira, nome_classe) -> pd.DataFrame:
    return pd.DataFrame({"NomeFundo": [f"{id_carteira} - {nome_classe}"], "Data Posicao": ["Sem dados aplicação"]})


def _promover_cabecalho(df: pd.DataFrame, *, id_carteira, nome_classe, data, renomear_posicoes: bool):
    """Usa a linha 'Data Aplicação' como cabeçalho e monta as colunas finais. None se a linha não existe."""
    achadas = df[df.iloc[:, 0] == "Data Aplicação"].index
    if achadas.empty:
        return None
    linha_cabecalho = achadas[0]
    df.columns = df.iloc[linha_cabecalho]
    df = df.reset_index(drop=True).rename_axis(None, axis=1)
    df = df.iloc[linha_cabecalho + 1 :]
    df = df.dropna(axis=0, how="all")

    df["NomeFundo"] = f"{id_carteira} - {nome_classe}"
    df = df.dropna(subset=["Data Aplicação"]).copy()
    df["Cotista"] = df["Data Aplicação"].where(df["Valor Aplicado"].isna())
    df["Cotista"] = df["Cotista"].ffill()
    df["Data Posicao"] = data
    df = df.dropna(subset=["Valor Aplicado"]).copy()
    df = df.dropna(axis=1, how="all")

    if renomear_posicoes:
        colunas = list(df.columns)
        colunas[1] = "Valor da Cota na Aplicação"
        colunas[11] = "Valor Pendente Liquidação"
        df.columns = colunas
    return df[COLUNAS_SAIDA]


def transformar_posicao_cotista(df_bruto: pd.DataFrame, *, id_carteira, nome_classe: str) -> pd.DataFrame:
    try:
        df = df_bruto.dropna(axis=1, how="all")
        if df.empty:
            return _sem_dados(id_carteira, nome_classe)

        linha_data = df[df.iloc[:, 0] == "Data Posicão:"].index
        if linha_data.empty:
            raise EstruturaInesperada(f"posição da carteira {id_carteira}: linha 'Data Posicão:' não encontrada")

        data = df.iloc[linha_data[0], 4]
        renomear = False
        if pd.isna(data):
            data = df.iloc[linha_data[0], 5]
            if pd.isna(data):
                data = df.iloc[linha_data[0], 6]
            renomear = True

        resultado = _promover_cabecalho(
            df, id_carteira=id_carteira, nome_classe=nome_classe, data=data, renomear_posicoes=renomear
        )
        if resultado is None:
            return _sem_dados(id_carteira, nome_classe)

        resultado[["Data Aplicação", "Data Posicao"]] = resultado[["Data Aplicação", "Data Posicao"]].apply(pd.to_datetime)
        resultado[["Data Aplicação", "Data Posicao"]] = resultado[["Data Aplicação", "Data Posicao"]].apply(substituir_mes)
        return resultado.reset_index(drop=True).rename_axis(None, axis=1)
    except EstruturaInesperada:
        raise
    except (KeyError, IndexError, ValueError, TypeError, AttributeError) as exc:
        raise EstruturaInesperada(
            f"posição de cotistas da carteira {id_carteira} fora do formato esperado: {type(exc).__name__}: {exc}"
        ) from exc
