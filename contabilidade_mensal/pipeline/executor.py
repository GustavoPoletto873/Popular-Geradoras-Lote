"""Executa UMA etapa já reivindicada: chama o handler e traduz o resultado/erro em transição de estado.

Mapa de decisão:
    handler retorna                    → sucesso (artefatos com sha256), zera o contador do disjuntor
    ProcessamentoPendente              → aguardando_britech (ou falha, se passou do timeout de polling)
    BritechErro                        → retentável? backoff : falha; conta para o disjuntor se `conta_para_disjuntor`
    qualquer outra exceção             → falha imediata `erro_inesperado` (bug não se conserta repetindo)
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from django.utils import timezone

from contabilidade_mensal.core.models import EtapaExecucao
from contabilidade_mensal.integrations.britech.erros import ArquivoInvalido, BritechErro, ProcessamentoPendente
from contabilidade_mensal.observability.logging import contexto

from . import disjuntor, fila, parametros
from .definicao import chave_disjuntor
from .tipos import ContextoEtapa, Handler, ResultadoEtapa

logger = logging.getLogger(__name__)


def executar(
    e: EtapaExecucao,
    handlers: Mapping[str, Handler],
    *,
    relogio: Callable = timezone.now,
) -> str:
    """Devolve o status final da etapa após esta execução."""
    p = parametros.obter()
    fundo = e.fundo
    competencia = e.execucao.competencia
    payload: dict[str, Any] = dict(e.payload or {})

    with contexto(
        execucao_id=e.execucao_id,
        correlation_id=str(e.execucao.correlation_id),
        fundo=fundo.nome,
        competencia=competencia.aaaamm,
        etapa=e.etapa,
        backend=e.backend,
        tentativa=e.tentativas,
        worker_id=e.worker_id,
    ):
        handler = handlers.get(e.etapa)
        if handler is None:
            logger.error("nenhum handler registrado para a etapa")
            return fila.registrar_falha(
                e, "handler_ausente", f"sem handler para {e.etapa}", retentavel=False, payload=payload, agora=relogio()
            )

        ctx = ContextoEtapa(
            etapa_exec=e,
            fundo=fundo,
            competencia=competencia,
            execucao=e.execucao,
            agora=relogio(),
            payload=payload,
            parametros=p,
        )
        chave_dj = chave_disjuntor(e.etapa, e.backend, fundo.administradora_id)
        logger.info("etapa iniciada")
        try:
            resultado = handler(ctx) or ResultadoEtapa()
            for artefato in resultado.artefatos:
                if not artefato.caminho.is_file():
                    raise ArquivoInvalido(f"artefato declarado não existe: {artefato.caminho}")
        except ProcessamentoPendente as exc:
            return _aguardar(e, ctx, exc, relogio())
        except BritechErro as exc:
            return _tratar_erro_britech(e, exc, chave_dj, ctx.payload, relogio())
        except Exception as exc:  # noqa: BLE001 - qualquer erro inesperado falha alto e claro
            logger.exception("erro inesperado na etapa")
            return fila.registrar_falha(
                e, "erro_inesperado", f"{type(exc).__name__}: {exc}", retentavel=False, payload=ctx.payload, agora=relogio()
            )

        fila.concluir_sucesso(e, resultado.artefatos, payload=ctx.payload, agora=relogio())
        disjuntor.registrar_sucesso(chave_dj)
        logger.info("etapa concluída", extra={"artefatos": len(resultado.artefatos)})
        return e.status


def _aguardar(e: EtapaExecucao, ctx: ContextoEtapa, exc: ProcessamentoPendente, agora) -> str:
    p = ctx.parametros
    desde = e.aguardando_desde or agora
    if (agora - desde).total_seconds() > p.polling_timeout_s:
        logger.error("timeout aguardando a Britech", extra={"aguardando_desde": desde.isoformat()})
        return fila.registrar_falha(
            e,
            "timeout_processamento",
            f"a Britech não concluiu em {p.polling_timeout_s:.0f}s",
            retentavel=False,
            payload=ctx.payload,
            agora=agora,
        )
    fila.aguardar_britech(e, intervalo_s=exc.espera_s or p.polling_intervalo_s, payload=ctx.payload, agora=agora)
    logger.info("aguardando a Britech")
    return e.status


def _tratar_erro_britech(e: EtapaExecucao, exc: BritechErro, chave_dj: str, payload: dict, agora) -> str:
    logger.warning("erro da Britech", extra={"erro_tipo": exc.codigo, "retentavel": exc.retentavel, "detalhe": str(exc)})
    if exc.conta_para_disjuntor:
        disjuntor.registrar_falha(chave_dj, exc.codigo, agora=agora)
    return fila.registrar_falha(
        e, exc.codigo, str(exc), retentavel=exc.retentavel, espera_s=exc.espera_s, payload=payload, agora=agora
    )
