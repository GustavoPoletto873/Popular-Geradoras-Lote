from __future__ import annotations

import logging

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from ...erros import AutenticacaoFalhou, SessaoBloqueada, TelaMudou
from .. import seletores as sel

logger = logging.getLogger(__name__)


def _sem_segredos(texto: str, segredos: tuple[str, ...]) -> str:
    """O log de chamadas do Playwright em mensagens de erro inclui o argumento do `fill(...)`: tira a senha."""
    for segredo in segredos:
        if segredo:
            texto = texto.replace(segredo, "***")
    return texto


class LoginPage:
    def __init__(self, page: Page, base_url: str, *, timeout_ms: int, tentativas_logout: int = 3) -> None:
        self.page = page
        self.base_url = base_url
        self.timeout_ms = timeout_ms
        self.tentativas_logout = tentativas_logout

    def sessao_ativa(self) -> bool:
        return self.page.locator(sel.LOGIN_USUARIO).count() == 0

    def entrar(self, usuario: str, senha: str) -> None:
        logger.info("login: abrindo %s", self.base_url)
        try:
            self.page.goto(self.base_url)
            self.page.fill(sel.LOGIN_USUARIO, usuario)
            self.page.fill(sel.LOGIN_SENHA, senha)
            self.page.press(sel.LOGIN_SENHA, "Enter")
        except PlaywrightError as exc:
            # sem `from exc`: a cadeia guardaria a mensagem original (com a senha) no traceback
            raise TelaMudou(
                f"tela de login não respondeu como esperado: {_sem_segredos(str(exc), (senha, usuario))}"
            ) from None

        try:
            self.page.locator(sel.MENU_PROCESSAMENTO).first.wait_for(state="visible", timeout=self.timeout_ms)
        except PlaywrightError:
            if self.page.locator(sel.LOGIN_USUARIO).count() > 0:
                # continua na tela de login: usuário/senha recusados (ou sessão presa) — NUNCA repetir sozinho
                raise AutenticacaoFalhou("login recusado: a tela de login continua aberta") from None
            raise TelaMudou("login aparentemente concluído, mas o menu 'Processamento' não apareceu") from None
        logger.info("login confirmado")

    def sair(self) -> None:
        """Logout CONFIRMADO (a tela de login reapareceu). Se não confirmar, a sessão pode ficar presa na Britech."""
        if not self.sessao_ativa():
            logger.info("sessão já estava encerrada")
            return
        ultimo: Exception | None = None
        for tentativa in range(1, self.tentativas_logout + 1):
            try:
                botao = self.page.locator(sel.LINK_SAIR).first
                if not botao.is_visible():
                    self.page.goto(self.base_url)
                    if not self.sessao_ativa():
                        return
                botao.wait_for(state="visible", timeout=self.timeout_ms)
                botao.click()
                self.page.locator(sel.LOGIN_USUARIO).wait_for(state="visible", timeout=self.timeout_ms)
                logger.info("logout confirmado")
                return
            except PlaywrightError as exc:
                ultimo = exc
                logger.warning("falha ao sair (tentativa %s/%s)", tentativa, self.tentativas_logout)
        raise SessaoBloqueada(
            f"logout não confirmado após {self.tentativas_logout} tentativas; a sessão pode ter ficado presa"
        ) from ultimo
