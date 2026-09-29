"""ApiBackend de ponta a ponta com um cliente HTTP FALSO (sem rede): arquivos, nomes, empilhamento, PDFs, datas."""

import re
from pathlib import Path

import pandas as pd
import pytest

from contabilidade_mensal.core.choices import TipoArtefato
from contabilidade_mensal.integrations.britech import erros
from contabilidade_mensal.integrations.britech.api_backend import urls
from contabilidade_mensal.integrations.britech.api_backend.backend import ApiBackend
from contabilidade_mensal.integrations.britech.api_backend.cadastro import ler_cadastro, normalizar_cnpj
from contabilidade_mensal.integrations.britech.api_backend.credenciais import Credencial, CredenciaisDoAmbiente
from contabilidade_mensal.integrations.britech.factory import BritechGateway, OPERACOES
from contabilidade_mensal.integrations.britech.interface import (
    AdministradoraRef,
    CarteiraRef,
    CompetenciaRef,
    TipoInsumo,
)
from tests.paridade import cenarios as cen

DOURADOS = Path(__file__).parent / "dourados"
ADM = AdministradoraRef("ID CORRETORA", "id", "ID_CORRETORA")
COMP = CompetenciaRef(*cen.COMPETENCIA)
CARTEIRA = CarteiraRef("111", cen.FUNDO["cnpj"], cen.FUNDO["fundo"], cen.FUNDO["exercicio_mes"])


class CredenciaisFalsas:
    def obter(self, segredo_ref):
        return Credencial("u", "s")


def cadastro_json(classes, implantacao="2020-01-01T00:00:00"):
    return [
        {
            "ClienteInfo": {"IdCliente": int(id_), "Implantacao": implantacao},
            "CarteiraInfo": {"Nome": nome, "CPFCNPJFundo": "12.345.678/0001-90"},
        }
        for id_, nome in classes
    ]


class ClienteFalso:
    """Serve as respostas sintéticas do cenário e registra as URLs chamadas."""

    def __init__(self, cenario_por_tipo, classes):
        self.cenario_por_tipo = cenario_por_tipo  # ex.: {"CarteiraFinal": "carteira_final"}
        self.classes = classes
        self.chamadas: list[str] = []
        self.fechado = False
        self.falhar_pdf = False

    def fechar(self):
        self.fechado = True

    def _cenario(self, url):
        for chave, cenario in self.cenario_por_tipo.items():
            if chave in url:
                return cenario
        raise AssertionError(f"URL inesperada: {url}")

    def get_bytes(self, caminho):
        self.chamadas.append(caminho)
        if "TipoArquivo=PDF" in caminho:
            if self.falhar_pdf:
                raise erros.ErroApiBritech("PDF indisponível", status_http=500)
            return b"%PDF-fake"
        return self._resposta(caminho)[1]

    def get_json(self, caminho):
        self.chamadas.append(caminho)
        if caminho == urls.CADASTRO_FUNDOS:
            return cadastro_json(self.classes)
        return self._resposta(caminho)[1]

    def _resposta(self, caminho):
        id_ = re.search(r"(?:IdCarteira|IdCliente|IdsCarteira|idCarteira)=(\d+)", caminho).group(1)
        return cen.entrada(self._cenario(caminho), id_)


def backend_com(cliente):
    return ApiBackend(CredenciaisFalsas(), fabrica_cliente=lambda *a, **k: cliente)


def baixar(cliente, tipo, tmp_path, carteira=CARTEIRA):
    backend = backend_com(cliente)
    sessao = backend.abrir_sessao(ADM)
    return backend.baixar_insumo(sessao, carteira, COMP, tipo, tmp_path)


def conteudo(caminho):
    return pd.read_excel(caminho)


def igual(a, b):
    pd.testing.assert_frame_equal(a, b, check_dtype=False)


# --- ativo ----------------------------------------------------------------------------------------------------


def test_carteira_final_gera_xlsx_canonico_e_pdf_de_evidencia(tmp_path):
    cliente = ClienteFalso({"RelatorioComposicaoCarteira": "carteira_final"}, [cen.CLASSE_1])
    r = baixar(cliente, TipoInsumo.CARTEIRA_FINAL, tmp_path)

    assert r.tipo == TipoArtefato.INSUMO_CARTEIRA_FINAL
    assert r.caminho.name == "202608_12345678000190_CarteiraFinal.xlsx"
    assert [c.caminho.name for c in r.complementos] == ["202608_12345678000190_CarteiraFinal.pdf"]
    assert r.complementos[0].tipo == TipoArtefato.INSUMO_PDF
    igual(conteudo(r.caminho), conteudo(DOURADOS / "carteira_final/saida/202608_12345678000190_CarteiraFinal.xlsx"))


def test_carteira_inicial_usa_a_data_do_fim_do_exercicio_anterior(tmp_path):
    cliente = ClienteFalso({"RelatorioComposicaoCarteira": "carteira_inicial"}, [cen.CLASSE_1])
    baixar(cliente, TipoInsumo.CARTEIRA_INICIAL, tmp_path)
    excel = [c for c in cliente.chamadas if "ExcelAlinhado" in c][0]
    assert f"DataReferencia={cen.FIM_ANTERIOR}&" in excel


def test_extrato_usa_inicio_do_exercicio_e_data_final(tmp_path):
    cliente = ClienteFalso({"RelatorioExtratoContaCorrente": "extrato_padrao"}, [cen.CLASSE_1])
    r = baixar(cliente, TipoInsumo.EXTRATO_CC, tmp_path)
    excel = [c for c in cliente.chamadas if "RelatorioExtratoContaCorrente" in c and "TipoArquivo=Excel" in c][0]
    assert f"DataInicio={cen.INICIO_EXERCICIO}&DataFim={cen.DATA_FINAL}&" in excel
    igual(conteudo(r.caminho), conteudo(DOURADOS / "extrato_padrao/saida/202608_12345678000190_ExtratoCC.xlsx"))


def test_data_de_implantacao_posterior_adia_o_inicio_do_exercicio(tmp_path):
    cliente = ClienteFalso({"RelatorioExtratoContaCorrente": "extrato_padrao"}, [cen.CLASSE_1])
    cliente.get_json = lambda caminho: cadastro_json([cen.CLASSE_1], implantacao="2026-02-10T00:00:00")
    baixar(cliente, TipoInsumo.EXTRATO_CC, tmp_path)
    assert "DataInicio=2026-02-10&" in cliente.chamadas[0]  # get_json foi trocado: só a URL do extrato foi registrada


# --- passivo: empilhamento por classes ------------------------------------------------------------------------------


def test_mov_cotista_com_duas_classes_empilha_e_guarda_os_separados(tmp_path):
    cliente = ClienteFalso({"OperacaoCotistaAnalitico": "mov_duas_classes"}, [cen.CLASSE_1, cen.CLASSE_2])
    r = baixar(cliente, TipoInsumo.MOV_COTISTA, tmp_path)

    assert r.caminho.name == "202608_12345678000190_MovCotista.xlsx"
    igual(conteudo(r.caminho), conteudo(DOURADOS / "mov_duas_classes/saida/202608_12345678000190_MovCotista.xlsx"))
    separados = sorted(p.name for p in (tmp_path / "Arquivos separados").iterdir())
    assert separados == ["202608_111_12345678000190_MovCotista.xlsx", "202608_222_12345678000190_MovCotista.xlsx"]
    for id_ in ("111", "222"):
        nome = f"202608_{id_}_12345678000190_MovCotista.xlsx"
        igual(conteudo(tmp_path / "Arquivos separados" / nome), conteudo(DOURADOS / "mov_duas_classes/saida/Arquivos separados" / nome))


def test_mov_cotista_com_uma_classe_gera_so_o_arquivo_canonico(tmp_path):
    cliente = ClienteFalso({"OperacaoCotistaAnalitico": "mov_uma_classe"}, [cen.CLASSE_1])
    r = baixar(cliente, TipoInsumo.MOV_COTISTA, tmp_path)
    assert r.caminho.name == "202608_12345678000190_MovCotista.xlsx"  # canônico, sem id (o original deixava o id no nome)
    assert not (tmp_path / "Arquivos separados").exists()
    igual(conteudo(r.caminho), conteudo(DOURADOS / "mov_uma_classe/saida/202608_111_12345678000190_MovCotista.xlsx"))


def test_posicao_inicial_uma_pdf_por_classe_e_data_do_fim_anterior(tmp_path):
    cliente = ClienteFalso({"RelatorioSaldoAplicacoesCotista": "posicao_inicial_duas_classes"}, [cen.CLASSE_1, cen.CLASSE_2])
    r = baixar(cliente, TipoInsumo.POSICAO_COTISTA_INICIAL, tmp_path)
    assert r.caminho.name == "202608_12345678000190_SaldoAplicacaoCotistaInicial.xlsx"
    assert sorted(c.caminho.name for c in r.complementos) == [
        "202608_111_12345678000190_SaldoAplicacaoCotistaInicial.pdf",
        "202608_222_12345678000190_SaldoAplicacaoCotistaInicial.pdf",
    ]
    assert all(f"DataReferencia={cen.FIM_ANTERIOR}&" in c for c in cliente.chamadas if "RelatorioSaldo" in c)
    igual(conteudo(r.caminho), conteudo(DOURADOS / "posicao_inicial_duas_classes/saida/202608_12345678000190_SaldoAplicacaoCotistaInicial.xlsx"))


def test_historico_de_cota_usa_o_formato_datetime_do_original(tmp_path):
    cliente = ClienteFalso({"BuscaHistoricoCotaRentabilidade": "historico_duas_classes"}, [cen.CLASSE_1, cen.CLASSE_2])
    r = baixar(cliente, TipoInsumo.HISTORICO_COTA, tmp_path)
    assert all(f"DataFim={cen.DATA_FINAL} 00:00:00" in c for c in cliente.chamadas if "Historico" in c)
    igual(conteudo(r.caminho), conteudo(DOURADOS / "historico_duas_classes/saida/202608_12345678000190_Histórico de Cota.xlsx"))


def test_cadastro_e_consultado_uma_unica_vez_por_sessao(tmp_path):
    cliente = ClienteFalso({"OperacaoCotistaAnalitico": "mov_duas_classes", "BuscaHistorico": "historico_duas_classes"}, [cen.CLASSE_1, cen.CLASSE_2])
    backend = backend_com(cliente)
    sessao = backend.abrir_sessao(ADM)
    backend.baixar_insumo(sessao, CARTEIRA, COMP, TipoInsumo.MOV_COTISTA, tmp_path)
    backend.baixar_insumo(sessao, CARTEIRA, COMP, TipoInsumo.HISTORICO_COTA, tmp_path)
    assert cliente.chamadas.count(urls.CADASTRO_FUNDOS) == 1


# --- falhas -------------------------------------------------------------------------------------------------------------------


def test_pdf_que_falha_nao_derruba_o_insumo(tmp_path):
    cliente = ClienteFalso({"RelatorioComposicaoCarteira": "carteira_final"}, [cen.CLASSE_1])
    cliente.falhar_pdf = True
    r = baixar(cliente, TipoInsumo.CARTEIRA_FINAL, tmp_path)
    assert r.caminho.exists() and r.complementos == ()


def test_cadastro_incompleto_e_recusado_antes_de_chamar_a_api(tmp_path):
    cliente = ClienteFalso({}, [cen.CLASSE_1])
    with pytest.raises(erros.CadastroIncompleto):
        baixar(cliente, TipoInsumo.CARTEIRA_FINAL, tmp_path, carteira=CarteiraRef("111", cen.FUNDO["cnpj"], "X", None))
    with pytest.raises(erros.CadastroIncompleto):
        baixar(cliente, TipoInsumo.CARTEIRA_FINAL, tmp_path, carteira=CarteiraRef("111", "", "X", 11))
    assert cliente.chamadas == []


def test_cnpj_sem_carteira_no_cadastro(tmp_path):
    cliente = ClienteFalso({"OperacaoCotistaAnalitico": "mov_uma_classe"}, [])
    with pytest.raises(erros.CarteiraNaoEncontrada):
        baixar(cliente, TipoInsumo.MOV_COTISTA, tmp_path)


def test_planilha_ilegivel_vira_arquivo_invalido(tmp_path):
    cliente = ClienteFalso({"RelatorioComposicaoCarteira": "carteira_final"}, [cen.CLASSE_1])
    cliente.get_bytes = lambda caminho: b"isto nao e uma planilha"
    with pytest.raises(erros.ArquivoInvalido):
        baixar(cliente, TipoInsumo.CARTEIRA_FINAL, tmp_path)


def test_resposta_vazia_vira_arquivo_invalido(tmp_path):
    cliente = ClienteFalso({"RelatorioComposicaoCarteira": "carteira_final"}, [cen.CLASSE_1])
    cliente.get_bytes = lambda caminho: b""
    with pytest.raises(erros.ArquivoInvalido):
        baixar(cliente, TipoInsumo.CARTEIRA_FINAL, tmp_path)


def test_operacoes_que_a_api_nao_cobre_sao_recusadas():
    backend = backend_com(ClienteFalso({}, []))
    sessao = backend.abrir_sessao(ADM)
    with pytest.raises(erros.OperacaoNaoSuportada):
        backend.processar_contabil(sessao, [CARTEIRA], COMP, dry_run=True)
    with pytest.raises(erros.OperacaoNaoSuportada):
        backend.baixar_balancete(sessao, CARTEIRA, COMP, Path("."))


def test_pelo_gateway_a_sessao_do_cliente_e_fechada(tmp_path):
    cliente = ClienteFalso({"RelatorioComposicaoCarteira": "carteira_final"}, [cen.CLASSE_1])
    gateway = BritechGateway({"api": backend_com(cliente)}, {op: "api" for op in OPERACOES})
    with gateway.sessao(ADM) as s:
        gateway.baixar_insumo(s, CARTEIRA, COMP, TipoInsumo.CARTEIRA_FINAL, tmp_path)
    assert cliente.fechado


# --- credenciais e cadastro ---------------------------------------------------------------------------------------------------


def test_credenciais_do_ambiente_sem_expor_valores():
    provedor = CredenciaisDoAmbiente({"BRITECH_ID_CORRETORA_USER": "joao", "BRITECH_ID_CORRETORA_SENHA": "s3gredo"})
    c = provedor.obter("ID_CORRETORA")
    assert c.usuario == "joao" and c.senha == "s3gredo"
    assert "s3gredo" not in repr(c)  # a senha nunca aparece em repr/log


def test_credencial_ausente_e_erro_de_autenticacao_sem_vazar_nada():
    with pytest.raises(erros.AutenticacaoFalhou, match="BRITECH_OUTRA_USER"):
        CredenciaisDoAmbiente({"BRITECH_OUTRA_SENHA": "x"}).obter("OUTRA")
    with pytest.raises(erros.AutenticacaoFalhou):
        CredenciaisDoAmbiente({}).obter("")


def test_ler_cadastro_normaliza_cnpj_e_datas():
    classes = ler_cadastro(cadastro_json([cen.CLASSE_1, cen.CLASSE_2], implantacao="2024-05-17T00:00:00"))
    assert [(c.id_cliente, c.cnpj) for c in classes] == [("111", "12345678000190"), ("222", "12345678000190")]
    assert str(classes[0].implantacao) == "2024-05-17"
    assert normalizar_cnpj("12.345.678/0001-90") == "12345678000190" and normalizar_cnpj(None) == ""


def test_cadastro_sem_as_colunas_esperadas():
    with pytest.raises(erros.EstruturaInesperada):
        ler_cadastro([{"outra": 1}])


def test_carteira_nao_consulta_o_cadastro(tmp_path):
    """A carteira não depende da data de implantação; um cadastro fora do ar não pode derrubá-la."""
    cliente = ClienteFalso({"RelatorioComposicaoCarteira": "carteira_final"}, [cen.CLASSE_1])
    cliente.get_json = lambda caminho: (_ for _ in ()).throw(erros.ErroApiBritech("cadastro fora do ar", status_http=500))
    assert baixar(cliente, TipoInsumo.CARTEIRA_FINAL, tmp_path).caminho.exists()
