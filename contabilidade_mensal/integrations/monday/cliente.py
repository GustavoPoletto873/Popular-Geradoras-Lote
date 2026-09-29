"""Cliente GraphQL do Monday.com — cadastro mestre de fundos.

Portado de `britech/monday_client.py` (Lucas) e das colunas usadas em `monday_ctb_britech2.py` (Simplifica).
O token vem de fora (variável `MONDAY_API_TOKEN`); NUNCA é escrito no código nem em log.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass

import requests

from contabilidade_mensal.core.calendario import mes_por_nome

logger = logging.getLogger(__name__)

API_URL = "https://api.monday.com/v2"
PAGINA = 500


class ErroMonday(Exception):
    """Falha ao consultar o Monday (HTTP, autenticação ou erro GraphQL)."""


@dataclass(frozen=True)
class ColunasMonday:
    """IDs das colunas do board (não são segredos; vêm de settings.MONDAY)."""

    cnpj: str = "texto"
    administrador: str = "status8__1"
    carteira: str = "texto3"
    exercicio: str = "exerc_cio_social__1"
    sistema: str = "dup__of_administrador_mkkz14qe"

    def todas(self) -> list[str]:
        return [self.cnpj, self.administrador, self.carteira, self.exercicio, self.sistema]


@dataclass(frozen=True)
class RegistroMonday:
    item_id: str
    fundo: str
    cnpj: str
    administrador: str
    carteira: str
    exercicio_mes: int | None
    tipo: str
    sistema: str


class ClienteMonday:
    def __init__(self, token: str, *, sessao: requests.Session | None = None, timeout: float = 60.0) -> None:
        if not token:
            raise ErroMonday("MONDAY_API_TOKEN não configurado")
        self._token = token
        self._sessao = sessao or requests.Session()
        self._timeout = timeout

    def _consultar(self, consulta: str) -> dict:
        try:
            resposta = self._sessao.post(
                API_URL, json={"query": consulta}, headers={"Authorization": self._token}, timeout=self._timeout
            )
        except requests.RequestException as exc:
            raise ErroMonday(f"falha de rede ao consultar o Monday ({type(exc).__name__})") from exc
        if resposta.status_code in (401, 403):
            raise ErroMonday(f"Monday recusou a credencial (HTTP {resposta.status_code})")
        if resposta.status_code >= 400:
            raise ErroMonday(f"Monday respondeu HTTP {resposta.status_code}")
        try:
            corpo = resposta.json()
        except ValueError as exc:
            raise ErroMonday("resposta do Monday não é JSON") from exc
        if corpo.get("errors") or corpo.get("error_message"):
            raise ErroMonday(f"erro GraphQL do Monday: {str(corpo.get('errors') or corpo.get('error_message'))[:200]}")
        return corpo

    def buscar_fundos(
        self, *, board_id: str, grupos: Mapping[str, str], colunas: ColunasMonday | None = None
    ) -> list[RegistroMonday]:
        """Todos os itens dos grupos. `grupos` = {id do grupo: tipo do fundo (FIF/FIDC/FII/FIP)}."""
        colunas = colunas or ColunasMonday()
        campos = f"id name column_values(ids: {json.dumps(colunas.todas())}) {{ id text }}"
        consulta = (
            f'{{ boards(ids: "{board_id}") {{ groups(ids: {json.dumps(list(grupos))}) {{ id '
            f"items_page(limit: {PAGINA}) {{ cursor items {{ {campos} }} }} }} }} }}"
        )
        registros: list[RegistroMonday] = []
        for board in self._consultar(consulta).get("data", {}).get("boards", []):
            for grupo in board.get("groups", []):
                tipo = grupos.get(grupo.get("id", ""), "")
                pagina = grupo.get("items_page") or {}
                itens = list(pagina.get("items", []))
                cursor = pagina.get("cursor")
                while cursor:
                    proxima = self._consultar(
                        f"{{ next_items_page(limit: {PAGINA}, cursor: {json.dumps(cursor)}) {{ cursor items {{ {campos} }} }} }}"
                    )["data"]["next_items_page"] or {"items": [], "cursor": None}
                    itens.extend(proxima.get("items", []))
                    cursor = proxima.get("cursor")
                registros.extend(self._registro(item, colunas, tipo) for item in itens)
        return registros

    @staticmethod
    def _registro(item: dict, colunas: ColunasMonday, tipo: str) -> RegistroMonday:
        valores = {c["id"]: (c.get("text") or "") for c in item.get("column_values", [])}
        return RegistroMonday(
            item_id=str(item.get("id", "")),
            fundo=(item.get("name") or "").strip(),
            cnpj=valores.get(colunas.cnpj, "").strip(),
            administrador=valores.get(colunas.administrador, "").strip(),
            carteira=valores.get(colunas.carteira, "").replace(".", "").strip(),
            exercicio_mes=mes_por_nome(valores.get(colunas.exercicio, "")),
            tipo=tipo,
            sistema=valores.get(colunas.sistema, "").strip(),
        )
