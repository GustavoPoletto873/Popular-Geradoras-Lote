import datetime as dt

from contabilidade_mensal.core.models import TravaRecurso
from contabilidade_mensal.pipeline import travas

T0 = dt.datetime(2026, 9, 1, 8, 0, tzinfo=dt.timezone.utc)


def test_quem_chega_primeiro_leva_e_o_outro_espera(db):
    assert travas.adquirir("britech:1", "w1", lease_s=60, agora=T0)
    assert not travas.adquirir("britech:1", "w2", lease_s=60, agora=T0 + dt.timedelta(seconds=10))


def test_o_dono_pode_readquirir_e_estende_o_lease(db):
    travas.adquirir("britech:1", "w1", lease_s=60, agora=T0)
    assert travas.adquirir("britech:1", "w1", lease_s=60, agora=T0 + dt.timedelta(seconds=30))
    assert TravaRecurso.objects.get(chave="britech:1").lease_ate == T0 + dt.timedelta(seconds=90)


def test_lease_vencido_permite_que_outro_assuma(db):
    travas.adquirir("britech:1", "w1", lease_s=60, agora=T0)
    assert travas.adquirir("britech:1", "w2", lease_s=60, agora=T0 + dt.timedelta(seconds=61))
    assert TravaRecurso.objects.get(chave="britech:1").dono == "w2"


def test_chaves_diferentes_nao_se_bloqueiam(db):
    assert travas.adquirir("britech:1", "w1", lease_s=60, agora=T0)
    assert travas.adquirir("britech:2", "w2", lease_s=60, agora=T0)


def test_liberar_so_funciona_para_o_dono(db):
    travas.adquirir("britech:1", "w1", lease_s=60, agora=T0)
    assert not travas.liberar("britech:1", "w2")
    assert travas.liberar("britech:1", "w1")
    assert travas.adquirir("britech:1", "w2", lease_s=60, agora=T0)


def test_renovar_so_funciona_para_o_dono(db):
    travas.adquirir("britech:1", "w1", lease_s=60, agora=T0)
    assert not travas.renovar("britech:1", "w2", lease_s=60, agora=T0)
    assert travas.renovar("britech:1", "w1", lease_s=600, agora=T0)
    assert TravaRecurso.objects.get(chave="britech:1").lease_ate == T0 + dt.timedelta(seconds=600)
