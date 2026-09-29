"""Gateway Britech: roteamento por operação, sessões preguiçosas, backend fake e nomes canônicos."""

import pytest

from contabilidade_mensal.core.choices import TipoArtefato
from contabilidade_mensal.integrations.britech import erros, factory
from contabilidade_mensal.integrations.britech.factory import OPERACOES, BritechGateway, montar_gateway
from contabilidade_mensal.integrations.britech.fake import FakeBackend
from contabilidade_mensal.integrations.britech.interface import (
    AdministradoraRef,
    CarteiraRef,
    CompetenciaRef,
    StatusProcessamento,
    TipoInsumo,
)
from contabilidade_mensal.integrations.britech.nomes import nome_balancete_canonico, nome_insumo_canonico

ADM = AdministradoraRef("ID CORRETORA", "id")
CARTEIRA = CarteiraRef("44680491", "44680491000134", "FUNDO X")
COMP = CompetenciaRef(2026, 8)


def config(**overrides):
    base = {op: "a" for op in OPERACOES}
    base.update(overrides)
    return base


# --- roteamento -------------------------------------------------------------------


def test_cada_operacao_vai_para_o_backend_configurado(tmp_path):
    a, b = FakeBackend(), FakeBackend()
    gw = BritechGateway({"a": a, "b": b}, config(baixar_balancete="b"))
    with gw.sessao(ADM) as s:
        gw.baixar_insumo(s, CARTEIRA, COMP, TipoInsumo.EXTRATO_CC, tmp_path)
        gw.baixar_balancete(s, CARTEIRA, COMP, tmp_path)
    assert [c[0] for c in a.chamadas if c[0] != "abrir_sessao"] == ["baixar_insumo"]
    assert [c[0] for c in b.chamadas if c[0] != "abrir_sessao"] == ["baixar_balancete"]


def test_sessao_do_backend_so_abre_se_for_usado(tmp_path):
    a, b = FakeBackend(), FakeBackend()
    gw = BritechGateway({"a": a, "b": b}, config(baixar_balancete="b"))
    with gw.sessao(ADM) as s:
        gw.baixar_insumo(s, CARTEIRA, COMP, TipoInsumo.EXTRATO_CC, tmp_path)
    assert len(a.sessoes) == 1 and b.sessoes == []  # uma execução 100% API nunca sobe o navegador


def test_a_mesma_sessao_e_reaproveitada_no_bloco(tmp_path):
    a = FakeBackend()
    gw = BritechGateway({"a": a}, config())
    with gw.sessao(ADM) as s:
        gw.baixar_insumo(s, CARTEIRA, COMP, TipoInsumo.EXTRATO_CC, tmp_path)
        gw.baixar_insumo(s, CARTEIRA, COMP, TipoInsumo.MOV_COTISTA, tmp_path)
    assert len(a.sessoes) == 1


def test_sessao_e_fechada_mesmo_quando_o_trabalho_falha(tmp_path):
    a = FakeBackend()
    a.programar("baixar_insumo", "44680491", erros.TimeoutBritech("lento"))
    gw = BritechGateway({"a": a}, config())
    with pytest.raises(erros.TimeoutBritech):
        with gw.sessao(ADM) as s:
            gw.baixar_insumo(s, CARTEIRA, COMP, TipoInsumo.EXTRATO_CC, tmp_path)
    assert a.sessoes[0].fechada


def test_falha_ao_fechar_uma_sessao_nao_impede_fechar_as_outras(tmp_path):
    a, b = FakeBackend(), FakeBackend()
    gw = BritechGateway({"a": a, "b": b}, config(baixar_balancete="b"))
    with pytest.raises(erros.SessaoBloqueada):
        with gw.sessao(ADM) as s:
            gw.baixar_insumo(s, CARTEIRA, COMP, TipoInsumo.EXTRATO_CC, tmp_path)
            gw.baixar_balancete(s, CARTEIRA, COMP, tmp_path)
            b.sessoes[0].fechar = lambda: (_ for _ in ()).throw(RuntimeError("logout falhou"))
    assert a.sessoes[0].fechada  # a outra foi fechada mesmo assim


def test_configuracao_incompleta_ou_com_backend_desconhecido_e_recusada():
    with pytest.raises(ValueError, match="sem backend"):
        BritechGateway({"a": FakeBackend()}, {"baixar_insumo": "a"})
    with pytest.raises(erros.BackendNaoDisponivel):
        BritechGateway({"a": FakeBackend()}, config(baixar_balancete="nao_existe"))


def test_montar_gateway_recusa_backend_desconhecido():
    with pytest.raises(erros.BackendNaoDisponivel, match="não existe"):
        montar_gateway({op: "selenium" for op in OPERACOES})


def test_backends_api_e_browser_estao_registrados():
    assert {"api", "browser"} <= set(factory._FABRICAS)


def test_montar_gateway_usa_a_configuracao_do_django():
    gw = montar_gateway()  # settings de teste: tudo fake
    assert gw.backend_de("processar_contabil") == "fake"


def test_registrar_backend_permite_plugar_api_e_navegador_nas_proximas_fases(monkeypatch):
    monkeypatch.setitem(factory._FABRICAS, "api", FakeBackend)
    gw = montar_gateway(config(baixar_insumo="api", **{op: "fake" for op in OPERACOES if op != "baixar_insumo"}))
    assert gw.backend_de("baixar_insumo") == "api" and gw.backend_de("baixar_balancete") == "fake"


# --- backend fake ---------------------------------------------------------------------


def test_fake_grava_arquivos_com_nome_canonico(tmp_path):
    fake = FakeBackend()
    with BritechGateway({"a": fake}, config()).sessao(ADM) as s:
        gw = BritechGateway({"a": fake}, config())
        arq = gw.baixar_insumo(s, CARTEIRA, COMP, TipoInsumo.CARTEIRA_FINAL, tmp_path)
        bal = gw.baixar_balancete(s, CARTEIRA, COMP, tmp_path)
    assert arq.tipo == TipoArtefato.INSUMO_CARTEIRA_FINAL
    assert arq.caminho.name == "202608_44680491000134_CarteiraFinal.xlsx" and arq.caminho.read_bytes()
    assert bal.pdf.name == "202608_44680491000134_BalanceteContabilFinal.pdf"
    assert bal.xls.name == "202608_44680491000134_BalanceteContabilFinal.xls"


def test_fake_roteiro_erro_depois_sucesso_e_status(tmp_path):
    fake = FakeBackend()
    fake.programar("baixar_insumo", "44680491", erros.TimeoutBritech, None)
    fake.programar("status_processamento", "44680491", StatusProcessamento.EM_ANDAMENTO)
    gw = BritechGateway({"a": fake}, config())
    with gw.sessao(ADM) as s:
        with pytest.raises(erros.TimeoutBritech):
            gw.baixar_insumo(s, CARTEIRA, COMP, TipoInsumo.EXTRATO_CC, tmp_path)
        assert gw.baixar_insumo(s, CARTEIRA, COMP, TipoInsumo.EXTRATO_CC, tmp_path).caminho.exists()
        assert gw.status_processamento(s, CARTEIRA, COMP) is StatusProcessamento.EM_ANDAMENTO
        assert gw.status_processamento(s, CARTEIRA, COMP) is StatusProcessamento.CONCLUIDO  # roteiro acabou


def test_fake_registra_o_dry_run_do_processamento():
    fake = FakeBackend()
    gw = BritechGateway({"a": fake}, config())
    with gw.sessao(ADM) as s:
        r = gw.processar_contabil(s, [CARTEIRA], COMP, dry_run=True)
    assert r.dry_run and r.carteiras == ("44680491",) and fake.disparos == [(("44680491",), True)]


# --- nomes canônicos -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "tipo, esperado",
    [  # nomes REAIS de Insumos/ recentes (FIDC ACELERA CASH, 202608)
        (TipoInsumo.CARTEIRA_FINAL, "202608_46557432000107_CarteiraFinal.xlsx"),
        (TipoInsumo.CARTEIRA_INICIAL, "202608_46557432000107_CarteiraInicial.xlsx"),
        (TipoInsumo.EXTRATO_CC, "202608_46557432000107_ExtratoCC.xlsx"),
        (TipoInsumo.MOV_COTISTA, "202608_46557432000107_MovCotista.xlsx"),
        (TipoInsumo.POSICAO_COTISTA_FINAL, "202608_46557432000107_SaldoAplicacaoCotistaFinal.xlsx"),
        (TipoInsumo.POSICAO_COTISTA_INICIAL, "202608_46557432000107_SaldoAplicacaoCotistaInicial.xlsx"),
        (TipoInsumo.HISTORICO_COTA, "202608_46557432000107_Histórico de Cota.xlsx"),
    ],
)
def test_nome_insumo_canonico_bate_com_arquivos_reais(tipo, esperado):
    assert nome_insumo_canonico(tipo, CompetenciaRef(2026, 8), "46557432000107") == esperado


def test_nome_do_balancete_canonico():
    assert nome_balancete_canonico(COMP, "46557432000107", ".xls") == "202608_46557432000107_BalanceteContabilFinal.xls"


def test_nome_canonico_do_balancete_e_reconhecido_pelo_populador():
    """O populador (etapa Excel) procura 'balancete' sem 'inicial' — o nome canônico tem que passar."""
    from populador import matching

    canon = matching.canonicalizar(nome_balancete_canonico(COMP, "46557432000107", "xls"))
    assert "balancete" in canon and "inicial" not in canon


# --- contrato de erros -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "erro, retentavel, disjuntor",
    [
        (erros.AutenticacaoFalhou(), False, True),
        (erros.SessaoBloqueada(), True, True),
        (erros.TelaMudou(), False, True),
        (erros.CarteiraNaoEncontrada(), False, False),
        (erros.TimeoutBritech(), True, True),
        (erros.ArquivoInvalido(), True, False),
        (erros.ErroApiBritech(status_http=503), True, True),
        (erros.ErroApiBritech(status_http=404), False, True),
        (erros.ErroApiBritech(status_http=None), True, True),
        (erros.LimiteTaxa(), True, False),
    ],
)
def test_contrato_de_erros(erro, retentavel, disjuntor):
    assert erro.retentavel is retentavel and erro.conta_para_disjuntor is disjuntor


def test_limite_de_taxa_sugere_espera_e_sessao_bloqueada_espera_bastante():
    assert erros.LimiteTaxa(espera_s=90).espera_s == 90
    assert erros.SessaoBloqueada().espera_s == 300
