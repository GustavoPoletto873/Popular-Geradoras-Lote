"""Fase 7: sessão compartilhada por lote de uma credencial e heartbeat do lease."""

import datetime as dt
import time

import pytest
from django.utils import timezone

from contabilidade_mensal.core.choices import Etapa
from contabilidade_mensal.core.choices import StatusEtapa as S
from contabilidade_mensal.core.models import Administradora, Competencia, EtapaExecucao, Fundo, TravaRecurso
from contabilidade_mensal.integrations.britech.erros import TelaMudou
from contabilidade_mensal.integrations.britech.interface import AdministradoraRef
from contabilidade_mensal.pipeline import fila, servicos, wiring
from contabilidade_mensal.pipeline.heartbeat import Heartbeat
from contabilidade_mensal.pipeline.worker import Worker

ADM = AdministradoraRef("ID", "id", "ID")


# --- sessão compartilhada -------------------------------------------------------------------------------------------


def test_sem_lote_cada_uso_abre_e_fecha_a_propria_sessao(gateway, fake):
    for _ in range(3):
        with gateway.sessao(ADM) as s:
            s.obter("fake")
    assert len(fake.sessoes) == 3 and all(s.fechada for s in fake.sessoes)


def test_lote_faz_login_uma_vez_e_logout_no_fim(gateway, fake):
    with gateway.lote(ADM):
        for _ in range(3):
            with gateway.sessao(ADM) as s:
                s.obter("fake")
        assert len(fake.sessoes) == 1 and not fake.sessoes[0].fechada  # ainda aberta entre as etapas
    assert len(fake.sessoes) == 1 and fake.sessoes[0].fechada


def test_lote_nao_mistura_administradoras(gateway, fake):
    outra = AdministradoraRef("AMERICA", "america", "AMERICA")
    with gateway.lote(ADM):
        with gateway.sessao(outra) as s:
            s.obter("fake")
        assert fake.sessoes[0].administradora == outra and fake.sessoes[0].fechada  # a de outra credencial é avulsa


def test_erro_que_deixa_a_sessao_suspeita_fecha_e_a_proxima_etapa_reloga(gateway, fake):
    with gateway.lote(ADM):
        with pytest.raises(TelaMudou):
            with gateway.sessao(ADM) as s:
                s.obter("fake")
                raise TelaMudou("mudou")
        assert fake.sessoes[0].fechada  # a suspeita foi encerrada na hora
        with gateway.sessao(ADM) as s:
            s.obter("fake")
        assert len(fake.sessoes) == 2 and not fake.sessoes[1].fechada
    assert all(s.fechada for s in fake.sessoes)


def test_erro_sem_relevancia_para_a_sessao_nao_a_derruba(gateway, fake):
    from contabilidade_mensal.integrations.britech.erros import CarteiraNaoEncontrada

    with gateway.lote(ADM):
        with pytest.raises(CarteiraNaoEncontrada):
            with gateway.sessao(ADM) as s:
                s.obter("fake")
                raise CarteiraNaoEncontrada("só deste fundo")
        with gateway.sessao(ADM) as s:
            s.obter("fake")
        assert len(fake.sessoes) == 1


def test_worker_com_lote_processa_varios_fundos_em_uma_sessao(criar_fundo, competencia, relogio, gateway, handlers, fake):
    fundos = [criar_fundo(1000 + i) for i in range(3)]
    servicos.criar_execucao(competencia, fundos, etapas=[Etapa.PROCESSAR_CONTABIL], agora=relogio())
    worker = Worker(
        "browser", handlers, worker_id="w", lote=3, relogio=relogio, abrir_lote=wiring.abrir_lote_para(gateway)
    )
    assert worker.ciclo() == 3  # o disparo dos três
    disparos = [s for s in fake.sessoes]
    assert len(disparos) == 1 and disparos[0].fechada  # UMA sessão para os 3 fundos
    assert len(fake.disparos) == 3


def test_worker_sem_abrir_lote_usa_uma_sessao_por_etapa(criar_fundo, competencia, relogio, handlers, fake):
    fundos = [criar_fundo(1000 + i) for i in range(3)]
    servicos.criar_execucao(competencia, fundos, etapas=[Etapa.PROCESSAR_CONTABIL], agora=relogio())
    Worker("browser", handlers, worker_id="w", lote=3, relogio=relogio).ciclo()
    assert len(fake.sessoes) == 3


# --- heartbeat --------------------------------------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_heartbeat_renova_lease_e_trava_enquanto_a_etapa_roda():
    adm = Administradora.objects.create(nome="ID HB", url_adm="id")
    fundo = Fundo.objects.create(administradora=adm, codigo_britech="1", cnpj="1" * 14, nome="F", tipo="FII", exercicio_mes=12)
    comp = Competencia.objects.create(ano=2026, mes=8)
    execucao = servicos.criar_execucao(comp, [fundo], etapas=[Etapa.PROCESSAR_CONTABIL])
    etapa = fila.reivindicar("browser", "w-hb", limite=1)[0]
    curto = timezone.now() + dt.timedelta(seconds=2)  # lease quase vencendo
    EtapaExecucao.objects.filter(pk=etapa.pk).update(lease_ate=curto)
    TravaRecurso.objects.filter(chave=etapa.lock_key).update(lease_ate=curto)

    with Heartbeat([etapa], "w-hb", intervalo_s=0.05) as hb:
        time.sleep(0.5)
    assert hb.renovacoes >= 3
    assert EtapaExecucao.objects.get(pk=etapa.pk).lease_ate > curto + dt.timedelta(seconds=100)
    assert TravaRecurso.objects.get(chave=etapa.lock_key).lease_ate > curto + dt.timedelta(seconds=100)


@pytest.mark.django_db(transaction=True)
def test_heartbeat_nao_ressuscita_etapa_que_ja_terminou():
    adm = Administradora.objects.create(nome="ID HB2", url_adm="id")
    fundo = Fundo.objects.create(administradora=adm, codigo_britech="2", cnpj="2" * 14, nome="F2", tipo="FII", exercicio_mes=12)
    comp = Competencia.objects.create(ano=2026, mes=8)
    servicos.criar_execucao(comp, [fundo], etapas=[Etapa.BAIXAR_INSUMOS])
    etapa = fila.reivindicar("api", "w-hb2", limite=1)[0]
    EtapaExecucao.objects.filter(pk=etapa.pk).update(status=S.SUCESSO, lease_ate=None)
    with Heartbeat([etapa], "w-hb2", intervalo_s=0.05):
        time.sleep(0.2)
    assert EtapaExecucao.objects.get(pk=etapa.pk).lease_ate is None


@pytest.mark.django_db(transaction=True)
def test_sem_heartbeat_outro_worker_recupera_a_etapa_com_lease_vencido():
    """O contrário: o que o heartbeat evita quando a etapa demora mais que o lease."""
    adm = Administradora.objects.create(nome="ID HB3", url_adm="id")
    fundo = Fundo.objects.create(administradora=adm, codigo_britech="3", cnpj="3" * 14, nome="F3", tipo="FII", exercicio_mes=12)
    comp = Competencia.objects.create(ano=2026, mes=8)
    servicos.criar_execucao(comp, [fundo], etapas=[Etapa.BAIXAR_INSUMOS])
    etapa = fila.reivindicar("api", "w-lento", limite=1)[0]
    agora = timezone.now() + dt.timedelta(seconds=400)  # passou dos 300 s do lease
    assert fila.recuperar_orfas(agora=agora) == 1
    assert EtapaExecucao.objects.get(pk=etapa.pk).status == S.PENDENTE
