import pandas as pd
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from contabilidade_mensal.core.choices import TipoArtefato
from contabilidade_mensal.core.models import Fundo
from contabilidade_mensal.core.administradoras import garantir_administradora
from contabilidade_mensal.integrations.britech.erros import AutenticacaoFalhou
from contabilidade_mensal.integrations.britech.interface import ArquivoBaixado
from contabilidade_mensal.storage.comparacao import comparar_pastas

CNPJ = "12345678000190"


def salvar(pasta, nome, linhas, colunas=("A", "B")):
    pasta.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(linhas, columns=list(colunas)).to_excel(pasta / nome, index=False)


def test_pastas_iguais(tmp_path):
    for p in ("a", "b"):
        salvar(tmp_path / p, f"202608_{CNPJ}_MovCotista.xlsx", [[1, "x"], [2, None]])
    r = comparar_pastas(tmp_path / "a", tmp_path / "b")
    assert r.ok and len(r.iguais) == 1


def test_id_no_nome_de_fundo_de_classe_unica_e_ignorado(tmp_path):
    salvar(tmp_path / "a", f"202608_{CNPJ}_MovCotista.xlsx", [[1, "x"]])
    salvar(tmp_path / "b", f"202608_111_{CNPJ}_MovCotista.xlsx", [[1, "x"]])
    assert comparar_pastas(tmp_path / "a", tmp_path / "b").ok


def test_em_arquivos_separados_o_id_faz_parte_da_chave(tmp_path):
    salvar(tmp_path / "a" / "Arquivos separados", f"202608_111_{CNPJ}_ExtratoCC.xlsx", [[1, "x"]])
    salvar(tmp_path / "b" / "Arquivos separados", f"202608_222_{CNPJ}_ExtratoCC.xlsx", [[1, "x"]])
    r = comparar_pastas(tmp_path / "a", tmp_path / "b")
    assert not r.ok and len(r.so_em_a) == 1 and len(r.so_em_b) == 1


def test_aponta_a_celula_diferente(tmp_path):
    nome = f"202608_{CNPJ}_ExtratoCC.xlsx"
    salvar(tmp_path / "a", nome, [[1, "x"], [2, "y"]])
    salvar(tmp_path / "b", nome, [[1, "x"], [2, "z"]])
    r = comparar_pastas(tmp_path / "a", tmp_path / "b")
    [(rotulo, difs)] = r.diferentes.items()
    assert rotulo.endswith("ExtratoCC")
    assert [(d.linha, d.coluna, d.a, d.b) for d in difs] == [(3, "B", "y", "z")]


def test_estrutura_diferente(tmp_path):
    nome = f"202608_{CNPJ}_ExtratoCC.xlsx"
    salvar(tmp_path / "a", nome, [[1, "x"]])
    salvar(tmp_path / "b", nome, [[1, "x"], [2, "y"]])
    [detalhe] = comparar_pastas(tmp_path / "a", tmp_path / "b").diferentes.values()
    assert isinstance(detalhe, str) and "linhas" in detalhe


def test_arquivo_so_de_um_lado(tmp_path):
    salvar(tmp_path / "a", f"202608_{CNPJ}_ExtratoCC.xlsx", [[1, "x"]])
    (tmp_path / "b").mkdir()
    r = comparar_pastas(tmp_path / "a", tmp_path / "b")
    assert not r.ok and len(r.so_em_a) == 1


def test_comando_falha_quando_diferente_e_passa_quando_igual(tmp_path):
    nome = f"202608_{CNPJ}_ExtratoCC.xlsx"
    salvar(tmp_path / "a", nome, [[1, "x"]])
    salvar(tmp_path / "b", nome, [[1, "x"]])
    call_command("comparar_insumos", a=tmp_path / "a", b=tmp_path / "b")
    salvar(tmp_path / "b", nome, [[1, "outro"]])
    with pytest.raises(CommandError, match="NÃO"):
        call_command("comparar_insumos", a=tmp_path / "a", b=tmp_path / "b")


def test_comando_recusa_pasta_inexistente(tmp_path):
    with pytest.raises(CommandError, match="não encontrada"):
        call_command("comparar_insumos", a=tmp_path / "nada", b=tmp_path)


# --- baixar_insumos_api ---------------------------------------------------------------------------------------


class SessaoFalsa:
    fechada = False

    def fechar(self):
        self.fechada = True


class BackendFalso:
    def __init__(self, falha_em=None):
        self.falha_em, self.sessao, self.pedidos = falha_em, SessaoFalsa(), []

    def abrir_sessao(self, administradora):
        self.administradora = administradora
        return self.sessao

    def baixar_insumo(self, sessao, carteira, competencia, tipo, destino):
        self.pedidos.append((carteira, competencia, tipo))
        if tipo == self.falha_em:
            raise AutenticacaoFalhou("credencial recusada")
        destino.mkdir(parents=True, exist_ok=True)
        arquivo = destino / f"{competencia.aaaamm}_{carteira.cnpj}_{tipo.value}.xlsx"
        arquivo.write_bytes(b"conteudo")
        return ArquivoBaixado(TipoArtefato.INSUMO_EXTRATO_CC, arquivo)


@pytest.fixture
def fundo(db):
    return Fundo.objects.create(
        administradora=garantir_administradora("ID CORRETORA"), codigo_britech="777", cnpj=CNPJ, nome="FII X", exercicio_mes=11
    )


def rodar(monkeypatch, backend, tmp_path, **extra):
    from contabilidade_mensal.core.management.commands import baixar_insumos_api

    monkeypatch.setattr(baixar_insumos_api, "criar_backend", lambda: backend)
    call_command(
        "baixar_insumos_api", administradora="ID CORRETORA", carteira="777", ano=2026, mes=8, destino=tmp_path / "out", **extra
    )


def test_baixa_todos_os_insumos_e_fecha_a_sessao(fundo, monkeypatch, tmp_path, capsys):
    backend = BackendFalso()
    rodar(monkeypatch, backend, tmp_path)
    assert len(backend.pedidos) == 7 and backend.sessao.fechada
    assert backend.administradora.segredo_ref == "ID_CORRETORA"
    assert "sha256=" in capsys.readouterr().out
    assert len(list((tmp_path / "out").glob("*.xlsx"))) == 7


def test_tipos_restringem_o_que_e_baixado(fundo, monkeypatch, tmp_path):
    backend = BackendFalso()
    rodar(monkeypatch, backend, tmp_path, tipos=["ExtratoCC"])
    assert [p[2].value for p in backend.pedidos] == ["ExtratoCC"]


def test_falha_de_um_insumo_nao_impede_os_outros_mas_falha_o_comando(fundo, monkeypatch, tmp_path):
    from contabilidade_mensal.integrations.britech.interface import TipoInsumo

    backend = BackendFalso(falha_em=TipoInsumo.EXTRATO_CC)
    with pytest.raises(CommandError, match="1 insumo"):
        rodar(monkeypatch, backend, tmp_path)
    assert len(backend.pedidos) == 7 and backend.sessao.fechada


def test_fundo_desconhecido(db, monkeypatch, tmp_path):
    with pytest.raises(CommandError, match="sincronizar_cadastro"):
        rodar(monkeypatch, BackendFalso(), tmp_path)
