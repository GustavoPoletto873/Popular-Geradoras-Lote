"""PARIDADE com o código original do Simplifica.

Os arquivos em tests/dourados/ foram gerados pelo código ORIGINAL (pandas 2) sobre entradas sintéticas
(tools/paridade/gerar_dourados.py). Aqui as transformações PORTADAS (rodando em pandas 3) recebem as
mesmas entradas, e o resultado gravado em Excel tem que ser IGUAL, célula a célula.
"""

import json
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from contabilidade_mensal.core import calendario
from contabilidade_mensal.integrations.britech.api_backend import urls
from contabilidade_mensal.integrations.britech.api_backend.transformacoes.carteira import transformar_composicao_carteira
from contabilidade_mensal.integrations.britech.api_backend.transformacoes.empilhar import empilhar
from contabilidade_mensal.integrations.britech.api_backend.transformacoes.extrato import transformar_extrato
from contabilidade_mensal.integrations.britech.api_backend.transformacoes.historico_cota import transformar_historico_cota
from contabilidade_mensal.integrations.britech.api_backend.transformacoes.mov_cotista import transformar_mov_cotista
from contabilidade_mensal.integrations.britech.api_backend.transformacoes.posicao_cotista import transformar_posicao_cotista
from tests.paridade import cenarios as cen

DOURADOS = Path(__file__).parent / "dourados"
BASE = "https://id.britech.com.br/WS/api/"
CNPJ = cen.FUNDO["cnpj"]
AAAAMM = "202608"


def ler(caminho: Path) -> pd.DataFrame:
    return pd.read_excel(caminho)


def como_excel(df: pd.DataFrame, tmp_path: Path, nome: str = "nosso.xlsx") -> pd.DataFrame:
    caminho = tmp_path / nome
    df.to_excel(caminho, index=False)
    return pd.read_excel(caminho)


def assert_igual(nosso: pd.DataFrame, referencia: pd.DataFrame) -> None:
    pd.testing.assert_frame_equal(nosso, referencia, check_dtype=False, check_exact=False, rtol=0, atol=0)


def bruto_excel(cenario: str, id_classe: str = "111") -> pd.DataFrame:
    _, conteudo = cen.entrada(cenario, id_classe)
    return pd.read_excel(BytesIO(conteudo))


def urls_de_referencia(cenario: str) -> list[str]:
    return json.loads((DOURADOS / cenario / "urls.json").read_text(encoding="utf-8"))


def referencia_empilhada(cenario: str, sufixo: str) -> Path:
    """Arquivo final do cenário: o empilhado (sem id) se houve mais de uma classe; senão o único com id."""
    saida = DOURADOS / cenario / "saida"
    empilhado = saida / f"{AAAAMM}_{CNPJ}_{sufixo}.xlsx"
    if empilhado.exists():
        return empilhado
    unicos = list(saida.glob(f"{AAAAMM}_*_{CNPJ}_{sufixo}.xlsx"))
    assert len(unicos) == 1, unicos
    return unicos[0]


# --- as datas que o backend calcula batem com as do cenário do original -----------------------------------------


def test_datas_do_calendario_batem_com_as_do_cenario():
    final = calendario.data_final_carteira(*cen.COMPETENCIA)
    fim = calendario.fim_exercicio_anterior(cen.FUNDO["exercicio_mes"], final)
    assert final.isoformat() == cen.DATA_FINAL
    assert fim.isoformat() == cen.FIM_ANTERIOR
    assert calendario.inicio_exercicio(fim, None).isoformat() == cen.INICIO_EXERCICIO
    assert calendario.ano_exercicio_proximo(fim) == int(cen.FUNDO["ano_exercicio_proximo"])


# --- carteira ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("cenario", ["carteira_final", "carteira_inicial", "carteira_sem_rentabilidade"])
def test_carteira_igual_ao_original(cenario, tmp_path):
    inicial = cen.CENARIOS[cenario]["inicial"]
    data = cen.FIM_ANTERIOR if inicial else cen.DATA_FINAL
    sufixo = "CarteiraInicial" if inicial else "CarteiraFinal"

    nosso = transformar_composicao_carteira(bruto_excel(cenario), id_carteira="111", data_ref=data)

    assert_igual(como_excel(nosso, tmp_path), ler(DOURADOS / cenario / "saida" / f"{AAAAMM}_{CNPJ}_{sufixo}.xlsx"))
    esperadas = [
        BASE + urls.composicao_carteira("111", data, tipo_arquivo="ExcelAlinhado"),
        BASE + urls.composicao_carteira("111", data, tipo_arquivo="PDF"),
    ]
    assert urls_de_referencia(cenario) == esperadas


# --- extrato ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("cenario", ["extrato_padrao", "extrato_colunas_deslocadas", "extrato_sem_movimentacao"])
def test_extrato_igual_ao_original(cenario, tmp_path):
    nosso = transformar_extrato(bruto_excel(cenario), id_carteira="111")

    assert_igual(como_excel(nosso, tmp_path), ler(DOURADOS / cenario / "saida" / f"{AAAAMM}_{CNPJ}_ExtratoCC.xlsx"))
    esperadas = [
        BASE + urls.extrato_conta_corrente("111", cen.INICIO_EXERCICIO, cen.DATA_FINAL, tipo_arquivo="Excel"),
        BASE + urls.extrato_conta_corrente("111", cen.INICIO_EXERCICIO, cen.DATA_FINAL, tipo_arquivo="PDF"),
    ]
    assert urls_de_referencia(cenario) == esperadas


# --- passivo: movimentação, posição, histórico (por classe, depois empilhados) ---------------------------------------------


def _dfs_por_classe(cenario: str, transformar) -> list[pd.DataFrame]:
    return [transformar(id_, nome) for id_, nome in cen.CENARIOS[cenario]["classes"]]


@pytest.mark.parametrize("cenario", ["mov_uma_classe", "mov_duas_classes", "mov_sem_operacoes", "mov_fora_do_periodo"])
def test_mov_cotista_igual_ao_original(cenario, tmp_path):
    def transformar(id_, nome):
        _, registros = cen.entrada(cenario, id_)
        return transformar_mov_cotista(
            registros, id_carteira=id_, nome_classe=nome, data_inicio=cen.INICIO_EXERCICIO, data_fim=cen.DATA_FINAL
        )

    por_classe = _dfs_por_classe(cenario, transformar)
    assert_igual(como_excel(empilhar(por_classe, "MovCotista"), tmp_path), ler(referencia_empilhada(cenario, "MovCotista")))
    _comparar_separados(cenario, "MovCotista", por_classe, tmp_path)
    assert urls_de_referencia(cenario) == [BASE + urls.mov_cotista(id_) for id_, _ in cen.CENARIOS[cenario]["classes"]]


@pytest.mark.parametrize(
    "cenario",
    ["posicao_final_data_col4", "posicao_final_data_col5", "posicao_sem_aplicacoes", "posicao_inicial_duas_classes"],
)
def test_posicao_cotista_igual_ao_original(cenario, tmp_path):
    inicial = cen.CENARIOS[cenario]["inicial"]
    sufixo = "SaldoAplicacaoCotistaInicial" if inicial else "SaldoAplicacaoCotistaFinal"
    data = cen.FIM_ANTERIOR if inicial else cen.DATA_FINAL

    def transformar(id_, nome):
        return transformar_posicao_cotista(bruto_excel(cenario, id_), id_carteira=id_, nome_classe=nome)

    por_classe = _dfs_por_classe(cenario, transformar)
    assert_igual(como_excel(empilhar(por_classe, sufixo), tmp_path), ler(referencia_empilhada(cenario, sufixo)))
    _comparar_separados(cenario, sufixo, por_classe, tmp_path)
    esperadas = []
    for id_, _ in cen.CENARIOS[cenario]["classes"]:
        esperadas += [
            BASE + urls.saldo_aplicacoes_cotista(id_, data, tipo_arquivo="Excel"),
            BASE + urls.saldo_aplicacoes_cotista(id_, data, tipo_arquivo="PDF"),
        ]
    assert urls_de_referencia(cenario) == esperadas


@pytest.mark.parametrize("cenario", ["historico_uma_classe", "historico_duas_classes", "historico_vazio"])
def test_historico_cota_igual_ao_original(cenario, tmp_path):
    def transformar(id_, nome):
        _, registros = cen.entrada(cenario, id_)
        return transformar_historico_cota(registros, id_carteira=id_, nome_classe=nome)

    por_classe = _dfs_por_classe(cenario, transformar)
    assert_igual(como_excel(empilhar(por_classe, "Histórico de Cota"), tmp_path), ler(referencia_empilhada(cenario, "Histórico de Cota")))
    _comparar_separados(cenario, "Histórico de Cota", por_classe, tmp_path)
    # o original manda DataFim como str(datetime): 'AAAA-MM-DD 00:00:00'
    fim_datetime = f"{cen.DATA_FINAL} 00:00:00"
    esperadas = [BASE + urls.historico_cota(id_, cen.FIM_ANTERIOR, fim_datetime) for id_, _ in cen.CENARIOS[cenario]["classes"]]
    assert urls_de_referencia(cenario) == esperadas


def _comparar_separados(cenario: str, sufixo: str, por_classe: list[pd.DataFrame], tmp_path: Path) -> None:
    """Com várias classes, o original guarda cada uma em 'Arquivos separados'; as nossas têm que ser iguais."""
    classes = cen.CENARIOS[cenario]["classes"]
    if len(classes) < 2:
        return
    for (id_, _), df in zip(classes, por_classe):
        golden = DOURADOS / cenario / "saida" / "Arquivos separados" / f"{AAAAMM}_{id_}_{CNPJ}_{sufixo}.xlsx"
        assert_igual(como_excel(df, tmp_path, f"sep_{id_}.xlsx"), ler(golden))


# --- comportamentos que o porte muda de propósito (o original quebraria) -------------------------------------------------


def test_planilha_de_posicao_vazia_devolve_sem_dados_em_vez_de_quebrar():
    """No original, uma planilha totalmente vazia derruba o processo (IndexError). No porte vira a linha 'Sem dados aplicação'."""
    vazio = pd.DataFrame()
    resultado = transformar_posicao_cotista(vazio, id_carteira="111", nome_classe="X")
    assert list(resultado["Data Posicao"]) == ["Sem dados aplicação"]


def test_estrutura_inesperada_vira_erro_tipado():
    from contabilidade_mensal.integrations.britech.erros import EstruturaInesperada

    with pytest.raises(EstruturaInesperada):
        transformar_composicao_carteira(pd.DataFrame({"COLUNA": [1]}), id_carteira="111", data_ref="2026-08-31")
    with pytest.raises(EstruturaInesperada):
        transformar_extrato(pd.DataFrame({"a": [1]}), id_carteira="111")
