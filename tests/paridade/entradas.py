"""Entradas SINTÉTICAS para os testes de paridade (formato inferido do código original).

ATENÇÃO: são sintéticas — não são respostas reais da Britech. Servem para exercitar todos os
caminhos das transformações e provar que o porte devolve o mesmo que o código original. Quando
houver respostas reais gravadas (com dados anonimizados), devem entrar aqui como novos cenários.

Usado tanto pelo script-oráculo (pandas 2, roda o código original) quanto pelos testes (pandas 3).
"""

from __future__ import annotations

import datetime as dt
from io import BytesIO

import pandas as pd

D = dt.datetime


def _xlsx(df: pd.DataFrame, *, header: bool) -> bytes:
    buf = BytesIO()
    df.to_excel(buf, index=False, header=header)
    return buf.getvalue()


# --- composição da carteira (ExcelAlinhado) ---------------------------------------------------

COLUNAS_CARTEIRA = [
    "MERCADO", "GRUPO", "ID POSIÇÃO", "CÓDIGO", "DESCRIÇÃO", "TIPO", "EMISSOR", "INSTITUIÇÃO", "DATA AQUISIÇÃO",
    "DATA LANÇAMENTO", "DATA OPERAÇÃO", "DATA EMISSÃO", "DATA VENCIMENTO", "ÍNDICE", "TAXA", "QUANTIDADE", "QTDE COTAS",
    "QTDE BLOQUEADA", "QTDE DÍSPONIVEL", "PU CUSTO", "VALOR CUSTO", "APLICAÇÃO", "PU MERCADO", "VALOR COTA",
    "VALOR MERCADO", "VALOR", "VALOR LÍQUIDO", "VALOR BRUTO", "% PL", "% C/C", "% Valores", "RESULTADO",
    "MOEDA ORIGEM", "% OUTROS ATIVOS", "% COTAS", "TRIBUTOS",
]  # fmt: skip


def _linha_carteira(**campos) -> dict:
    linha = {c: None for c in COLUNAS_CARTEIRA}
    linha.update(campos)
    return linha


def carteira_bruta(variante: str = "completa") -> bytes:
    linhas = [
        _linha_carteira(MERCADO="Patrimônio Líquido", GRUPO="Patrimônio Líquido", **{"VALOR MERCADO": 15234567.89}),
        _linha_carteira(MERCADO="Resumo da Carteira", GRUPO="Qtd. Antes Mov", **{"QTDE COTAS": 1000.5}),
        _linha_carteira(MERCADO="Resumo da Carteira", GRUPO="Qtd. Cotas", **{"QTDE COTAS": 1010.25}),
        _linha_carteira(MERCADO="Resumo da Carteira", GRUPO="Cota Bruta", **{"PU MERCADO": 1.2345}),
        _linha_carteira(MERCADO="Resumo da Carteira", GRUPO="Cota Líquida", **{"VALOR COTA": 1.2}),
        _linha_carteira(MERCADO="Resumo da Carteira", GRUPO="Cota Rendimento", **{"PU MERCADO": "1.1"}),
        _linha_carteira(
            MERCADO="Renda Fixa", GRUPO="CDB", CÓDIGO="CDB123", DESCRIÇÃO="CDB-BANCO X-2030", EMISSOR="BANCO X",
            **{
                "DATA AQUISIÇÃO": D(2025, 3, 15), "DATA EMISSÃO": D(2025, 3, 10), "DATA VENCIMENTO": "2030-03-10",
                "QUANTIDADE": 100, "VALOR MERCADO": 1500000.5, "VALOR CUSTO": 1400000.0, "PU MERCADO": 15000.005,
                "TAXA": 1.05, "% PL": 9.85, "RESULTADO": 100000.5, "MOEDA ORIGEM": "BRL",
            },
        ),  # fmt: skip
        _linha_carteira(
            MERCADO="Direitos Creditórios", GRUPO="DC", CÓDIGO="DC77", DESCRIÇÃO="DC - CEDENTE Y", INSTITUIÇÃO="Cedente Y",
            **{
                "DATA LANÇAMENTO": "2026-01-20", "DATA EMISSÃO": D(2026, 1, 15), "DATA VENCIMENTO": D(2027, 1, 15),
                "VALOR": "250000,75", "APLICAÇÃO": "240000.1", "TAXA": "12,5", "% PL": 1.64, "% OUTROS ATIVOS": 0.5,
            },
        ),  # fmt: skip
        _linha_carteira(
            MERCADO="Cotas de Fundos", GRUPO="FIDC", CÓDIGO="FID9", DESCRIÇÃO="FIDC ALFA - SENIOR",
            **{
                "DATA OPERAÇÃO": D(2025, 11, 3), "DATA EMISSÃO": None, "DATA VENCIMENTO": None,
                "QTDE COTAS": 5000.0, "VALOR COTA": 1.5, "VALOR LÍQUIDO": 7500.0, "% PL": 0.05, "% COTAS": 0.05,
            },
        ),  # fmt: skip
        _linha_carteira(
            MERCADO="Disponibilidades", GRUPO="Conta Corrente", DESCRIÇÃO="Banco Z CC", VALOR=12345.67,
            **{"% C/C": 0.08, "% Valores": 0.01, "DATA EMISSÃO": None, "DATA VENCIMENTO": None},
        ),  # fmt: skip
    ]
    if variante == "completa":
        for grupo, valor in (("Dia", 0.0012), ("Mês", 0.015), ("Ano", 0.09), ("6 Meses", 0.05), ("12 Meses", 0.1), ("Inicial", 0.3)):
            linhas.append(_linha_carteira(MERCADO="Rentabilidade", GRUPO=grupo, **{"VALOR MERCADO": valor}))
    elif variante == "sem_rentabilidade":
        pass  # exercita os defaults (Rent_dia/Rent_mes = 0)
    else:
        raise ValueError(variante)
    return _xlsx(pd.DataFrame(linhas, columns=COLUNAS_CARTEIRA), header=True)


# --- extrato de conta corrente --------------------------------------------------------------------


def extrato_bruto(variante: str = "padrao") -> bytes:
    if variante == "sem_movimentacao":
        grade = [
            ["Extrato de Conta Corrente", None, None, None, None, None],
            [None, None, None, None, None, None],
            ["Conta N°: 45031 - Valores em R$", None, None, "Saldo Anterior: 0,00", None, None],
        ]
        return _xlsx(pd.DataFrame(grade), header=False)

    deslocado = variante == "colunas_deslocadas"
    cabecalho = ["Vencimento", "Movimento", "Descrição", None, "Débito", "Crédito", "Saldo", None]

    def linha(venc, mov, desc, deb, cred, saldo):
        # no cenário "deslocado" a descrição vem na coluna vizinha (a de nome 'Descrição' fica vazia)
        return [venc, mov, None if deslocado else desc, desc if deslocado else None, deb, cred, saldo, None]

    grade = [
        ["Extrato de Conta Corrente", None, None, None, None, None, None, None],
        [None] * 8,
        ["Data de Emissão:", None, "01/09/2026", None, None, "10:27:19", None, None],
        ["Cliente:", "FUNDO X", None, None, None, None, None, None],
        ["Período:", None, None, D(2025, 12, 1), None, "à", D(2026, 8, 31), None],
        ["Conta N°: 45031 - Valores em R$", None, None, None, None, "Saldo Anterior: 1.234,56", None, None],
        cabecalho,
        linha(D(2026, 1, 3), D(2026, 1, 3), "Aplicação CDB", "(1.500,00)", None, "3.000,00"),
        linha(None, D(2026, 1, 15), "Resgate CDB", None, "2.000,50", "5.000,50"),  # Vencimento vazio -> ffill
        linha(D(2026, 2, 10), D(2026, 2, 10), "Tarifa", "(10,25)", None, "4.990,25"),
        linha(D(2026, 3, 2), None, "Sem movimento (descartar)", None, None, None),
    ]
    return _xlsx(pd.DataFrame(grade), header=False)


# --- movimentação de cotistas (JSON) ------------------------------------------------------------------


def mov_json(variante: str = "com_operacoes", *, nome_fundo: str = "FUNDO X - CLASSE SENIOR", deslocamento: int = 0) -> list[dict]:
    if variante == "vazio":
        return []

    def op(dia, tipo, qtd, cota, bruto, liquido, cotista="COTISTA A"):
        return {
            "IdOperacao": 1000 + dia.day + deslocamento,
            "DataOperacao": dia.strftime("%Y-%m-%dT00:00:00"),
            "DataConversao": dia.strftime("%Y-%m-%dT00:00:00"),
            "DataLiquidacao": (dia + dt.timedelta(days=1)).strftime("%Y-%m-%dT00:00:00"),
            "TipoOperacao": tipo,
            "NomeFundo": nome_fundo,
            "NomeCotista": cotista,
            "Quantidade": qtd,
            "CotaOperacao": cota,
            "ValorBruto": bruto,
            "ValorLiquido": liquido,
            "IdCotista": 9,
        }

    if variante == "fora_do_periodo":
        return [op(D(2020, 1, 10), 1, 10.0, 1.0, 10.0, 10.0), op(D(2030, 1, 10), 1, 10.0, 1.0, 10.0, 10.0)]
    return [
        op(D(2020, 1, 10), 1, 10.0, 1.0, 10.0, 10.0),  # antes do exercício: filtrado
        op(D(2026, 3, 10), 1, 100.123456, 1.23456789, 123.45, 120.0),
        op(D(2026, 1, 5), 80, 50.5, 2.5, 126.25, 125.0, cotista="COTISTA B"),
        op(D(2026, 5, 20), 999, 1.0, 1.0, 1.0, 1.0),  # tipo desconhecido -> NaN
        op(D(2026, 6, 30), 3, 1000.987, 1.5, 1481.48, 1400.1, cotista="COTISTA C"),
        op(D(2030, 1, 10), 1, 10.0, 1.0, 10.0, 10.0),  # depois do fim: filtrado
    ]


# --- posição de cotistas ----------------------------------------------------------------------------------

_CAB_POSICAO = [
    "Data Aplicação", "Valor da Cota na Aplicação", "Valor Aplicado", "Qtd. Cotas", "Saldo Bruto", "Valor IR",
    "Valor IOF", "Saldo Líquido", "Valor Pfee.", "Particip.", "Qtde Pendente Liquidação", "Valor Pendente Liquidação",
]  # fmt: skip


def posicao_bruta(variante: str = "data_na_coluna_4") -> bytes:
    n = len(_CAB_POSICAO)

    def preencher(*valores):
        return list(valores) + [None] * (n - len(valores))

    aplicacoes = [
        preencher("COTISTA A LTDA"),
        preencher(D(2025, 12, 5), 1.01, 1000.0, 990.1, 1010.0, 0.0, 0.0, 1010.0, 0.0, 50.0, 0.0, 0.0),
        preencher(D(2026, 2, 6), 1.02, 500.0, 480.5, 520.0, 1.5, 0.0, 518.5, 0.0, 25.0, 0.0, 0.0),
        preencher("COTISTA B S.A."),
        preencher(D(2026, 4, 9), 1.03, 800.0, 760.0, 830.0, 0.0, 0.0, 830.0, 0.0, 25.0, 0.0, 0.0),
    ]
    titulo = preencher("Posição de Aplicações por Cotista")
    carteira = preencher("Carteira:", "FUNDO X - CLASSE SENIOR")

    if variante == "sem_linha_de_aplicacoes":
        # largura realista (>= 7 colunas com conteúdo): o código lê a coluna 4 depois de descartar colunas vazias
        observacao = preencher("Observação", "sem aplicações no período", "-", "-", "-", "-", "-")
        grade = [titulo, carteira, preencher("Data Posicão:", None, None, None, D(2026, 8, 31)), observacao]
    elif variante == "data_na_coluna_4":
        grade = [titulo, carteira, preencher("Data Posicão:", None, None, None, D(2026, 8, 31)), _CAB_POSICAO] + aplicacoes
    elif variante == "data_na_coluna_5":
        # data fora da coluna 4 e cabeçalho com rótulos vazios nas posições 1 e 11 (o código renomeia)
        cab = list(_CAB_POSICAO)
        cab[1] = None
        cab[11] = None
        grade = [titulo, carteira, preencher("Data Posicão:", None, None, None, None, D(2026, 8, 31)), cab] + aplicacoes
    else:
        raise ValueError(variante)
    return _xlsx(pd.DataFrame(grade), header=False)


# --- histórico de cota (JSON) ---------------------------------------------------------------------------------


def historico_json(variante: str = "completo") -> list[dict]:
    if variante == "vazio":
        return []
    return [
        {
            "data": d.strftime("%Y-%m-%dT00:00:00"),
            "Entrada": 0.0,
            "Saida": 0.0,
            "PLFechamento": 1234567.891 + i * 1000.5,
            "QtdCotas": 1000.5 + i,
            "CotaFechamento": 1.2345 + i / 1000,
            "Dia": 0.001 * i,
            "Mes": 0.0123,
            "Ano": 0.0876,
            "DozeMeses": 0.1234,
            "Extra": "ignorado",
        }
        for i, d in enumerate([D(2026, 8, 28), D(2026, 8, 31)], start=1)
    ]
