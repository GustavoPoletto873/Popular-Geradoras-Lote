"""Relógio controlável para testes e simulações (backoff/polling sem esperar de verdade)."""

from __future__ import annotations

import datetime as dt

from django.utils import timezone


class RelogioSimulado:
    def __init__(self, inicio: dt.datetime | None = None) -> None:
        self._agora = inicio or timezone.now()

    def __call__(self) -> dt.datetime:
        return self._agora

    def avancar(self, segundos: float) -> dt.datetime:
        self._agora += dt.timedelta(seconds=segundos)
        return self._agora

    def avancar_para(self, momento: dt.datetime) -> dt.datetime:
        if momento > self._agora:
            self._agora = momento
        return self._agora
