"""Máquina de estados de `EtapaExecucao` (diagrama em docs/unificacao/05_arquitetura.md §9.5).

Toda mudança de status passa por `validar_transicao`.
"""

from __future__ import annotations

from contabilidade_mensal.core.choices import StatusEtapa as S

TRANSICOES: dict[str, frozenset[str]] = {
    S.PENDENTE: frozenset({S.EM_ANDAMENTO, S.PULADO}),
    S.EM_ANDAMENTO: frozenset({S.SUCESSO, S.FALHA, S.PENDENTE, S.AGUARDANDO_BRITECH}),
    S.AGUARDANDO_BRITECH: frozenset({S.EM_ANDAMENTO, S.FALHA}),
    S.FALHA: frozenset({S.PENDENTE}),  # reprocesso manual
    S.SUCESSO: frozenset({S.PENDENTE}),  # reprocesso forçado
    S.PULADO: frozenset({S.PENDENTE}),  # reprocesso (ex.: dependência que falhou foi corrigida)
}

ESTADOS_ABERTOS = frozenset({S.PENDENTE, S.EM_ANDAMENTO, S.AGUARDANDO_BRITECH})
ESTADOS_FINAIS = frozenset({S.SUCESSO, S.FALHA, S.PULADO})


class TransicaoInvalida(Exception):
    """Transição fora da máquina de estados, ou perdida para outro worker (condição de corrida)."""


def validar_transicao(de: str, para: str) -> None:
    if para not in TRANSICOES.get(de, frozenset()):
        raise TransicaoInvalida(f"transição não permitida: {de} -> {para}")
