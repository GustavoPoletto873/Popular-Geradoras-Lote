"""Alertas sem n8n: e-mail + Slack enviados pelo Django, com gravação, deduplicação e nunca derrubando o pipeline."""

import datetime as dt
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core import mail
from django.core.management import call_command

from contabilidade_mensal.core.models import Alerta
from contabilidade_mensal.integrations.britech.erros import AutenticacaoFalhou, TelaMudou
from contabilidade_mensal.observability import alertas
from contabilidade_mensal.pipeline import servicos
from contabilidade_mensal.pipeline.definicao import FILAS
from contabilidade_mensal.pipeline.worker import drenar

AGORA = dt.datetime(2026, 9, 1, 8, 0, tzinfo=dt.timezone.utc)


class SlackFalso:
    def __init__(self, status=200, erro=None):
        self.status, self.erro, self.posts = status, erro, []

    def post(self, url, json=None, timeout=None):
        self.posts.append((url, json))
        if self.erro:
            raise self.erro
        return SimpleNamespace(status_code=self.status)


@pytest.fixture
def com_canais(settings):
    settings.ALERTAS = {
        "email_para": ["time@exemplo.com"],
        "email_de": "cm@exemplo.com",
        "slack_webhook": "https://hooks.exemplo/segredo",
        "prefixo": "[CM]",
    }


# --- núcleo ----------------------------------------------------------------------------------------------------------


def test_sem_canal_grava_e_nao_falha(settings, db):
    settings.ALERTAS = {}
    a = alertas.enviar("k", "Título", "corpo", agora=AGORA)
    assert a.canais == "" and a.enviado_em is None and Alerta.objects.count() == 1


def test_envia_por_email_e_slack(com_canais, db):
    slack = SlackFalso()
    a = alertas.enviar("k", "Disjuntor aberto", "detalhe", severidade=alertas.CRITICO, sessao_http=slack)
    assert a.enviado_em is not None and a.canais == "email,slack" and a.erro_envio == ""
    assert mail.outbox[0].subject == "[CM] Disjuntor aberto" and mail.outbox[0].to == ["time@exemplo.com"]
    assert slack.posts[0][0] == "https://hooks.exemplo/segredo" and "Disjuntor aberto" in slack.posts[0][1]["text"]


def test_duplicado_dentro_da_janela_so_conta_repeticao(com_canais, db):
    slack = SlackFalso()
    assert alertas.enviar("k", "T", agora=AGORA, sessao_http=slack) is not None
    assert alertas.enviar("k", "T", agora=AGORA + dt.timedelta(minutes=30), sessao_http=slack) is None
    assert alertas.enviar("k", "T", agora=AGORA + dt.timedelta(minutes=40), sessao_http=slack) is None
    assert Alerta.objects.get().repeticoes == 2 and len(mail.outbox) == 1 and len(slack.posts) == 1


def test_depois_da_janela_envia_de_novo(com_canais, db):
    alertas.enviar("k", "T", dedup_s=600, agora=AGORA, sessao_http=SlackFalso())
    assert alertas.enviar("k", "T", dedup_s=600, agora=AGORA + dt.timedelta(minutes=11), sessao_http=SlackFalso())
    assert Alerta.objects.count() == 2


def test_falha_de_canal_e_registrada_e_nao_levanta(com_canais, db, monkeypatch):
    def quebrado(*a, **k):
        raise OSError("smtp fora")

    monkeypatch.setattr(alertas, "send_mail", quebrado)
    a = alertas.enviar("k", "T", sessao_http=SlackFalso(status=500))
    assert a.enviado_em is None and "email: OSError" in a.erro_envio and "slack: RuntimeError" in a.erro_envio


def test_se_um_canal_falha_o_outro_ainda_entrega(com_canais, db):
    a = alertas.enviar("k", "T", sessao_http=SlackFalso(erro=ConnectionError("x")))
    assert a.enviado_em is not None and "slack" in a.erro_envio and len(mail.outbox) == 1


def test_webhook_nunca_aparece_no_alerta_gravado(com_canais, db):
    a = alertas.enviar("k", "T", "corpo", sessao_http=SlackFalso(erro=ConnectionError("x")))
    assert "segredo" not in (a.titulo + a.corpo + a.erro_envio + a.canais)


# --- eventos do pipeline -----------------------------------------------------------------------------------------------


def rodar(criar_fundo, competencia, relogio, handlers, n=1):
    fundos = [criar_fundo(1000 + i) for i in range(n)]
    execucao = servicos.criar_execucao(competencia, fundos, agora=relogio())
    drenar(FILAS, handlers, relogio)
    return execucao, fundos


def chaves():
    return set(Alerta.objects.values_list("chave", flat=True))


def test_execucao_concluida_gera_um_alerta_com_resumo(criar_fundo, competencia, relogio, handlers, com_canais, monkeypatch):
    monkeypatch.setattr(alertas, "requests", SimpleNamespace(post=SlackFalso().post))
    execucao, _ = rodar(criar_fundo, competencia, relogio, handlers, n=2)
    a = Alerta.objects.get(chave=f"concluida:{execucao.pk}")
    assert a.titulo == "Competência 202608 concluída" and a.severidade == "info" and "10 sucesso" in a.corpo


def test_login_recusado_alerta_critico_e_o_disjuntor_impede_novas_tentativas(
    criar_fundo, competencia, relogio, handlers, fake, com_canais, monkeypatch
):
    monkeypatch.setattr(alertas, "requests", SimpleNamespace(post=SlackFalso().post))
    for codigo in (1000, 1001, 1002):
        fake.programar("processar_contabil", str(codigo), AutenticacaoFalhou("recusado"))
    execucao, fundos = rodar(criar_fundo, competencia, relogio, handlers, n=3)
    adm = fundos[0].administradora
    criticos = Alerta.objects.filter(chave=f"critico:autenticacao_falhou:{adm.pk}")
    assert criticos.count() == 1 and criticos.get().severidade == "critico"
    # o disjuntor (limite 1 para login recusado) abriu na primeira falha: os outros fundos NÃO tentaram logar de novo
    assert [c for c in fake.chamadas if c[0] == "processar_contabil"] == [("processar_contabil", "1000")]
    assert not any(c.startswith("falha:processar_contabil") for c in chaves())  # sem alerta duplicado de falha genérica
    assert any(c.startswith("disjuntor:") for c in chaves())  # limite de autenticacao_falhou é 1: abriu


def test_tela_mudou_abre_disjuntor_no_terceiro_fundo(criar_fundo, competencia, relogio, handlers, fake, com_canais, monkeypatch):
    monkeypatch.setattr(alertas, "requests", SimpleNamespace(post=SlackFalso().post))
    for codigo in (1000, 1001, 1002):
        fake.programar("baixar_balancete", str(codigo), TelaMudou("botão sumiu"))
    execucao, fundos = rodar(criar_fundo, competencia, relogio, handlers, n=3)
    ab = Alerta.objects.filter(chave__startswith="disjuntor:")
    assert ab.count() == 1 and ab.get().severidade == "critico" and "tela_mudou" in ab.get().corpo
    assert "Falhas" in Alerta.objects.get(chave=f"concluida:{execucao.pk}").corpo


def test_falha_comum_gera_um_aviso_por_tipo_e_etapa_nao_por_fundo(
    criar_fundo, competencia, relogio, handlers, fake, com_canais, monkeypatch
):
    from contabilidade_mensal.integrations.britech.erros import ArquivoInvalido

    monkeypatch.setattr(alertas, "requests", SimpleNamespace(post=SlackFalso().post))
    for codigo in (1000, 1001, 1002, 1003):
        fake.programar("baixar_balancete", str(codigo), *([ArquivoInvalido("vazio")] * 3))
    rodar(criar_fundo, competencia, relogio, handlers, n=4)
    a = Alerta.objects.get(chave="falha:baixar_balancete:arquivo_invalido")
    assert a.repeticoes == 3 and a.severidade == "aviso"


def test_modo_manual_avisa_que_precisa_confirmar(criar_fundo, competencia, relogio, handlers, settings, com_canais, monkeypatch):
    monkeypatch.setattr(alertas, "requests", SimpleNamespace(post=SlackFalso().post))
    settings.PIPELINE = {"processamento_conclusao": "manual", "polling_timeout_s": 10**6}
    fundo = criar_fundo(1001)
    execucao = servicos.criar_execucao(competencia, [fundo], agora=relogio())
    drenar(FILAS, handlers, relogio, max_ciclos=6)
    assert Alerta.objects.filter(chave=f"confirmar:{execucao.pk}").count() == 1


def test_alerta_que_falha_nao_derruba_a_etapa(criar_fundo, competencia, relogio, handlers, fake, com_canais, monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("canal fora")

    monkeypatch.setattr(alertas, "send_mail", explode)
    monkeypatch.setattr(alertas, "requests", SimpleNamespace(post=explode))
    fake.programar("baixar_balancete", "1000", TelaMudou("x"))
    execucao, _ = rodar(criar_fundo, competencia, relogio, handlers, n=1)
    from contabilidade_mensal.core.models import EtapaExecucao

    assert EtapaExecucao.objects.get(execucao=execucao, etapa="baixar_balancete").status == "falha"  # o pipeline seguiu


# --- resumo diário ------------------------------------------------------------------------------------------------------


def test_resumo_diario(criar_fundo, competencia, relogio, handlers, fake, com_canais, monkeypatch):
    monkeypatch.setattr(alertas, "requests", SimpleNamespace(post=SlackFalso().post))
    fake.programar("baixar_balancete", "1001", TelaMudou("x"))
    rodar(criar_fundo, competencia, relogio, handlers, n=2)
    saida = StringIO()
    call_command("resumo_diario", competencia="2026-08", stdout=saida)
    texto = saida.getvalue()
    assert "Competência 202608" in texto and "falha" in texto and "FUNDO 1001/baixar_balancete: tela_mudou" in texto
    assert Alerta.objects.filter(chave__startswith="resumo:202608").count() == 1


def test_resumo_de_competencia_sem_execucao(db):
    saida = StringIO()
    call_command("resumo_diario", competencia="auto", hoje="2026-09-01", stdout=saida)
    assert "nenhuma execução" in saida.getvalue()
