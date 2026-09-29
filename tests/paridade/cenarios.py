"""Cenários de paridade: parâmetros e respostas simuladas da API, compartilhados entre o oráculo e os testes."""

from __future__ import annotations

from . import entradas

# Fundo fictício e datas coerentes com core/calendario.py (exercício em novembro, competência 2026-08)
FUNDO = {
    "cnpj": "12345678000190",
    "fundo": "FUNDO X",
    "tipo": "FII",
    "exercicio_mes": 11,
    "exercicio_nome": "Novembro",
    "ano_exercicio_proximo": "2026",
}
COMPETENCIA = (2026, 8)
DATA_FINAL = "2026-08-31"  # último dia útil de ago/2026
FIM_ANTERIOR = "2025-11-28"  # último dia útil de nov/2025 (MES_EXERCICIO)
INICIO_EXERCICIO = "2025-12-01"  # dia útil seguinte

CLASSE_1 = ("111", "FUNDO X - CLASSE SENIOR")
CLASSE_2 = ("222", "FUNDO X - CLASSE SUBORDINADA")

# kind: carteira | extrato | mov | posicao | historico
CENARIOS: dict[str, dict] = {
    "carteira_final": dict(kind="carteira", inicial=False, variante="completa"),
    "carteira_inicial": dict(kind="carteira", inicial=True, variante="completa"),
    "carteira_sem_rentabilidade": dict(kind="carteira", inicial=False, variante="sem_rentabilidade"),
    "extrato_padrao": dict(kind="extrato", variante="padrao"),
    "extrato_colunas_deslocadas": dict(kind="extrato", variante="colunas_deslocadas"),
    "extrato_sem_movimentacao": dict(kind="extrato", variante="sem_movimentacao"),
    "mov_uma_classe": dict(kind="mov", classes=[CLASSE_1], variantes=["com_operacoes"]),
    "mov_duas_classes": dict(kind="mov", classes=[CLASSE_1, CLASSE_2], variantes=["com_operacoes", "com_operacoes"]),
    "mov_sem_operacoes": dict(kind="mov", classes=[CLASSE_1], variantes=["vazio"]),
    "mov_fora_do_periodo": dict(kind="mov", classes=[CLASSE_1], variantes=["fora_do_periodo"]),
    "posicao_final_data_col4": dict(kind="posicao", inicial=False, classes=[CLASSE_1], variantes=["data_na_coluna_4"]),
    "posicao_final_data_col5": dict(kind="posicao", inicial=False, classes=[CLASSE_1], variantes=["data_na_coluna_5"]),
    "posicao_sem_aplicacoes": dict(kind="posicao", inicial=False, classes=[CLASSE_1], variantes=["sem_linha_de_aplicacoes"]),
    "posicao_inicial_duas_classes": dict(
        kind="posicao", inicial=True, classes=[CLASSE_1, CLASSE_2], variantes=["data_na_coluna_4", "data_na_coluna_5"]
    ),
    "historico_uma_classe": dict(kind="historico", classes=[CLASSE_1], variantes=["completo"]),
    "historico_duas_classes": dict(kind="historico", classes=[CLASSE_1, CLASSE_2], variantes=["completo", "completo"]),
    "historico_vazio": dict(kind="historico", classes=[CLASSE_1], variantes=["vazio"]),
}


def entrada(cenario: str, id_classe: str = "111"):
    """Resposta simulada da API para o endpoint principal do cenário: ('bytes', xlsx) ou ('json', lista)."""
    c = CENARIOS[cenario]
    kind = c["kind"]
    if kind == "carteira":
        return "bytes", entradas.carteira_bruta(c["variante"])
    if kind == "extrato":
        return "bytes", entradas.extrato_bruto(c["variante"])
    posicao = [i for i, (cid, _) in enumerate(c["classes"]) if cid == id_classe][0]
    nome = c["classes"][posicao][1]
    variante = c["variantes"][posicao]
    if kind == "mov":
        return "json", entradas.mov_json(variante, nome_fundo=nome, deslocamento=posicao * 10)
    if kind == "posicao":
        return "bytes", entradas.posicao_bruta(variante)
    return "json", entradas.historico_json(variante)
