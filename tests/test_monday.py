import json

import pytest
import requests

from contabilidade_mensal.core.administradoras import CATALOGO, garantir_administradora
from contabilidade_mensal.core.models import Administradora, Fundo
from contabilidade_mensal.integrations.monday.cliente import ClienteMonday, ColunasMonday, ErroMonday, RegistroMonday
from contabilidade_mensal.integrations.monday.sincronizacao import sincronizar

GRUPOS = {"g_fii": "FII", "g_fidc": "FIDC"}


def item(id_, nome, *, cnpj="12.345.678/0001-90", adm="ID CORRETORA", carteira="44.680.491", exercicio="Novembro", sistema="Britech"):
    valores = {
        "texto": cnpj,
        "status8__1": adm,
        "texto3": carteira,
        "exerc_cio_social__1": exercicio,
        "dup__of_administrador_mkkz14qe": sistema,
    }
    return {"id": id_, "name": nome, "column_values": [{"id": k, "text": v} for k, v in valores.items()]}


class RespostaFalsa:
    def __init__(self, corpo, status=200):
        self._corpo, self.status_code = corpo, status

    def json(self):
        if self._corpo is None:
            raise ValueError("sem json")
        return self._corpo


class SessaoFalsa:
    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.consultas: list[str] = []
        self.headers_usados: list[dict] = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.consultas.append(json["query"])
        self.headers_usados.append(headers)
        item_ = self.respostas.pop(0)
        if isinstance(item_, Exception):
            raise item_
        return item_


def pagina_inicial(*grupos):
    return RespostaFalsa({"data": {"boards": [{"groups": list(grupos)}]}})


def grupo(id_, itens, cursor=None):
    return {"id": id_, "items_page": {"cursor": cursor, "items": itens}}


# --- cliente ---------------------------------------------------------------------------------------------------


def test_le_colunas_e_normaliza_carteira_e_exercicio():
    sessao = SessaoFalsa(pagina_inicial(grupo("g_fii", [item("9", "FII KRONOS")])))
    [r] = ClienteMonday("tok", sessao=sessao).buscar_fundos(board_id="1", grupos=GRUPOS)
    assert r == RegistroMonday(
        item_id="9", fundo="FII KRONOS", cnpj="12.345.678/0001-90", administrador="ID CORRETORA",
        carteira="44680491", exercicio_mes=11, tipo="FII", sistema="Britech",
    )  # fmt: skip


def test_pagina_ate_acabar_o_cursor():
    sessao = SessaoFalsa(
        pagina_inicial(grupo("g_fii", [item("1", "A")], cursor="c1")),
        RespostaFalsa({"data": {"next_items_page": {"cursor": "c2", "items": [item("2", "B")]}}}),
        RespostaFalsa({"data": {"next_items_page": {"cursor": None, "items": [item("3", "C")]}}}),
    )
    registros = ClienteMonday("tok", sessao=sessao).buscar_fundos(board_id="1", grupos=GRUPOS)
    assert [r.fundo for r in registros] == ["A", "B", "C"]
    assert 'cursor: "c1"' in sessao.consultas[1] and 'cursor: "c2"' in sessao.consultas[2]


def test_tipo_vem_do_grupo():
    sessao = SessaoFalsa(pagina_inicial(grupo("g_fii", [item("1", "A")]), grupo("g_fidc", [item("2", "B")])))
    tipos = {r.fundo: r.tipo for r in ClienteMonday("tok", sessao=sessao).buscar_fundos(board_id="1", grupos=GRUPOS)}
    assert tipos == {"A": "FII", "B": "FIDC"}


def test_token_vai_no_header_e_nunca_na_consulta_nem_no_erro():
    sessao = SessaoFalsa(RespostaFalsa(None, status=401))
    with pytest.raises(ErroMonday) as e:
        ClienteMonday("token-secreto", sessao=sessao).buscar_fundos(board_id="1", grupos=GRUPOS)
    assert sessao.headers_usados == [{"Authorization": "token-secreto"}]
    assert "token-secreto" not in sessao.consultas[0] and "token-secreto" not in str(e.value)


@pytest.mark.parametrize(
    "resposta",
    [RespostaFalsa(None, 500), RespostaFalsa({"errors": [{"message": "x"}]}), RespostaFalsa(None), requests.ConnectionError("x")],
)
def test_falhas_viram_erro_monday(resposta):
    with pytest.raises(ErroMonday):
        ClienteMonday("tok", sessao=SessaoFalsa(resposta)).buscar_fundos(board_id="1", grupos=GRUPOS)


def test_sem_token_e_recusado_de_cara():
    with pytest.raises(ErroMonday, match="MONDAY_API_TOKEN"):
        ClienteMonday("")


def test_ids_das_colunas_sao_configuraveis():
    colunas = ColunasMonday(cnpj="outra_coluna")
    assert "outra_coluna" in colunas.todas() and "texto" not in colunas.todas()


# --- sincronização -----------------------------------------------------------------------------------------------


def reg(nome="FII KRONOS", *, carteira="44680491", adm="ID CORRETORA", cnpj="12.345.678/0001-90", exercicio=11, tipo="FII", sistema="Britech", item_id="9"):
    return RegistroMonday(item_id, nome, cnpj, adm, carteira, exercicio, tipo, sistema)


def test_cria_o_fundo_e_a_administradora_do_catalogo(db):
    r = sincronizar([reg()])
    fundo = Fundo.objects.get()
    assert (r.criados, r.atualizados) == (1, 0)
    assert (fundo.nome, fundo.cnpj, fundo.exercicio_mes, fundo.tipo, fundo.monday_item_id) == ("FII KRONOS", "12345678000190", 11, "FII", "9")
    assert fundo.administradora.nome == "ID CORRETORA" and fundo.administradora.segredo_ref == "ID_CORRETORA"
    assert fundo.administradora.url_adm == "id"


def test_repetir_a_sincronizacao_nao_altera_nada(db):
    sincronizar([reg()])
    r = sincronizar([reg()])
    assert (r.criados, r.atualizados, r.sem_alteracao) == (0, 0, 1) and Fundo.objects.count() == 1


def test_atualiza_o_que_mudou_no_monday(db):
    sincronizar([reg()])
    r = sincronizar([reg(nome="FII KRONOS RENOMEADO", exercicio=6)])
    fundo = Fundo.objects.get()
    assert r.atualizados == 1 and (fundo.nome, fundo.exercicio_mes) == ("FII KRONOS RENOMEADO", 6)


def test_campo_em_branco_no_monday_nao_apaga_o_que_ja_existe(db):
    sincronizar([reg()])
    r = sincronizar([reg(cnpj="", exercicio=None)])
    fundo = Fundo.objects.get()
    assert (fundo.cnpj, fundo.exercicio_mes) == ("12345678000190", 11)
    assert r.sem_cnpj_valido == ["FII KRONOS"] and r.sem_exercicio == ["FII KRONOS"]


def test_ignora_o_que_nao_e_britech_ou_nao_tem_carteira(db):
    r = sincronizar([reg(sistema="Sinqia"), reg(nome="B", carteira="")])
    assert Fundo.objects.count() == 0 and r.fora_do_sistema_britech == 2


def test_administradora_fora_do_catalogo_e_reportada_e_ignorada(db):
    r = sincronizar([reg(adm="ADM DESCONHECIDA")])
    assert Fundo.objects.count() == 0 and r.administradoras_fora_do_catalogo == {"ADM DESCONHECIDA"}


def test_cnpj_invalido_nao_e_gravado(db):
    r = sincronizar([reg(cnpj="123")])
    assert Fundo.objects.get().cnpj == "" and r.sem_cnpj_valido == ["FII KRONOS"]


def test_mesma_carteira_duas_vezes_e_reportada(db):
    r = sincronizar([reg(), reg(nome="OUTRO NOME")])
    assert Fundo.objects.count() == 1 and len(r.duplicados) == 1


def test_dry_run_nao_grava(db):
    r = sincronizar([reg()], dry_run=True)
    assert r.criados == 1 and Fundo.objects.count() == 0 and Administradora.objects.count() == 0


def test_tipo_desconhecido_vira_outro(db):
    sincronizar([reg(tipo="FUNDO NOVO")])
    assert Fundo.objects.get().tipo == "OUTRO"


# --- catálogo ------------------------------------------------------------------------------------------------------------


def test_catalogo_tem_as_12_administradoras_do_projeto_do_lucas():
    assert len(CATALOGO) == 12 and len({nome for nome, _, _ in CATALOGO}) == 12
    assert ("ID CORRETORA", "id", "ID_CORRETORA") in CATALOGO


def test_garantir_administradora_e_idempotente_e_recusa_desconhecida(db):
    assert garantir_administradora("ID CORRETORA").pk == garantir_administradora(" ID CORRETORA ").pk
    assert garantir_administradora("NAO EXISTE") is None and Administradora.objects.count() == 1
