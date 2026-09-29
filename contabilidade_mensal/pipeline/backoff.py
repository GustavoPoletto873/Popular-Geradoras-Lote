"""Backoff exponencial com jitter (função pura)."""

from __future__ import annotations

import random
from collections.abc import Callable


def calcular_backoff(
    tentativa: int,
    *,
    base_s: float,
    teto_s: float,
    jitter: float = 0.0,
    aleatorio: Callable[[], float] = random.random,
) -> float:
    """Espera (s) antes da próxima tentativa. `tentativa` é o nº da tentativa que acabou de falhar (1, 2, …).

    espera = min(teto, base * 2^(tentativa-1)), ±jitter (fração), sem nunca passar do teto.
    """
    espera = min(teto_s, base_s * (2 ** max(0, tentativa - 1)))
    if jitter:
        espera *= 1 + jitter * (2 * aleatorio() - 1)
    return max(0.0, min(espera, teto_s))
