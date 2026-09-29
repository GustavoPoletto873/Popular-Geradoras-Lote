import datetime as dt

from populador import matching


def test_canonicalizar_ignora_acento_caixa_e_pontuacao():
    assert matching.canonicalizar("Balancete Contábil.xls") == "balancetecontabilxls"
    assert matching.canonicalizar("BALANCETE_CONTABIL.XLS") == "balancetecontabilxls"


def test_exato_tem_prioridade_sobre_fallback(tmp_path):
    """Caso real do fundo FII LAZIO II: o padrão exato do VBA já bate, então
    o fallback nem deveria ser consultado."""
    (tmp_path / "202509_x_Carteira.xlsx").touch()
    (tmp_path / "Carteira_999_31-12-2025.xlsx").touch()  # ruído extra
    resultado = matching.resolver_insumo(tmp_path, "carteira_final")
    assert resultado.origem == "exato"
    assert resultado.arquivos == [tmp_path / "202509_x_Carteira.xlsx"]


def test_fallback_resolve_nome_estilo_fii_kronos(tmp_path):
    (tmp_path / "Carteira_558338_31-12-2025.xlsx").touch()
    resultado = matching.resolver_insumo(tmp_path, "carteira_final")
    assert resultado.origem == "fallback"
    assert resultado.arquivos == [tmp_path / "Carteira_558338_31-12-2025.xlsx"]


def test_fallback_nao_confunde_final_com_inicial(tmp_path):
    # nome que não bate o padrão exato "CarteiraInicial.xlsx" (tem sufixo de
    # data depois de "Inicial"), mas contém os tokens "carteira" + "inicial".
    nome = "202512_44177_CarteiraInicial_2025.xlsx"
    (tmp_path / nome).touch()
    resultado = matching.resolver_insumo(tmp_path, "carteira_final")
    assert resultado.origem == "nao_encontrado"

    resultado_inicial = matching.resolver_insumo(tmp_path, "carteira_inicial")
    assert resultado_inicial.origem == "fallback"
    assert resultado_inicial.arquivos == [tmp_path / nome]


def test_fallback_ambiguo_estilo_fii_octo(tmp_path):
    """Caso real do FII OCTO: duas Carteiras datadas, nenhuma com 'Inicial'
    no nome -- não dá pra saber qual é a final sem um critério de negócio
    que ainda não foi confirmado, então fica ambíguo."""
    (tmp_path / "Carteira_44177538_31-12-2024.xlsx").touch()
    (tmp_path / "Carteira_44177538_31-12-2025.xlsx").touch()
    resultado = matching.resolver_insumo(tmp_path, "carteira_final")
    assert resultado.origem == "ambiguo"
    assert resultado.arquivos == []
    assert len(resultado.candidatos_ambiguos) == 2


def test_balancete_final_ignora_variante_inicial(tmp_path):
    (tmp_path / "BalanceteContabilInicial.xls").touch()
    resultado = matching.resolver_insumo(tmp_path, "balancete_final")
    assert resultado.origem == "nao_encontrado"


def test_balancete_final_fallback_estilo_fidc(tmp_path):
    (tmp_path / "BalanceteContabil_566391_34691300000186_.xls").touch()
    resultado = matching.resolver_insumo(tmp_path, "balancete_final")
    assert resultado.origem == "fallback"


def test_mov_cotista_fallback_report_movimentacao(tmp_path):
    """Caso real do FIDC ALPHA (2022/2023): arquivo chamado
    'ReportMovimentacaoCotista.xls', bem diferente do padrão 'MovCotista.xls'."""
    (tmp_path / "ReportMovimentacaoCotista.xls").touch()
    resultado = matching.resolver_insumo(tmp_path, "mov_cotista")
    assert resultado.origem == "fallback"


def test_nao_encontrado_pasta_vazia(tmp_path):
    resultado = matching.resolver_insumo(tmp_path, "posicao_cotista")
    assert resultado.origem == "nao_encontrado"
    assert resultado.arquivos == []


def test_extrair_data_provavel_formatos_reais():
    assert matching.extrair_data_provavel("Carteira_44177538_31-12-2025.xlsx") == dt.date(2025, 12, 31)
    assert matching.extrair_data_provavel("Carteira_566391_31-1-2023.xlsx") == dt.date(2023, 1, 31)
    assert matching.extrair_data_provavel("SaldoAplicacaoCotista558338_31-12-2025.xlsx") == dt.date(2025, 12, 31)


def test_extrair_data_provavel_sem_data_retorna_none():
    assert matching.extrair_data_provavel("CarteiraFinal.xlsx") is None
    assert matching.extrair_data_provavel("Balancete 30.09.xls") is None  # sem ano, não é confiável
