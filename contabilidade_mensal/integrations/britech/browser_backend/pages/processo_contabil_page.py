from __future__ import annotations

import logging

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, expect

from ...erros import CarteiraNaoEncontrada, SessaoBloqueada, TelaMudou
from .. import seletores as sel
from ..espera import frame_com_elemento

logger = logging.getLogger(__name__)


class ProcessoContabilPage:
    """Tela Processamento > Processo Contábil. As seleções no grid são CUMULATIVAS: o "Processar" é um clique só
    para o lote inteiro, depois de selecionar todas as carteiras."""

    def __init__(self, page: Page, base_url: str, *, timeout_ms: int) -> None:
        self.page = page
        self.base_url = base_url
        self.timeout_ms = timeout_ms
        self._frame = None

    def abrir(self) -> None:
        try:
            self.page.goto(self.base_url)
            self.page.locator(sel.MENU_PROCESSAMENTO).first.click()
            self.page.locator(sel.MENU_PROCESSO_CONTABIL).first.click()
        except PlaywrightError as exc:
            raise TelaMudou(f"menu Processamento > Processo Contábil não abriu: {type(exc).__name__}") from None
        self._frame = frame_com_elemento(self.page, sel.PC_FILTRO_CARTEIRA, timeout_ms=self.timeout_ms)
        logger.info("Processo Contábil aberto")

    @property
    def frame(self):
        if self._frame is None:
            raise RuntimeError("chame abrir() antes")
        return self._frame

    def _garantir_sessao(self, carteira_id: str) -> None:
        if self.page.locator(sel.LOGIN_USUARIO).count() > 0:
            raise SessaoBloqueada(f"a sessão caiu durante a seleção da carteira {carteira_id} (tela de login reapareceu)")

    def selecionar_carteira(self, carteira_id: str) -> None:
        carteira_id = str(carteira_id).strip()
        campo = self.frame.locator(sel.PC_FILTRO_CARTEIRA)
        try:
            campo.wait_for(state="visible", timeout=self.timeout_ms)
            campo.scroll_into_view_if_needed()
            campo.click()
            campo.fill("")
            campo.press_sequentially(carteira_id, delay=50)
            expect(campo).to_have_value(carteira_id, timeout=5_000)
            campo.blur()
        except (PlaywrightError, AssertionError):
            raise TelaMudou(f"o campo de filtro não recebeu o id {carteira_id!r}") from None

        resultado = self.frame.locator(sel.celula_com_titulo(carteira_id))
        try:
            resultado.first.wait_for(state="visible", timeout=self.timeout_ms)
        except PlaywrightError:
            self._garantir_sessao(carteira_id)
            raise CarteiraNaoEncontrada(f"a busca da carteira {carteira_id} não retornou resultado") from None
        quantidade = resultado.count()
        if quantidade != 1:
            raise CarteiraNaoEncontrada(f"esperado 1 resultado para a carteira {carteira_id}, encontrado {quantidade}")

        checkbox = self.frame.locator(sel.PC_CHECKBOX_PRIMEIRA_LINHA)
        checkbox.click()
        if checkbox.get_attribute("aria-checked") is None:
            logger.warning("checkbox sem aria-checked: não dá para confirmar a seleção da carteira %s", carteira_id)
        else:
            try:
                expect(checkbox).to_have_attribute("aria-checked", "true", timeout=5_000)
            except AssertionError:
                raise TelaMudou(f"a carteira {carteira_id} não ficou marcada após o clique") from None
        self._garantir_sessao(carteira_id)
        logger.info("carteira %s selecionada", carteira_id)

    def botao_processar_presente(self) -> bool:
        return self.frame.locator(sel.PC_BOTAO_PROCESSAR).count() > 0

    def clicar_processar(self) -> None:
        """Clique REAL em "Processar" — altera dados na Britech. Quem chama decide (dry-run/allowlist ficam no fluxo)."""
        if not self.botao_processar_presente():
            raise TelaMudou("botão 'Processar' (#btnRun) não encontrado")
        self.frame.locator(sel.PC_BOTAO_PROCESSAR).first.click()
