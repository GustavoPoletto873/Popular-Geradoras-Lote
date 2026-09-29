"""
Resolução de insumo em duas camadas.

Camada 1 (fiel ao VBA): substring exata, sensível a maiúsculas/minúsculas,
igual ao `InStr` original (ver paths.encontrar_insumos / config.INSUMO_PATTERNS).

Camada 2 (fallback, só entra se a camada 1 não achar nada): reconhecimento
por palavra-chave, ignorando acento/caixa/pontuação, baseado em convenções de
nome REALMENTE observadas em fundos de produção (ver config.INSUMO_FALLBACK e
o comentário lá explicando a evidência de cada padrão). Não inventa nomes:
só reconhece o que já foi visto em disco.

Quando o fallback encontra mais de um candidato plausível para o mesmo tipo
de insumo (ex.: dois arquivos de "Carteira" com datas diferentes e nenhuma
palavra "Inicial"/"Final" no nome, caso real do fundo "FII OCTO"), o
resultado é "ambíguo" — o código NÃO escolhe sozinho qual é o certo, porque
errar isso numa conciliação contábil é pior do que deixar em branco com
aviso.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from . import config, paths
from .config import RegraFallback

# Padrões de data observados em nomes reais de insumo (dd-mm-aaaa / dd.mm.aaaa
# com separador "-" ou ".", e aaaammdd contíguo). Só para EXIBIÇÃO ao humano
# que resolve uma ambiguidade — nunca usado para decidir sozinho qual arquivo
# é o certo (ver docstring do módulo).
_PADROES_DATA = (
    (re.compile(r"(\d{1,2})[-.](\d{1,2})[-.](\d{4})"), lambda m: (int(m[3]), int(m[2]), int(m[1]))),
    (re.compile(r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})"), lambda m: (int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)"), lambda m: (int(m[1]), int(m[2]), int(m[3]))),
)


def extrair_data_provavel(nome: str) -> dt.date | None:
    """Melhor palpite de data embutida no nome do arquivo, best-effort.

    Usado só para ajudar um humano a decidir entre candidatos ambíguos
    (ex.: "qual desses dois é o mais recente?") — nunca para automatizar a
    escolha."""
    for padrao, montar in _PADROES_DATA:
        m = padrao.search(nome)
        if m:
            try:
                ano, mes, dia = montar(m)
                return dt.date(ano, mes, dia)
            except ValueError:
                continue
    return None


def canonicalizar(nome: str) -> str:
    """minúsculo, sem acento, só alfanumérico — pra comparar nomes de
    arquivo que variam em acentuação/espaçamento/pontuação."""
    sem_acento = unicodedata.normalize("NFKD", nome)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return "".join(ch.lower() for ch in sem_acento if ch.isalnum())


def _encontrar_por_regra(pasta: Path, regra: RegraFallback) -> list[Path]:
    if not pasta.exists():
        return []
    achados = []
    for item in pasta.iterdir():
        if not item.is_file() or item.suffix.lower() not in regra.extensoes:
            continue
        canon = canonicalizar(item.name)
        if all(tok in canon for tok in regra.obrigatorias) and not any(
            tok in canon for tok in regra.proibidas
        ):
            achados.append(item)
    return sorted(achados)


def encontrar_candidatos_fallback(pasta: Path, step: str) -> list[Path]:
    vistos: set[Path] = set()
    unicos: list[Path] = []
    for regra in config.INSUMO_FALLBACK.get(step, ()):
        for item in _encontrar_por_regra(pasta, regra):
            if item not in vistos:
                vistos.add(item)
                unicos.append(item)
    return unicos


@dataclass
class ResultadoMatch:
    arquivos: list[Path]
    origem: str  # "exato" | "fallback" | "nao_encontrado" | "ambiguo"
    candidatos_ambiguos: list[Path] = field(default_factory=list)


def resolver_insumo(pasta_insumos: Path, step: str) -> ResultadoMatch:
    """Resolve o(s) arquivo(s) de insumo pro `step` dado.

    Camada exata: pode retornar MAIS DE UM arquivo (fiel ao VBA original —
    Popula_Posicao_Cotista/PopulaMovimentacaoV2 acumulam todos os matches).
    Camada fallback: só resolve sozinho quando há exatamente UM candidato
    plausível; mais de um vira "ambiguo" e não é escolhido automaticamente.
    """
    padrao = config.INSUMO_PATTERNS[step]
    exatos = paths.encontrar_insumos(pasta_insumos, padrao)
    if exatos:
        return ResultadoMatch(arquivos=exatos, origem="exato")

    candidatos = encontrar_candidatos_fallback(pasta_insumos, step)
    if len(candidatos) == 1:
        return ResultadoMatch(arquivos=candidatos, origem="fallback")
    if len(candidatos) > 1:
        return ResultadoMatch(arquivos=[], origem="ambiguo", candidatos_ambiguos=candidatos)
    return ResultadoMatch(arquivos=[], origem="nao_encontrado")
