"""Verificação de ponta a ponta da sessão de navegador, SEM alterar nada na Britech.

Usada pelo comando `testar_navegador_britech` e pelo teste `@pytest.mark.browser`. Nunca seleciona carteira nem clica
em "Processar": só faz login, abre as duas telas e sai, `repeticoes` vezes, e confere que cada logout foi confirmado.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..interface import AdministradoraRef
from .backend import BrowserBackend
from .pages.balancete_page import BalanceteContabilPage
from .pages.processo_contabil_page import ProcessoContabilPage


@dataclass(frozen=True)
class ResultadoRepeticao:
    numero: int
    segundos: float


def _abrir_telas(page, base_url: str, timeout_ms: int) -> None:
    ProcessoContabilPage(page, base_url, timeout_ms=timeout_ms).abrir()
    BalanceteContabilPage(page, base_url, timeout_ms=timeout_ms).abrir()


def verificar_sessao(
    backend: BrowserBackend, administradora: AdministradoraRef, *, repeticoes: int = 1, timeout_ms: int = 30_000
) -> list[ResultadoRepeticao]:
    """Levanta a `BritechErro` da primeira falha (o logout é tentado mesmo assim)."""
    resultados: list[ResultadoRepeticao] = []
    for numero in range(1, repeticoes + 1):
        inicio = time.monotonic()
        sessao = backend.abrir_sessao(administradora)
        try:
            sessao.executar("diagnostico", lambda page, base: _abrir_telas(page, base, timeout_ms))
        finally:
            sessao.fechar()  # se o logout não confirmar, SessaoBloqueada sobe (e interrompe a série)
        resultados.append(ResultadoRepeticao(numero, round(time.monotonic() - inicio, 1)))
    return resultados
