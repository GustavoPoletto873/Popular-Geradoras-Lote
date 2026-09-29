from contabilidade_mensal.core.choices import Etapa
from contabilidade_mensal.pipeline import definicao as d


def test_ordem_e_topologica_e_cobre_todas_as_etapas():
    assert set(d.ORDEM) == set(Etapa.values) == set(d.DEPENDENCIAS)
    posicao = {etapa: i for i, etapa in enumerate(d.ORDEM)}
    for etapa, dependencias in d.DEPENDENCIAS.items():
        assert all(posicao[dep] < posicao[etapa] for dep in dependencias), etapa


def test_a_jusante():
    assert d.a_jusante({Etapa.PROCESSAR_CONTABIL}) == {
        Etapa.BAIXAR_BALANCETE,
        Etapa.POPULAR_EXCEL,
        Etapa.PUBLICAR_DRIVE,
    }
    assert d.a_jusante({Etapa.BAIXAR_INSUMOS}) == {Etapa.POPULAR_EXCEL, Etapa.PUBLICAR_DRIVE}
    assert d.a_jusante({Etapa.PUBLICAR_DRIVE}) == set()
    # não inclui as próprias etapas pedidas
    assert Etapa.BAIXAR_BALANCETE not in d.a_jusante({Etapa.PROCESSAR_CONTABIL, Etapa.BAIXAR_BALANCETE})


def test_plano_com_backends_fake_segue_a_fila_logica():
    assert d.planejar_etapa(Etapa.BAIXAR_INSUMOS, 7) == d.PlanoEtapa("fake", "api", "")
    assert d.planejar_etapa(Etapa.PROCESSAR_CONTABIL, 7) == d.PlanoEtapa("fake", "browser", "britech:7")
    assert d.planejar_etapa(Etapa.BAIXAR_BALANCETE, 7) == d.PlanoEtapa("fake", "browser", "britech:7")
    assert d.planejar_etapa(Etapa.POPULAR_EXCEL, 7) == d.PlanoEtapa("excel", "excel", "")
    assert d.planejar_etapa(Etapa.PUBLICAR_DRIVE, 7) == d.PlanoEtapa("drive", "drive", "")


def test_plano_muda_com_a_configuracao_sem_mexer_no_codigo(settings):
    settings.BRITECH_BACKENDS = {
        "baixar_insumo": "browser",
        "processar_contabil": "browser",
        "status_processamento": "browser",
        "baixar_balancete": "api",  # ex.: a Britech passou a oferecer endpoint de balancete
    }
    assert d.planejar_etapa(Etapa.BAIXAR_INSUMOS, 3) == d.PlanoEtapa("browser", "browser", "britech:3")
    assert d.planejar_etapa(Etapa.BAIXAR_BALANCETE, 3) == d.PlanoEtapa("api", "api", "")


def test_chave_do_disjuntor():
    assert d.chave_disjuntor("baixar_balancete", "browser", 3) == "baixar_balancete:browser:3"
