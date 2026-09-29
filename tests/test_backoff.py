from contabilidade_mensal.pipeline.backoff import calcular_backoff


def test_cresce_exponencialmente_ate_o_teto():
    esperas = [calcular_backoff(n, base_s=30, teto_s=900) for n in range(1, 8)]
    assert esperas == [30, 60, 120, 240, 480, 900, 900]


def test_jitter_fica_dentro_da_faixa():
    minimo = calcular_backoff(3, base_s=30, teto_s=900, jitter=0.2, aleatorio=lambda: 0.0)
    maximo = calcular_backoff(3, base_s=30, teto_s=900, jitter=0.2, aleatorio=lambda: 1.0)
    assert minimo == 120 * 0.8
    assert maximo == 120 * 1.2


def test_jitter_nunca_passa_do_teto():
    assert calcular_backoff(10, base_s=30, teto_s=900, jitter=0.5, aleatorio=lambda: 1.0) == 900


def test_sem_jitter_e_deterministico():
    assert calcular_backoff(2, base_s=10, teto_s=1000) == calcular_backoff(2, base_s=10, teto_s=1000)
