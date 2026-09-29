"""Extrato de conta corrente (`Relatorio/RelatorioExtratoContaCorrente`, `TipoArquivo=Excel`).

Porte do bloco de processamento de `caixa_ctb_britech.py`. Diferenças sem efeito no resultado:
`fillna(method='ffill', inplace=True)` → `.ffill()` (removido no pandas 3); `st.error` + `continue`
→ exceção tipada.
"""

from __future__ import annotations

import pandas as pd

from ...erros import EstruturaInesperada
from .comum import substituir_mes


def transformar_extrato(df_bruto: pd.DataFrame, *, id_carteira) -> pd.DataFrame:
    try:
        df = df_bruto.dropna(axis=1, how="all")

        linha_conta = df[df.iloc[:, 0].str.contains("Conta", na=False)].index[0]
        coluna_saldo = None
        for col in df.columns:
            if "Saldo Anterior:" in str(df.at[linha_conta, col]):
                coluna_saldo = col
                break
        df_saldo = df[[coluna_saldo]].copy()
        df_saldo.columns = ["Saldo"]
        df_saldo = df_saldo.dropna(how="all")
        df_saldo["Saldo"] = (
            df_saldo["Saldo"]
            .astype(str)
            .str.replace("Saldo Anterior: ", "", regex=False)
            .str.replace("R$", "", regex=False)
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False)
            .str.strip()
        )
        df_saldo["Saldo"] = pd.to_numeric(df_saldo["Saldo"], errors="coerce")
        df_saldo = df_saldo.dropna()
        total_saldo = df_saldo["Saldo"].sum()

        indice_cliente = df[df.iloc[:, 0] == "Cliente:"].index
        if len(indice_cliente) == 0:
            return pd.DataFrame({"Status": ["Arquivo sem movimentacao"]})

        carteira = df.iloc[indice_cliente[0], 1]

        linha_cabecalho = df[df.iloc[:, 0] == "Vencimento"].index[0]
        df.columns = df.iloc[linha_cabecalho]
        df = df.reset_index(drop=True).rename_axis(None, axis=1)
        df = df.iloc[linha_cabecalho + 1 :]

        # 1. colunas sem nome ganham nome temporário único
        novas_colunas = []
        contador = 0
        for col in df.columns:
            if pd.isna(col) or str(col).strip() == "" or str(col) == "NaT":
                novas_colunas.append(f"_temp_col_{contador}")
                contador += 1
            else:
                novas_colunas.append(col)
        df.columns = novas_colunas

        # 2/3. colunas importantes vazias recebem os dados da coluna temporária vizinha
        for col_importante in ["Vencimento", "Movimento", "Descrição", "Débito", "Crédito", "Saldo"]:
            if col_importante in df.columns:
                if df[col_importante].isna().all() or (df[col_importante].astype(str).str.strip() == "").all():
                    idx = df.columns.get_loc(col_importante)
                    for deslocamento in [-1, 1, -2, 2]:
                        vizinho = idx + deslocamento
                        if 0 <= vizinho < len(df.columns):
                            col_vizinha = df.columns[vizinho]
                            if col_vizinha.startswith("_temp_col_") and not df[col_vizinha].isna().all():
                                df[col_importante] = df[col_vizinha].copy()
                                break

        if "Vencimento" in df.columns:
            df["Vencimento"] = df["Vencimento"].ffill()

        # 4/5. remove as colunas temporárias
        df = df.drop(columns=[c for c in df.columns if c.startswith("_temp_col_") and df[c].isna().all()])
        restantes = [c for c in df.columns if c.startswith("_temp_col_")]
        if restantes:
            df = df.drop(columns=restantes)

        df = df.reset_index(drop=True).rename_axis(None, axis=1)
        df["Carteira"] = carteira

        if "Movimento" not in df.columns:
            raise EstruturaInesperada(f"extrato da carteira {id_carteira}: coluna 'Movimento' não encontrada")

        df.dropna(subset=["Movimento"], inplace=True)
        if "Débito" not in df.columns:
            raise EstruturaInesperada(f"extrato da carteira {id_carteira}: coluna 'Débito' não encontrada")
        df["Débito"] = df["Débito"].astype(str)
        df["Débito"] = df["Débito"].str.replace("(", "-", regex=False)
        df["Débito"] = df["Débito"].str.replace(")", "", regex=False)
        df["Débito"] = df["Débito"].str.replace(".", "", regex=False)
        df["Débito"] = df["Débito"].str.replace(",", ".", regex=False)
        df["Débito"] = pd.to_numeric(df["Débito"], errors="coerce")

        df = df[df["Vencimento"] != "Vencimento"].reset_index(drop=True)
        df[["Vencimento", "Movimento"]] = df[["Vencimento", "Movimento"]].apply(pd.to_datetime, errors="coerce")
        df[["Vencimento", "Movimento"]] = df[["Vencimento", "Movimento"]].apply(substituir_mes)

        df["Código da Carteira"] = id_carteira
        df["Saldo Anterior"] = total_saldo
        return df
    except EstruturaInesperada:
        raise
    except (KeyError, IndexError, ValueError, TypeError, AttributeError) as exc:
        raise EstruturaInesperada(
            f"extrato da carteira {id_carteira} fora do formato esperado: {type(exc).__name__}: {exc}"
        ) from exc
