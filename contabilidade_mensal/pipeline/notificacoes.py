"""Quais eventos do pipeline viram alerta, e com que texto/dedup. Chamado por executor, fila e servicos."""

from __future__ import annotations

import collections
import datetime as dt

from contabilidade_mensal.core.choices import StatusEtapa
from contabilidade_mensal.core.models import EtapaExecucao, Execucao
from contabilidade_mensal.observability import alertas

# Erros que bloqueiam a credencial/tela: alerta imediato e crítico, uma vez por hora por administradora+erro.
CODIGOS_CRITICOS = {
    "autenticacao_falhou": "Login recusado na Britech",
    "sessao_bloqueada": "Sessão presa na Britech (logout não confirmado)",
    "tela_mudou": "Uma tela da Britech mudou (seletor não encontrado)",
    "drive_autenticacao_falhou": "drive_api recusou o token",
}


def _quem(e: EtapaExecucao) -> str:
    return f"{e.fundo.nome} ({e.fundo.administradora.nome}/{e.fundo.codigo_britech})"


def erro_critico(e: EtapaExecucao, codigo: str, detalhe: str, *, agora: dt.datetime | None = None) -> None:
    if codigo not in CODIGOS_CRITICOS:
        return
    adm = e.fundo.administradora
    alertas.enviar(
        f"critico:{codigo}:{adm.pk}",
        f"{CODIGOS_CRITICOS[codigo]} — {adm.nome}",
        f"Etapa {e.etapa} do fundo {_quem(e)} (execução {e.execucao_id}).\nDetalhe: {detalhe}\n"
        "Não repetir sozinho: corrija a causa e, se for o caso, feche o disjuntor no admin.",
        severidade=alertas.CRITICO,
        agora=agora,
    )


def disjuntor_aberto(chave: str, erro_tipo: str, *, agora: dt.datetime | None = None) -> None:
    alertas.enviar(
        f"disjuntor:{chave}",
        f"Disjuntor ABERTO: {chave}",
        f"Falhas seguidas do tipo {erro_tipo}. A fila dessa chave está pausada; uma tentativa de teste sai após o "
        "resfriamento. Depois de corrigir, feche o disjuntor no admin.",
        severidade=alertas.CRITICO,
        agora=agora,
    )


def falha_definitiva(e: EtapaExecucao, *, agora: dt.datetime | None = None) -> None:
    """Etapa esgotou as tentativas (ou erro não retentável). Erros críticos já têm alerta próprio."""
    if e.erro_tipo in CODIGOS_CRITICOS:
        return
    alertas.enviar(
        f"falha:{e.etapa}:{e.erro_tipo}",
        f"Falha em {e.etapa}: {e.erro_tipo}",
        f"Primeiro caso: {_quem(e)}, execução {e.execucao_id}, {e.tentativas} tentativa(s).\n{e.erro_msg[:500]}\n"
        "Novos fundos com o mesmo erro na próxima hora não geram novo aviso (entram no resumo).",
        severidade=alertas.AVISO,
        agora=agora,
    )


def aguardando_confirmacao(e: EtapaExecucao, *, agora: dt.datetime | None = None) -> None:
    alertas.enviar(
        f"confirmar:{e.execucao_id}",
        f"Confirmar processamento na Britech — execução {e.execucao_id}",
        f"O 'Processar Contábil' de {_quem(e)} (e possivelmente de outros fundos) foi disparado. Confira na PAS e use "
        "a ação 'Confirmar que a Britech terminou o processamento' no admin (EtapaExecucao).",
        severidade=alertas.INFO,
        dedup_s=6 * 3600,
        agora=agora,
    )


def resumo_execucao(execucao: Execucao) -> tuple[dict[str, int], list[str]]:
    contagem = collections.Counter(EtapaExecucao.objects.filter(execucao=execucao).values_list("status", flat=True))
    falhas = [
        f"{e.fundo.nome}/{e.etapa}: {e.erro_tipo}"
        for e in EtapaExecucao.objects.filter(execucao=execucao, status=StatusEtapa.FALHA).select_related("fundo")[:15]
    ]
    return dict(contagem), falhas


def execucao_concluida(execucao: Execucao, status: str, *, agora: dt.datetime | None = None) -> None:
    contagem, falhas = resumo_execucao(execucao)
    com_falhas = status != "concluida"
    resumo = ", ".join(f"{n} {s}" for s, n in sorted(contagem.items()))
    corpo = f"Competência {execucao.competencia.aaaamm}, execução {execucao.pk}: {resumo}."
    if falhas:
        corpo += "\nFalhas:\n- " + "\n- ".join(falhas)
    alertas.enviar(
        f"concluida:{execucao.pk}",
        f"Competência {execucao.competencia.aaaamm} {'concluída COM FALHAS' if com_falhas else 'concluída'}",
        corpo,
        severidade=alertas.AVISO if com_falhas else alertas.INFO,
        agora=agora,
    )
