"""Cliente do drive_api (HTTP simulado) e publicador (Drive em memória)."""

import json

import pytest
import requests

from contabilidade_mensal.core.models import PastaCompetencia
from contabilidade_mensal.integrations.britech.erros import ArquivoInvalido
from contabilidade_mensal.integrations.drive.cliente import (
    DestinoJaExiste,
    DriveApiCliente,
    DriveAutenticacaoFalhou,
    DriveErro,
    DriveIndisponivel,
    PastaDriveNaoEncontrada,
)
from contabilidade_mensal.integrations.drive.publicador import PublicadorDrive
from tests.drive_falso import DriveFalso


# --- cliente HTTP ----------------------------------------------------------------------------------------------------


class Resp:
    def __init__(self, status=200, corpo=None, conteudo=b""):
        self.status_code, self._corpo, self.content = status, corpo, conteudo
        self.text = json.dumps(corpo) if corpo is not None else ""

    def json(self):
        return self._corpo


class SessaoHttp:
    def __init__(self, *respostas):
        self.respostas, self.pedidos, self.headers = list(respostas), [], {}

    def request(self, metodo, url, **kw):
        self.pedidos.append((metodo, url, kw))
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def cliente(*respostas):
    sessao = SessaoHttp(*respostas)
    return DriveApiCliente("https://drive.exemplo/api/", "tok-secreto-123", sessao=sessao), sessao


def test_token_vai_no_header_e_nunca_em_erro_ou_repr():
    c, sessao = cliente(Resp(401))
    with pytest.raises(DriveAutenticacaoFalhou) as e:
        c.listar("p")
    assert sessao.headers["Authorization"] == "Token tok-secreto-123"
    assert "tok-secreto-123" not in str(e.value) and "tok-secreto-123" not in repr(c)


def test_sem_url_ou_token_e_recusado():
    with pytest.raises(DriveAutenticacaoFalhou, match="DRIVE_API_TOKEN"):
        DriveApiCliente("https://x", "")


@pytest.mark.parametrize(
    "resposta, erro, retentavel",
    [
        (Resp(500), DriveIndisponivel, True),
        (Resp(429), DriveIndisponivel, True),
        (requests.ConnectionError("x"), DriveIndisponivel, True),
        (requests.Timeout("x"), DriveIndisponivel, True),
        (Resp(400, {"erro": "ruim"}), DriveErro, False),
        (Resp(403), DriveAutenticacaoFalhou, False),
    ],
)
def test_status_e_falhas_viram_erro_tipado(resposta, erro, retentavel):
    c, _ = cliente(resposta)
    with pytest.raises(erro) as e:
        c.baixar("a1")
    assert e.value.retentavel is retentavel


def test_buscar_pasta_404_e_none_e_listar_pagina():
    c, sessao = cliente(Resp(404), Resp(200, {"arquivos": [{"id": "1"}], "next_page_token": "t"}), Resp(200, {"arquivos": [{"id": "2"}], "next_page_token": None}))
    assert c.buscar_pasta("FII", "raiz") is None
    assert [i["id"] for i in c.listar("p")] == ["1", "2"]
    assert sessao.pedidos[2][2]["params"]["page_token"] == "t"
    assert sessao.pedidos[0][1] == "https://drive.exemplo/api/pastas/buscar/"


def test_enviar_manda_multipart_com_pasta_e_nome(tmp_path):
    arquivo = tmp_path / "b.xlsb"
    arquivo.write_bytes(b"dados")
    c, sessao = cliente(Resp(201, {"id": "novo"}))
    assert c.enviar("pasta1", arquivo)["id"] == "novo"
    _, url, kw = sessao.pedidos[0]
    assert url.endswith("arquivos/") and kw["data"] == {"pasta_pai_id": "pasta1", "nome": "b.xlsb"} and "arquivo" in kw["files"]


def test_enviar_para_pasta_inexistente(tmp_path):
    arquivo = tmp_path / "b.xlsb"
    arquivo.write_bytes(b"x")
    c, _ = cliente(Resp(404))
    with pytest.raises(PastaDriveNaoEncontrada):
        c.enviar("nada", arquivo)


# --- publicador ------------------------------------------------------------------------------------------------------


@pytest.fixture
def fundo_drive(criar_fundo):
    return criar_fundo(1001, nome="FII KRONOS", tipo="FII", exercicio_mes=11)


@pytest.fixture
def boleta(tmp_path):
    arquivo = tmp_path / "FII KRONOS 202608.xlsb"
    arquivo.write_bytes(b"boleta-conteudo")
    return arquivo


def preparar(drive):
    drive.caminho("FII", "FII KRONOS")  # Tipo e Fundo existem; Data Base e AAAAMM ainda não


def test_cria_data_base_e_competencia_e_envia_com_hash_conferido(fundo_drive, competencia, boleta):
    drive = DriveFalso()
    preparar(drive)
    feita = PublicadorDrive(drive, "raiz").publicar(fundo_drive, competencia, boleta)
    assert feita.caminho_relativo == "FII/FII KRONOS/Data Base Novembro 2026/202608"
    assert drive.conteudos[feita.file_id] == b"boleta-conteudo" and feita.reaproveitada is False
    assert PastaCompetencia.objects.get(fundo=fundo_drive, competencia=competencia).drive_folder_id == feita.pasta_id


def test_publicar_de_novo_reaproveita_sem_novo_upload(fundo_drive, competencia, boleta):
    drive = DriveFalso()
    preparar(drive)
    pub = PublicadorDrive(drive, "raiz")
    primeira = pub.publicar(fundo_drive, competencia, boleta)
    segunda = pub.publicar(fundo_drive, competencia, boleta)
    assert segunda.reaproveitada is True and segunda.file_id == primeira.file_id and drive.envios == 1


def test_tipo_ou_fundo_inexistente_nao_e_criado(fundo_drive, competencia, boleta):
    drive = DriveFalso()
    drive.caminho("FII")  # falta a pasta do fundo
    with pytest.raises(PastaDriveNaoEncontrada, match="FII KRONOS"):
        PublicadorDrive(drive, "raiz").publicar(fundo_drive, competencia, boleta)
    assert drive.envios == 0 and not PastaCompetencia.objects.exists()


def test_outra_planilha_na_pasta_bloqueia_sem_forcar(fundo_drive, competencia, boleta):
    drive = DriveFalso()
    pasta = drive.caminho("FII", "FII KRONOS", "Data Base Novembro 2026", "202608")
    drive.arquivo("Boleta manual.xlsb", pasta, b"feita-a-mao")
    with pytest.raises(DestinoJaExiste, match="Boleta manual"):
        PublicadorDrive(drive, "raiz").publicar(fundo_drive, competencia, boleta)
    assert drive.envios == 0 and drive.conteudos[next(iter(drive.conteudos))] == b"feita-a-mao"  # nada foi tocado


def test_forcar_sobrescreve_o_mesmo_nome(fundo_drive, competencia, boleta):
    drive = DriveFalso()
    pasta = drive.caminho("FII", "FII KRONOS", "Data Base Novembro 2026", "202608")
    antigo = drive.arquivo(boleta.name, pasta, b"versao-antiga")
    feita = PublicadorDrive(drive, "raiz").publicar(fundo_drive, competencia, boleta, forcar=True)
    assert feita.file_id == antigo and drive.conteudos[antigo] == b"boleta-conteudo" and drive.sobrescritas == 1


def test_upload_corrompido_tem_uma_segunda_chance(fundo_drive, competencia, boleta):
    drive = DriveFalso()
    preparar(drive)
    drive.corromper_proximo_envio = 1
    feita = PublicadorDrive(drive, "raiz").publicar(fundo_drive, competencia, boleta)
    assert drive.conteudos[feita.file_id] == b"boleta-conteudo" and drive.sobrescritas == 1


def test_upload_sempre_corrompido_falha_com_arquivo_invalido(fundo_drive, competencia, boleta):
    drive = DriveFalso()
    preparar(drive)
    drive.corromper_proximo_envio = 5
    with pytest.raises(ArquivoInvalido, match="SHA-256"):
        PublicadorDrive(drive, "raiz").publicar(fundo_drive, competencia, boleta)


def test_dry_run_prever_nao_cria_nem_envia(fundo_drive, competencia, boleta):
    drive = DriveFalso()
    preparar(drive)
    n_itens = len(drive.itens)
    previsao = PublicadorDrive(drive, "raiz").prever(fundo_drive, competencia, boleta)
    assert previsao.acao == "criar pastas e enviar" and previsao.pasta_existe is False
    assert len(drive.itens) == n_itens and drive.envios == 0 and not PastaCompetencia.objects.exists()


def test_prever_reaproveitar_e_conflito(fundo_drive, competencia, boleta):
    drive = DriveFalso()
    pub = PublicadorDrive(drive, "raiz")
    pasta = drive.caminho("FII", "FII KRONOS", "Data Base Novembro 2026", "202608")
    assert pub.prever(fundo_drive, competencia, boleta).acao == "enviar"
    drive.arquivo(boleta.name, pasta, b"boleta-conteudo")
    assert pub.prever(fundo_drive, competencia, boleta).acao == "reaproveitar"
    drive.conteudos[next(iter(drive.conteudos))] = b"outra coisa"
    assert pub.prever(fundo_drive, competencia, boleta).acao == "conflito"


def test_id_da_pasta_corrigido_no_admin_vale_mais_que_o_nome(fundo_drive, competencia, boleta):
    drive = DriveFalso()
    real = drive.caminho("Pasta com outro nome")
    PastaCompetencia.objects.create(fundo=fundo_drive, competencia=competencia, drive_folder_id=real)
    feita = PublicadorDrive(drive, "raiz").publicar(fundo_drive, competencia, boleta)
    assert feita.pasta_id == real and drive.envios == 1


def test_sem_raiz_configurada():
    with pytest.raises(PastaDriveNaoEncontrada, match="DRIVE_RAIZ_ID"):
        PublicadorDrive(DriveFalso(), "")
