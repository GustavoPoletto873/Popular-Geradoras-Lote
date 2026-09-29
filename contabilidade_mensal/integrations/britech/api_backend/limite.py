"""Limite de taxa (token bucket) por administradora para a API da Britech.

Os limites reais da Britech são desconhecidos (Q10), então o padrão é conservador e configurável
(`settings.BRITECH_API = {"rps": ..., "burst": ...}`; `rps = 0` desliga). Um 429 da Britech esvazia o balde pelo
tempo de `Retry-After`, para todos os workers do processo esperarem juntos.

Escopo: por PROCESSO. Com vários workers `api` no mesmo host, o limite efetivo é a soma; comece com um worker `api`
(ou divida `rps` pelo número de workers).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class TokenBucket:
    def __init__(
        self,
        taxa_por_s: float,
        capacidade: int,
        *,
        relogio: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        if taxa_por_s <= 0 or capacidade < 1:
            raise ValueError("taxa e capacidade devem ser positivas")
        self._taxa, self._capacidade = float(taxa_por_s), float(capacidade)
        self._relogio, self._dormir = relogio, dormir
        self._tokens = float(capacidade)
        self._atualizado = relogio()
        self._trava = threading.Lock()

    def _repor(self) -> None:
        agora = self._relogio()
        self._tokens = min(self._capacidade, self._tokens + (agora - self._atualizado) * self._taxa)
        self._atualizado = agora

    def adquirir(self, n: float = 1.0) -> float:
        """Bloqueia até haver `n` tokens. Devolve quantos segundos esperou."""
        esperou = 0.0
        while True:
            with self._trava:
                self._repor()
                if self._tokens >= n:
                    self._tokens -= n
                    return esperou
                falta = (n - self._tokens) / self._taxa
            self._dormir(falta)
            esperou += falta

    def penalizar(self, segundos: float) -> None:
        """Depois de um 429: fica sem tokens por `segundos` (ninguém do processo chama a Britech nesse tempo)."""
        with self._trava:
            self._repor()
            self._tokens = -segundos * self._taxa


_BALDES: dict[str, TokenBucket] = {}
_TRAVA_REGISTRO = threading.Lock()


def balde_da_administradora(url_adm: str) -> TokenBucket | None:
    """Balde compartilhado (por processo) da administradora, conforme `settings.BRITECH_API`; None se desligado."""
    try:
        from django.conf import settings

        cfg = dict(getattr(settings, "BRITECH_API", {}) or {})
    except Exception:  # noqa: BLE001 - fora do Django não há limite
        return None
    rps, burst = float(cfg.get("rps", 0) or 0), int(cfg.get("burst", 1) or 1)
    if rps <= 0:
        return None
    with _TRAVA_REGISTRO:
        chave = f"{url_adm}:{rps}:{burst}"
        if chave not in _BALDES:
            _BALDES[chave] = TokenBucket(rps, burst)
        return _BALDES[chave]
