from pathlib import Path

from populador import paths


def test_montar_caminhos():
    c = paths.montar_caminhos(
        pasta_raiz=r"G:\Raiz",
        tipo="FII",
        fundo="FII LAZIO II",
        exercicio="Junho 2026",
        periodo_origem="202508",
        periodo_destino="202509",
    )
    assert c.pasta_origem == Path(r"G:\Raiz\FII\FII LAZIO II\Data Base Junho 2026\202508")
    assert c.pasta_saida == Path(r"G:\Raiz\FII\FII LAZIO II\Data Base Junho 2026\202509")
    assert c.pasta_insumos == Path(r"G:\Raiz\FII\FII LAZIO II\Data Base Junho 2026\202509\Insumos")


def test_montar_caminhos_com_pasta_saida_redirecionada():
    c = paths.montar_caminhos(
        pasta_raiz=r"G:\Raiz",
        tipo="FII",
        fundo="FII LAZIO II",
        exercicio="Junho 2026",
        periodo_origem="202508",
        periodo_destino="202509",
        pasta_raiz_saida=r"C:\saida_segura",
    )
    # origem e insumos continuam sempre na pasta real (só leitura)
    assert c.pasta_origem == Path(r"G:\Raiz\FII\FII LAZIO II\Data Base Junho 2026\202508")
    assert c.pasta_insumos == Path(r"G:\Raiz\FII\FII LAZIO II\Data Base Junho 2026\202509\Insumos")
    # só a saída vai pra pasta redirecionada
    assert c.pasta_saida == Path(r"C:\saida_segura\FII\FII LAZIO II\Data Base Junho 2026\202509")


def test_saida_ja_existe_pasta_ausente(tmp_path):
    assert paths.saida_ja_existe(tmp_path / "nao existe") is False


def test_saida_ja_existe_com_xlsb(tmp_path):
    (tmp_path / "Fundo X 202509.xlsb").touch()
    assert paths.saida_ja_existe(tmp_path) is True


def test_saida_ja_existe_pasta_vazia(tmp_path):
    assert paths.saida_ja_existe(tmp_path) is False


def test_saida_ja_existe_ignora_arquivos_nao_relacionados(tmp_path):
    (tmp_path / "notas.txt").touch()
    assert paths.saida_ja_existe(tmp_path) is False


def test_encontrar_arquivo_origem_pasta_ausente(tmp_path):
    assert paths.encontrar_arquivo_origem(tmp_path / "nao existe") is None


def test_encontrar_arquivo_origem_escolhe_qualquer_xls(tmp_path):
    (tmp_path / "leiame.txt").touch()
    (tmp_path / "Fundo X 202508.xlsb").touch()
    achado = paths.encontrar_arquivo_origem(tmp_path)
    assert achado == tmp_path / "Fundo X 202508.xlsb"


def test_encontrar_arquivo_origem_deterministico_com_varios_candidatos(tmp_path):
    (tmp_path / "b.xlsx").touch()
    (tmp_path / "a.xlsb").touch()
    achado = paths.encontrar_arquivo_origem(tmp_path)
    assert achado == tmp_path / "a.xlsb"  # ordem alfabética, não a do SO


def test_encontrar_insumos_case_sensitive_como_o_vba(tmp_path):
    (tmp_path / "202509_x_Carteira.xlsx").touch()
    achados = paths.encontrar_insumos(tmp_path, "Carteira.xlsx")
    assert achados == [tmp_path / "202509_x_Carteira.xlsx"]


def test_encontrar_insumos_regressao_saldoaplicacaocotista_final_nao_bate():
    """
    Documenta o achado real: para o fundo FII testado, o arquivo de insumo
    real se chama "..._SaldoAplicacaoCotistaFinal.xlsx", que NÃO contém a
    substring exata "SaldoAplicacaoCotista.xlsx" usada pelo VBA original
    (há "Final" entre "Cotista" e ".xlsx"). Isso é replicado de propósito —
    ver config.py e populate.py sobre o aviso gerado quando isso acontece.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        tmp_path = Path(d)
        (tmp_path / "202509_x_SaldoAplicacaoCotistaFinal.xlsx").touch()
        achados = paths.encontrar_insumos(tmp_path, "SaldoAplicacaoCotista.xlsx")
        assert achados == []


def test_encontrar_insumos_nao_confunde_carteira_com_carteira_inicial(tmp_path):
    (tmp_path / "202509_x_CarteiraInicial.xlsx").touch()
    achados = paths.encontrar_insumos(tmp_path, "Carteira.xlsx")
    assert achados == []  # "CarteiraInicial.xlsx" não contém "Carteira.xlsx" como substring contígua


def test_nome_arquivo_destino():
    assert paths.nome_arquivo_destino("FII LAZIO II", "202509", "xlsb") == "FII LAZIO II 202509.xlsb"
    assert paths.nome_arquivo_destino("FII LAZIO II", "202509", ".xlsb") == "FII LAZIO II 202509.xlsb"
