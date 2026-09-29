"""Watchdog de processos órfãos (EXCEL.EXE de automação e Chromium do Playwright) e de travas vencidas.

Só toca em processos que são INEQUIVOCAMENTE nossos:
  - Excel: instância iniciada por automação COM (`/automation` e `-embedding` na linha de comando) — o Excel que
    alguém abriu com duplo clique nunca casa;
  - Chromium: executável dentro de uma pasta `ms-playwright`.
E só se (a) tem mais de `idade_min_s` de vida e (b) NENHUMA etapa da fila correspondente está em andamento
(conservador: com etapa rodando, qualquer instância pode ser a dela).
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from django.utils import timezone

from contabilidade_mensal.core.choices import StatusEtapa
from contabilidade_mensal.core.models import EtapaExecucao, TravaRecurso

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Processo:
    pid: int
    nome: str
    tipo: str  # "excel" | "chromium"
    idade_s: float
    cmdline: str


def _classificar(nome: str, exe: str, cmdline: str) -> str | None:
    minusculo_cmd = cmdline.lower()
    if nome.lower() == "excel.exe" and "/automation" in minusculo_cmd and "-embedding" in minusculo_cmd:
        return "excel"
    if "ms-playwright" in exe.lower().replace("\\", "/"):
        return "chromium"
    return None


def listar_processos(iterador: Callable[[], Iterable] | None = None, agora: float | None = None) -> list[Processo]:
    import psutil

    agora = agora if agora is not None else time.time()
    achados: list[Processo] = []
    for p in (iterador or (lambda: psutil.process_iter(["pid", "name", "exe", "cmdline", "create_time"])))():
        try:
            info = p.info if hasattr(p, "info") else p
            cmd = " ".join(info.get("cmdline") or [])
            tipo = _classificar(info.get("name") or "", info.get("exe") or "", cmd)
            if tipo:
                achados.append(Processo(info["pid"], info["name"], tipo, agora - info["create_time"], cmd[:200]))
        except Exception:  # noqa: BLE001 - processo que morreu/negou acesso durante a varredura
            continue
    return achados


def fila_ativa(tipo: str) -> bool:
    filas = {"excel": ["excel"], "chromium": ["browser"]}[tipo]
    return EtapaExecucao.objects.filter(fila__in=filas, status=StatusEtapa.EM_ANDAMENTO).exists()


def orfaos(processos: Iterable[Processo], *, idade_min_s: float) -> list[Processo]:
    ativas = {tipo: fila_ativa(tipo) for tipo in ("excel", "chromium")}
    return [p for p in processos if p.idade_s >= idade_min_s and not ativas[p.tipo]]


def encerrar(processos: Iterable[Processo], matar: Callable[[int], None] | None = None) -> list[int]:
    if matar is None:
        import psutil

        def matar(pid: int) -> None:
            psutil.Process(pid).kill()

    encerrados: list[int] = []
    for p in processos:
        try:
            matar(p.pid)
            encerrados.append(p.pid)
            logger.warning("processo órfão encerrado", extra={"pid": p.pid, "tipo": p.tipo, "idade_s": int(p.idade_s)})
        except Exception:  # noqa: BLE001
            logger.warning("não foi possível encerrar o processo %s", p.pid, exc_info=True)
    return encerrados


def limpar_travas_vencidas(*, agora: dt.datetime | None = None) -> int:
    agora = agora or timezone.now()
    apagadas, _ = TravaRecurso.objects.filter(lease_ate__lt=agora).delete()
    return apagadas
