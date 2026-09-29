"""Montagem das URLs (caminho + query) dos endpoints — idênticas às do downloader do Simplifica.

Funções puras: a paridade com o original é conferida comparando as URLs chamadas (tests/test_paridade_*).
"""

from __future__ import annotations

_COMPOSICAO = (
    "Relatorio/RelatorioComposicaoCarteira?&IdCarteira={id}&DataReferencia={data}&IdMoeda=1&SeparaCustodia=N"
    "&AgrupaValoresLiquidacao=N&DemonstraGrossUp=S&AgrupaDireitoCreditorio=S&IdLingua=1&TipoRelatorio=1"
    "&DespesasSubclasse=S&TipoArquivo={tipo}"
)


def composicao_carteira(id_carteira, data_referencia: str, *, tipo_arquivo: str) -> str:
    """`tipo_arquivo`: 'ExcelAlinhado' (dados) ou 'PDF' (evidência)."""
    return _COMPOSICAO.format(id=id_carteira, data=data_referencia, tipo=tipo_arquivo)


def extrato_conta_corrente(id_carteira, data_inicio: str, data_fim: str, *, tipo_arquivo: str) -> str:
    """`tipo_arquivo`: 'Excel' ou 'PDF'."""
    return (
        f"Relatorio/RelatorioExtratoContaCorrente"
        f"?IdCliente={id_carteira}&DataInicio={data_inicio}&DataFim={data_fim}&Periodo=1&TipoArquivo={tipo_arquivo}"
    )


def mov_cotista(id_carteira) -> str:
    """PECULIARIDADE PRESERVADA DO ORIGINAL: `DataInicio` e `DataFim` seguem LITERAIS (`{data_inicio}`,
    `{DataFimArquivo}`) porque no Simplifica o 2º pedaço da string não é f-string. A API responde e o
    filtro por data é feito depois, no pandas (transformar_mov_cotista). Como isso funciona hoje em
    produção, mantemos byte a byte; trocar por datas reais é uma decisão a testar contra a Britech."""
    return (
        f"Fundo/OperacaoCotistaAnalitico_PorCarteiraCotista"
        f"?IdsCarteira={id_carteira}&IdsCotista="
        "&DataInicio={data_inicio}&DataFim={DataFimArquivo}"
    )


def saldo_aplicacoes_cotista(id_carteira, data_referencia: str, *, tipo_arquivo: str) -> str:
    """`tipo_arquivo`: 'Excel' ou 'PDF'."""
    return (
        f"Relatorio/RelatorioSaldoAplicacoesCotista"
        f"?IdCarteira={id_carteira}&DataReferencia={data_referencia}&IdCotista=&CpfCnpjCotista=&OpcoesCampo=1"
        f"&TipoRelatorio=1&TipoGrupamento=1&OpcaoValorAplicado=1&TipoLingua=&IncluiRetorno=true&TipoArquivo={tipo_arquivo}"
    )


def historico_cota(id_carteira, data_inicio: str, data_fim_datetime: str) -> str:
    """`data_fim_datetime` segue o formato do original: `str(datetime)` → 'AAAA-MM-DD 00:00:00'."""
    return (
        f"Fundo/BuscaHistoricoCotaRentabilidade"
        f"?idCarteira={id_carteira}&DataInicio={data_inicio}&DataFim={data_fim_datetime}"
    )


CADASTRO_FUNDOS = "Fundo/BuscaListaFundos?idsCliente="
