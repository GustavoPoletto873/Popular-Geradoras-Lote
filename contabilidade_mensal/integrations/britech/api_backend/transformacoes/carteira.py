"""Composição da carteira (`Relatorio/RelatorioComposicaoCarteira`, `TipoArquivo=ExcelAlinhado`).

Porte de `carteira_britech_idV2.processar_carteira` (do trecho após `pd.read_excel` em diante).
Alterações intencionais, sem efeito no resultado: compatibilidade com pandas 3 (checagens de
dtype e `.astype(str)`), `print` → exceção tipada, nomes em português.
"""

from __future__ import annotations

import logging
import re
import warnings
from datetime import date, datetime

import pandas as pd

from ...erros import EstruturaInesperada
from .comum import eh_texto

logger = logging.getLogger(__name__)

COLUNAS_PADRAO = [
    "Fundo", "Carteira", "Data Carteira", "Arquivo", "MERCADO", "GRUPO", "ID POSIÇÃO", "ID OPERAÇÃO", "ID TÍTULO", "CÓDIGO", "DESCRIÇÃO", "TIPO", "TIPO COMPANHIA",
    "InstituicaoEmissor", "DataAquisicao", "Dt_Aquisição", "DATA EMISSÃO", "DATA VENCIMENTO", "ÍNDICE", "TAXA", "QTDE BLOQUEADA", "QTDE DÍSPONIVEL", "QTDE", "PU CUSTO",
    "VALOR CUSTO", "PU_Mercado", "ValorMercado", "% PL", "% C/C", "% Valores",
]  # fmt: skip

COLUNAS_PONTO_POR_VIRGULA = [
    "QUANTIDADE", "QTDE DÍSPONIVEL", "QTDE BLOQUEADA", "QTDE COTAS", "PU CUSTO LÍQUIDO", "VALOR CUSTO LÍQUIDO", "PU MERCADO", "VALOR MERCADO", "RESULTADO", "PU EXERCICIO",
    "VALOR", "VALOR COTA", "VALOR TERMO", "VALOR CORRIGIDO", "VALOR LÍQUIDAR", "VALOR LÍQUIDO", "VALOR BASE", "VALOR CUSTO", "VALOR APLICAÇÃO", "VALOR COMISSÃO", "VALOR EMOLUMENTOS",
    "VALOR ATIVO", "VALOR PASSIVO", "VALOR PASSIVO MTM", "VALOR LÍQUIDO TRIBUTOS", "VALOR MOEDA VENDIDA", "VALOR MOEDA COMPRADA", "VALOR KNOCK IN", "VALOR KNOCK OUT", "VALOR JUROS",
    "VALOR ATIVO MTM", "VALOR IR", "PU BASE", "PU TERMO", "PU ORIGINAL", "TAXA", "TAXA OPERAÇÃO", "TAXA JUROS", "COMISSÃO", "APLICAÇÃO", "PREÇO LÍMITE EXERCÍCIO", "VALOR RESGATE",
    "TRIBUTOS", "RENDIMENTO DIA", "RENDIMENTO APROPRIAR", "RENDIMENTO APROPRIADO", "RENDIMENTO TOTAL", "PU RESGATE", "AJUSTE DIÁRIO", "QUANTIDADE", "VALOR CUSTO", "PU CUSTO", "ÍNDICE",
    "AJUSTE MOEDA CARTEIRA", "AJUSTE MOEDA VENDIDA", "AJUSTE MOEDA LIQUIDAÇÃO", "SALDO MTM", "SALDO", "% SWAP", "% OUTROS ATIVOS", "% COTAS", "% TERMO", "% RENDA FIXA", "% OPÇÕES",
    "% AÇÕES", "% PL", "% FUTUROS", "TAXA JUROS CONTRA PARTE", "VALOR BRUTO", "% C/C", "% Valores", "PU TERMO LIQUIDO", "VALOR ATUALIZADO", "PU VENCIMENTO",
]  # fmt: skip

COLUNAS_DATAS = ["Data Carteira", "DataAquisicao", "DATA EMISSÃO", "DATA VENCIMENTO"]

COLUNAS_FINAIS = [
    "Patrimonio Fechamento", "Qtd Antes Mov", "Qtd Cotas", "Cota Bruta", "Cota Liquida", "Cota Rendimento", "Rent_dia", "Rent_mes",
]  # fmt: skip

_MESES_AJUSTE = (("jan", "jan"), ("feb", "fev"), ("apr", "abr"), ("may", "mai"), ("aug", "ago"), ("sep", "set"), ("oct", "out"), ("dec", "dez"))


def _ajuste_data(coluna: pd.Series) -> pd.Series:
    """Converte para 'dd-mmm-aaaa' (mês em português); inválidos viram NaN.

    `dayfirst=True` é do original e é preservado: textos 'dd/mm/aaaa' saem certos; textos ISO 'aaaa-mm-dd'
    (dia <= 12) têm dia e mês trocados — o pandas avisa disso, e o aviso é silenciado para não poluir o log.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Parsing dates in .* when dayfirst=True", category=UserWarning)
        datas = pd.to_datetime(coluna, errors="coerce", dayfirst=True)
    texto = datas.dt.strftime("%d-%b-%Y").str.lower()
    for en, pt in _MESES_AJUSTE:
        texto = texto.str.replace(en, pt)
    return texto


def _reorganizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    padrao = [c for c in COLUNAS_PADRAO if c in df.columns]
    extras = [c for c in df.columns if c not in COLUNAS_PADRAO]
    return df[padrao + extras]


def _merge_columns(df: pd.DataFrame, colunas: list[str], nova_coluna: str, modo: str) -> pd.DataFrame:
    """Funde colunas equivalentes em uma. modo: 'all' (junta textos com ' - '), 'less'/'more' (menor/maior valor numérico)."""
    presentes = [c for c in colunas if c in df.columns]
    if not presentes:
        return df
    valores_da_nova: list[str] = []
    for _, linha in df[presentes].iterrows():
        validos = list(dict.fromkeys([str(v).strip() for v in linha if pd.notna(v) and str(v).strip()]))
        if modo == "all":
            novo = " - ".join(validos)
        else:
            numericos: list[float] = []
            for v in validos:
                try:
                    numericos.append(float(v.replace(",", ".")))
                except ValueError:
                    pass  # textos não entram na comparação numérica
            if numericos:
                if modo == "more":
                    novo = f"{max(numericos):.8f}".replace(".", ",")
                elif modo == "less":
                    novo = f"{min(numericos):.8f}".replace(".", ",")
                else:
                    novo = ""
            else:
                novo = ""
        valores_da_nova.append(novo)
    df[nova_coluna] = valores_da_nova
    return df.drop(columns=presentes)


def _remover_colunas_vazias(df: pd.DataFrame) -> None:
    vazias = []
    for col in df.columns:
        if col in COLUNAS_PADRAO:
            continue
        if df[col].isna().all():
            vazias.append(col)
        elif eh_texto(df[col]) and df[col].str.strip().eq("").all():
            vazias.append(col)
    df.drop(columns=vazias, inplace=True)


def _numericas(df: pd.DataFrame) -> pd.DataFrame:
    """Converte textos que representam número ('1234,5', '-1.2e3') em float; o resto fica como está."""
    for coluna in df.columns:
        try:
            if eh_texto(df[coluna]):
                df[coluna] = df[coluna].apply(
                    lambda x: pd.to_numeric(str(x).replace(",", "."), errors="coerce")
                    if isinstance(x, str) and re.match(r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$", x.replace(",", "."))
                    else x
                )
        except Exception as exc:  # noqa: BLE001 - igual ao original: uma coluna problemática não derruba o arquivo
            logger.warning("coluna %r não pôde ser convertida para número: %s", coluna, exc)
    return df


def _pegar_e_remover(df: pd.DataFrame, mercado: str, grupo: str, coluna: str, padrao=""):
    subset = df.loc[(df["MERCADO"] == mercado) & (df["GRUPO"] == grupo), coluna]
    if not subset.empty:
        valor = subset.iloc[0]
        df.drop(subset.index, inplace=True)
        return valor
    return padrao


def transformar_composicao_carteira(df: pd.DataFrame, *, id_carteira, data_ref) -> pd.DataFrame:
    """`df` = planilha bruta da API já lida com `pd.read_excel`. `data_ref` = 'AAAA-MM-DD' (ou date/datetime)."""
    if isinstance(data_ref, str):
        data_obj = datetime.strptime(data_ref, "%Y-%m-%d")
    elif isinstance(data_ref, (datetime, date)):
        data_obj = data_ref
    else:
        raise ValueError("data_ref deve ser string 'AAAA-MM-DD', date ou datetime")
    nome_carteira = f"Carteira_{id_carteira}_{data_obj.strftime('%d-%m-%Y')}.xlsx"

    try:
        df = df.copy()
        df = _merge_columns(df, ["QUANTIDADE", "QTDE COTAS"], "QTDE", "less")
        df = _merge_columns(df, ["VALOR MERCADO", "VALOR", "VALOR LÍQUIDO"], "ValorMercado", "less")
        df = _merge_columns(df, ["DATA AQUISIÇÃO", "DATA LANÇAMENTO", "DATA OPERAÇÃO"], "DataAquisicao", "all")
        df = _merge_columns(df, ["VALOR CUSTO", "APLICAÇÃO", "VALOR APLICAÇÃO"], "ValorCusto", "less")
        df = _merge_columns(df, ["EMISSOR", "INSTITUIÇÃO"], "InstituicaoEmissor", "all")
        df = _merge_columns(df, ["PU MERCADO", "VALOR COTA"], "PU_Mercado", "less")

        df = df.drop(
            columns=["RESULTADO", "MOEDA ORIGEM", "% OUTROS ATIVOS", "% COTAS", "% RENDA FIXA", "% AÇÕES", "TRIBUTOS"],
            errors="ignore",
        )
        df = _reorganizar_colunas(df)

        for coluna in COLUNAS_PONTO_POR_VIRGULA:
            if coluna in df.columns:
                df[coluna] = df[coluna].apply(
                    lambda x: str(x).replace(".", ",") if isinstance(x, str) or isinstance(x, float) else x
                )

        if "DESCRIÇÃO" in df.columns:
            df["DESCRIÇÃO"] = df["DESCRIÇÃO"].apply(
                lambda x: str(x).replace("-", "") if isinstance(x, str) or isinstance(x, float) else x
            )

        df.insert(0, "Fundo", "")
        df.insert(1, "Carteira", id_carteira)
        df.insert(2, "Data Carteira", data_ref)
        df.insert(3, "Arquivo", nome_carteira)

        df[COLUNAS_DATAS] = df[COLUNAS_DATAS].apply(_ajuste_data)

        for col in COLUNAS_FINAIS:
            if col not in df.columns:
                df[col] = ""

        df["Patrimonio Fechamento"] = _pegar_e_remover(df, "Patrimônio Líquido", "Patrimônio Líquido", "ValorMercado")
        df["Qtd Antes Mov"] = _pegar_e_remover(df, "Resumo da Carteira", "Qtd. Antes Mov", "QTDE")
        df["Qtd Cotas"] = _pegar_e_remover(df, "Resumo da Carteira", "Qtd. Cotas", "QTDE")
        df["Cota Bruta"] = _pegar_e_remover(df, "Resumo da Carteira", "Cota Bruta", "PU_Mercado")
        df["Cota Liquida"] = _pegar_e_remover(df, "Resumo da Carteira", "Cota Líquida", "PU_Mercado")
        df["Cota Rendimento"] = _pegar_e_remover(df, "Resumo da Carteira", "Cota Rendimento", "PU_Mercado")
        df["Rent_dia"] = _pegar_e_remover(df, "Rentabilidade", "Dia", "ValorMercado", 0)
        df["Rent_mes"] = _pegar_e_remover(df, "Rentabilidade", "Mês", "ValorMercado", 0)

        df["Rent_dia"] = pd.to_numeric(df["Rent_dia"].astype(str).str.replace(",", "."), errors="coerce") * 100
        df["Rent_mes"] = pd.to_numeric(df["Rent_mes"].astype(str).str.replace(",", "."), errors="coerce") * 100

        df["Rent_dia"] = df["Rent_dia"].apply(lambda x: "{:.8f}".format(x).replace(".", ","))
        df["Rent_mes"] = df["Rent_mes"].apply(lambda x: "{:.8f}".format(x).replace(".", ","))

        for grupo in ("Ano", "6 Meses", "12 Meses", "Inicial"):
            df = df[~((df["MERCADO"] == "Rentabilidade") & (df["GRUPO"] == grupo))]

        df = df.fillna("")
        df = df.astype(str).replace("nan", "")

        df = df[[c for c in df.columns if c != "VALOR BRUTO"] + ["VALOR BRUTO"]]

        _remover_colunas_vazias(df)
        _numericas(df)
        return df
    except (KeyError, IndexError, ValueError, TypeError, AttributeError) as exc:
        raise EstruturaInesperada(
            f"planilha da composição da carteira {id_carteira} fora do formato esperado: {type(exc).__name__}: {exc}"
        ) from exc
