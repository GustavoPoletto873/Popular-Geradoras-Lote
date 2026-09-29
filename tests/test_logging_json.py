import json
import logging

from contabilidade_mensal.observability.logging import JsonFormatter, contexto, contexto_atual


def formatar(mensagem="oi", **extra):
    registro = logging.LogRecord("x", logging.INFO, __file__, 1, mensagem, (), None)
    for chave, valor in extra.items():
        setattr(registro, chave, valor)
    return json.loads(JsonFormatter().format(registro))


def test_linha_json_tem_campos_fixos():
    linha = formatar("iniciando")
    assert linha["mensagem"] == "iniciando" and linha["nivel"] == "INFO" and linha["logger"] == "x"
    assert linha["ts"].endswith("+00:00")


def test_contexto_aparece_dentro_do_bloco_e_some_fora():
    with contexto(execucao_id=7, fundo="FII X"):
        assert formatar()["execucao_id"] == 7
        with contexto(etapa="baixar_insumos"):
            linha = formatar()
            assert linha["execucao_id"] == 7 and linha["etapa"] == "baixar_insumos"
        assert "etapa" not in formatar()
    assert contexto_atual() == {}


def test_campos_none_sao_ignorados_no_contexto():
    with contexto(fundo=None, etapa="x"):
        assert "fundo" not in contexto_atual()


def test_campos_extras_do_log_entram_no_json():
    assert formatar(artefatos=3)["artefatos"] == 3


def test_valores_sensiveis_sao_mascarados():
    linha = formatar(senha="abc123", api_token="xyz", Authorization="Basic zzz", cookie="a=b", normal="ok")
    assert linha["senha"] == linha["api_token"] == linha["Authorization"] == linha["cookie"] == "***"
    assert linha["normal"] == "ok"
    with contexto(password="segredo"):
        assert formatar()["password"] == "***"


def test_acentos_saem_escapados_para_qualquer_console():
    bruto = JsonFormatter().format(logging.LogRecord("x", logging.INFO, __file__, 1, "conclusão", (), None))
    assert "\\u00e3" in bruto and json.loads(bruto)["mensagem"] == "conclusão"


def test_excecao_vai_no_campo_excecao():
    try:
        raise ValueError("falhou")
    except ValueError:
        import sys

        registro = logging.LogRecord("x", logging.ERROR, __file__, 1, "erro", (), sys.exc_info())
    assert "ValueError: falhou" in json.loads(JsonFormatter().format(registro))["excecao"]
