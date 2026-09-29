import pytest
import requests

from contabilidade_mensal.integrations.britech import erros
from contabilidade_mensal.integrations.britech.api_backend.cliente import ClienteBritech


class RespostaFalsa:
    def __init__(self, status=200, conteudo=b"ok", headers=None, json_data=None):
        self.status_code = status
        self.content = conteudo
        self.text = conteudo.decode("latin-1", errors="replace")
        self.headers = headers or {}
        self._json = json_data

    def json(self):
        if self._json is None:
            raise ValueError("sem json")
        return self._json


class SessaoFalsa:
    def __init__(self, resposta=None, excecao=None):
        self.resposta, self.excecao = resposta, excecao
        self.chamadas = []
        self.fechada = False

    def get(self, url, auth=None, timeout=None):
        self.chamadas.append((url, auth, timeout))
        if self.excecao:
            raise self.excecao
        return self.resposta

    def close(self):
        self.fechada = True


def cliente(resposta=None, excecao=None):
    sessao = SessaoFalsa(resposta, excecao)
    return ClienteBritech("id", "usuario", "senha", sessao=sessao), sessao


def test_monta_a_url_base_e_manda_basic_auth_com_timeout():
    c, sessao = cliente(RespostaFalsa(conteudo=b"dados"))
    assert c.get_bytes("Fundo/BuscaListaFundos?idsCliente=") == b"dados"
    url, auth, timeout = sessao.chamadas[0]
    assert url == "https://id.britech.com.br/WS/api/Fundo/BuscaListaFundos?idsCliente="
    assert auth == ("usuario", "senha") and timeout == (10.0, 180.0)


def test_barra_inicial_e_tolerada():
    c, sessao = cliente(RespostaFalsa())
    c.get("/Fundo/X")
    assert sessao.chamadas[0][0].endswith("/WS/api/Fundo/X")


@pytest.mark.parametrize("status", [401, 403])
def test_401_e_403_sao_falha_de_autenticacao_que_nao_retenta(status):
    c, _ = cliente(RespostaFalsa(status))
    with pytest.raises(erros.AutenticacaoFalhou) as e:
        c.get("Fundo/X")
    assert e.value.retentavel is False and e.value.conta_para_disjuntor is True


def test_429_respeita_o_retry_after():
    c, _ = cliente(RespostaFalsa(429, headers={"Retry-After": "90"}))
    with pytest.raises(erros.LimiteTaxa) as e:
        c.get("Fundo/X")
    assert e.value.espera_s == 90 and e.value.retentavel is True and e.value.conta_para_disjuntor is False


def test_429_sem_retry_after_usa_espera_padrao():
    c, _ = cliente(RespostaFalsa(429))
    with pytest.raises(erros.LimiteTaxa) as e:
        c.get("Fundo/X")
    assert e.value.espera_s == 60


@pytest.mark.parametrize("status, retentavel", [(500, True), (502, True), (503, True), (400, False), (404, False)])
def test_demais_status_seguem_a_regra_de_retentabilidade(status, retentavel):
    c, _ = cliente(RespostaFalsa(status))
    with pytest.raises(erros.ErroApiBritech) as e:
        c.get("Fundo/X")
    assert e.value.retentavel is retentavel and e.value.status_http == status


def test_timeout_de_rede_vira_timeout_britech():
    c, _ = cliente(excecao=requests.Timeout("lento"))
    with pytest.raises(erros.TimeoutBritech):
        c.get("Fundo/X")


def test_falha_de_conexao_e_retentavel():
    c, _ = cliente(excecao=requests.ConnectionError("sem rede"))
    with pytest.raises(erros.ErroApiBritech) as e:
        c.get("Fundo/X")
    assert e.value.retentavel is True


def test_json_invalido():
    c, _ = cliente(RespostaFalsa())
    with pytest.raises(erros.ErroApiBritech):
        c.get_json("Fundo/X")
    ok, _ = cliente(RespostaFalsa(json_data=[{"a": 1}]))
    assert ok.get_json("Fundo/X") == [{"a": 1}]


def test_mensagens_de_erro_nao_carregam_credenciais():
    c, _ = cliente(RespostaFalsa(401))
    with pytest.raises(erros.AutenticacaoFalhou) as e:
        c.get("Fundo/X?idsCliente=1")
    assert "senha" not in str(e.value) and "usuario" not in str(e.value)


def test_fechar_fecha_a_sessao_http():
    c, sessao = cliente(RespostaFalsa())
    c.fechar()
    assert sessao.fechada
