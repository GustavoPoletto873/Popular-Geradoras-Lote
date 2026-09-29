"""Diretório temporário por execução: `<root>/<AAAAMM>/<execucao>/<fundo>/Insumos`."""

from __future__ import annotations

from pathlib import Path


def pasta_insumos(raiz: Path, aaaamm: str, execucao_id: int, fundo_id: int) -> Path:
    pasta = Path(raiz) / aaaamm / str(execucao_id) / str(fundo_id) / "Insumos"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def pasta_saida(raiz: Path, aaaamm: str, execucao_id: int, fundo_id: int) -> Path:
    pasta = Path(raiz) / aaaamm / str(execucao_id) / str(fundo_id) / "Saida"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta
