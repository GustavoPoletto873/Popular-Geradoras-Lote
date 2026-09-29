"""Como o pipeline decide que o "Processar Contábil" terminou (Q4 em aberto): status | espera | manual."""

import pytest

from contabilidade_mensal.core.choices import Etapa
from contabilidade_mensal.core.choices import StatusEtapa as S
from contabilidade_mensal.core.models import EtapaExecucao
from contabilidade_mensal.pipeline import fila, servicos
from contabilidade_mensal.pipeline.definicao import FILAS
from contabilidade_mensal.pipeline.worker import drenar


def etapa(execucao, fundo, nome=Etapa.PROCESSAR_CONTABIL):
    return EtapaExecucao.objects.get(execucao=execucao, fundo=fundo, etapa=nome)


def consultas_de_status(fake):
    return [c for c in fake.chamadas if c[0] == "status_processamento"]


def test_espera_minima_so_conclui_depois_do_prazo(criar_fundo, competencia, relogio, handlers, settings, fake):
    settings.PIPELINE = {"processamento_conclusao": "espera", "processamento_espera_s": 300, "polling_intervalo_s": 60}
    fundo = criar_fundo(1001)
    execucao = servicos.criar_execucao(competencia, [fundo], agora=relogio())
    inicio = relogio()
    drenar(FILAS, handlers, relogio)

    e = etapa(execucao, fundo)
    assert e.status == S.SUCESSO
    assert (relogio() - inicio).total_seconds() >= 300  # não concluiu antes dos 5 min
    assert consultas_de_status(fake) == []  # nunca perguntou ao backend


def test_manual_fica_aguardando_ate_alguem_confirmar(criar_fundo, competencia, relogio, handlers, settings, fake):
    settings.PIPELINE = {"processamento_conclusao": "manual", "polling_intervalo_s": 60, "polling_timeout_s": 10**6}
    fundo = criar_fundo(1001)
    execucao = servicos.criar_execucao(competencia, [fundo], agora=relogio())
    drenar(FILAS, handlers, relogio, max_ciclos=8)

    e = etapa(execucao, fundo)
    assert e.status == S.AGUARDANDO_BRITECH and e.payload.get("disparado") is True
    assert etapa(execucao, fundo, Etapa.BAIXAR_BALANCETE).status == S.PENDENTE  # nada a jusante andou

    assert fila.confirmar_processamento(e) is True
    drenar(FILAS, handlers, relogio)
    assert etapa(execucao, fundo).status == S.SUCESSO
    assert etapa(execucao, fundo, Etapa.PUBLICAR_DRIVE).status == S.SUCESSO
    assert consultas_de_status(fake) == []


def test_confirmar_so_vale_para_etapa_aguardando(criar_fundo, competencia, relogio, handlers):
    fundo = criar_fundo(1001)
    execucao = servicos.criar_execucao(competencia, [fundo], agora=relogio())
    e = etapa(execucao, fundo)  # ainda pendente
    assert fila.confirmar_processamento(e) is False


def test_manual_sem_confirmacao_estoura_o_timeout_do_polling(criar_fundo, competencia, relogio, handlers, settings):
    settings.PIPELINE = {"processamento_conclusao": "manual", "polling_intervalo_s": 60, "polling_timeout_s": 300}
    fundo = criar_fundo(1001)
    execucao = servicos.criar_execucao(competencia, [fundo], agora=relogio())
    drenar(FILAS, handlers, relogio)
    e = etapa(execucao, fundo)
    assert e.status == S.FALHA and e.erro_tipo == "timeout_processamento"


def test_modo_invalido_e_recusado(settings):
    from contabilidade_mensal.pipeline import parametros

    settings.PIPELINE = {"processamento_conclusao": "adivinhar"}
    with pytest.raises(ValueError, match="processamento_conclusao"):
        parametros.obter()
