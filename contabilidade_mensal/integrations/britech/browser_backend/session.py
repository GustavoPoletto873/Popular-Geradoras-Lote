"""Sessão de navegador na PAS: login e logout CONFIRMADOS, trace só depois do login, evidência em falha.

Por que uma thread dedicada: a API síncrona do Playwright mantém um event loop rodando na thread que a usou, e o
Django ORM recusa consultas em thread com loop ativo (`SynchronousOnlyOperation`). O worker precisa gravar no banco
entre uma ação de navegador e outra, então TODO acesso ao Playwright acontece numa thread própria (`_pool`), e o
resto do programa só chama `executar(...)`.

Segredos: a senha só passa por `LoginPage.entrar`; o trace é iniciado depois disso, e as mensagens de erro do
login têm a senha removida.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, TypeVar

from playwright.sync_api import BrowserContext, Page, sync_playwright

from ..erros import BritechErro, SessaoBloqueada
from ..interface import AdministradoraRef
from .config import ConfigNavegador, url_pas
from .evidencias import salvar_screenshot, salvar_trace
from .pages.login_page import LoginPage

logger = logging.getLogger(__name__)

T = TypeVar("T")


class SessaoNavegador:
    def __init__(
        self,
        administradora: AdministradoraRef,
        usuario: str,
        senha: str,
        config: ConfigNavegador,
        *,
        preparar_contexto: Callable[[BrowserContext], None] | None = None,
    ) -> None:
        self.administradora = administradora
        self.config = config
        self.base_url = url_pas(administradora.url_adm)
        self.evidencias: list[Path] = []
        self._usuario, self._senha = usuario, senha
        self._preparar_contexto = preparar_contexto
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="playwright")
        self._pw = self._browser = self._context = self._page = None
        self._logado = False
        self._fechada = False

    def __repr__(self) -> str:  # nunca inclui credenciais
        return f"<SessaoNavegador {self.administradora.nome} logado={self._logado}>"

    # --- ciclo de vida ------------------------------------------------------------------------------------------

    def abrir(self) -> "SessaoNavegador":
        try:
            self._pool.submit(self._abrir).result()
        except BaseException:
            self._pool.submit(self._liberar).result()
            self._pool.shutdown(wait=True)
            self._fechada = True
            raise
        return self

    def _abrir(self) -> None:
        cfg = self.config
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=cfg.headless)
        self._context = self._browser.new_context(accept_downloads=True)
        self._context.set_default_timeout(cfg.timeout_ms)
        if self._preparar_contexto:
            self._preparar_contexto(self._context)
        self._page = self._context.new_page()
        login = LoginPage(self._page, self.base_url, timeout_ms=cfg.timeout_ms, tentativas_logout=cfg.tentativas_logout)
        try:
            login.entrar(self._usuario, self._senha)
        except BritechErro:
            self._evidencia_de_falha("login")
            raise
        self._logado = True
        # o trace começa DEPOIS do login: assim ele não registra o preenchimento da senha
        self._context.tracing.start(screenshots=True, snapshots=True)

    def executar(self, rotulo: str, funcao: Callable[[Page, str], T]) -> T:
        """Roda `funcao(page, base_url)` na thread do navegador. Em erro, guarda screenshot + trace em `evidencias`."""
        if self._fechada:
            raise SessaoBloqueada("sessão de navegador já encerrada")

        def _rodar() -> T:
            try:
                return funcao(self._page, self.base_url)
            except BaseException:
                self._evidencia_de_falha(rotulo)
                raise

        return self._pool.submit(_rodar).result()

    def _evidencia_de_falha(self, rotulo: str) -> None:
        pasta = self.config.pasta_evidencias
        nome = f"{self.administradora.url_adm}_{rotulo}"
        if self._page is not None:
            caminho = salvar_screenshot(self._page, pasta, nome)
            if caminho:
                self.evidencias.append(caminho)
        if self._logado and self._context is not None:
            caminho = salvar_trace(self._context, pasta, nome)
            if caminho:
                self.evidencias.append(caminho)

    def fechar(self) -> None:
        """Logout confirmado + encerra tudo. Idempotente. Se o logout não confirmar, fecha o resto e lança
        `SessaoBloqueada` (a credencial pode ficar presa na Britech: quem chama deve alertar)."""
        if self._fechada:
            return
        self._fechada = True
        try:
            self._pool.submit(self._encerrar).result()
        finally:
            self._pool.shutdown(wait=True)

    def _encerrar(self) -> None:
        erro: BritechErro | None = None
        if self._logado and self._page is not None:
            login = LoginPage(
                self._page, self.base_url, timeout_ms=self.config.timeout_ms, tentativas_logout=self.config.tentativas_logout
            )
            try:
                login.sair()
                self._logado = False
            except BritechErro as exc:
                self._evidencia_de_falha("logout")
                erro = exc
        self._liberar()
        if erro:
            raise erro

    def _liberar(self) -> None:
        """Descarta trace (sucesso = sem evidência), contexto, navegador e Playwright. Nunca lança."""
        passos: list[tuple[str, Callable[[], Any]]] = []
        if self._context is not None and self._logado:
            passos.append(("trace", lambda: self._context.tracing.stop()))
        if self._context is not None:
            passos.append(("contexto", self._context.close))
        if self._browser is not None:
            passos.append(("navegador", self._browser.close))
        if self._pw is not None:
            passos.append(("playwright", self._pw.stop))
        for nome, passo in passos:
            try:
                passo()
            except Exception:  # noqa: BLE001
                logger.warning("falha ao encerrar %s", nome, exc_info=True)
        self._pw = self._browser = self._context = self._page = None
