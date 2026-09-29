"""
Porte de `ProcessarEmLoop` (Sub_Main.bas). Orquestra: ler a aba Painel, para
cada fundo marcado com X, montar os caminhos, copiar o arquivo do período
anterior, popular as abas a partir dos insumos, salvar e escrever o status
de volta na coluna C — exatamente como o botão da planilha faz hoje.

Diferenças deliberadas em relação ao VBA original (todas confirmadas com o
usuário, ver histórico da conversa):
  1. Bug da extensão ao reabrir o arquivo copiado: CORRIGIDO (ver copiar.py).
  2. Insumo não encontrado: gera aviso no relatório em vez de falhar em
     silêncio.
  3. Isolamento de erro por fundo: um fundo com erro não trava os demais
     (o VBA original, por causa de um `On Error GoTo 0` no meio do loop,
     efetivamente pararia de tratar erros depois da primeira falha).
  4. Salva a aba Painel a cada fundo processado (não só no fim), para não
     perder o progresso se o processo for interrompido no meio de um lote
     grande — o VBA original só mantém isso em memória até alguém salvar
     manually.
"""

from __future__ import annotations

import csv
import datetime as dt
import logging
from dataclasses import dataclass, field
from pathlib import Path

from . import config, paths, painel, populate
from .excel_app import ExcelSession
from .fundo import popular_arquivo

logger = logging.getLogger(__name__)


@dataclass
class ResultadoFundo:
    linha: int
    fundo: str
    tipo: str
    exercicio: str
    status: str
    avisos: list[str] = field(default_factory=list)
    erro: str | None = None


def processar_fundo(
    session: ExcelSession,
    ws_painel,
    row: painel.FundoRow,
    params: painel.ParametrosGlobais,
    dry_run: bool,
    resolver_ambiguidade: "populate.ResolverAmbiguidadeFundo | None" = None,
    pasta_raiz_saida: str | None = None,
) -> ResultadoFundo:
    resultado = ResultadoFundo(
        linha=row.linha, fundo=row.fundo, tipo=row.tipo, exercicio=row.exercicio, status=""
    )

    caminhos = paths.montar_caminhos(
        pasta_raiz=params.pasta_raiz,
        tipo=row.tipo,
        fundo=row.fundo,
        exercicio=row.exercicio,
        periodo_origem=params.periodo_origem,
        periodo_destino=params.periodo_destino,
        pasta_raiz_saida=pasta_raiz_saida,
    )

    if paths.saida_ja_existe(caminhos.pasta_saida):
        resultado.status = config.STATUS_JA_EXISTE
        if not dry_run:
            painel.escrever_status(ws_painel, row.linha, resultado.status)
        return resultado

    if dry_run:
        resultado.status = "(dry-run) seria processado"
        return resultado

    resolver_do_step = None
    if resolver_ambiguidade is not None:
        resolver_do_step = lambda step, candidatos: resolver_ambiguidade(row.fundo, step, candidatos)

    populado = popular_arquivo(
        session,
        fundo=row.fundo,
        periodo_destino=params.periodo_destino,
        pasta_origem=caminhos.pasta_origem,
        pasta_insumos=caminhos.pasta_insumos,
        pasta_saida=caminhos.pasta_saida,
        resolver_ambiguidade=resolver_do_step,
    )
    resultado.status = populado.status
    resultado.avisos = populado.avisos
    resultado.erro = populado.erro
    painel.escrever_status(ws_painel, row.linha, resultado.status)
    return resultado


def processar_em_lote(
    caminho_painel: Path,
    dry_run: bool = False,
    apenas_fundo: str | None = None,
    visible: bool = False,
    relatorio_csv: Path | None = None,
    resolver_ambiguidade: "populate.ResolverAmbiguidadeFundo | None" = None,
    pasta_raiz_saida: str | None = None,
) -> list[ResultadoFundo]:
    resultados: list[ResultadoFundo] = []

    with ExcelSession(visible=visible) as session:
        wb_painel = session.open_workbook(caminho_painel, read_only=dry_run)
        try:
            ws = wb_painel.Sheets(config.SHEET_PAINEL)
            params = painel.ler_parametros_globais(ws)
            linhas = list(painel.iterar_fundos(ws))

            for row in linhas:
                if not row.marcado:
                    continue
                if apenas_fundo and row.fundo != apenas_fundo:
                    continue

                logger.info("Processando fundo: %s (linha %d)", row.fundo, row.linha)
                try:
                    resultado = processar_fundo(
                        session,
                        ws,
                        row,
                        params,
                        dry_run,
                        resolver_ambiguidade=resolver_ambiguidade,
                        pasta_raiz_saida=pasta_raiz_saida,
                    )
                except Exception as exc:
                    logger.exception("Falha inesperada processando %s", row.fundo)
                    resultado = ResultadoFundo(
                        linha=row.linha,
                        fundo=row.fundo,
                        tipo=row.tipo,
                        exercicio=row.exercicio,
                        status=config.STATUS_ERRO,
                        erro=str(exc),
                    )
                    if not dry_run:
                        try:
                            painel.escrever_status(ws, row.linha, resultado.status)
                        except Exception:
                            logger.warning("Falha ao gravar status de erro na planilha.", exc_info=True)

                resultados.append(resultado)

                if not dry_run:
                    wb_painel.Save()
        finally:
            wb_painel.Close(SaveChanges=not dry_run)

    if relatorio_csv is not None:
        _gravar_relatorio_csv(relatorio_csv, resultados)

    return resultados


def _gravar_relatorio_csv(caminho: Path, resultados: list[ResultadoFundo]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    novo = not caminho.exists()
    with caminho.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        if novo:
            writer.writerow(["timestamp", "linha", "fundo", "tipo", "exercicio", "status", "avisos", "erro"])
        agora = dt.datetime.now().isoformat(timespec="seconds")
        for r in resultados:
            writer.writerow(
                [agora, r.linha, r.fundo, r.tipo, r.exercicio, r.status, " | ".join(r.avisos), r.erro or ""]
            )
