"""Worker: reivindica etapas de UMA fila e as executa.

Sem threads nesta fase: o lease (300 s por padrão) cobre etapas curtas. O heartbeat
automático para etapas longas (renovar_lease em segundo plano) fica para a Fase 7.
"""

from __future__ import annotations

import logging
import os
import socket
import time
from collections.abc import Callable, Mapping, Sequence

from django.db.models import Min
from django.utils import timezone

from contabilidade_mensal.core.choices import StatusEtapa
from contabilidade_mensal.core.models import EtapaExecucao

from . import executor, fila, travas
from .relogio import RelogioSimulado
from .tipos import Handler

logger = logging.getLogger(__name__)


def worker_id_padrao(fila_nome: str) -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{fila_nome}"


class Worker:
    def __init__(
        self,
        fila_nome: str,
        handlers: Mapping[str, Handler],
        *,
        worker_id: str | None = None,
        lote: int = 1,
        relogio: Callable = timezone.now,
    ) -> None:
        self.fila = fila_nome
        self.handlers = handlers
        self.worker_id = worker_id or worker_id_padrao(fila_nome)
        self.lote = lote
        self.relogio = relogio

    def ciclo(self) -> int:
        """Um ciclo: recupera órfãs, reivindica um lote e o executa. Devolve quantas etapas rodou."""
        agora = self.relogio()
        fila.recuperar_orfas(agora=agora)
        etapas = fila.reivindicar(self.fila, self.worker_id, limite=self.lote, agora=agora)
        try:
            for etapa in etapas:
                try:
                    executor.executar(etapa, self.handlers, relogio=self.relogio)
                except Exception:  # noqa: BLE001 - o lease recupera a etapa; o worker segue vivo
                    logger.exception("falha ao executar etapa", extra={"etapa_execucao_id": etapa.pk})
        finally:
            for chave in {e.lock_key for e in etapas if e.lock_key}:
                travas.liberar(chave, self.worker_id)
        return len(etapas)

    def rodar(
        self,
        *,
        intervalo_s: float = 5.0,
        parar_quando_vazio: bool = False,
        max_ciclos: int | None = None,
        dormir: Callable[[float], None] = time.sleep,
    ) -> int:
        executadas = 0
        ciclos = 0
        while max_ciclos is None or ciclos < max_ciclos:
            ciclos += 1
            n = self.ciclo()
            executadas += n
            if n == 0:
                if parar_quando_vazio:
                    break
                dormir(intervalo_s)
        return executadas


def drenar(
    filas: Sequence[str],
    handlers: Mapping[str, Handler],
    relogio: RelogioSimulado,
    *,
    max_ciclos: int = 1000,
) -> int:
    """Roda todos os workers em rodízio até não haver mais trabalho, avançando o relógio simulado
    até o próximo `disponivel_em` quando só restam esperas (backoff/polling). Útil em testes e no demo."""
    workers = [Worker(f, handlers, worker_id=f"drenar:{f}", relogio=relogio) for f in filas]
    total = 0
    for _ in range(max_ciclos):
        feitas = sum(w.ciclo() for w in workers)
        total += feitas
        if feitas:
            continue
        proximo = EtapaExecucao.objects.filter(
            status__in=[StatusEtapa.PENDENTE, StatusEtapa.AGUARDANDO_BRITECH],
            fila__in=list(filas),
            disponivel_em__gt=relogio(),
        ).aggregate(m=Min("disponivel_em"))["m"]
        if proximo is None:
            break  # nada a esperar; o que sobrou está bloqueado por dependência/disjuntor
        relogio.avancar_para(proximo)
    return total
