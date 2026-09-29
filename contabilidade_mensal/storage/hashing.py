"""Hash e metadados de arquivo (SHA-256)."""

from __future__ import annotations

import hashlib
from pathlib import Path

_BLOCO = 1024 * 1024


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with Path(caminho).open("rb") as f:
        for bloco in iter(lambda: f.read(_BLOCO), b""):
            h.update(bloco)
    return h.hexdigest()


def descrever(caminho: Path) -> tuple[str, int]:
    """(sha256, tamanho em bytes)."""
    caminho = Path(caminho)
    return sha256_arquivo(caminho), caminho.stat().st_size
