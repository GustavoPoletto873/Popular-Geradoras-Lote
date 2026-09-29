"""Esperas por estado (sem `sleep` fixo)."""

from __future__ import annotations

import time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from ..erros import TelaMudou


def frame_com_elemento(page: Page, seletor: str, *, timeout_ms: int, rodada_ms: int = 1_000):
    """Devolve a página ou o iframe em que `seletor` fica visível.

    A PAS carrega as telas em iframes que nascem depois da navegação; a cada rodada reavalia a lista de frames
    e espera *por estado* (`wait_for`) em cada candidato — não há pausa fixa.
    """
    limite = time.monotonic() + timeout_ms / 1000
    while True:
        candidatos = [page, *(f for f in page.frames if f != page.main_frame)]
        for alvo in candidatos:
            restante = int((limite - time.monotonic()) * 1000)
            if restante <= 0:
                break
            try:
                alvo.locator(seletor).first.wait_for(state="visible", timeout=min(rodada_ms, restante))
                return alvo
            except PlaywrightError:
                continue
        if time.monotonic() >= limite:
            raise TelaMudou(
                f"elemento {seletor!r} não apareceu na página principal nem em nenhum dos "
                f"{max(len(page.frames) - 1, 0)} iframe(s) em {timeout_ms} ms"
            )
