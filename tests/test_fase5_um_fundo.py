"""Fase 5: um fundo percorre o pipeline inteiro pelos comandos que o Agendador do Windows vai chamar."""

import datetime as dt
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from contabilidade_mensal.core.choices import Etapa
from contabilidade_mensal.core.choices import StatusEtapa as S
from contabilidade_mensal.core.models import Artefato, Competencia, EtapaExecucao, Execucao
from contabilidade_mensal.observability.logging import contexto_atual
from contabilidade_mensal.pipeline import servicos
from contabilidade_mensal.pipeline.definicao import FILAS
from contabilidade_mensal.pipeline.worker import drenar


def iniciar(*args, **kw):
    saida = StringIO()
    call_command("iniciar_execucao", *args, stdout=saida, **kw)
    return saida.getvalue()


def matriz_texto(competencia="2026-08"):
    saida = StringIO()
    call_command("mostrar_matriz", competencia=competencia, stdout=saida)
    return saida.getvalue()


def status_da_execucao(execucao):
    return {e.etapa: e.status for e in execucao.etapas.all()}


# --- competência e escolha de fundos -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hoje, esperado",
    [(dt.date(2026, 9, 1), (2026, 8)), (dt.date(2026, 1, 15), (2025, 12)), (dt.date(2028, 3, 31), (2028, 2))],
)
def test_competencia_auto_e_o_mes_fechado_anterior(hoje, esperado):
    assert servicos.competencia_anterior(hoje) == esperado


def test_cria_execucao_so_para_fundos_completos_e_avisa_dos_incompletos(criar_fundo, db):
    bom = criar_fundo(1001)
    criar_fundo(1002, cnpj="")
    criar_fundo(1003, exercicio_mes=None)
    saida = iniciar(competencia="2026-08")
    execucao = Execucao.objects.get()
    assert execucao.etapas.values_list("fundo_id", flat=True).distinct().get() == bom.pk
    assert "FUNDO 1002" in saida and "sem CNPJ" in saida and "sem mês do exercício" in saida


def test_fundo_inexistente_e_erro(criar_fundo, db):
    criar_fundo(1001)
    with pytest.raises(CommandError, match="9999"):
        iniciar(competencia="2026-08", fundos=["9999"])


def test_dry_run_nao_cria_nada(criar_fundo, db):
    criar_fundo(1001)
    saida = iniciar(competencia="2026-08", dry_run=True)
    assert "[dry-run]" in saida and "FUNDO 1001" in saida
    assert Execucao.objects.count() == 0 and Competencia.objects.count() == 0


def test_competencia_invalida(db):
    with pytest.raises(CommandError, match="AAAA-MM"):
        iniciar(competencia="2026-13")


def test_auto_usa_o_mes_anterior_e_marca_disparo_do_agendador(criar_fundo, db):
    criar_fundo(1001)
    iniciar(competencia="auto", hoje="2026-09-01", disparada_por="agendador")
    execucao = Execucao.objects.get()
    assert execucao.competencia.aaaamm == "202608" and execucao.disparada_por == "agendador"


# --- idempotência do gatilho diário -----------------------------------------------------------------------------------


def test_rodar_todo_dia_nao_duplica_execucao_em_andamento(criar_fundo, db):
    criar_fundo(1001)
    iniciar(competencia="auto", hoje="2026-09-01")
    saida = iniciar(competencia="auto", hoje="2026-09-02")  # ainda nada rodou: já tem etapas abertas
    assert "nada a fazer" in saida and Execucao.objects.count() == 1


def test_depois_de_concluir_o_gatilho_diario_nao_cria_mais_nada(criar_fundo, relogio, handlers, db):
    criar_fundo(1001)
    iniciar(competencia="auto", hoje="2026-09-01")
    drenar(FILAS, handlers, relogio)
    assert "nada a fazer" in iniciar(competencia="auto", hoje="2026-09-03")
    assert Execucao.objects.count() == 1


def test_fundo_com_falha_volta_a_entrar_na_proxima_rodada(criar_fundo, relogio, handlers, fake, db):
    from contabilidade_mensal.integrations.britech.erros import TelaMudou

    criar_fundo(1001)
    fake.programar("baixar_balancete", "1001", TelaMudou("mudou"))
    iniciar(competencia="auto", hoje="2026-09-01")
    drenar(FILAS, handlers, relogio)
    saida = iniciar(competencia="auto", hoje="2026-09-02")  # falhou: precisa de nova tentativa
    assert "Execução" in saida and Execucao.objects.count() == 2


def test_forcar_e_somente_pendentes_se_contradizem(db):
    with pytest.raises(CommandError, match="contradizem"):
        iniciar(competencia="2026-08", forcar=True, somente_pendentes=True)


# --- critério de pronto: um fundo de ponta a ponta -------------------------------------------------------------------


def test_um_fundo_ponta_a_ponta_reexecutar_e_reprocessar(criar_fundo, competencia, relogio, handlers, db):
    fundo = criar_fundo(1001)

    # 1) primeira execução: todas as etapas até sucesso, logs correlacionados por correlation_id
    correlacionados = set()
    originais = dict(handlers)

    def espiao(nome):
        def _h(ctx):
            correlacionados.add(contexto_atual().get("correlation_id"))
            return originais[nome](ctx)

        return _h

    hand = {nome: espiao(nome) for nome in originais}
    iniciar(competencia="2026-08", fundos=["1001"])
    primeira = Execucao.objects.get()
    drenar(FILAS, hand, relogio)
    assert set(status_da_execucao(primeira).values()) == {S.SUCESSO}
    assert correlacionados == {str(primeira.correlation_id)}
    artefatos_antes = Artefato.objects.count()
    assert "sucesso" in matriz_texto() and "falha" not in matriz_texto()

    # 2) reexecutar sem forçar: tudo `pulado` por idempotência e nenhum artefato novo
    iniciar(competencia="2026-08", fundos=["1001"])
    segunda = Execucao.objects.latest("id")
    drenar(FILAS, handlers, relogio)
    assert {e.status for e in segunda.etapas.all()} == {S.PULADO}
    assert {e.erro_tipo for e in segunda.etapas.all()} == {"idempotencia"}
    assert Artefato.objects.count() == artefatos_antes
    assert "pulado" not in matriz_texto()  # a matriz mostra o estado VIGENTE (sucesso), não o pulo

    # 3) reprocessar o balancete com cascata: refaz balancete -> excel -> drive, e só isso
    iniciar(competencia="2026-08", fundos=["1001"], etapas=[Etapa.BAIXAR_BALANCETE], forcar=True, cascata=True)
    terceira = Execucao.objects.latest("id")
    assert set(terceira.etapas.values_list("etapa", flat=True)) == {
        Etapa.BAIXAR_BALANCETE,
        Etapa.POPULAR_EXCEL,
        Etapa.PUBLICAR_DRIVE,
    }
    drenar(FILAS, handlers, relogio)
    assert {e.status for e in terceira.etapas.all()} == {S.SUCESSO}  # refeitas de verdade, não puladas
    assert EtapaExecucao.objects.filter(execucao=terceira, forcar=True).count() == 3


# --- matriz no admin -------------------------------------------------------------------------------------------------


def test_matriz_no_admin(criar_fundo, competencia, relogio, handlers, client, django_user_model, db):
    criar_fundo(1001)
    iniciar(competencia="2026-08")
    drenar(FILAS, handlers, relogio)
    django_user_model.objects.create_superuser("admin", "a@b.c", "senha-de-teste")
    client.login(username="admin", password="senha-de-teste")
    r = client.get(f"/admin/core/competencia/{competencia.pk}/matriz/")
    assert r.status_code == 200
    html = r.content.decode()
    assert "FUNDO 1001" in html and html.count("sucesso") >= 5
    assert "matriz" in client.get("/admin/core/competencia/").content.decode()


# --- filas de stub ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("fila", ["excel", "drive"])
def test_filas_de_stub_exigem_a_flag(fila, settings, db):
    settings.PERMITIR_STUBS_EXCEL_DRIVE = False
    with pytest.raises(CommandError, match="STUB"):
        call_command("run_worker", fila=fila, once=True)
    settings.PERMITIR_STUBS_EXCEL_DRIVE = True
    call_command("run_worker", fila=fila, once=True, stdout=StringIO())


def test_run_worker_aceita_backends_reais_configurados(settings, db):
    settings.BRITECH_BACKENDS = {op: "api" for op in settings.BRITECH_BACKENDS}
    call_command("run_worker", fila="api", once=True, stdout=StringIO())  # monta o gateway api sem erro
