"""Regra do exercício, verificada contra pastas REAIS do Shared Drive (ver dominio.py)."""

import pytest

from contabilidade_mensal.core import dominio


@pytest.mark.parametrize(
    "exercicio_mes, ano, mes, esperado",
    [
        # FIDC ACELERA CASH — pasta "Data Base Novembro 2026" contém 202512 … 202608
        (11, 2026, 8, "Data Base Novembro 2026"),
        (11, 2025, 12, "Data Base Novembro 2026"),
        (11, 2025, 11, "Data Base Novembro 2025"),
        # FII LAZIO II — "Data Base Junho 2026" contém 202507 … 202512
        (6, 2025, 9, "Data Base Junho 2026"),
        (6, 2025, 12, "Data Base Junho 2026"),
        (6, 2025, 6, "Data Base Junho 2025"),
        # FII KRONOS — exercício em dezembro
        (12, 2025, 12, "Data Base Dezembro 2025"),
        (12, 2026, 1, "Data Base Dezembro 2026"),
        # ALPHA FIDC — "Data Base Março 2024" contém 202304 … 202403
        (3, 2023, 4, "Data Base Março 2024"),
        (3, 2024, 3, "Data Base Março 2024"),
        (3, 2025, 4, "Data Base Março 2026"),
    ],
)
def test_nome_pasta_exercicio_bate_com_pastas_reais(exercicio_mes, ano, mes, esperado):
    assert dominio.nome_pasta_exercicio(exercicio_mes, ano, mes) == esperado


def test_nome_pasta_competencia():
    assert dominio.nome_pasta_competencia(2026, 8) == "202608"
    assert dominio.nome_pasta_competencia(2026, 12) == "202612"


def test_caminho_relativo_competencia():
    assert dominio.caminho_relativo_competencia("FIDC", "FIDC ACELERA CASH", 11, 2026, 8) == (
        "FIDC",
        "FIDC ACELERA CASH",
        "Data Base Novembro 2026",
        "202608",
    )


@pytest.mark.parametrize("invalido", [0, 13, -1])
def test_exercicio_mes_invalido(invalido):
    with pytest.raises(ValueError):
        dominio.ano_do_exercicio(invalido, 2026, 1)
