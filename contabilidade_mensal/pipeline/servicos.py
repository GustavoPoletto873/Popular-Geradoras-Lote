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
from contabilidade_mensal.core.models import Competencia, EstadoEtapa, EtapaExecucao, Execucao, Fundo

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
    anterior = Execucao.objects.filter(pk=execucao.pk).values_list("status", flat=True).first()
    Execucao.objects.filter(pk=execucao.pk).update(status=status, finalizada_em=fim)
    Competencia.objects.filter(pk=execucao.competencia_id).update(status=status_competencia)
    if anterior == StatusExecucao.EM_ANDAMENTO and status != StatusExecucao.EM_ANDAMENTO:
        from . import notificacoes  # import tardio: notificacoes usa os modelos e este módulo é importado por fila

        notificacoes.execucao_concluida(execucao, status, agora=agora)
    return status


# --- escolha de fundos e competência (usadas por `iniciar_execucao`) -------------------------------------------------


def competencia_anterior(hoje: dt.date) -> tuple[int, int]:
    """Competência "auto": o mês fechado que precede o mês de `hoje` (rodando em setembro, fecha agosto)."""
    ultimo_do_anterior = hoje.replace(day=1) - dt.timedelta(days=1)
    return ultimo_do_anterior.year, ultimo_do_anterior.month


def fundos_elegiveis(
    *, administradora: str | None = None, codigos: Sequence[str] | None = None
) -> tuple[list[Fundo], list[tuple[Fundo, str]]]:
    """Fundos ativos separados em (aptos, incompletos-com-motivo). Sem CNPJ ou sem mês do exercício a etapa de
    insumos falharia com `cadastro_incompleto`; melhor avisar na hora de iniciar do que falhar depois."""
    consulta = Fundo.objects.filter(ativo=True).select_related("administradora").order_by("administradora__nome", "nome")
    if administradora:
        consulta = consulta.filter(administradora__nome=administradora)
    if codigos:
        consulta = consulta.filter(codigo_britech__in=[str(c) for c in codigos])
    aptos: list[Fundo] = []
    incompletos: list[tuple[Fundo, str]] = []
    for fundo in consulta:
        faltas = [nome for nome, valor in (("CNPJ", fundo.cnpj), ("mês do exercício", fundo.exercicio_mes)) if not valor]
        if faltas:
            incompletos.append((fundo, "sem " + " e ".join(faltas)))
        else:
            aptos.append(fundo)
    return aptos, incompletos


def fundos_pendentes(competencia: Competencia, fundos: Sequence[Fundo], etapas: Iterable[str]) -> list[Fundo]:
    """Tira os fundos que já têm TODAS as `etapas` em sucesso ou que já têm etapa em andamento nesta competência."""
    etapas = list(etapas)
    ids = [f.pk for f in fundos]
    concluidos: dict[int, int] = {}
    for fundo_id in EstadoEtapa.objects.filter(
        competencia=competencia, fundo_id__in=ids, etapa__in=etapas, status=StatusEtapa.SUCESSO
    ).values_list("fundo_id", flat=True):
        concluidos[fundo_id] = concluidos.get(fundo_id, 0) + 1
    em_andamento = set(
        EtapaExecucao.objects.filter(
            execucao__competencia=competencia, fundo_id__in=ids, status__in=list(ESTADOS_ABERTOS)
        ).values_list("fundo_id", flat=True)
    )
    return [f for f in fundos if concluidos.get(f.pk, 0) < len(etapas) and f.pk not in em_andamento]


def matriz(competencia: Competencia, fundos: Sequence[Fundo] | None = None) -> list[dict]:
    """Matriz fundo × etapa da competência, pelo estado VIGENTE (`EstadoEtapa`).

    Cada linha: {"fundo": Fundo, "celulas": [{"etapa", "status", "erro"}...]} na ordem do pipeline.
    `status` vem de EstadoEtapa; se a etapa ainda não teve resultado mas está na fila, mostra o status da fila.
    """
    if fundos is None:
        ids = set(EstadoEtapa.objects.filter(competencia=competencia).values_list("fundo_id", flat=True)) | set(
            EtapaExecucao.objects.filter(execucao__competencia=competencia).values_list("fundo_id", flat=True)
        )
        fundos = list(Fundo.objects.filter(pk__in=ids).select_related("administradora").order_by("administradora__nome", "nome"))
    estados = {
        (e.fundo_id, e.etapa): e
        for e in EstadoEtapa.objects.filter(competencia=competencia).select_related("ultima_etapa_execucao")
    }
    na_fila: dict[tuple[int, str], EtapaExecucao] = {}
    for e in EtapaExecucao.objects.filter(execucao__competencia=competencia).order_by("id"):
        na_fila[(e.fundo_id, e.etapa)] = e  # a mais recente vence
    linhas = []
    for fundo in fundos:
        celulas = []
        for etapa in ORDEM:
            estado, ultima = estados.get((fundo.pk, etapa)), na_fila.get((fundo.pk, etapa))
            reexecucao_idempotente = bool(
                estado and ultima and estado.status == StatusEtapa.SUCESSO
                and ultima.status == StatusEtapa.PULADO and ultima.erro_tipo == "idempotencia"
            )
            if estado and (not ultima or reexecucao_idempotente or ultima.pk <= (estado.ultima_etapa_execucao_id or 0)):
                status, origem = estado.status, estado.ultima_etapa_execucao
            elif ultima:
                status, origem = ultima.status, ultima
            else:
                status, origem = "", None
            celulas.append(
                {"etapa": etapa, "status": status, "erro": (origem.erro_tipo if origem and status in ("falha", "pulado") else "")}
            )
        linhas.append({"fundo": fundo, "celulas": celulas})
    return linhas
