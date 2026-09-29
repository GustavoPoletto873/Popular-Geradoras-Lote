"""Pipeline de brinquedo ponta a ponta: executor + workers + gateway FAKE (sem Britech, Excel ou Playwright).

Cobre o critério de pronto da Fase 1: falha injetada, retry, `pulado` por idempotência e reprocesso `forcar`.
"""

import pytest

from contabilidade_mensal.core.choices import Etapa, StatusCompetencia, StatusExecucao, TipoArtefato
from contabilidade_mensal.core.choices import StatusEtapa as S
from contabilidade_mensal.core.models import Artefato, Disjuntor, EstadoEtapa, EtapaExecucao
from contabilidade_mensal.integrations.britech.erros import (
    AutenticacaoFalhou,
    TelaMudou,
    TimeoutBritech,
)
from contabilidade_mensal.integrations.britech.interface import INSUMOS_DO_LOTE, StatusProcessamento
from contabilidade_mensal.pipeline import disjuntor, fakes, servicos
from contabilidade_mensal.pipeline.definicao import FILAS, chave_disjuntor
from contabilidade_mensal.pipeline.worker import drenar
from contabilidade_mensal.storage.hashing import sha256_arquivo


@pytest.fixture
def rodar(competencia, relogio, handlers):
    """Cria uma execução e a drena até o fim. Devolve (execucao, quantas etapas rodaram)."""

    def _rodar(fundos, *, hand=None, **kw):
        execucao = servicos.criar_execucao(competencia, fundos, agora=relogio(), **kw)
        n = drenar(FILAS, hand or handlers, relogio)
        execucao.refresh_from_db()
        return execucao, n

    return _rodar


def status_de(execucao, fundo):
    return {e.etapa: e.status for e in EtapaExecucao.objects.filter(execucao=execucao, fundo=fundo)}


TODAS_OK = {
    Etapa.BAIXAR_INSUMOS: S.SUCESSO,
    Etapa.PROCESSAR_CONTABIL: S.SUCESSO,
    Etapa.BAIXAR_BALANCETE: S.SUCESSO,
    Etapa.POPULAR_EXCEL: S.SUCESSO,
    Etapa.PUBLICAR_DRIVE: S.SUCESSO,
}


# --- caminho feliz -----------------------------------------------------------


def test_caminho_feliz_com_dois_fundos(criar_fundo, competencia, rodar, fake):
    fundos = [criar_fundo(1001), criar_fundo(1002)]
    execucao, n = rodar(fundos)

    # 2 fundos × 5 etapas = 10 linhas; `processar_contabil` roda 2× por fundo (disparo + 1 consulta de status)
    assert n == 12 and execucao.etapas.count() == 10
    assert execucao.status == StatusExecucao.CONCLUIDA and execucao.finalizada_em is not None
    competencia.refresh_from_db()
    assert competencia.status == StatusCompetencia.CONCLUIDA
    for fundo in fundos:
        assert status_de(execucao, fundo) == TODAS_OK
        vigentes = EstadoEtapa.objects.filter(fundo=fundo, competencia=competencia)
        assert vigentes.count() == 5 and set(vigentes.values_list("status", flat=True)) == {S.SUCESSO}
    # toda sessão aberta na Britech foi encerrada
    assert fake.sessoes and all(s.fechada for s in fake.sessoes)


def test_artefatos_tem_hash_e_tamanho_reais(criar_fundo, rodar):
    fundo = criar_fundo(1001)
    execucao, _ = rodar([fundo])
    artefatos = Artefato.objects.filter(etapa_execucao__execucao=execucao)
    tipos = sorted(artefatos.values_list("tipo", flat=True))
    assert tipos.count(TipoArtefato.BOLETA) == 2  # a populada e a publicada
    assert len([t for t in tipos if t.startswith("insumo_")]) == len(INSUMOS_DO_LOTE)
    assert {TipoArtefato.BALANCETE_PDF, TipoArtefato.BALANCETE_XLS} <= set(tipos)
    from pathlib import Path

    for a in artefatos:
        caminho = Path(a.caminho_local)
        assert a.sha256 == sha256_arquivo(caminho) and a.tamanho_bytes == caminho.stat().st_size
    publicado = artefatos.get(tipo=TipoArtefato.BOLETA, drive_file_id__startswith="fake-drive-")
    assert publicado.verificado_em is not None and publicado.drive_checksum == publicado.sha256


def test_cada_execucao_de_etapa_grava_duracao_e_tentativa(criar_fundo, rodar):
    execucao, _ = rodar([criar_fundo(1001)])
    for e in execucao.etapas.all():
        assert e.tentativas == 1 and e.iniciado_em and e.finalizado_em and e.duracao_ms is not None


# --- falha isolada -------------------------------------------------------------


def test_falha_num_fundo_nao_derruba_os_outros(criar_fundo, competencia, rodar, fake):
    a, b, c = criar_fundo(1001), criar_fundo(1002), criar_fundo(1003)
    fake.programar("baixar_balancete", "1003", TelaMudou("botão de Excel não encontrado"))
    execucao, _ = rodar([a, b, c])

    assert status_de(execucao, a) == TODAS_OK and status_de(execucao, b) == TODAS_OK
    assert status_de(execucao, c) == {
        Etapa.BAIXAR_INSUMOS: S.SUCESSO,
        Etapa.PROCESSAR_CONTABIL: S.SUCESSO,
        Etapa.BAIXAR_BALANCETE: S.FALHA,
        Etapa.POPULAR_EXCEL: S.PULADO,
        Etapa.PUBLICAR_DRIVE: S.PULADO,
    }
    falha = EtapaExecucao.objects.get(execucao=execucao, fundo=c, etapa=Etapa.BAIXAR_BALANCETE)
    assert falha.erro_tipo == "tela_mudou" and falha.tentativas == 1  # não retentável
    assert execucao.status == StatusExecucao.CONCLUIDA_COM_FALHAS
    competencia.refresh_from_db()
    assert competencia.status == StatusCompetencia.CONCLUIDA_COM_FALHAS
    assert all(s.fechada for s in fake.sessoes)  # inclusive a da etapa que falhou


def test_erro_inesperado_falha_alto_sem_retry(criar_fundo, rodar, fake):
    fundo = criar_fundo(1001)
    fake.programar("baixar_insumo", "1001", RuntimeError("bug no adapter"))
    execucao, _ = rodar([fundo])
    e = EtapaExecucao.objects.get(execucao=execucao, fundo=fundo, etapa=Etapa.BAIXAR_INSUMOS)
    assert e.status == S.FALHA and e.erro_tipo == "erro_inesperado" and e.tentativas == 1
    assert "bug no adapter" in e.erro_msg


def test_etapa_sem_handler_falha_com_motivo_claro(criar_fundo, competencia, relogio, handlers):
    fundo = criar_fundo(1001)
    sem_excel = {k: v for k, v in handlers.items() if k != Etapa.POPULAR_EXCEL}
    execucao = servicos.criar_execucao(competencia, [fundo], agora=relogio())
    drenar(FILAS, sem_excel, relogio)
    e = EtapaExecucao.objects.get(execucao=execucao, fundo=fundo, etapa=Etapa.POPULAR_EXCEL)
    assert e.status == S.FALHA and e.erro_tipo == "handler_ausente"


# --- retry -----------------------------------------------------------------------


def test_erro_retentavel_tenta_de_novo_e_no_fim_da_certo(criar_fundo, rodar, fake, relogio):
    fundo = criar_fundo(1001)
    fake.programar("baixar_insumo", "1001", TimeoutBritech("lento"), TimeoutBritech("lento"))  # 3ª tentativa passa
    inicio = relogio()
    execucao, _ = rodar([fundo])
    e = EtapaExecucao.objects.get(execucao=execucao, fundo=fundo, etapa=Etapa.BAIXAR_INSUMOS)
    assert e.status == S.SUCESSO and e.tentativas == 3
    assert (relogio() - inicio).total_seconds() >= 30 + 60 - 30 * 0.4  # esperou os backoffs (com jitter de ±20%)
    assert status_de(execucao, fundo) == TODAS_OK


def test_retry_esgotado_vira_falha(criar_fundo, rodar, fake):
    fundo = criar_fundo(1001)
    fake.programar("baixar_insumo", "1001", *[TimeoutBritech("lento")] * 3)
    execucao, _ = rodar([fundo])
    e = EtapaExecucao.objects.get(execucao=execucao, fundo=fundo, etapa=Etapa.BAIXAR_INSUMOS)
    assert (e.status, e.tentativas, e.erro_tipo) == (S.FALHA, 3, "timeout_britech")
    assert status_de(execucao, fundo)[Etapa.POPULAR_EXCEL] == S.PULADO


# --- disjuntor ----------------------------------------------------------------------


def test_falha_de_autenticacao_abre_o_disjuntor_e_segura_o_resto_da_fila(criar_fundo, rodar, fake):
    a, b = criar_fundo(1001), criar_fundo(1002)
    fake.programar("baixar_insumo", "1001", AutenticacaoFalhou("senha recusada"))
    execucao, _ = rodar([a, b])

    chave = chave_disjuntor(Etapa.BAIXAR_INSUMOS, "fake", a.administradora_id)
    assert Disjuntor.objects.get(chave=chave).aberto
    ea = EtapaExecucao.objects.get(execucao=execucao, fundo=a, etapa=Etapa.BAIXAR_INSUMOS)
    eb = EtapaExecucao.objects.get(execucao=execucao, fundo=b, etapa=Etapa.BAIXAR_INSUMOS)
    assert ea.status == S.FALHA and ea.tentativas == 1  # nunca retenta credencial inválida
    assert eb.status == S.PENDENTE and eb.tentativas == 0  # nem foi tentada: fila pausada
    assert execucao.status == StatusExecucao.EM_ANDAMENTO
    # o que não usa aquela chave segue normalmente
    assert status_de(execucao, b)[Etapa.PROCESSAR_CONTABIL] == S.SUCESSO


def test_fechar_o_disjuntor_libera_a_fila(criar_fundo, rodar, fake, relogio, handlers):
    a, b = criar_fundo(1001), criar_fundo(1002)
    fake.programar("baixar_insumo", "1001", AutenticacaoFalhou("senha recusada"))
    execucao, _ = rodar([a, b])
    disjuntor.fechar(chave_disjuntor(Etapa.BAIXAR_INSUMOS, "fake", a.administradora_id), por="teste")
    drenar(FILAS, handlers, relogio)
    assert status_de(execucao, b) == TODAS_OK


# --- polling do processamento ---------------------------------------------------------


def test_processar_contabil_aguarda_a_britech_sem_prender_a_sessao(criar_fundo, rodar, fake, relogio):
    fundo = criar_fundo(1001)
    fake.programar(
        "status_processamento", "1001", StatusProcessamento.EM_ANDAMENTO, StatusProcessamento.EM_ANDAMENTO
    )  # depois disso: concluído
    inicio = relogio()
    execucao, _ = rodar([fundo], etapas=[Etapa.PROCESSAR_CONTABIL])

    e = EtapaExecucao.objects.get(execucao=execucao, fundo=fundo, etapa=Etapa.PROCESSAR_CONTABIL)
    assert e.status == S.SUCESSO and e.tentativas == 1  # consultas de status não são "tentativas"
    assert e.payload.get("disparado") is True
    assert len(fake.disparos) == 1  # disparou UMA vez, mesmo consultando 3×
    assert [c for c in fake.chamadas if c[0] == "status_processamento"] == [("status_processamento", "1001")] * 3
    assert (relogio() - inicio).total_seconds() >= 120  # esperou 2 intervalos de polling (60 s)
    assert all(s.fechada for s in fake.sessoes)
    assert len(fake.sessoes) == 4  # 1 sessão por passo: disparo + 3 consultas (a credencial fica livre entre elas)


def test_timeout_do_polling_vira_falha(criar_fundo, rodar, fake, settings):
    settings.PIPELINE = {"polling_intervalo_s": 60, "polling_timeout_s": 200}
    fundo = criar_fundo(1001)
    fake.programar("status_processamento", "1001", *[StatusProcessamento.EM_ANDAMENTO] * 50)
    execucao, _ = rodar([fundo], etapas=[Etapa.PROCESSAR_CONTABIL, Etapa.BAIXAR_BALANCETE])
    e = EtapaExecucao.objects.get(execucao=execucao, fundo=fundo, etapa=Etapa.PROCESSAR_CONTABIL)
    assert e.status == S.FALHA and e.erro_tipo == "timeout_processamento"
    assert status_de(execucao, fundo)[Etapa.BAIXAR_BALANCETE] == S.PULADO


def test_dry_run_do_processar_nao_clica_nem_espera(criar_fundo, competencia, relogio, gateway, raiz_staging, fake):
    fundo = criar_fundo(1001)
    hand = fakes.montar_handlers(gateway, raiz_staging, dry_run_processar=True)
    execucao = servicos.criar_execucao(competencia, [fundo], etapas=[Etapa.PROCESSAR_CONTABIL], agora=relogio())
    drenar(FILAS, hand, relogio)
    e = EtapaExecucao.objects.get(execucao=execucao, fundo=fundo, etapa=Etapa.PROCESSAR_CONTABIL)
    assert e.status == S.SUCESSO
    assert fake.disparos == [(("1001",), True)]  # dry_run=True chegou ao backend
    assert not [c for c in fake.chamadas if c[0] == "status_processamento"]


# --- idempotência e reprocesso ------------------------------------------------------------


def test_segunda_execucao_pula_tudo_por_idempotencia(criar_fundo, rodar, fake):
    fundo = criar_fundo(1001)
    rodar([fundo])
    chamadas = list(fake.chamadas)
    segunda, n = rodar([fundo])
    assert n == 0  # ninguém executou nada
    assert set(segunda.etapas.values_list("status", flat=True)) == {S.PULADO}
    assert set(segunda.etapas.values_list("erro_tipo", flat=True)) == {"idempotencia"}
    assert fake.chamadas == chamadas  # nenhuma chamada nova à Britech
    assert segunda.status == StatusExecucao.CONCLUIDA


def test_forcar_reexecuta_so_o_que_foi_pedido_mais_a_cascata(criar_fundo, rodar, fake):
    fundo = criar_fundo(1001)
    primeira, _ = rodar([fundo])
    insumos_antes = sum(1 for c in fake.chamadas if c[0] == "baixar_insumo")
    balancetes_antes = sum(1 for c in fake.chamadas if c[0] == "baixar_balancete")

    terceira, n = rodar([fundo], etapas=[Etapa.BAIXAR_BALANCETE], forcar=True, cascata=True)

    assert set(terceira.etapas.values_list("etapa", flat=True)) == {
        Etapa.BAIXAR_BALANCETE,
        Etapa.POPULAR_EXCEL,
        Etapa.PUBLICAR_DRIVE,
    }
    assert set(terceira.etapas.values_list("status", flat=True)) == {S.SUCESSO} and n == 3
    assert sum(1 for c in fake.chamadas if c[0] == "baixar_balancete") == balancetes_antes + 1
    assert sum(1 for c in fake.chamadas if c[0] == "baixar_insumo") == insumos_antes  # insumos não foram refeitos
    # o estado vigente aponta para as novas execuções; o histórico da primeira fica preservado
    vigente = EstadoEtapa.objects.get(fundo=fundo, etapa=Etapa.POPULAR_EXCEL)
    assert vigente.ultima_etapa_execucao.execucao_id == terceira.pk
    assert primeira.etapas.get(etapa=Etapa.POPULAR_EXCEL).artefatos.exists()


def test_artefato_corrompido_ou_sumido_invalida_a_idempotencia(criar_fundo, rodar):
    from pathlib import Path

    fundo = criar_fundo(1001)
    rodar([fundo])
    um_insumo = Artefato.objects.filter(tipo=TipoArtefato.INSUMO_EXTRATO_CC).get()
    Path(um_insumo.caminho_local).unlink()  # arquivo sumiu do staging

    segunda, _ = rodar([fundo])
    estados = status_de(segunda, fundo)
    assert estados[Etapa.BAIXAR_INSUMOS] == S.SUCESSO  # refeito, porque os artefatos não estão mais íntegros
    assert estados[Etapa.PROCESSAR_CONTABIL] == S.PULADO  # essa segue íntegra (não tem arquivos)
    assert estados[Etapa.BAIXAR_BALANCETE] == S.PULADO


def test_etapa_com_dependencia_de_outra_execucao_usa_o_estado_vigente(criar_fundo, rodar):
    fundo = criar_fundo(1001)
    rodar([fundo])
    # nova execução só do Excel: as dependências não estão nela, mas estão vigentes e íntegras
    segunda, n = rodar([fundo], etapas=[Etapa.POPULAR_EXCEL], forcar=True)
    assert n == 1 and status_de(segunda, fundo) == {Etapa.POPULAR_EXCEL: S.SUCESSO}


def test_dependencia_ausente_deixa_a_etapa_esperando(criar_fundo, rodar):
    fundo = criar_fundo(1001)
    execucao, n = rodar([fundo], etapas=[Etapa.POPULAR_EXCEL])  # nunca houve insumo nem balancete
    assert n == 0 and status_de(execucao, fundo) == {Etapa.POPULAR_EXCEL: S.PENDENTE}


# --- log estruturado --------------------------------------------------------------------------


def test_logs_do_executor_saem_em_json_com_contexto(criar_fundo, competencia, relogio, handlers):
    import json
    import logging

    from contabilidade_mensal.observability.logging import JsonFormatter

    linhas = []

    class Coletor(logging.Handler):
        def emit(self, record):
            linhas.append(json.loads(JsonFormatter().format(record)))

    logger = logging.getLogger("contabilidade_mensal.pipeline.executor")
    coletor = Coletor()
    logger.addHandler(coletor)
    nivel = logger.level
    logger.setLevel(logging.INFO)
    try:
        fundo = criar_fundo(1001)
        execucao = servicos.criar_execucao(competencia, [fundo], etapas=[Etapa.BAIXAR_INSUMOS], agora=relogio())
        drenar(FILAS, handlers, relogio)
    finally:
        logger.removeHandler(coletor)
        logger.setLevel(nivel)

    concluida = [x for x in linhas if x["mensagem"] == "etapa concluída"]
    assert len(concluida) == 1
    registro = concluida[0]
    assert registro["execucao_id"] == execucao.pk and registro["etapa"] == "baixar_insumos"
    assert registro["fundo"] == "FUNDO 1001" and registro["competencia"] == "202608"
    assert registro["backend"] == "fake" and registro["tentativa"] == 1 and registro["artefatos"] == 7
    assert registro["correlation_id"] == str(execucao.correlation_id)
