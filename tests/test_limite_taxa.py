"""Token bucket por administradora na API da Britech."""

import pytest

from contabilidade_mensal.integrations.britech.api_backend import limite
from contabilidade_mensal.integrations.britech.api_backend.cliente import ClienteBritech
from contabilidade_mensal.integrations.britech.api_backend.limite import TokenBucket
from contabilidade_mensal.integrations.britech.erros import LimiteTaxa


class Tempo:
    def __init__(self):
        self.agora, self.dormidas = 0.0, []

    def __call__(self):
        return self.agora

    def dormir(self, s):
        self.dormidas.append(s)
        self.agora += s


def balde(taxa=2, capacidade=3):
    t = Tempo()
    return TokenBucket(taxa, capacidade, relogio=t, dormir=t.dormir), t


def test_rajada_ate_a_capacidade_sem_esperar_e_depois_no_ritmo():
    b, t = balde(taxa=2, capacidade=3)
    assert [b.adquirir() for _ in range(3)] == [0.0, 0.0, 0.0]
    assert b.adquirir() == pytest.approx(0.5)  # 2 req/s => 0,5 s por requisição
    assert b.adquirir() == pytest.approx(0.5) and t.agora == pytest.approx(1.0)


def test_repoe_tokens_com_o_tempo_sem_passar_da_capacidade():
    b, t = balde(taxa=1, capacidade=2)
    b.adquirir(), b.adquirir()
    t.agora += 100
    assert [b.adquirir(), b.adquirir()] == [0.0, 0.0]
    assert b.adquirir() == pytest.approx(1.0)


def test_penalizar_faz_todos_esperarem_o_retry_after():
    b, t = balde(taxa=1, capacidade=5)
    b.penalizar(30)
    assert b.adquirir() == pytest.approx(31.0)


def test_parametros_invalidos():
    with pytest.raises(ValueError):
        TokenBucket(0, 1)


class Resp:
    def __init__(self, status=200, headers=None):
        self.status_code, self.headers, self.content = status, headers or {}, b"ok"


class Sessao:
    def __init__(self, *respostas):
        self.respostas = list(respostas)

    def get(self, url, **kw):
        return self.respostas.pop(0)


def test_cliente_espera_o_balde_antes_de_cada_requisicao():
    b, t = balde(taxa=1, capacidade=1)
    c = ClienteBritech("id", "u", "s", sessao=Sessao(Resp(), Resp(), Resp()))
    c.usar_balde(b)
    for _ in range(3):
        c.get("Relatorio/X")
    assert t.dormidas == [pytest.approx(1.0), pytest.approx(1.0)]


def test_429_esvazia_o_balde_pelo_retry_after():
    b, t = balde(taxa=1, capacidade=5)
    c = ClienteBritech("id", "u", "s", sessao=Sessao(Resp(429, {"Retry-After": "20"}), Resp()))
    c.usar_balde(b)
    with pytest.raises(LimiteTaxa):
        c.get("Relatorio/X")
    c.get("Relatorio/Y")
    assert t.dormidas and sum(t.dormidas) >= 20  # a próxima chamada (de qualquer cliente do processo) esperou


def test_registro_devolve_o_mesmo_balde_por_administradora_e_respeita_o_desligado(settings):
    settings.BRITECH_API = {"rps": 0, "burst": 1}
    assert limite.balde_da_administradora("id") is None
    settings.BRITECH_API = {"rps": 3, "burst": 2}
    a, b, c = (limite.balde_da_administradora(x) for x in ("id", "id", "america"))
    assert a is b and a is not c
