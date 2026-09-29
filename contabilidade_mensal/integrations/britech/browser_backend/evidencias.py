"""Evidência de falha: screenshot e trace do Playwright. Ambos são artefatos SENSÍVEIS (mostram dados de fundos).

O trace só é iniciado DEPOIS do login (session.py), então não contém o `fill` da senha.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from pathlib import Path

from playwright.sync_api import BrowserContext, Page

logger = logging.getLogger(__name__)


def _slug(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", texto)[:80] or "sem_nome"


def _carimbo() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def salvar_screenshot(page: Page, pasta: Path, rotulo: str) -> Path | None:
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        caminho = pasta / f"erro_{_slug(rotulo)}_{_carimbo()}.png"
        page.screenshot(path=str(caminho), full_page=True)
        return caminho
    except Exception:  # noqa: BLE001 - evidência é melhor-esforço, nunca esconde o erro original
        logger.warning("não foi possível salvar o screenshot", exc_info=True)
        return None


def salvar_trace(contexto: BrowserContext, pasta: Path, rotulo: str) -> Path | None:
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        caminho = pasta / f"trace_{_slug(rotulo)}_{_carimbo()}.zip"
        contexto.tracing.stop_chunk(path=str(caminho))
        contexto.tracing.start_chunk()
        return caminho
    except Exception:  # noqa: BLE001
        logger.warning("não foi possível salvar o trace", exc_info=True)
        return None
