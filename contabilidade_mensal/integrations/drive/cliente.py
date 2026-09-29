"""Cliente HTTP do serviço `drive_api` (Django/DRF existente da Denver): pastas e arquivos do Shared Drive.

Autenticação: DRF TokenAuthentication (`Authorization: Token <token>`). O token vem SÓ do ambiente
(`DRIVE_API_TOKEN`) e nunca aparece em mensagem de erro/log.

O `drive_api` NÃO devolve checksum dos arquivos (só id, nome, mime, tamanho, datas): a verificação pós-upload é feita
baixando o conteúdo de volta e comparando SHA-256 (ver `publicador.py`).

Contrato observado no código do serviço (somente leitura, sem alterá-lo):
    GET  pastas/buscar/?nome=&pasta_pai_id=      -> 200 pasta | 404
    POST pastas/  {nome, pasta_pai_id}           -> 201 pasta | 404 (pai inexistente)
    GET  arquivos/?pasta_id=&page_token=         -> 200 {arquivos:[...], next_page_token}
    POST arquivos/ multipart(arquivo, pasta_pai_id, nome)   -> 201 arquivo
    PUT  arquivos/<id>/conteudo/ multipart(arquivo)         -> 200 arquivo
    GET  arquivos/<id>/conteudo/                 -> 200 bytes
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import requests

from ..britech.erros import BritechErro

logger = logging.getLogger(__name__)

MIME_PASTA = "application/vnd.google-apps.folder"


class DriveErro(BritechErro):
    """Erros do Drive reaproveitam o contrato de erros do pipeline (`codigo`, `retentavel`, `conta_para_disjuntor`)."""

    codigo = "erro_drive"


class DriveIndisponivel(DriveErro):
    codigo = "drive_indisponivel"
    retentavel = True
    conta_para_disjuntor = True


class DriveAutenticacaoFalhou(DriveErro):
    codigo = "drive_autenticacao_falhou"
    conta_para_disjuntor = True


class PastaDriveNaoEncontrada(DriveErro):
    """Nome de tipo/fundo diferente do que existe no Drive (problema de cadastro): humano precisa ajustar."""

    codigo = "pasta_drive_nao_encontrada"


class DestinoJaExiste(DriveErro):
    """A pasta da competência já tem uma boleta diferente da nossa. Só sobrescreve com `forcar`."""

    codigo = "destino_ja_existe"


class DriveApiCliente:
    def __init__(
        self, base_url: str, token: str, *, sessao: requests.Session | None = None, timeout: tuple[float, float] = (10, 180)
    ) -> None:
        if not base_url or not token:
            raise DriveAutenticacaoFalhou("defina DRIVE_API_URL e DRIVE_API_TOKEN")
        self._base = base_url.rstrip("/") + "/"
        self._sessao = sessao or requests.Session()
        self._sessao.headers["Authorization"] = f"Token {token}"
        self._timeout = timeout

    def __repr__(self) -> str:
        return f"<DriveApiCliente {self._base}>"

    # --- núcleo -------------------------------------------------------------------------------------------------

    def _pedir(self, metodo: str, caminho: str, *, aceitar_404: bool = False, **kw: Any) -> requests.Response:
        try:
            r = self._sessao.request(metodo, self._base + caminho, timeout=self._timeout, **kw)
        except requests.Timeout as exc:
            raise DriveIndisponivel(f"timeout em {metodo} {caminho}") from exc
        except requests.RequestException as exc:
            raise DriveIndisponivel(f"falha de rede em {metodo} {caminho}: {type(exc).__name__}") from exc
        if r.status_code in (401, 403):
            raise DriveAutenticacaoFalhou(f"o drive_api recusou o token (HTTP {r.status_code})")
        if r.status_code == 404 and aceitar_404:
            return r
        if r.status_code == 429 or r.status_code >= 500:
            raise DriveIndisponivel(f"drive_api respondeu HTTP {r.status_code} em {metodo} {caminho}")
        if r.status_code >= 400:
            raise DriveErro(f"drive_api respondeu HTTP {r.status_code} em {metodo} {caminho}: {r.text[:200]}")
        return r

    # --- pastas -------------------------------------------------------------------------------------------------

    def buscar_pasta(self, nome: str, pai_id: str) -> dict | None:
        r = self._pedir("GET", "pastas/buscar/", aceitar_404=True, params={"nome": nome, "pasta_pai_id": pai_id})
        return None if r.status_code == 404 else r.json()

    def criar_pasta(self, nome: str, pai_id: str) -> dict:
        r = self._pedir("POST", "pastas/", aceitar_404=True, json={"nome": nome, "pasta_pai_id": pai_id})
        if r.status_code == 404:
            raise PastaDriveNaoEncontrada(f"pasta pai {pai_id} não existe")
        return r.json()

    # --- arquivos -----------------------------------------------------------------------------------------------

    def listar(self, pasta_id: str) -> list[dict]:
        itens: list[dict] = []
        token: str | None = None
        while True:
            params = {"pasta_id": pasta_id, **({"page_token": token} if token else {})}
            corpo = self._pedir("GET", "arquivos/", params=params).json()
            itens.extend(corpo.get("arquivos", []))
            token = corpo.get("next_page_token")
            if not token:
                return itens

    def enviar(self, pasta_id: str, caminho: Path, nome: str | None = None) -> dict:
        with Path(caminho).open("rb") as f:
            r = self._pedir(
                "POST",
                "arquivos/",
                aceitar_404=True,
                files={"arquivo": (nome or Path(caminho).name, f)},
                data={"pasta_pai_id": pasta_id, "nome": nome or Path(caminho).name},
            )
        if r.status_code == 404:
            raise PastaDriveNaoEncontrada(f"pasta {pasta_id} não existe")
        return r.json()

    def sobrescrever(self, arquivo_id: str, caminho: Path) -> dict:
        with Path(caminho).open("rb") as f:
            r = self._pedir("PUT", f"arquivos/{arquivo_id}/conteudo/", files={"arquivo": (Path(caminho).name, f)})
        return r.json()

    def baixar(self, arquivo_id: str) -> bytes:
        return self._pedir("GET", f"arquivos/{arquivo_id}/conteudo/").content
