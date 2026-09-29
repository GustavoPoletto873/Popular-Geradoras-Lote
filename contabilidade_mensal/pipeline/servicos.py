"""Serviços de alto nível: criar execução (com cascata) e consolidar o status."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence

from django.db import transaction
from django.utils import timezone

from contabilidade_mensal.core.choices import (
    Etapa,
    StatusCompetencia,
    StatusEtapa,
    StatusExecucao,
)
from contabilidade_mensal.core.models import Competencia, EtapaExecucao, Execucao, Fundo

from . import parametros
from .definicao import ORDEM, a_jusante, planejar_etapa
from .estados import ESTADOS_ABERTOS

MOTIVO_DEPENDENCIA_FALHOU = "dependencia_falhou"


def obter_competencia(ano: int, mes: int) -> Competencia:
    competencia, _ = Competencia.objects.get_or_create(ano=ano, mes=mes)
    return competencia


@transaction.atomic
def criar_execucao(
    competencia: Competencia,
    fundos: Sequence[Fundo],
    *,
    etapas: Iterable[str] | None = None,
    disparada_por: str = "manual",
    forcar: bool = False,
    cascata: bool = False,
    agora: dt.datetime | None = None,
) -> Execucao:
    """Cria a execução e uma `EtapaExecucao` pendente por (fundo, etapa).

    - `etapas=None` → todas.
    - `forcar` → ignora a idempotência nas etapas pedidas (reprocesso).
    - `cascata` → também agenda, já forçadas, as etapas que dependem das pedidas
      (ex.: refazer `baixar_balancete` refaz `popular_excel` e `publicar_drive`).
    """
    agora = agora or timezone.now()
    validas = set(Etapa.values)
    pedidas = list(etapas) if etapas is not None else list(ORDEM)
    invalidas = [e for e in pedidas if e not in validas]
    if invalidas:
        raise ValueError(f"etapas desconhecidas: {invalidas}")

    por_cascata: set[str] = a_jusante(pedidas) - set(pedidas) if cascata else set()
    a_criar = [e for e in ORDEM if e in set(pedidas) | por_cascata]
    p = parametros.obter()

    execucao = Execucao.objects.create(
        competencia=competencia,
        disparada_por=disparada_por,
        escopo={"fundos": [f.pk for f in fundos], "etapas": list(a_criar)},
        forcar=forcar,
        cascata=cascata,
        iniciada_em=agora,
    )
    linhas = []
    for fundo in fundos:
        for etapa in a_criar:
            plano = planejar_etapa(etapa, fundo.administradora_id)
            linhas.append(
                EtapaExecucao(
                    execucao=execucao,
                    fundo=fundo,
                    etapa=etapa,
                    fila=plano.fila,
                    backend=plano.backend,
                    max_tentativas=p.max_tentativas,
                    forcar=forcar or etapa in por_cascata,
                    lock_key=plano.lock_key,
                    disponivel_em=agora,
                )
            )
    EtapaExecucao.objects.bulk_create(linhas)
    Competencia.objects.filter(pk=competencia.pk).update(status=StatusCompetencia.EM_EXECUCAO)
    return execucao


def atualizar_status_execucao(execucao: Execucao, *, agora: dt.datetime | None = None) -> str:
    """Consolida o status da execução (e da competência) a partir das etapas."""
    agora = agora or timezone.now()
    etapas = EtapaExecucao.objects.filter(execucao=execucao)
    if etapas.filter(status__in=list(ESTADOS_ABERTOS)).exists():
        status, fim = StatusExecucao.EM_ANDAMENTO, None
        status_competencia = StatusCompetencia.EM_EXECUCAO
    else:
        falhou = etapas.filter(status=StatusEtapa.FALHA).exists() or etapas.filter(
            status=StatusEtapa.PULADO, erro_tipo=MOTIVO_DEPENDENCIA_FALHOU
        ).exists()
        if falhou:
            status, status_competencia = StatusExecucao.CONCLUIDA_COM_FALHAS, StatusCompetencia.CONCLUIDA_COM_FALHAS
        else:
            status, status_competencia = StatusExecucao.CONCLUIDA, StatusCompetencia.CONCLUIDA
        fim = agora
    Execucao.objects.filter(pk=execucao.pk).update(status=status, finalizada_em=fim)
    Competencia.objects.filter(pk=execucao.competencia_id).update(status=status_competencia)
    return status
