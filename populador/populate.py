"""
Porte das funções `Popula_*` de Functions.bas — mas SOMENTE as que
`ProcessarEmLoop` realmente chama hoje (ver config.BATCH_STEPS). Cada
função é um espelho linha-a-linha da correspondente em VBA: mesma faixa de
colunas copiada, mesma aba de destino, mesmo range copiado.

Duas coisas não são espelho 1:1 do VBA original:

1. A busca do arquivo de insumo: usamos `matching.resolver_insumo`, que
   tenta primeiro o padrão exato do VBA e só cai para reconhecimento por
   palavra-chave (fallback) se o exato não achar nada — ver matching.py e
   config.INSUMO_FALLBACK para a evidência de cada padrão alternativo.
   Confirmado com o usuário depois de constatar que a maioria dos fundos
   reais não usa mais os nomes de arquivo literais que o VBA de 2021 espera.

2. Desmesclamos (`UnMerge`) a aba de destino antes de colar em TODOS os
   steps, não só em Posição_Cotista (única aba que o VBA original desmescla).
   Achado testando com 2 fundos reais no mesmo lote: o Extrato de "FII
   KRONOS" tem células mescladas no cabeçalho do template (herdadas do
   arquivo do período anterior, que o ClearContents não remove), e colar ali
   sem desmesclar quebra com "Não podemos fazer isto em uma célula mesclada"
   — o mesmo erro que o VBA original evitou em Posição_Cotista adicionando
   um UnMerge lá. Estendemos a mesma defesa pra todo mundo porque é
   idempotente (não faz nada se não houver mesclagem) e evita o batch inteiro
   travar num fundo cujo template tenha esse detalhe.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from . import config
from .excel_app import ExcelSession, copy_paste_all, last_row, unmerge_all
from .matching import ResultadoMatch, resolver_insumo

# (step, candidatos_ambiguos) -> arquivo escolhido, ou None pra manter como
# ambíguo/deixar em branco (comportamento padrão). Ver cli.py para a
# implementação interativa usada com `--interativo`.
ResolverAmbiguidade = Callable[[str, list[Path]], "Path | None"]

# Variante usada em runner.py/cli.py, que também recebe o nome do fundo (pra
# identificar de qual fundo é a ambiguidade quando se está processando vários).
ResolverAmbiguidadeFundo = Callable[[str, str, list[Path]], "Path | None"]

logger = logging.getLogger(__name__)


def _abrir_fonte_e_copiar(session: ExcelSession, arquivo: Path):
    """Abre a fonte read-only; devolve (wbSource, wsSource). Chamador deve
    fechar com `wbSource.Close(SaveChanges=False)` — igual ao VBA."""
    wb = session.open_workbook(arquivo, read_only=True)
    return wb, wb.Sheets(1)


def _copiar_um_arquivo(
    session: ExcelSession,
    arquivo: Path,
    wb_destino,
    sheet_destino: str,
    faixa_origem: str,
    celula_destino: str,
) -> None:
    """Réplica do padrão comum a Popula_Carteira / Popula_Balancete: copia
    uma faixa fixa de colunas para uma célula de destino.

    Desmescla a aba de destino antes de colar (ver nota em
    executar_batch_steps sobre por que isso é necessário em todos os steps,
    não só em Posição_Cotista como no VBA original)."""
    ws_target = wb_destino.Sheets(sheet_destino)
    unmerge_all(ws_target)
    wb_source, ws_source = _abrir_fonte_e_copiar(session, arquivo)
    try:
        copy_paste_all(ws_source.Range(faixa_origem), ws_target.Range(celula_destino), session.app)
    finally:
        wb_source.Close(SaveChanges=False)


def _acumular_arquivos(
    session: ExcelSession,
    arquivos: list[Path],
    wb_destino,
    sheet_destino: str,
    coluna_ultima_linha: str,
    faixa_colunas: str,
) -> None:
    """Réplica do padrão de Popula_Posicao_Cotista / PopulaMovimentacaoV2:
    itera pelos arquivos passados, colando cada um em sequência, avançando
    a linha de destino.

    Nota: a matemática de avanço de linha (`UltimaLinha = jp + UltimaLinha`)
    é exatamente a do VBA original — não "corrigimos" para um acúmulo mais
    intuitivo, porque isso mudaria o resultado numérico e não foi confirmado
    como bug.
    """
    ws_target = wb_destino.Sheets(sheet_destino)
    unmerge_all(ws_target)

    ultima_linha = 1
    for arquivo in arquivos:
        wb_source, ws_source = _abrir_fonte_e_copiar(session, arquivo)
        try:
            jp = last_row(ws_source, coluna_ultima_linha)
            col_ini, col_fim = faixa_colunas.split(":")
            faixa = f"{col_ini}1:{col_fim}{jp}"
            copy_paste_all(ws_source.Range(faixa), ws_target.Range(f"A{ultima_linha}"), session.app)
            ultima_linha = jp + ultima_linha
        finally:
            wb_source.Close(SaveChanges=False)


# --- steps de arquivo único (Exit Function após o primeiro match no VBA) ----

_STEP_SIMPLES = {
    "carteira_final": ("B:EE", "B1"),
    "carteira_inicial": ("B:EE", "B1"),
    "balancete_final": ("B:EE", "B1"),
}

# --- steps de acúmulo (loop sem Exit Function no VBA) ------------------------

_STEP_ACUMULADO = {
    "posicao_cotista": ("B", "A:AJ"),
    "mov_cotista": ("B", "A:AJ"),
}


def _mensagem_para(step: str, resultado: ResultadoMatch, pasta_insumos: Path) -> str | None:
    padrao = config.INSUMO_PATTERNS[step]
    if resultado.origem == "manual":
        return f"'{step}': ambiguidade resolvida manualmente -> {resultado.arquivos[0].name}"
    if resultado.origem == "fallback":
        nomes = ", ".join(p.name for p in resultado.arquivos)
        return (
            f"'{step}': padrão exato {padrao!r} não bateu, mas usei por fallback "
            f"(revisar): {nomes}"
        )
    if resultado.origem == "ambiguo":
        nomes = ", ".join(p.name for p in resultado.candidatos_ambiguos)
        return (
            f"'{step}': múltiplos candidatos ambíguos, nenhum escolhido automaticamente "
            f"(decida manualmente, ou rode com --interativo): {nomes}"
        )
    if resultado.origem == "nao_encontrado":
        return f"'{step}': insumo não encontrado (padrão: {padrao!r}) em {pasta_insumos}"
    return None  # "exato" -- sem aviso, comportamento igual ao VBA


def executar_batch_steps(
    session: ExcelSession,
    wb_destino,
    pasta_insumos: Path,
    resolver_ambiguidade: ResolverAmbiguidade | None = None,
) -> list[str]:
    """Executa config.BATCH_STEPS na ordem definida, na mesma ordem em que
    ProcessarEmLoop chama (Carteira final, Carteira inicial, Extrato,
    Balancete final, Posição_Cotista, Mov_Cotista).

    Retorna avisos para: insumo não encontrado, match resolvido só por
    fallback (pra auditoria — alguém deveria conferir que o arquivo certo
    foi usado), e candidatos ambíguos que ficaram de fora de propósito (a
    menos que `resolver_ambiguidade` resolva na hora — modo --interativo).
    """
    avisos: list[str] = []
    for step in config.BATCH_STEPS:
        resultado = resolver_insumo(pasta_insumos, step)

        if resultado.origem == "ambiguo" and resolver_ambiguidade is not None:
            escolhido = resolver_ambiguidade(step, resultado.candidatos_ambiguos)
            if escolhido is not None:
                resultado = ResultadoMatch(
                    arquivos=[escolhido], origem="manual", candidatos_ambiguos=resultado.candidatos_ambiguos
                )

        if resultado.arquivos:
            sheet = config.SHEET_DESTINO[step]
            if step == "extrato":
                arquivo = resultado.arquivos[0]
                ws_target = wb_destino.Sheets(sheet)
                unmerge_all(ws_target)
                wb_source, ws_source = _abrir_fonte_e_copiar(session, arquivo)
                try:
                    j = last_row(ws_source, "E")
                    copy_paste_all(ws_source.Range(f"A1:W{j}"), ws_target.Range("A1"), session.app)
                finally:
                    wb_source.Close(SaveChanges=False)
            elif step in _STEP_SIMPLES:
                faixa_origem, celula_destino = _STEP_SIMPLES[step]
                _copiar_um_arquivo(session, resultado.arquivos[0], wb_destino, sheet, faixa_origem, celula_destino)
            elif step in _STEP_ACUMULADO:
                coluna_ultima_linha, faixa_colunas = _STEP_ACUMULADO[step]
                _acumular_arquivos(session, resultado.arquivos, wb_destino, sheet, coluna_ultima_linha, faixa_colunas)

        mensagem = _mensagem_para(step, resultado, pasta_insumos)
        if mensagem:
            logger.warning(mensagem)
            avisos.append(mensagem)

    return avisos
