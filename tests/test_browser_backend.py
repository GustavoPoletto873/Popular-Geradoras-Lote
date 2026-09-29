"""Page Objects e sessão do backend `browser`, contra a PAS FALSA (tests/pas_falsa.py) — sem tocar a Britech.

Rodam por padrão (só precisam do Chromium do Playwright instalado; sem ele, são pulados).
"""

import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest

from contabilidade_mensal.core.models import Administradora
from contabilidade_mensal.integrations.britech.api_backend.credenciais import Credencial
from contabilidade_mensal.integrations.britech.browser_backend.backend import BrowserBackend
from contabilidade_mensal.integrations.britech.browser_backend.config import ConfigNavegador
from contabilidade_mensal.integrations.britech.browser_backend.pages.balancete_page import BalanceteContabilPage
from contabilidade_mensal.integrations.britech.browser_backend.pages.processo_contabil_page import ProcessoContabilPage
from contabilidade_mensal.integrations.britech.browser_backend.session import SessaoNavegador
from contabilidade_mensal.integrations.britech.erros import (
    ArquivoInvalido,
    AutenticacaoFalhou,
    CarteiraNaoEncontrada,
    OperacaoNaoSuportada,
    ProcessamentoNaoAutorizado,
    SessaoBloqueada,
    TelaMudou,
)
from contabilidade_mensal.integrations.britech.interface import AdministradoraRef, CarteiraRef, CompetenciaRef
from contabilidade_mensal.integrations.britech.erros import BritechErro as BritechErroBase
from tests.pas_falsa import PasFalsa

ADM = AdministradoraRef("ID CORRETORA", "id", "ID_CORRETORA")
CNPJ = "12345678000190"
COMPETENCIA = CompetenciaRef(2026, 8)
CARTEIRA_101 = CarteiraRef("101", CNPJ, "FUNDO 101", 12)
CARTEIRA_4468 = CarteiraRef("44680491", "98765432000110", "FUNDO 4468", 12)
TIMEOUT_MS = 3_000


def _chromium_disponivel() -> bool:
    def _tentar() -> bool:
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as p:
                p.chromium.launch(headless=True).close()
            return True
        except Exception:  # noqa: BLE001
            return False

    with ThreadPoolExecutor(1) as pool:
        return pool.submit(_tentar).result()


@pytest.fixture(scope="module", autouse=True)
def _exige_chromium():
    if not _chromium_disponivel():
        pytest.skip("Chromium do Playwright não instalado (`playwright install chromium`)")


@pytest.fixture
def pas():
    return PasFalsa()


@pytest.fixture
def cfg(tmp_path):
    return ConfigNavegador(headless=True, timeout_ms=TIMEOUT_MS, tentativas_logout=2, pasta_evidencias=tmp_path / "evidencias")


@pytest.fixture
def abrir(pas, cfg):
    abertas = []

    def _abrir(*, senha=None, usuario=None) -> SessaoNavegador:
        sessao = SessaoNavegador(ADM, usuario or pas.usuario, senha or pas.senha, cfg, preparar_contexto=pas.instalar)
        abertas.append(sessao)
        return sessao.abrir()

    yield _abrir
    for sessao in abertas:
        try:
            sessao.fechar()
        except Exception:  # noqa: BLE001 - os testes que esperam erro de logout já o verificaram
            pass


def _processo_contabil(sessao, fluxo):
    return sessao.executar("pc", lambda page, base: fluxo(ProcessoContabilPage(page, base, timeout_ms=TIMEOUT_MS)))


# --- login / logout -------------------------------------------------------------------------------------------------


def test_login_e_logout_confirmados(pas, abrir):
    sessao = abrir()
    assert pas.logado and pas.logins == 1
    sessao.fechar()
    assert not pas.logado and pas.logouts == 1
    assert pas.requisicoes_bloqueadas == []  # nada saiu para fora da PAS falsa


def test_fechar_e_idempotente(pas, abrir):
    sessao = abrir()
    sessao.fechar()
    sessao.fechar()
    assert pas.logouts == 1


def test_senha_errada_e_autenticacao_falhou_e_nao_deixa_navegador_aberto(pas, abrir):
    with pytest.raises(AutenticacaoFalhou) as e:
        abrir(senha="senha-errada-123")
    assert "senha-errada-123" not in str(e.value) and pas.logins == 0


def test_senha_nao_vaza_na_mensagem_de_erro_quando_a_tela_de_login_muda(pas, cfg):
    def sem_campos(contexto):
        contexto.route("**/*", lambda rota: rota.fulfill(status=200, content_type="text/html", body="<html>manutenção</html>"))

    sessao = SessaoNavegador(ADM, "usuario.x", "SenhaQueNaoPodeVazar!", cfg, preparar_contexto=sem_campos)
    with pytest.raises(TelaMudou) as e:
        sessao.abrir()
    assert "SenhaQueNaoPodeVazar!" not in str(e.value)
    assert "SenhaQueNaoPodeVazar!" not in repr(e.value.__cause__) and e.value.__suppress_context__


def test_repr_da_sessao_nao_tem_credenciais(pas, abrir):
    texto = repr(abrir())
    assert pas.senha not in texto and pas.usuario not in texto


def test_logout_nao_confirmado_vira_sessao_bloqueada(pas, abrir):
    sessao = abrir()
    pas.logout_funciona = False
    with pytest.raises(SessaoBloqueada, match="não confirmado"):
        sessao.fechar()
    assert pas.logado  # ficou presa na "Britech" e o erro avisa; o navegador foi encerrado mesmo assim


def test_sessao_que_ja_caiu_nao_e_erro_ao_fechar(pas, abrir):
    sessao = abrir()
    pas.derrubar_sessao()
    sessao.fechar()  # goto -> tela de login -> nada a fazer


def test_varias_sessoes_seguidas_nao_deixam_sessao_presa(pas, abrir):
    for _ in range(5):
        abrir().fechar()
    assert pas.logins == pas.logouts == 5 and not pas.logado


def test_orm_funciona_com_a_sessao_de_navegador_aberta(pas, abrir, db):
    """O motivo da thread dedicada: o worker grava no banco entre as ações do navegador."""
    sessao = abrir()
    Administradora.objects.create(nome="X", url_adm="x", segredo_ref="X")
    assert Administradora.objects.count() == 1
    sessao.fechar()


# --- Processo Contábil ----------------------------------------------------------------------------------------------


def test_seleciona_carteiras_em_lote_e_processar_so_e_clicado_quando_pedido(pas, abrir):
    sessao = abrir()

    def fluxo(pagina):
        pagina.abrir()
        pagina.selecionar_carteira("101")
        pagina.selecionar_carteira("44680491")
        return pagina.botao_processar_presente()

    assert _processo_contabil(sessao, fluxo) is True
    assert pas.processamentos == []  # selecionar NÃO processa
    _processo_contabil(sessao, lambda p: (p.abrir(), p.selecionar_carteira("101"), p.clicar_processar()))
    assert pas.processamentos == [["101"]]  # a página foi reaberta: seleção nova


def test_selecao_e_cumulativa_no_grid(pas, abrir):
    sessao = abrir()

    def fluxo(pagina):
        pagina.abrir()
        pagina.selecionar_carteira("101")
        pagina.selecionar_carteira("44680491")
        pagina.clicar_processar()
        pagina.page.wait_for_load_state("networkidle")  # o POST do fetch do "Processar" já chegou à PAS falsa

    _processo_contabil(sessao, fluxo)
    assert sorted(pas.processamentos[-1]) == ["101", "44680491"]


def test_carteira_inexistente(pas, abrir):
    sessao = abrir()
    with pytest.raises(CarteiraNaoEncontrada, match="não retornou resultado"):
        _processo_contabil(sessao, lambda p: (p.abrir(), p.selecionar_carteira("555")))


def test_carteira_ambigua_exige_exatamente_um_resultado(pas, abrir):
    sessao = abrir()
    with pytest.raises(CarteiraNaoEncontrada, match="encontrado 2"):
        _processo_contabil(sessao, lambda p: (p.abrir(), p.selecionar_carteira("700")))


def test_tela_sem_o_campo_de_filtro_vira_tela_mudou(pas, abrir, monkeypatch):
    from contabilidade_mensal.integrations.britech.browser_backend import seletores

    monkeypatch.setattr(seletores, "PC_FILTRO_CARTEIRA", "#campo_que_nao_existe")
    sessao = abrir()
    with pytest.raises(TelaMudou, match="iframe"):
        _processo_contabil(sessao, lambda p: p.abrir())


# --- evidência de falha -----------------------------------------------------------------------------------------------


def test_falha_gera_screenshot_e_trace_sem_a_senha(pas, abrir):
    sessao = abrir()
    with pytest.raises(CarteiraNaoEncontrada):
        _processo_contabil(sessao, lambda p: (p.abrir(), p.selecionar_carteira("555")))
    tipos = sorted(caminho.suffix for caminho in sessao.evidencias)
    assert tipos == [".png", ".zip"]
    trace = next(c for c in sessao.evidencias if c.suffix == ".zip")
    with zipfile.ZipFile(trace) as z:
        for nome in z.namelist():
            conteudo = z.read(nome)
            assert pas.senha.encode() not in conteudo, nome
    sessao.fechar()  # e a sessão continua utilizável/encerrável depois de gerar o trace


def test_sucesso_nao_deixa_evidencia(pas, abrir, cfg):
    sessao = abrir()
    _processo_contabil(sessao, lambda p: (p.abrir(), p.selecionar_carteira("101")))
    sessao.fechar()
    assert sessao.evidencias == [] and not cfg.pasta_evidencias.exists()


# --- Balancete ----------------------------------------------------------------------------------------------------


def _balancete(sessao, fluxo):
    return sessao.executar("bal", lambda page, base: fluxo(BalanceteContabilPage(page, base, timeout_ms=TIMEOUT_MS)))


def test_baixa_pdf_e_excel_da_carteira_no_periodo(pas, abrir, tmp_path):
    sessao = abrir()

    def fluxo(pagina):
        pagina.abrir()
        pagina.selecionar_carteira("101")
        pagina.preencher_periodo("01/08/2026", "31/08/2026")
        return pagina.baixar_pdf(tmp_path / "b.pdf"), pagina.baixar_excel(tmp_path / "b.xls")

    pdf, xls = _balancete(sessao, fluxo)
    assert pdf.read_text() == xls.read_text() == "balancete|101|01/08/2026|31/08/2026"
    assert [d["tipo"] for d in pas.downloads] == ["pdf", "xls"]


def test_troca_de_carteira_desmarca_a_anterior(pas, abrir, tmp_path):
    sessao = abrir()

    def fluxo(pagina):
        pagina.abrir()
        pagina.selecionar_carteira("101")
        pagina.selecionar_carteira("44680491", desmarcar="101")
        pagina.preencher_periodo("01/08/2026", "31/08/2026")
        return pagina.baixar_pdf(tmp_path / "b.pdf")

    assert _balancete(sessao, fluxo).read_text().startswith("balancete|44680491|")  # só a segunda, nunca as duas


def test_sessao_que_cai_na_tela_de_balancete_vira_sessao_bloqueada(pas, abrir):
    sessao = abrir()
    pas.derrubar_sessao()
    with pytest.raises(SessaoBloqueada, match="caiu"):
        _balancete(sessao, lambda p: p.abrir())


def test_carteira_fora_da_lista_do_balancete(pas, abrir):
    sessao = abrir()
    with pytest.raises(CarteiraNaoEncontrada):
        _balancete(sessao, lambda p: (p.abrir(), p.selecionar_carteira("555")))


def test_download_vazio_e_arquivo_invalido(pas, abrir, tmp_path, monkeypatch):
    from contabilidade_mensal.integrations.britech.browser_backend import seletores

    monkeypatch.setattr(seletores, "BAL_BOTAO_PDF", "#botao_que_nao_existe")
    sessao = abrir()
    with pytest.raises(ArquivoInvalido):
        _balancete(sessao, lambda p: (p.abrir(), p.baixar_pdf(tmp_path / "x.pdf")))


# --- backend ------------------------------------------------------------------------------------------------------


class Credenciais:
    def __init__(self, pas):
        self.pas = pas

    def obter(self, segredo_ref):
        return Credencial(self.pas.usuario, self.pas.senha)


def test_backend_abre_sessao_e_recusa_o_que_nao_e_dele(pas, cfg):
    backend = BrowserBackend(Credenciais(pas), cfg, preparar_contexto=pas.instalar)
    sessao = backend.abrir_sessao(ADM)
    try:
        with pytest.raises(OperacaoNaoSuportada, match="Q4"):
            backend.status_processamento(sessao, CARTEIRA_101, COMPETENCIA)
        with pytest.raises(OperacaoNaoSuportada):
            backend.baixar_insumo(sessao, CARTEIRA_101, COMPETENCIA, None, None)
    finally:
        sessao.fechar()
    assert pas.logins == pas.logouts == 1


def test_backend_sem_credencial_falha_antes_de_abrir_o_navegador(cfg):
    from contabilidade_mensal.integrations.britech.api_backend.credenciais import CredenciaisDoAmbiente

    backend = BrowserBackend(CredenciaisDoAmbiente({}), cfg)
    with pytest.raises(AutenticacaoFalhou, match="BRITECH_ID_CORRETORA_USER"):
        backend.abrir_sessao(ADM)


# --- diagnóstico e regras de código --------------------------------------------------------------------------------


def test_diagnostico_repete_login_telas_e_logout(pas, cfg):
    from contabilidade_mensal.integrations.britech.browser_backend.diagnostico import verificar_sessao

    backend = BrowserBackend(Credenciais(pas), cfg, preparar_contexto=pas.instalar)
    resultados = verificar_sessao(backend, ADM, repeticoes=3, timeout_ms=TIMEOUT_MS)
    assert [r.numero for r in resultados] == [1, 2, 3]
    assert pas.logins == pas.logouts == 3 and not pas.logado and pas.processamentos == []  # nunca processa


def test_diagnostico_com_logout_preso_interrompe_a_serie(pas, cfg):
    from contabilidade_mensal.integrations.britech.browser_backend.diagnostico import verificar_sessao

    pas.logout_funciona = False
    backend = BrowserBackend(Credenciais(pas), cfg, preparar_contexto=pas.instalar)
    with pytest.raises(SessaoBloqueada):
        verificar_sessao(backend, ADM, repeticoes=5, timeout_ms=TIMEOUT_MS)
    assert pas.logins == 1


def test_codigo_do_navegador_nao_tem_pausa_fixa():
    from pathlib import Path

    import contabilidade_mensal.integrations.britech.browser_backend as pacote

    for arquivo in Path(pacote.__file__).parent.rglob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        assert "wait_for_timeout" not in texto and "time.sleep" not in texto, arquivo.name


# --- Fase 4: fluxos ---------------------------------------------------------------------------------------------------


@pytest.fixture
def backend(pas, cfg):
    def _criar(allowlist=()):
        return BrowserBackend(Credenciais(pas), cfg, preparar_contexto=pas.instalar, allowlist_processar=allowlist)

    return _criar


def test_dry_run_seleciona_mas_nao_clica_em_processar(pas, backend):
    b = backend(allowlist=["101"])
    sessao = b.abrir_sessao(ADM)
    try:
        r = b.processar_contabil(sessao, [CARTEIRA_101], COMPETENCIA, dry_run=True)
    finally:
        sessao.fechar()
    assert r.dry_run is True and r.carteiras == ("101",)
    assert pas.processamentos == []


def test_clique_real_exige_allowlist_e_falha_antes_de_abrir_a_tela(pas, backend):
    b = backend(allowlist=["outra"])
    sessao = b.abrir_sessao(ADM)
    try:
        with pytest.raises(ProcessamentoNaoAutorizado, match="101"):
            b.processar_contabil(sessao, [CARTEIRA_101], COMPETENCIA, dry_run=False)
    finally:
        sessao.fechar()
    assert pas.processamentos == [] and sessao.evidencias == []  # nem chegou a abrir a tela


def test_clique_real_na_allowlist_processa_o_lote_inteiro(pas, backend):
    b = backend(allowlist=["101", "44680491"])
    sessao = b.abrir_sessao(ADM)
    try:
        r = b.processar_contabil(sessao, [CARTEIRA_101, CARTEIRA_4468], COMPETENCIA, dry_run=False)
    finally:
        sessao.fechar()
    assert r.dry_run is False and r.carteiras == ("101", "44680491")
    assert len(pas.processamentos) == 1 and sorted(pas.processamentos[0]) == ["101", "44680491"]  # UM clique


def test_carteira_ruim_no_lote_impede_qualquer_processamento(pas, backend):
    b = backend(allowlist=["101", "555"])
    sessao = b.abrir_sessao(ADM)
    try:
        with pytest.raises(CarteiraNaoEncontrada, match="555"):
            b.processar_contabil(sessao, [CARTEIRA_101, CarteiraRef("555", CNPJ)], COMPETENCIA, dry_run=False)
    finally:
        sessao.fechar()
    assert pas.processamentos == []  # nada foi processado, nem a carteira boa
    assert {c.suffix for c in sessao.evidencias} == {".png", ".zip"}


def test_sessao_que_cai_antes_do_processamento_nunca_termina_em_sucesso(pas, backend):
    b = backend(allowlist=["101"])
    sessao = b.abrir_sessao(ADM)
    try:
        pas.derrubar_sessao()
        with pytest.raises(BritechErroBase):
            b.processar_contabil(sessao, [CARTEIRA_101], COMPETENCIA, dry_run=False)
    finally:
        sessao.fechar()
    assert pas.processamentos == []


def test_balancete_usa_o_periodo_da_competencia_e_nomes_canonicos(pas, backend, tmp_path):
    b = backend()
    sessao = b.abrir_sessao(ADM)
    try:
        r = b.baixar_balancete(sessao, CARTEIRA_101, COMPETENCIA, tmp_path / "saida")
    finally:
        sessao.fechar()
    assert r.pdf.name == f"202608_{CNPJ}_BalanceteContabilFinal.pdf"
    assert r.xls.name == f"202608_{CNPJ}_BalanceteContabilFinal.xls"
    assert r.pdf.read_text() == r.xls.read_text() == "balancete|101|01/08/2026|31/08/2026"  # mês fechado, não datas fixas


def test_balancete_de_fevereiro_bissexto(pas, backend, tmp_path):
    b = backend()
    sessao = b.abrir_sessao(ADM)
    try:
        r = b.baixar_balancete(sessao, CARTEIRA_101, CompetenciaRef(2028, 2), tmp_path)
    finally:
        sessao.fechar()
    assert r.pdf.read_text() == "balancete|101|01/02/2028|29/02/2028"


def test_balancete_de_carteira_inexistente_gera_erro_tipado(pas, backend, tmp_path):
    b = backend()
    sessao = b.abrir_sessao(ADM)
    try:
        with pytest.raises(CarteiraNaoEncontrada):
            b.baixar_balancete(sessao, CarteiraRef("555", CNPJ), COMPETENCIA, tmp_path)
    finally:
        sessao.fechar()
    assert not list(tmp_path.glob("*.pdf")) and not list(tmp_path.glob("*.xls"))  # nada baixado (a pasta tem só as evidências)


def test_pipeline_com_o_backend_browser_e_a_pas_falsa(pas, backend, tmp_path, settings, db):
    """Gateway + BrowserBackend + PAS falsa: processar (espera mínima) -> balancete, com o worker gravando no banco."""
    import datetime as dt

    from contabilidade_mensal.core.choices import Etapa, StatusEtapa
    from contabilidade_mensal.core.models import Competencia, EtapaExecucao, Fundo
    from contabilidade_mensal.integrations.britech.factory import BritechGateway
    from contabilidade_mensal.integrations.britech.fake import FakeBackend
    from contabilidade_mensal.pipeline import fakes, servicos
    from contabilidade_mensal.pipeline.definicao import FILAS
    from contabilidade_mensal.pipeline.relogio import RelogioSimulado
    from contabilidade_mensal.pipeline.worker import drenar

    settings.PIPELINE = {"processamento_conclusao": "espera", "processamento_espera_s": 120, "polling_intervalo_s": 60}
    adm = Administradora.objects.create(nome="ID CORRETORA", url_adm="id", segredo_ref="ID_CORRETORA")
    fundo = Fundo.objects.create(
        administradora=adm, codigo_britech="101", cnpj=CNPJ, nome="FUNDO 101", tipo="FII", exercicio_mes=12
    )
    comp = Competencia.objects.create(ano=2026, mes=8)
    operacoes = {
        "baixar_insumo": "fake",
        "processar_contabil": "browser",
        "status_processamento": "browser",
        "baixar_balancete": "browser",
    }
    gateway = BritechGateway({"fake": FakeBackend(), "browser": backend(allowlist=["101"])}, operacoes)
    relogio = RelogioSimulado(dt.datetime(2026, 9, 1, 8, 0, tzinfo=dt.timezone.utc))
    handlers = fakes.montar_handlers(gateway, tmp_path / "staging", dry_run_processar=False)

    execucao = servicos.criar_execucao(comp, [fundo], agora=relogio())
    drenar(FILAS, handlers, relogio)

    status = {e.etapa: e.status for e in EtapaExecucao.objects.filter(execucao=execucao)}
    assert status[Etapa.PROCESSAR_CONTABIL] == StatusEtapa.SUCESSO
    assert status[Etapa.BAIXAR_BALANCETE] == StatusEtapa.SUCESSO
    assert pas.processamentos == [["101"]]
    assert pas.logins == pas.logouts and not pas.logado  # nenhuma sessão presa
