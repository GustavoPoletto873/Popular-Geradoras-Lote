"""Heartbeat: renova, em segundo plano, o lease das etapas em andamento e das travas de credencial.

Sem isso, uma etapa mais longa que `lease_segundos` (300 s) seria "recuperada" por outro worker enquanto ainda roda
(duas sessões na mesma credencial, dois Excel na mesma boleta). O heartbeat morre com o processo: se o worker cai,
o lease vence e `recuperar_orfas` devolve a etapa à fila — que é exatamente o comportamento desejado.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence

from django.db import connection

from contabilidade_mensal.core.models import EtapaExecucao

from . import fila, parametros, travas

logger = logging.getLogger(__name__)


class Heartbeat:
    def __init__(self, etapas: Sequence[EtapaExecucao], worker_id: str, *, intervalo_s: float | None = None) -> None:
        self._etapas = list(etapas)
        self._worker_id = worker_id
        self._intervalo_s = intervalo_s
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self.renovacoes = 0

    def _intervalo(self) -> float:
        return self._intervalo_s or max(1.0, parametros.obter().lease_segundos / 3)

    def __enter__(self) -> "Heartbeat":
        if self._etapas:
            self._thread = threading.Thread(target=self._loop, name="heartbeat", daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._parar.set()
        if self._thread is not None:
            self._thread.join(timeout=self._intervalo() + 10)

    def _loop(self) -> None:
        try:
            p = parametros.obter()
            chaves = {e.lock_key for e in self._etapas if e.lock_key}
            while not self._parar.wait(self._intervalo()):
                try:
                    for etapa in self._etapas:
                        fila.renovar_lease(etapa, self._worker_id)  # etapa já terminada: filtro de status devolve False
                    for chave in chaves:
                        travas.renovar(chave, self._worker_id, lease_s=p.lease_segundos)
                    self.renovacoes += 1
                except Exception:  # noqa: BLE001 - uma falha de banco não pode matar o worker; a próxima volta tenta de novo
                    logger.warning("falha ao renovar lease", exc_info=True)
        finally:
            connection.close()  # a conexão desta thread é só dela
