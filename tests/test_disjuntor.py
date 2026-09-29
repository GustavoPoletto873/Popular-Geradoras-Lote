import datetime as dt

from contabilidade_mensal.core.models import Disjuntor
from contabilidade_mensal.pipeline import disjuntor

T0 = dt.datetime(2026, 9, 1, 8, 0, tzinfo=dt.timezone.utc)
CHAVE = "baixar_balancete:browser:1"


def seg(n):
    return T0 + dt.timedelta(seconds=n)


def test_sem_historico_tudo_passa(db):
    assert disjuntor.permite(CHAVE, agora=T0)


def test_tela_mudou_abre_na_terceira_falha_seguida(db):
    assert not disjuntor.registrar_falha(CHAVE, "tela_mudou", agora=seg(0))
    assert not disjuntor.registrar_falha(CHAVE, "tela_mudou", agora=seg(1))
    assert disjuntor.registrar_falha(CHAVE, "tela_mudou", agora=seg(2))  # limite = 3
    assert not disjuntor.permite(CHAVE, agora=seg(3))


def test_falha_de_autenticacao_abre_na_primeira(db):
    """Evita bloquear a conta insistindo com senha errada."""
    assert disjuntor.registrar_falha(CHAVE, "autenticacao_falhou", agora=T0)
    assert not disjuntor.permite(CHAVE, agora=seg(1))


def test_erro_de_outro_tipo_recomeca_a_contagem(db):
    disjuntor.registrar_falha(CHAVE, "tela_mudou", agora=seg(0))
    disjuntor.registrar_falha(CHAVE, "tela_mudou", agora=seg(1))
    assert not disjuntor.registrar_falha(CHAVE, "timeout_britech", agora=seg(2))
    assert Disjuntor.objects.get(chave=CHAVE).falhas_consecutivas == 1
    assert disjuntor.permite(CHAVE, agora=seg(3))


def test_tipo_sem_limite_proprio_usa_o_padrao_de_cinco(db):
    for i in range(4):
        assert not disjuntor.registrar_falha(CHAVE, "timeout_britech", agora=seg(i))
    assert disjuntor.registrar_falha(CHAVE, "timeout_britech", agora=seg(4))


def test_sucesso_zera_o_contador(db):
    disjuntor.registrar_falha(CHAVE, "tela_mudou", agora=seg(0))
    disjuntor.registrar_falha(CHAVE, "tela_mudou", agora=seg(1))
    disjuntor.registrar_sucesso(CHAVE)
    assert not disjuntor.registrar_falha(CHAVE, "tela_mudou", agora=seg(2))  # recomeçou do 1


def test_meia_abertura_libera_uma_tentativa_por_periodo_de_resfriamento(db):
    disjuntor.registrar_falha(CHAVE, "autenticacao_falhou", agora=T0)  # abre; resfriamento padrão 900 s
    assert not disjuntor.permite(CHAVE, agora=seg(899))
    assert disjuntor.permite(CHAVE, agora=seg(900))  # tentativa de teste
    assert not disjuntor.permite(CHAVE, agora=seg(901))  # só uma por período


def test_falha_na_tentativa_de_teste_mantem_aberto(db):
    disjuntor.registrar_falha(CHAVE, "autenticacao_falhou", agora=T0)
    assert disjuntor.permite(CHAVE, agora=seg(900))
    disjuntor.registrar_falha(CHAVE, "autenticacao_falhou", agora=seg(901))
    assert Disjuntor.objects.get(chave=CHAVE).aberto
    assert not disjuntor.permite(CHAVE, agora=seg(1000))


def test_sucesso_na_tentativa_de_teste_fecha(db):
    disjuntor.registrar_falha(CHAVE, "autenticacao_falhou", agora=T0)
    assert disjuntor.permite(CHAVE, agora=seg(900))
    disjuntor.registrar_sucesso(CHAVE)
    assert disjuntor.permite(CHAVE, agora=seg(901))
    assert disjuntor.permite(CHAVE, agora=seg(902))


def test_fechamento_manual_registra_quem_fechou(db):
    disjuntor.registrar_falha(CHAVE, "autenticacao_falhou", agora=T0)
    disjuntor.fechar(CHAVE, por="gustavo")
    d = Disjuntor.objects.get(chave=CHAVE)
    assert not d.aberto and d.reaberto_por == "gustavo"
    assert disjuntor.permite(CHAVE, agora=seg(1))


def test_limites_vem_da_configuracao(db, settings):
    settings.PIPELINE = {"disjuntor_limites": {"tela_mudou": 1}}
    assert disjuntor.registrar_falha(CHAVE, "tela_mudou", agora=T0)
