"""Fila de trabalho sobre a tabela `EtapaExecucao` (sem Redis/Celery).

Concorrência por compare-and-set: cada mudança de status é um
`UPDATE … WHERE pk=? AND status=<esperado>`; quem perde a corrida vê 0 linhas
afetadas e segue para o próximo candidato. Funciona igual em SQLite e Postgres.

Ciclo de vida:
    pendente ──reivindicar──▶ em_andamento ──▶ sucesso | falha | pendente (retry) | aguardando_britech
    aguardando_britech ──(vence disponivel_em)──▶ em_andamento (novo polling)
    em_andamento com lease vencido ──recuperar_orfas──▶ pendente (ou falha, se sem tentativas)
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Iterable
from typing import Any

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from contabilidade_mensal.core.choices import StatusEtapa as S
from contabilidade_mensal.core.models import Artefato, EstadoEtapa, EtapaExecucao

from . import artefatos, disjuntor, parametros, servicos, travas
from .backoff import calcular_backoff
from .definicao import DEPENDENCIAS, a_jusante, chave_disjuntor
from .estados import ESTADOS_ABERTOS, TransicaoInvalida, validar_transicao
from .tipos import ArtefatoNovo

logger = logging.getLogger(__name__)

LIMITE_VARREDURA = 500  # candidatos examinados por chamada de reivindicar()


def _agora(agora: dt.datetime | None) -> dt.datetime:
    return agora or timezone.now()


def _transicionar(e: EtapaExecucao, de: str, para: str, **campos: Any) -> None:
    """Compare-and-set de status. Levanta TransicaoInvalida se a transição não existe ou se outro worker mexeu antes."""
    validar_transicao(de, para)
    alteradas = EtapaExecucao.objects.filter(pk=e.pk, status=de).update(status=para, **campos)
    if alteradas != 1:
        raise TransicaoInvalida(f"etapa {e.pk} não estava em {de!r} (mudou concorrentemente)")
    e.refresh_from_db()


# --- pré-condições -------------------------------------------------------------


def dependencias_satisfeitas(e: EtapaExecucao) -> bool:
    """Cada etapa da qual `e` depende precisa estar OK: na mesma execução (sucesso/pulado) ou,
    se não faz parte dela, no estado vigente do fundo/competência."""
    for anterior in DEPENDENCIAS[e.etapa]:
        linha = EtapaExecucao.objects.filter(execucao_id=e.execucao_id, fundo_id=e.fundo_id, etapa=anterior).first()
        if linha is not None:
            if linha.status == S.SUCESSO:
                continue
            if linha.status == S.PULADO and linha.erro_tipo != servicos.MOTIVO_DEPENDENCIA_FALHOU:
                continue
            return False
        estado = artefatos.estado_vigente(e.fundo_id, e.execucao.competencia_id, anterior)
        if estado is None or estado.status != S.SUCESSO:
            return False
    return True


def _atualizar_estado_vigente(e: EtapaExecucao) -> None:
    EstadoEtapa.objects.update_or_create(
        fundo_id=e.fundo_id,
        competencia_id=e.execucao.competencia_id,
        etapa=e.etapa,
        defaults={"status": e.status, "ultima_etapa_execucao": e},
    )


# --- reivindicar ---------------------------------------------------------------


def reivindicar(
    fila: str, worker_id: str, *, limite: int = 1, agora: dt.datetime | None = None
) -> list[EtapaExecucao]:
    """Reivindica até `limite` etapas da fila, prontas para rodar.

    Regras (nesta ordem, por candidato): dependências satisfeitas → idempotência (já concluída
    e íntegra ⇒ vira `pulado`) → trava da credencial → disjuntor → compare-and-set.
    Um lote só reúne etapas com o mesmo `lock_key` (mesma sessão/credencial).
    O chamador deve liberar as travas (`travas.liberar`) ao terminar o lote.
    """
    agora = _agora(agora)
    p = parametros.obter()
    candidatos = (
        EtapaExecucao.objects.select_related("execucao", "execucao__competencia", "fundo", "fundo__administradora")
        .filter(fila=fila, status__in=[S.PENDENTE, S.AGUARDANDO_BRITECH], disponivel_em__lte=agora)
        .order_by("disponivel_em", "id")[:LIMITE_VARREDURA]
    )
    lote: list[EtapaExecucao] = []
    chave_lote: str | None = None

    for c in candidatos:
        if len(lote) >= limite:
            break
        if lote and c.lock_key != chave_lote:
            continue  # lote de uma só credencial
        if not dependencias_satisfeitas(c):
            continue

        if c.status == S.PENDENTE and not c.forcar and artefatos.etapa_ja_concluida(
            c.fundo_id, c.execucao.competencia_id, c.etapa
        ):
            _pular(c, "idempotencia", "já concluída com artefatos íntegros", agora=agora)
            continue

        trava_nova = False
        if c.lock_key and not lote:
            if not travas.adquirir(c.lock_key, worker_id, lease_s=p.lease_segundos, agora=agora):
                continue
            trava_nova = True

        chave_dj = chave_disjuntor(c.etapa, c.backend, c.fundo.administradora_id)
        if not disjuntor.permite(chave_dj, agora=agora):
            if trava_nova:
                travas.liberar(c.lock_key, worker_id)
            continue

        incremento = 1 if c.status == S.PENDENTE else 0  # repolling não conta como tentativa
        ganhou = EtapaExecucao.objects.filter(pk=c.pk, status=c.status).update(
            status=S.EM_ANDAMENTO,
            worker_id=worker_id,
            lease_ate=agora + dt.timedelta(seconds=p.lease_segundos),
            iniciado_em=agora,
            tentativas=F("tentativas") + incremento,
        )
        if ganhou != 1:
            if trava_nova:
                travas.liberar(c.lock_key, worker_id)
            continue
        lote.append(
            EtapaExecucao.objects.select_related(
                "execucao", "execucao__competencia", "fundo", "fundo__administradora"
            ).get(pk=c.pk)
        )
        chave_lote = c.lock_key
    return lote


# --- transições de fim de execução -----------------------------------------------


def _pular(e: EtapaExecucao, motivo: str, mensagem: str, *, agora: dt.datetime) -> None:
    _transicionar(e, S.PENDENTE, S.PULADO, erro_tipo=motivo, erro_msg=mensagem, finalizado_em=agora)
    servicos.atualizar_status_execucao(e.execucao, agora=agora)


def _duracao_ms(e: EtapaExecucao, agora: dt.datetime) -> int | None:
    return int((agora - e.iniciado_em).total_seconds() * 1000) if e.iniciado_em else None


def concluir_sucesso(
    e: EtapaExecucao,
    novos: Iterable[ArtefatoNovo],
    *,
    payload: dict[str, Any],
    agora: dt.datetime | None = None,
) -> None:
    from contabilidade_mensal.storage.hashing import descrever

    agora = _agora(agora)
    with transaction.atomic():
        for novo in novos:
            sha, tamanho = descrever(novo.caminho)
            Artefato.objects.create(
                etapa_execucao=e,
                tipo=novo.tipo,
                nome=novo.caminho.name,
                caminho_local=str(novo.caminho),
                sha256=sha,
                tamanho_bytes=tamanho,
                drive_file_id=novo.drive_file_id,
                drive_checksum=novo.drive_checksum,
                verificado_em=novo.verificado_em,
            )
        _transicionar(
            e,
            S.EM_ANDAMENTO,
            S.SUCESSO,
            finalizado_em=agora,
            duracao_ms=_duracao_ms(e, agora),
            erro_tipo="",
            erro_msg="",
            lease_ate=None,
            aguardando_desde=None,
            payload=payload,
        )
        _atualizar_estado_vigente(e)
    servicos.atualizar_status_execucao(e.execucao, agora=agora)


def registrar_falha(
    e: EtapaExecucao,
    erro_tipo: str,
    mensagem: str,
    *,
    retentavel: bool,
    espera_s: float | None = None,
    payload: dict[str, Any],
    agora: dt.datetime | None = None,
) -> str:
    """Retentável e com tentativas sobrando → volta a `pendente` com backoff; senão → `falha`."""
    agora = _agora(agora)
    p = parametros.obter()
    if retentavel and e.tentativas < e.max_tentativas:
        espera = (
            espera_s
            if espera_s is not None
            else calcular_backoff(
                e.tentativas, base_s=p.backoff_base_s, teto_s=p.backoff_teto_s, jitter=p.backoff_jitter
            )
        )
        _transicionar(
            e,
            S.EM_ANDAMENTO,
            S.PENDENTE,
            erro_tipo=erro_tipo,
            erro_msg=mensagem,
            disponivel_em=agora + dt.timedelta(seconds=espera),
            worker_id="",
            lease_ate=None,
            payload=payload,
        )
        return S.PENDENTE

    _transicionar(
        e,
        S.EM_ANDAMENTO,
        S.FALHA,
        erro_tipo=erro_tipo,
        erro_msg=mensagem,
        finalizado_em=agora,
        duracao_ms=_duracao_ms(e, agora),
        lease_ate=None,
        payload=payload,
    )
    _atualizar_estado_vigente(e)
    propagar_falha(e, agora=agora)
    servicos.atualizar_status_execucao(e.execucao, agora=agora)
    return S.FALHA


def aguardar_britech(
    e: EtapaExecucao,
    *,
    intervalo_s: float,
    payload: dict[str, Any],
    agora: dt.datetime | None = None,
) -> None:
    agora = _agora(agora)
    _transicionar(
        e,
        S.EM_ANDAMENTO,
        S.AGUARDANDO_BRITECH,
        disponivel_em=agora + dt.timedelta(seconds=intervalo_s),
        aguardando_desde=e.aguardando_desde or agora,
        worker_id="",
        lease_ate=None,
        payload=payload,
    )


def propagar_falha(e: EtapaExecucao, *, agora: dt.datetime | None = None) -> int:
    """Etapas que dependem da que falhou, ainda pendentes na mesma execução/fundo, viram `pulado`."""
    agora = _agora(agora)
    afetadas = 0
    for linha in EtapaExecucao.objects.filter(
        execucao_id=e.execucao_id, fundo_id=e.fundo_id, etapa__in=a_jusante({e.etapa}), status=S.PENDENTE
    ):
        _transicionar(
            linha,
            S.PENDENTE,
            S.PULADO,
            erro_tipo=servicos.MOTIVO_DEPENDENCIA_FALHOU,
            erro_msg=f"depende de {e.etapa}, que falhou",
            finalizado_em=agora,
        )
        afetadas += 1
    return afetadas


# --- manutenção -----------------------------------------------------------------


def renovar_lease(e: EtapaExecucao, worker_id: str, *, agora: dt.datetime | None = None) -> bool:
    agora = _agora(agora)
    p = parametros.obter()
    return (
        EtapaExecucao.objects.filter(pk=e.pk, status=S.EM_ANDAMENTO, worker_id=worker_id).update(
            lease_ate=agora + dt.timedelta(seconds=p.lease_segundos)
        )
        == 1
    )


def recuperar_orfas(*, agora: dt.datetime | None = None) -> int:
    """Etapas `em_andamento` com lease vencido (worker morreu) voltam à fila — ou falham, se sem tentativas."""
    agora = _agora(agora)
    total = 0
    for e in EtapaExecucao.objects.select_related("execucao").filter(status=S.EM_ANDAMENTO, lease_ate__lt=agora):
        try:
            if e.tentativas >= e.max_tentativas:
                _transicionar(
                    e,
                    S.EM_ANDAMENTO,
                    S.FALHA,
                    erro_tipo="lease_expirado",
                    erro_msg="worker parou de responder e as tentativas acabaram",
                    finalizado_em=agora,
                    lease_ate=None,
                )
                _atualizar_estado_vigente(e)
                propagar_falha(e, agora=agora)
                servicos.atualizar_status_execucao(e.execucao, agora=agora)
            else:
                _transicionar(
                    e,
                    S.EM_ANDAMENTO,
                    S.PENDENTE,
                    erro_tipo="lease_expirado",
                    erro_msg="worker parou de responder",
                    disponivel_em=agora,
                    worker_id="",
                    lease_ate=None,
                )
            total += 1
        except TransicaoInvalida:
            continue  # outro processo já resolveu
    if total:
        logger.warning("etapas órfãs recuperadas", extra={"total": total})
    return total


def reprocessar_etapa(e: EtapaExecucao, *, cascata: bool = True, agora: dt.datetime | None = None) -> int:
    """Devolve a etapa (e, opcionalmente, as que dependem dela na mesma execução) à fila, forçadas.
    Devolve quantas linhas voltaram a `pendente`. Ignora linhas que já estão em curso."""
    agora = _agora(agora)
    etapas = {e.etapa} | (a_jusante({e.etapa}) if cascata else set())
    total = 0
    for linha in EtapaExecucao.objects.select_related("execucao").filter(
        execucao_id=e.execucao_id, fundo_id=e.fundo_id, etapa__in=etapas
    ):
        if linha.status in ESTADOS_ABERTOS:
            continue
        _transicionar(
            linha,
            linha.status,
            S.PENDENTE,
            tentativas=0,
            forcar=True,
            erro_tipo="",
            erro_msg="",
            finalizado_em=None,
            duracao_ms=None,
            disponivel_em=agora,
            aguardando_desde=None,
            payload={},
        )
        total += 1
    servicos.atualizar_status_execucao(e.execucao, agora=agora)
    return total
