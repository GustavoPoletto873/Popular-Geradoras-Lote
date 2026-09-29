"""Fluxo "Processar Contábil": seleciona as carteiras do lote e (só se autorizado) clica em Processar.

Regras de segurança (esta é a operação que ALTERA dados reais na Britech):
  - o clique só acontece com `dry_run=False`; a autorização por allowlist é conferida ANTES, em `BrowserBackend`;
  - se QUALQUER carteira do lote falhar na seleção, nada é processado (a exceção sobe antes do clique).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from ...erros import SessaoBloqueada
from ...interface import ResultadoDisparo
from .. import seletores as sel
from ..pages.processo_contabil_page import ProcessoContabilPage

logger = logging.getLogger(__name__)


def disparar_processamento(
    page: Page, base_url: str, carteiras: Sequence[str], *, dry_run: bool, timeout_ms: int
) -> ResultadoDisparo:
    pagina = ProcessoContabilPage(page, base_url, timeout_ms=timeout_ms)
    pagina.abrir()
    for carteira in carteiras:
        pagina.selecionar_carteira(carteira)

    if dry_run:
        logger.warning("dry-run: %s carteira(s) selecionada(s), 'Processar' NÃO foi clicado", len(carteiras))
        return ResultadoDisparo(tuple(carteiras), True)

    logger.info("clicando em 'Processar' para %s carteira(s)", len(carteiras))
    pagina.clicar_processar()
    try:  # melhor-esforço: deixa o pedido de processamento sair antes de o worker seguir e fazer logout
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PlaywrightError:
        logger.info("a página não ficou ociosa em 10 s após o clique; seguindo")
    if page.locator(sel.LOGIN_USUARIO).count() > 0:
        raise SessaoBloqueada("a sessão caiu logo após clicar em 'Processar'; o processamento pode não ter sido aceito")
    return ResultadoDisparo(tuple(carteiras), False)
