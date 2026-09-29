"""Fixtures compartilhadas dos testes do pipeline (a maioria usa o banco: fixture `db`)."""

import datetime as dt

import pytest

from contabilidade_mensal.core.models import Administradora, Competencia, Fundo
from contabilidade_mensal.integrations.britech.factory import OPERACOES, BritechGateway
from contabilidade_mensal.integrations.britech.fake import FakeBackend
from contabilidade_mensal.pipeline import fakes
from contabilidade_mensal.pipeline.relogio import RelogioSimulado

INICIO = dt.datetime(2026, 9, 1, 8, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def relogio():
    return RelogioSimulado(INICIO)


@pytest.fixture
def administradora(db):
    return Administradora.objects.create(nome="ID CORRETORA TESTE", url_adm="id")


@pytest.fixture
def criar_fundo(db, administradora):
    def _criar(codigo, *, administradora=administradora, **campos):
        padrao = {
            "nome": f"FUNDO {codigo}",
            "cnpj": f"{int(codigo):014d}",
            "tipo": "FII",
            "exercicio_mes": 12,
        }
        padrao.update(campos)
        return Fundo.objects.create(administradora=administradora, codigo_britech=str(codigo), **padrao)

    return _criar


@pytest.fixture
def competencia(db):
    return Competencia.objects.create(ano=2026, mes=8)


@pytest.fixture
def fake():
    return FakeBackend()


@pytest.fixture
def gateway(fake):
    return BritechGateway({"fake": fake}, {op: "fake" for op in OPERACOES})


@pytest.fixture
def raiz_staging(tmp_path):
    return tmp_path / "staging"


@pytest.fixture
def handlers(gateway, raiz_staging):
    return fakes.montar_handlers(gateway, raiz_staging)
