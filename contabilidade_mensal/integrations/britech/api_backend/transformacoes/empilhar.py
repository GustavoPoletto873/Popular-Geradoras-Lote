"""Empilhamento das classes de cotas (porte de `empilhar_relatorios_passivo.py`).

Um fundo pode ter várias carteiras (classes) na Britech. O passivo é baixado por classe e o
insumo final é UM arquivo por CNPJ:
  - 1 classe  → o DataFrame segue como está (todas as colunas);
  - N classes → concatena e mantém só as colunas configuradas, na ordem configurada.

ATENÇÃO (comportamento preservado do original): nas listas de posição a coluna aparece como
'Valor Pendente Liquidação.' (COM ponto final), que não existe nos dados; por isso o arquivo
empilhado NÃO traz 'Valor Pendente Liquidação', enquanto o de classe única traz. Se isso for
um erro de digitação, corrigir aqui muda a aba Posicao_Cotista — decisão do negócio.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

COLUNAS_EMPILHADAS = {
    "MovCotista": [
        "NomeFundo", "DataOperacao", "NomeCotista", "DataConversao", "DataLiquidacao", "TipoOperacao", "Tipo Cotista Mov",
        "Quantidade", "CotaOperacao", "ValorBruto", "Vl Penalty Fee", "Valor IR", "Valor IOF", "Rend. Trib.", "ValorLiquido",
    ],
    "SaldoAplicacaoCotistaInicial": [
        "Data Aplicação", "Valor da Cota na Aplicação", "Valor Aplicado", "Qtd. Cotas", "Saldo Bruto", "Valor IR", "Valor IOF",
        "Saldo Líquido", "Valor Pfee.", "Particip.", "Qtde Pendente Liquidação", "Valor Pendente Liquidação.",
        "NomeFundo", "Cotista", "Data Posicao",
    ],
    "SaldoAplicacaoCotistaFinal": [
        "Data Aplicação", "Valor da Cota na Aplicação", "Valor Aplicado", "Qtd. Cotas", "Saldo Bruto", "Valor IR", "Valor IOF",
        "Saldo Líquido", "Valor Pfee.", "Particip.", "Qtde Pendente Liquidação", "Valor Pendente Liquidação.",
        "NomeFundo", "Cotista", "Data Posicao",
    ],
    "Histórico de Cota": [
        "data", "Entrada", "Saida", "PLFechamento", "QtdCotas", "CotaFechamento", "Dia", "Mes", "Ano", "DozeMeses", "Carteira",
    ],
}  # fmt: skip


def empilhar(dfs: Sequence[pd.DataFrame], tipo: str) -> pd.DataFrame:
    """`tipo` = chave de COLUNAS_EMPILHADAS (sufixo do nome do arquivo)."""
    if not dfs:
        raise ValueError("nada para empilhar")
    if len(dfs) == 1:
        return dfs[0]
    consolidado = pd.concat(list(dfs), ignore_index=True)
    existentes = [c for c in COLUNAS_EMPILHADAS[tipo] if c in consolidado.columns]
    return consolidado[existentes]
