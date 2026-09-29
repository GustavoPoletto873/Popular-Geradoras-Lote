import datetime as dt

import pytest

from contabilidade_mensal.core import calendario as cal
from contabilidade_mensal.core.dominio import nome_pasta_exercicio

D = dt.date


def test_pascoa_de_varios_anos():
    assert cal.pascoa(2025) == D(2025, 4, 20)
    assert cal.pascoa(2026) == D(2026, 4, 5)
    assert cal.pascoa(2027) == D(2027, 3, 28)


def test_feriados_moveis_alem_dos_nacionais():
    f = cal.feriados(2026)
    assert D(2026, 2, 16) in f and D(2026, 2, 17) in f  # Carnaval
    assert D(2026, 4, 3) in f  # Sexta-feira Santa
    assert D(2026, 6, 4) in f  # Corpus Christi
    assert D(2026, 9, 7) in f and D(2026, 12, 25) in f  # nacionais fixos


@pytest.mark.parametrize(
    "ano, mes, esperado",
    [
        (2025, 9, D(2025, 9, 30)),  # terça
        (2025, 11, D(2025, 11, 28)),  # dia 30 é domingo
        (2025, 12, D(2025, 12, 31)),
        (2026, 1, D(2026, 1, 30)),  # dia 31 é sábado
        (2026, 2, D(2026, 2, 27)),  # dia 28 é sábado
        (2026, 5, D(2026, 5, 29)),  # dia 31 é domingo
        (2026, 8, D(2026, 8, 31)),  # segunda
    ],
)
def test_ultimo_dia_util(ano, mes, esperado):
    assert cal.ultimo_dia_util(ano, mes) == esperado
    assert cal.data_final_carteira(ano, mes) == esperado


def test_proximo_dia_util_pula_fim_de_semana_e_feriados_moveis():
    assert cal.proximo_dia_util(D(2025, 11, 28)) == D(2025, 12, 1)  # sexta -> segunda
    assert cal.proximo_dia_util(D(2026, 2, 13)) == D(2026, 2, 18)  # sexta antes do Carnaval -> quarta
    assert cal.proximo_dia_util(D(2026, 6, 3)) == D(2026, 6, 5)  # pula Corpus Christi (quinta)


@pytest.mark.parametrize(
    "exercicio_mes, referencia, esperado",
    [
        (11, D(2026, 8, 31), D(2025, 11, 28)),  # exercício ainda em curso -> fim do anterior
        (11, D(2025, 12, 31), D(2025, 11, 28)),  # já passou o mês de encerramento neste ano
        (11, D(2025, 11, 28), D(2024, 11, 29)),  # referência dentro do próprio mês de encerramento
        (6, D(2025, 9, 30), D(2025, 6, 30)),
        (12, D(2025, 12, 31), D(2024, 12, 31)),
        (12, D(2026, 1, 30), D(2025, 12, 31)),
    ],
)
def test_fim_exercicio_anterior(exercicio_mes, referencia, esperado):
    assert cal.fim_exercicio_anterior(exercicio_mes, referencia) == esperado


@pytest.mark.parametrize("exercicio_mes, ano, mes", [(11, 2026, 8), (11, 2025, 12), (6, 2025, 9), (12, 2025, 12), (3, 2024, 3)])
def test_ano_exercicio_proximo_e_coerente_com_a_pasta_data_base(exercicio_mes, ano, mes):
    """A regra do Simplifica (ano do fim do exercício anterior + 1) tem que dar o mesmo ano do nome da pasta."""
    referencia = cal.data_final_carteira(ano, mes)
    fim = cal.fim_exercicio_anterior(exercicio_mes, referencia)
    assert nome_pasta_exercicio(exercicio_mes, ano, mes).endswith(str(cal.ano_exercicio_proximo(fim)))


def test_inicio_do_exercicio_respeita_a_implantacao():
    fim = D(2025, 11, 28)
    assert cal.inicio_exercicio(fim, None) == D(2025, 12, 1)
    assert cal.inicio_exercicio(fim, D(2025, 3, 1)) == D(2025, 12, 1)  # fundo antigo: começa no exercício
    assert cal.inicio_exercicio(fim, D(2026, 2, 10)) == D(2026, 2, 10)  # fundo implantado depois


def test_mes_por_nome():
    assert cal.mes_por_nome("Novembro") == 11
    assert cal.mes_por_nome(" março ") == 3
    assert cal.mes_por_nome("") is None and cal.mes_por_nome(None) is None and cal.mes_por_nome("xyz") is None


def test_mes_de_exercicio_invalido():
    with pytest.raises(ValueError):
        cal.fim_exercicio_anterior(13, D(2026, 8, 31))
