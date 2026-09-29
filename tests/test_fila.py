"""Fila sobre EtapaExecucao: criação da execução, reivindicação, retry, polling, órfãs e reprocesso."""

import datetime as dt

import pytest

from contabilidade_mensal.core.choices import Etapa, StatusCompetencia
from contabilidade_mensal.core.choices import StatusEtapa as S
from contabilidade_mensal.core.models import Administradora, EtapaExecucao
from contabilidade_mensal.pipeline import fila, servicos, travas
from contabilidade_mensal.pipeline.estados import TransicaoInvalida


def seg(base, n):
    return base + dt.timedelta(seconds=n)


@pytest.fixture
def execucao_de(criar_fundo, competencia, relogio):
    def _criar(*codigos, **kw):
        fundos = [criar_fundo(c) for c in codigos]
        return servicos.criar_execucao(competencia, fundos, agora=relogio(), **kw), fundos

    return _criar


def linha(execucao, fundo, etapa):
    return EtapaExecucao.objects.get(execucao=execucao, fundo=fundo, etapa=etapa)


# --- criar_execucao ---------------------------------------------------------


def test_cria_uma_linha_por_fundo_e_etapa(execucao_de, competencia):
    execucao, fundos = execucao_de(1001, 1002)
    assert execucao.etapas.count() == 10
    e = linha(execucao, fundos[0], Etapa.PROCESSAR_CONTABIL)
    assert (e.fila, e.backend, e.lock_key, e.status) == ("browser", "fake", f"britech:{fundos[0].administradora_id}", S.PENDENTE)
    assert linha(execucao, fundos[0], Etapa.BAIXAR_INSUMOS).fila == "api"
    competencia.refresh_from_db()
    assert competencia.status == StatusCompetencia.EM_EXECUCAO


def test_etapas_desconhecidas_sao_recusadas(execucao_de):
    with pytest.raises(ValueError, match="desconhecidas"):
        execucao_de(1001, etapas=["inventada"])


def test_cascata_agenda_a_jusante_ja_forcada(execucao_de):
    execucao, fundos = execucao_de(1001, etapas=[Etapa.BAIXAR_BALANCETE], cascata=True)
    forcar = {e.etapa: e.forcar for e in execucao.etapas.all()}
    assert forcar == {
        Etapa.BAIXAR_BALANCETE: False,  # a pedida só é forçada se forcar=True
        Etapa.POPULAR_EXCEL: True,
        Etapa.PUBLICAR_DRIVE: True,
    }


def test_sem_cascata_so_cria_o_que_foi_pedido(execucao_de):
    execucao, _ = execucao_de(1001, etapas=[Etapa.BAIXAR_BALANCETE])
    assert set(execucao.etapas.values_list("etapa", flat=True)) == {Etapa.BAIXAR_BALANCETE}


# --- reivindicar ------------------------------------------------------------


def test_so_reivindica_o_que_tem_dependencias_satisfeitas(execucao_de, relogio):
    execucao, fundos = execucao_de(1001)
    assert fila.reivindicar("excel", "w", agora=relogio()) == []  # depende de insumos e balancete
    assert fila.reivindicar("drive", "w", agora=relogio()) == []
    api = fila.reivindicar("api", "w", agora=relogio())
    assert [e.etapa for e in api] == [Etapa.BAIXAR_INSUMOS]
    browser = fila.reivindicar("browser", "w", agora=relogio())
    assert [e.etapa for e in browser] == [Etapa.PROCESSAR_CONTABIL]  # balancete espera o processamento


def test_reivindicar_marca_em_andamento_e_nunca_devolve_a_mesma_duas_vezes(execucao_de, relogio):
    execucao, fundos = execucao_de(1001)
    primeira = fila.reivindicar("api", "w1", agora=relogio())
    assert len(primeira) == 1
    e = primeira[0]
    assert (e.status, e.tentativas, e.worker_id) == (S.EM_ANDAMENTO, 1, "w1")
    assert e.lease_ate == relogio() + dt.timedelta(seconds=300)
    assert fila.reivindicar("api", "w2", agora=relogio()) == []


def test_nao_reivindica_antes_do_disponivel_em(execucao_de, relogio):
    execucao, fundos = execucao_de(1001)
    EtapaExecucao.objects.filter(execucao=execucao).update(disponivel_em=seg(relogio(), 60))
    assert fila.reivindicar("api", "w", agora=relogio()) == []
    assert len(fila.reivindicar("api", "w", agora=seg(relogio(), 60))) == 1


def test_lote_da_mesma_credencial_segura_a_trava_ate_ser_liberada(execucao_de, relogio):
    execucao, fundos = execucao_de(1001, 1002, 1003, 1004, etapas=[Etapa.PROCESSAR_CONTABIL])
    lote = fila.reivindicar("browser", "w1", limite=3, agora=relogio())
    assert len(lote) == 3
    chave = f"britech:{fundos[0].administradora_id}"
    assert fila.reivindicar("browser", "w2", limite=3, agora=relogio()) == []  # 1 sessão por credencial
    travas.liberar(chave, "w1")
    restante = fila.reivindicar("browser", "w2", limite=3, agora=relogio())
    assert len(restante) == 1


def test_credenciais_diferentes_rodam_em_paralelo(criar_fundo, competencia, relogio):
    outra = Administradora.objects.create(nome="OUTRA ADM", url_adm="outra")
    f1, f2 = criar_fundo(1001), criar_fundo(1002, administradora=outra)
    servicos.criar_execucao(competencia, [f1, f2], etapas=[Etapa.PROCESSAR_CONTABIL], agora=relogio())
    a = fila.reivindicar("browser", "w1", agora=relogio())
    b = fila.reivindicar("browser", "w2", agora=relogio())
    assert [e.fundo_id for e in a] == [f1.pk] and [e.fundo_id for e in b] == [f2.pk]


# --- falhas e retry ---------------------------------------------------------


def test_falha_retentavel_volta_para_pendente_com_backoff(execucao_de, relogio, settings):
    settings.PIPELINE = {"backoff_jitter": 0.0}
    execucao, fundos = execucao_de(1001)
    e = fila.reivindicar("api", "w", agora=relogio())[0]
    estado = fila.registrar_falha(e, "timeout_britech", "lento", retentavel=True, payload={}, agora=relogio())
    e.refresh_from_db()
    assert estado == S.PENDENTE
    assert e.tentativas == 1 and e.erro_tipo == "timeout_britech" and e.worker_id == ""
    assert e.disponivel_em == relogio() + dt.timedelta(seconds=30)  # base do backoff
    assert fila.reivindicar("api", "w", agora=relogio()) == []  # ainda em espera
    assert len(fila.reivindicar("api", "w", agora=seg(relogio(), 30))) == 1


def test_espera_sugerida_pelo_erro_tem_prioridade_sobre_o_backoff(execucao_de, relogio):
    execucao, _ = execucao_de(1001)
    e = fila.reivindicar("api", "w", agora=relogio())[0]
    fila.registrar_falha(e, "limite_taxa", "429", retentavel=True, espera_s=120, payload={}, agora=relogio())
    e.refresh_from_db()
    assert e.disponivel_em == relogio() + dt.timedelta(seconds=120)


def test_sem_tentativas_restantes_vira_falha_e_pula_dependentes(execucao_de, relogio):
    execucao, fundos = execucao_de(1001)
    EtapaExecucao.objects.filter(etapa=Etapa.BAIXAR_INSUMOS).update(max_tentativas=1)
    e = fila.reivindicar("api", "w", agora=relogio())[0]
    assert fila.registrar_falha(e, "timeout_britech", "lento", retentavel=True, payload={}, agora=relogio()) == S.FALHA
    assert linha(execucao, fundos[0], Etapa.POPULAR_EXCEL).status == S.PULADO
    assert linha(execucao, fundos[0], Etapa.POPULAR_EXCEL).erro_tipo == servicos.MOTIVO_DEPENDENCIA_FALHOU
    assert linha(execucao, fundos[0], Etapa.PUBLICAR_DRIVE).status == S.PULADO
    # o que NÃO depende da que falhou segue pendente
    assert linha(execucao, fundos[0], Etapa.PROCESSAR_CONTABIL).status == S.PENDENTE


def test_falha_nao_retentavel_vai_direto_para_falha(execucao_de, relogio):
    execucao, _ = execucao_de(1001)
    e = fila.reivindicar("api", "w", agora=relogio())[0]
    assert fila.registrar_falha(e, "tela_mudou", "x", retentavel=False, payload={}, agora=relogio()) == S.FALHA
    e.refresh_from_db()
    assert e.tentativas == 1 and e.finalizado_em == relogio()


def test_falha_atualiza_o_estado_vigente(execucao_de, relogio):
    from contabilidade_mensal.core.models import EstadoEtapa

    execucao, fundos = execucao_de(1001)
    e = fila.reivindicar("api", "w", agora=relogio())[0]
    fila.registrar_falha(e, "tela_mudou", "x", retentavel=False, payload={}, agora=relogio())
    estado = EstadoEtapa.objects.get(fundo=fundos[0], etapa=Etapa.BAIXAR_INSUMOS)
    assert estado.status == S.FALHA and estado.ultima_etapa_execucao_id == e.pk


# --- polling ----------------------------------------------------------------


def test_aguardar_britech_e_nova_consulta_nao_contam_como_tentativa(execucao_de, relogio):
    execucao, fundos = execucao_de(1001)
    e = fila.reivindicar("browser", "w", agora=relogio())[0]
    fila.aguardar_britech(e, intervalo_s=60, payload={"disparado": True}, agora=relogio())
    e.refresh_from_db()
    assert e.status == S.AGUARDANDO_BRITECH and e.aguardando_desde == relogio() and e.payload == {"disparado": True}
    assert fila.reivindicar("browser", "w", agora=seg(relogio(), 59)) == []
    de_novo = fila.reivindicar("browser", "w", agora=seg(relogio(), 60))[0]
    assert de_novo.status == S.EM_ANDAMENTO and de_novo.tentativas == 1  # continua 1
    assert de_novo.aguardando_desde == relogio()  # o início da espera é preservado


# --- órfãs ------------------------------------------------------------------


def test_lease_vencido_devolve_a_etapa_para_a_fila(execucao_de, relogio):
    execucao, _ = execucao_de(1001)
    e = fila.reivindicar("api", "w", agora=relogio())[0]
    assert fila.recuperar_orfas(agora=seg(relogio(), 299)) == 0
    assert fila.recuperar_orfas(agora=seg(relogio(), 301)) == 1
    e.refresh_from_db()
    assert e.status == S.PENDENTE and e.erro_tipo == "lease_expirado" and e.tentativas == 1


def test_lease_vencido_sem_tentativas_falha(execucao_de, relogio):
    execucao, fundos = execucao_de(1001)
    EtapaExecucao.objects.filter(etapa=Etapa.BAIXAR_INSUMOS).update(max_tentativas=1)
    e = fila.reivindicar("api", "w", agora=relogio())[0]
    fila.recuperar_orfas(agora=seg(relogio(), 301))
    e.refresh_from_db()
    assert e.status == S.FALHA and e.erro_tipo == "lease_expirado"
    assert linha(execucao, fundos[0], Etapa.POPULAR_EXCEL).status == S.PULADO


def test_renovar_lease_evita_a_recuperacao(execucao_de, relogio):
    execucao, _ = execucao_de(1001)
    e = fila.reivindicar("api", "w", agora=relogio())[0]
    assert fila.renovar_lease(e, "w", agora=seg(relogio(), 200))
    assert fila.recuperar_orfas(agora=seg(relogio(), 301)) == 0
    assert not fila.renovar_lease(e, "outro-worker", agora=seg(relogio(), 200))


# --- reprocesso e concorrência ----------------------------------------------


def test_reprocessar_com_cascata_volta_o_que_depende(execucao_de, relogio):
    execucao, fundos = execucao_de(1001)
    EtapaExecucao.objects.filter(execucao=execucao).update(status=S.SUCESSO)
    balancete = linha(execucao, fundos[0], Etapa.BAIXAR_BALANCETE)
    assert fila.reprocessar_etapa(balancete, cascata=True, agora=relogio()) == 3
    status = {e.etapa: (e.status, e.forcar) for e in execucao.etapas.all()}
    assert status[Etapa.BAIXAR_BALANCETE] == (S.PENDENTE, True)
    assert status[Etapa.POPULAR_EXCEL] == (S.PENDENTE, True)
    assert status[Etapa.PUBLICAR_DRIVE] == (S.PENDENTE, True)
    assert status[Etapa.BAIXAR_INSUMOS] == (S.SUCESSO, False)  # não depende do balancete


def test_reprocessar_sem_cascata_mexe_so_na_etapa(execucao_de, relogio):
    execucao, fundos = execucao_de(1001)
    EtapaExecucao.objects.filter(execucao=execucao).update(status=S.FALHA)
    assert fila.reprocessar_etapa(linha(execucao, fundos[0], Etapa.BAIXAR_INSUMOS), cascata=False) == 1


def test_reprocessar_ignora_o_que_ja_esta_em_curso(execucao_de):
    execucao, fundos = execucao_de(1001)
    assert fila.reprocessar_etapa(linha(execucao, fundos[0], Etapa.BAIXAR_INSUMOS), cascata=True) == 0  # tudo pendente


def test_transicao_perdida_para_outro_worker_e_detectada(execucao_de, relogio):
    execucao, _ = execucao_de(1001)
    e = fila.reivindicar("api", "w", agora=relogio())[0]
    EtapaExecucao.objects.filter(pk=e.pk).update(status=S.FALHA)  # outro processo mexeu antes
    with pytest.raises(TransicaoInvalida):
        fila.concluir_sucesso(e, [], payload={}, agora=relogio())
