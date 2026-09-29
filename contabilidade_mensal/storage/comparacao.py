"""Comparação célula a célula de duas pastas de `Insumos` (ex.: gerada pelo pipeline × gerada pelo Simplifica).

Pareia arquivos pela chave (competência, CNPJ, tipo) e IGNORA o id da carteira que o Simplifica deixa no nome
quando o fundo tem uma só classe (`202608_111_<cnpj>_MovCotista.xlsx` ≡ `202608_<cnpj>_MovCotista.xlsx`).
Dentro de "Arquivos separados" o id faz parte da chave.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

_NOME = re.compile(r"^(?P<aaaamm>\d{6})_(?:(?P<id>\d+)_)?(?P<cnpj>\d{14})_(?P<sufixo>.+)\.xlsx$")

Chave = tuple[str, str, str, str, str]  # (subpasta, aaaamm, cnpj, sufixo, id se estiver em subpasta)


@dataclass(frozen=True)
class Diferenca:
    linha: int
    coluna: str
    a: object
    b: object


@dataclass
class RelatorioComparacao:
    iguais: list[str] = field(default_factory=list)
    diferentes: dict[str, list[Diferenca] | str] = field(default_factory=dict)  # str = estrutura diferente
    so_em_a: list[str] = field(default_factory=list)
    so_em_b: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.diferentes or self.so_em_a or self.so_em_b)


def _indexar(pasta: Path) -> dict[Chave, Path]:
    indice: dict[Chave, Path] = {}
    for arquivo in sorted(Path(pasta).rglob("*.xlsx")):
        m = _NOME.match(arquivo.name)
        if not m:
            continue
        subpasta = str(arquivo.parent.relative_to(pasta)).replace("\\", "/")
        subpasta = "" if subpasta == "." else subpasta
        id_ = (m["id"] or "") if subpasta else ""
        indice[(subpasta, m["aaaamm"], m["cnpj"], m["sufixo"], id_)] = arquivo
    return indice


def comparar_planilhas(a: Path, b: Path, *, limite: int = 20) -> list[Diferenca] | str:
    """Lista de diferenças (vazia = iguais) ou uma string descrevendo diferença de estrutura."""
    df_a, df_b = pd.read_excel(a), pd.read_excel(b)
    if list(df_a.columns) != list(df_b.columns):
        return f"colunas diferentes: {list(df_a.columns)} × {list(df_b.columns)}"
    if len(df_a) != len(df_b):
        return f"quantidade de linhas diferente: {len(df_a)} × {len(df_b)}"
    diferentes = ~((df_a == df_b) | (df_a.isna() & df_b.isna()))
    achadas: list[Diferenca] = []
    for linha, coluna in zip(*diferentes.to_numpy().nonzero()):
        achadas.append(Diferenca(int(linha) + 2, str(df_a.columns[coluna]), df_a.iat[linha, coluna], df_b.iat[linha, coluna]))
        if len(achadas) >= limite:
            break
    return achadas


def comparar_pastas(a: Path, b: Path, *, limite: int = 20) -> RelatorioComparacao:
    a, b = Path(a), Path(b)
    ia, ib = _indexar(a), _indexar(b)
    relatorio = RelatorioComparacao()
    for chave in sorted(set(ia) | set(ib)):
        rotulo = "/".join(x for x in (chave[0], f"{chave[1]}_{chave[2]}_{chave[3]}") if x)
        if chave not in ib:
            relatorio.so_em_a.append(rotulo)
        elif chave not in ia:
            relatorio.so_em_b.append(rotulo)
        else:
            resultado = comparar_planilhas(ia[chave], ib[chave], limite=limite)
            if resultado:
                relatorio.diferentes[rotulo] = resultado
            else:
                relatorio.iguais.append(rotulo)
    return relatorio
