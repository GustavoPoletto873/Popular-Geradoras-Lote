import itertools

import pytest

from contabilidade_mensal.core.choices import StatusEtapa as S
from contabilidade_mensal.pipeline.estados import TRANSICOES, TransicaoInvalida, validar_transicao

PERMITIDAS = [
    (S.PENDENTE, S.EM_ANDAMENTO),
    (S.PENDENTE, S.PULADO),
    (S.EM_ANDAMENTO, S.SUCESSO),
    (S.EM_ANDAMENTO, S.FALHA),
    (S.EM_ANDAMENTO, S.PENDENTE),
    (S.EM_ANDAMENTO, S.AGUARDANDO_BRITECH),
    (S.AGUARDANDO_BRITECH, S.EM_ANDAMENTO),
    (S.AGUARDANDO_BRITECH, S.FALHA),
    (S.FALHA, S.PENDENTE),
    (S.SUCESSO, S.PENDENTE),
    (S.PULADO, S.PENDENTE),
]


def test_todo_status_tem_entrada_na_tabela():
    assert set(TRANSICOES) == set(S.values)


@pytest.mark.parametrize("de, para", PERMITIDAS)
def test_transicoes_permitidas(de, para):
    validar_transicao(de, para)  # não levanta


def test_qualquer_outra_transicao_e_invalida():
    permitidas = set(PERMITIDAS)
    for de, para in itertools.product(S.values, repeat=2):
        if (de, para) in permitidas:
            continue
        with pytest.raises(TransicaoInvalida):
            validar_transicao(de, para)


def test_sucesso_nao_volta_direto_para_em_andamento():
    with pytest.raises(TransicaoInvalida):
        validar_transicao(S.SUCESSO, S.EM_ANDAMENTO)
