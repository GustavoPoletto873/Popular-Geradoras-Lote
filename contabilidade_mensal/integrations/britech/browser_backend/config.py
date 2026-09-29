from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def url_pas(url_adm: str) -> str:
    return f"https://{url_adm}.britech.com.br/PAS"


@dataclass(frozen=True)
class ConfigNavegador:
    headless: bool = True
    timeout_ms: int = 30_000
    tentativas_logout: int = 3
    timeout_download_ms: int = 60_000
    pasta_evidencias: Path = field(default_factory=lambda: Path("var") / "evidencias")

    @classmethod
    def do_django(cls) -> "ConfigNavegador":
        from django.conf import settings

        cfg = settings.BROWSER
        return cls(
            headless=cfg["headless"],
            timeout_ms=cfg["timeout_ms"],
            pasta_evidencias=Path(cfg["pasta_evidencias"]),
        )
