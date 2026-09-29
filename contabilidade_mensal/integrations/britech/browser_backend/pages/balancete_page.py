from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, expect

from ...erros import ArquivoInvalido, CarteiraNaoEncontrada, SessaoBloqueada, TelaMudou
from .. import seletores as sel

logger = logging.getLogger(__name__)


def so_digitos(texto: str) -> str:
    return "".join(c for c in (texto or "") if c.isdigit())


class BalanceteContabilPage:
    """Tela de relatório legal *Balancete Contábil*. Uma carteira por vez (marcar várias gera .zip)."""

    def __init__(self, page: Page, base_url: str, *, timeout_ms: int, timeout_download_ms: int = 60_000) -> None:
        self.page = page
        self.url = f"{base_url}/{sel.BAL_CAMINHO}"
        self.timeout_ms = timeout_ms
        self.timeout_download_ms = timeout_download_ms

    def abrir(self) -> None:
        try:
            self.page.goto(self.url)
            self.page.locator(sel.BAL_ABRIR_DROPDOWN).wait_for(state="visible", timeout=self.timeout_ms)
        except PlaywrightError:
            self._garantir_sessao()
            raise TelaMudou("a tela de Balancete Contábil não abriu como esperado") from None

    def _garantir_sessao(self) -> None:
        if self.page.locator(sel.LOGIN_USUARIO).count() > 0:
            raise SessaoBloqueada("a sessão caiu (tela de login reapareceu)")

    def _marcar(self, carteira_id: str, marcar: bool) -> None:
        filtro = self.page.locator(sel.BAL_FILTRO_CARTEIRA)
        checkbox = self.page.locator(sel.BAL_CHECKBOX_PRIMEIRA_LINHA)
        try:
            filtro.wait_for(state="visible", timeout=self.timeout_ms)
            filtro.click()
            filtro.press("Control+a")
            filtro.press("Delete")
            filtro.fill(carteira_id)
            filtro.press("Enter")
        except PlaywrightError:
            raise TelaMudou("o filtro de carteira do balancete não respondeu") from None
        # prova de que a tabela já refletiu o filtro: existe a célula com o id (evita clicar numa linha velha)
        try:
            self.page.locator(f"{sel.BAL_GRID} {sel.celula_com_titulo(carteira_id)}").first.wait_for(
                state="visible", timeout=self.timeout_ms
            )
        except PlaywrightError:
            self._garantir_sessao()
            raise CarteiraNaoEncontrada(f"a carteira {carteira_id} não apareceu na lista do balancete") from None
        checkbox.click()
        if checkbox.get_attribute("aria-checked") is not None:
            try:
                expect(checkbox).to_have_attribute("aria-checked", "true" if marcar else "false", timeout=5_000)
            except AssertionError:
                estado = "marcado" if marcar else "desmarcado"
                raise TelaMudou(f"o checkbox da carteira {carteira_id} não ficou {estado}") from None

    def selecionar_carteira(self, carteira_id: str, *, desmarcar: str | None = None) -> None:
        """Seleciona `carteira_id`; se `desmarcar` for dado, tira antes a marca da carteira anterior."""
        self.page.locator(sel.BAL_ABRIR_DROPDOWN).click()
        if desmarcar:
            self._marcar(str(desmarcar), marcar=False)
        self._marcar(str(carteira_id), marcar=True)
        self.page.keyboard.press("Enter")
        self._garantir_sessao()

    def _preencher_data(self, seletor: str, valor: str) -> None:
        campo = self.page.locator(seletor)
        try:
            campo.click()
            campo.press("Control+a")
            campo.press("Delete")
            campo.press_sequentially(so_digitos(valor))
            campo.press("Tab")
        except PlaywrightError:
            raise TelaMudou(f"o campo {seletor} não aceitou a data") from None
        if so_digitos(campo.input_value()) != so_digitos(valor):
            raise TelaMudou(f"o campo {seletor} ficou com {campo.input_value()!r} em vez de {valor!r}")

    def preencher_periodo(self, inicio: str, fim: str) -> None:
        """Datas no formato dd/mm/aaaa."""
        self._preencher_data(sel.BAL_DATA_INICIO, inicio)
        self._preencher_data(sel.BAL_DATA_FIM, fim)

    def _baixar(self, seletor_botao: str, destino: Path) -> Path:
        try:
            with self.page.expect_download(timeout=self.timeout_download_ms) as info:
                self.page.click(seletor_botao)
            info.value.save_as(str(destino))
        except PlaywrightError:
            self._garantir_sessao()
            raise ArquivoInvalido(f"o download do botão {seletor_botao} não veio") from None
        if not destino.is_file() or destino.stat().st_size == 0:
            raise ArquivoInvalido(f"arquivo baixado vazio: {destino.name}")
        self._garantir_sessao()
        return destino

    def baixar_pdf(self, destino: Path) -> Path:
        return self._baixar(sel.BAL_BOTAO_PDF, destino)

    def baixar_excel(self, destino: Path) -> Path:
        return self._baixar(sel.BAL_BOTAO_EXCEL, destino)
