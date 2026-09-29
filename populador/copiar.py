"""
Porte de `CopiarArquivoOrigem` (Sub_Main.bas): copia o arquivo do período
anterior (encontrado na pasta de origem) para a pasta de destino, renomeia,
abre e limpa as abas de dados antes de repopular.

BUG CORRIGIDO EM RELAÇÃO AO VBA ORIGINAL (confirmado com o usuário antes de
portar): em ProcessarEmLoop, a variável `extensaoArquivo` usada para reabrir
o arquivo depois de copiado nunca é atribuída naquele escopo (só existe uma
variável local homônima dentro de CopiarArquivoOrigem, sem relação com ela),
então o VBA tenta reabrir o arquivo sem extensão nenhuma (ex.:
"Fundo 202509" em vez de "Fundo 202509.xlsb"). Aqui, `copiar_arquivo_origem`
retorna a extensão real usada, e o chamador (runner.py) usa ela para montar
o caminho de reabertura corretamente.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import config, paths
from .excel_app import ExcelSession, clear_sheets

logger = logging.getLogger(__name__)


@dataclass
class ResultadoCopia:
    sucesso: bool
    extensao: str | None = None
    caminho_arquivo: Path | None = None
    mensagem: str = ""


def copiar_arquivo_origem(
    session: ExcelSession,
    pasta_origem: Path,
    fundo: str,
    pasta_destino: Path,
    periodo_destino: str,
) -> ResultadoCopia:
    arquivo_origem = paths.encontrar_arquivo_origem(pasta_origem)
    if arquivo_origem is None:
        return ResultadoCopia(
            sucesso=False,
            mensagem=f"Arquivo de origem não encontrado em {pasta_origem}",
        )

    extensao = arquivo_origem.suffix.lstrip(".")
    nome_destino = paths.nome_arquivo_destino(fundo, periodo_destino, extensao)
    caminho_destino = pasta_destino / nome_destino

    try:
        # No fluxo normal essa pasta já existe (é a mesma pasta dos insumos).
        # Quando a saída é redirecionada (--pasta-saida), a pasta ainda não
        # existe e precisa ser criada — mkdir com exist_ok não afeta o fluxo
        # normal.
        pasta_destino.mkdir(parents=True, exist_ok=True)
        if caminho_destino.exists():
            caminho_destino.unlink()
        shutil.copy2(arquivo_origem, caminho_destino)
    except OSError as exc:
        return ResultadoCopia(
            sucesso=False,
            mensagem=f"Falha ao copiar {arquivo_origem} -> {caminho_destino}: {exc}",
        )

    wb = None
    try:
        wb = session.open_workbook(caminho_destino, read_only=False)
        clear_sheets(wb, config.ABAS_PARA_LIMPAR)
        wb.Close(SaveChanges=True)
    except Exception as exc:
        if wb is not None:
            try:
                wb.Close(SaveChanges=False)
            except Exception:
                logger.warning("Falha ao fechar workbook após erro de limpeza.", exc_info=True)
        return ResultadoCopia(
            sucesso=False,
            mensagem=f"Falha ao abrir/limpar abas do arquivo copiado: {exc}",
        )

    return ResultadoCopia(sucesso=True, extensao=extensao, caminho_arquivo=caminho_destino)
