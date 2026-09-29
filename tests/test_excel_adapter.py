"""Adapter do Excel (sem abrir o Excel: o populador é substituído) + pipeline com populador e publicador reais-de-mentira."""

import contextlib
from types import SimpleNamespace

import pytest

from contabilidade_mensal.core.choices import Etapa, StatusEtapa, TipoArtefato
from contabilidade_mensal.core.models import Artefato, EtapaExecucao
from contabilidade_mensal.integrations.excel.adapter import ErroExcel, PopuladorExcel, PopulacaoRecusada
from contabilidade_mensal.integrations.excel.origem import BoletaAnteriorAusente, OrigemDrive, OrigemLocal
from contabilidade_mensal.integrations.drive.publicador import PublicadorDrive
from contabilidade_mensal.pipeline import fakes, servicos
from contabilidade_mensal.pipeline.definicao import FILAS
from contabilidade_mensal.pipeline.worker import drenar
from populador import config as cfg_pop
from tests.drive_falso import DriveFalso


@pytest.fixture
def fundo_kronos(criar_fundo):
    return criar_fundo(1001, nome="FII KRONOS", tipo="FII", exercicio_mes=11)


def raiz_local_com_boleta_anterior(tmp_path, nome="FII KRONOS 202607.xlsb", conteudo=b"modelo-julho"):
    pasta = tmp_path / "G" / "FII" / "FII KRONOS" / "Data Base Novembro 2026" / "202607"
    pasta.mkdir(parents=True)
    (pasta / nome).write_bytes(conteudo)
    return tmp_path / "G"


class ExcelFalso:
    """Substitui `popular_arquivo`: registra o que recebeu e devolve o resultado programado."""

    def __init__(self, status=cfg_pop.STATUS_SALVO, erro=None, avisos=()):
        self.status, self.erro, self.avisos, self.chamadas = status, erro, list(avisos), []

    def __call__(self, sessao, **kw):
        self.chamadas.append(kw)
        caminho = None
        if self.status == cfg_pop.STATUS_SALVO:
            caminho = kw["pasta_saida"] / f"{kw['fundo']} {kw['periodo_destino']}.xlsb"
            caminho.write_bytes(b"boleta-populada")
        return SimpleNamespace(status=self.status, caminho=caminho, avisos=self.avisos, erro=self.erro)


def populador(origem, excel):
    return PopuladorExcel(origem, sessao=contextlib.nullcontext, popular=excel)


def arquivos(tmp_path):
    pasta = tmp_path / "ins"
    pasta.mkdir()
    nomes = ["202608_1_CarteiraFinal.xlsx", "202608_1_ExtratoCC.xlsx", "202608_1_BalanceteContabilFinal.xls"]
    for n in nomes:
        (pasta / n).write_bytes(n.encode())
    return sorted(pasta.iterdir())


# --- adapter ----------------------------------------------------------------------------------------------------------


def test_monta_a_pasta_de_trabalho_e_devolve_a_boleta(fundo_kronos, competencia, tmp_path):
    excel = ExcelFalso(avisos=["aviso x"])
    origem = OrigemLocal(raiz_local_com_boleta_anterior(tmp_path))
    gerada = populador(origem, excel).popular(
        fundo=fundo_kronos, competencia=competencia, arquivos=arquivos(tmp_path), pasta_trabalho=tmp_path / "trab"
    )
    chamada = excel.chamadas[0]
    assert gerada.caminho.read_bytes() == b"boleta-populada" and gerada.avisos == ["aviso x"]
    assert chamada["fundo"] == "FII KRONOS" and chamada["periodo_destino"] == "202608"
    assert (chamada["pasta_origem"] / "FII KRONOS 202607.xlsb").read_bytes() == b"modelo-julho"  # o mês ANTERIOR
    assert sorted(p.name for p in chamada["pasta_insumos"].iterdir()) == [
        "202608_1_BalanceteContabilFinal.xls",
        "202608_1_CarteiraFinal.xlsx",
        "202608_1_ExtratoCC.xlsx",
    ]


def test_reexecucao_comeca_limpa(fundo_kronos, competencia, tmp_path):
    origem = OrigemLocal(raiz_local_com_boleta_anterior(tmp_path))
    excel = ExcelFalso()
    pop = populador(origem, excel)
    trabalho = tmp_path / "trab"
    (trabalho / "Saida").mkdir(parents=True)
    (trabalho / "Saida" / "sobra_de_tentativa_anterior.xlsb").write_bytes(b"lixo")
    pop.popular(fundo=fundo_kronos, competencia=competencia, arquivos=arquivos(tmp_path), pasta_trabalho=trabalho)
    assert [p.name for p in (trabalho / "Saida").iterdir()] == ["FII KRONOS 202608.xlsb"]


def test_sem_boleta_anterior_e_erro_claro_e_nao_abre_o_excel(fundo_kronos, competencia, tmp_path):
    excel = ExcelFalso()
    with pytest.raises(BoletaAnteriorAusente, match="202607"):
        populador(OrigemLocal(tmp_path / "vazio"), excel).popular(
            fundo=fundo_kronos, competencia=competencia, arquivos=arquivos(tmp_path), pasta_trabalho=tmp_path / "t"
        )
    assert excel.chamadas == []


def test_janeiro_busca_dezembro_do_ano_anterior(criar_fundo, tmp_path):
    from contabilidade_mensal.core.models import Competencia

    fundo = criar_fundo(1002, nome="FII X", tipo="FII", exercicio_mes=12)
    pasta = tmp_path / "G" / "FII" / "FII X" / "Data Base Dezembro 2025" / "202512"
    pasta.mkdir(parents=True)
    (pasta / "FII X 202512.xlsx").write_bytes(b"dez")
    alvo = OrigemLocal(tmp_path / "G").obter(fundo, Competencia(ano=2026, mes=1), tmp_path / "o")
    assert alvo.read_bytes() == b"dez"


@pytest.mark.parametrize(
    "status, erro_esperado, retentavel",
    [
        (cfg_pop.STATUS_ERRO, ErroExcel, True),
        (cfg_pop.STATUS_NAO_PROCESSADO, PopulacaoRecusada, False),
        (cfg_pop.STATUS_PASTA_NAO_ENCONTRADA, PopulacaoRecusada, False),
    ],
)
def test_status_do_populador_viram_erros_tipados(status, erro_esperado, retentavel, fundo_kronos, competencia, tmp_path):
    origem = OrigemLocal(raiz_local_com_boleta_anterior(tmp_path))
    with pytest.raises(erro_esperado) as e:
        populador(origem, ExcelFalso(status=status, erro="detalhe")).popular(
            fundo=fundo_kronos, competencia=competencia, arquivos=arquivos(tmp_path), pasta_trabalho=tmp_path / "t"
        )
    assert e.value.retentavel is retentavel


def test_origem_drive_baixa_a_planilha_do_mes_anterior(fundo_kronos, competencia, tmp_path):
    drive = DriveFalso()
    pasta = drive.caminho("FII", "FII KRONOS", "Data Base Novembro 2026", "202607")
    drive.arquivo("FII KRONOS 202607.xlsb", pasta, b"modelo-do-drive")
    drive.arquivo("Insumos", pasta, b"")  # não é planilha
    origem = OrigemDrive(drive, PublicadorDrive(drive, "raiz"))
    assert origem.obter(fundo_kronos, competencia, tmp_path / "o").read_bytes() == b"modelo-do-drive"


def test_origem_drive_sem_pasta_ou_sem_planilha(fundo_kronos, competencia, tmp_path):
    drive = DriveFalso()
    drive.caminho("FII", "FII KRONOS")
    origem = OrigemDrive(drive, PublicadorDrive(drive, "raiz"))
    with pytest.raises(BoletaAnteriorAusente):
        origem.obter(fundo_kronos, competencia, tmp_path / "o")


# --- pipeline inteiro com populador e publicador --------------------------------------------------------------------


def test_pipeline_ponta_a_ponta_com_excel_e_drive_reais_de_mentira(
    fundo_kronos, competencia, relogio, gateway, raiz_staging, tmp_path
):
    drive = DriveFalso()
    drive.caminho("FII", "FII KRONOS")
    origem = OrigemLocal(raiz_local_com_boleta_anterior(tmp_path))
    handlers = fakes.montar_handlers(
        gateway,
        raiz_staging,
        populador=populador(origem, ExcelFalso()),
        publicador=PublicadorDrive(drive, "raiz"),
    )
    execucao = servicos.criar_execucao(competencia, [fundo_kronos], agora=relogio())
    drenar(FILAS, handlers, relogio)

    status = {e.etapa: e.status for e in EtapaExecucao.objects.filter(execucao=execucao)}
    assert set(status.values()) == {StatusEtapa.SUCESSO}
    publicado = Artefato.objects.get(etapa_execucao__etapa=Etapa.PUBLICAR_DRIVE, tipo=TipoArtefato.BOLETA)
    assert publicado.drive_file_id and publicado.verificado_em and publicado.drive_checksum == publicado.sha256
    assert drive.conteudos[publicado.drive_file_id] == b"boleta-populada"

    # reexecutar: idempotente, sem novo upload
    servicos.criar_execucao(competencia, [fundo_kronos], agora=relogio())
    drenar(FILAS, handlers, relogio)
    assert drive.envios == 1


def test_publicar_em_dry_run_so_preve(fundo_kronos, competencia, relogio, gateway, raiz_staging, tmp_path):
    drive = DriveFalso()
    drive.caminho("FII", "FII KRONOS")
    origem = OrigemLocal(raiz_local_com_boleta_anterior(tmp_path))
    handlers = fakes.montar_handlers(
        gateway,
        raiz_staging,
        dry_run_publicar=True,
        populador=populador(origem, ExcelFalso()),
        publicador=PublicadorDrive(drive, "raiz"),
    )
    execucao = servicos.criar_execucao(competencia, [fundo_kronos], agora=relogio())
    drenar(FILAS, handlers, relogio)
    assert drive.envios == 0
    etapa = EtapaExecucao.objects.get(execucao=execucao, etapa=Etapa.PUBLICAR_DRIVE)
    assert etapa.status == StatusEtapa.SUCESSO
    assert Artefato.objects.filter(etapa_execucao=etapa).count() == 0  # nada publicado, nada registrado
    assert not any(i["name"].endswith(".xlsb") for i in drive.itens.values())


def test_boleta_anterior_ausente_falha_a_etapa_sem_retry(fundo_kronos, competencia, relogio, gateway, raiz_staging, tmp_path):
    handlers = fakes.montar_handlers(
        gateway, raiz_staging, populador=populador(OrigemLocal(tmp_path / "nada"), ExcelFalso())
    )
    execucao = servicos.criar_execucao(competencia, [fundo_kronos], agora=relogio())
    drenar(FILAS, handlers, relogio)
    e = EtapaExecucao.objects.get(execucao=execucao, etapa=Etapa.POPULAR_EXCEL)
    assert e.status == StatusEtapa.FALHA and e.erro_tipo == "boleta_anterior_ausente" and e.tentativas == 1
    assert EtapaExecucao.objects.get(execucao=execucao, etapa=Etapa.PUBLICAR_DRIVE).status == StatusEtapa.PULADO
