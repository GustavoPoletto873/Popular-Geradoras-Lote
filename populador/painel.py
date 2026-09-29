"""
Leitura/escrita da aba "Painel" — via COM, na MESMA planilha .xlsm que tem o
VBA (não uma cópia), para manter a mesma UX: status na coluna C, "X" limpo
na coluna D, exatamente como ProcessarEmLoop faz hoje.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from . import config
from .excel_app import XL_CENTER


@dataclass
class FundoRow:
    linha: int
    fundo: str
    tipo: str
    exercicio: str
    marcado: bool


@dataclass
class ParametrosGlobais:
    pasta_raiz: str
    periodo_destino: str
    periodo_origem: str


def ler_parametros_globais(ws) -> ParametrosGlobais:
    return ParametrosGlobais(
        pasta_raiz=str(ws.Range(config.CELL_PASTA_RAIZ).Value or "").strip(),
        periodo_destino=str(ws.Range(config.CELL_PERIODO_DESTINO).Value or "").strip(),
        periodo_origem=str(ws.Range(config.CELL_PERIODO_ORIGEM).Value or "").strip(),
    )


def iterar_fundos(ws) -> Iterator[FundoRow]:
    """Réplica de `Do While Not IsEmpty(Range("B" & linha).Value) ... linha = linha + 1 Loop`."""
    linha = config.FIRST_ROW
    while True:
        fundo = ws.Range(f"{config.COL_FUNDO}{linha}").Value
        if fundo is None or str(fundo).strip() == "":
            break
        marca = ws.Range(f"{config.COL_PROCESSA}{linha}").Value
        marcado = bool(marca) and str(marca).strip().upper() == config.MARCADOR_PROCESSAR
        tipo = ws.Range(f"{config.COL_TIPO}{linha}").Value
        exercicio = ws.Range(f"{config.COL_EXERCICIO}{linha}").Value
        yield FundoRow(
            linha=linha,
            fundo=str(fundo).strip(),
            tipo=str(tipo).strip() if tipo is not None else "",
            exercicio=str(exercicio).strip() if exercicio is not None else "",
            marcado=marcado,
        )
        linha += 1


def escrever_status(ws, linha: int, status: str, limpar_marcador: bool = True) -> None:
    celula_status = ws.Range(f"{config.COL_STATUS}{linha}")
    celula_status.Value = status
    celula_status.HorizontalAlignment = XL_CENTER
    if limpar_marcador:
        ws.Range(f"{config.COL_PROCESSA}{linha}").ClearContents()
