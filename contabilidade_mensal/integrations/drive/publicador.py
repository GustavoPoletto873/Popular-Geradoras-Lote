"""Publicação da boleta no Drive: resolve `Tipo/Fundo/Data Base X/AAAAMM`, envia e VERIFICA por hash.

Regras:
  - `Tipo` e `Fundo` precisam existir com o nome exato (divergência de nome é cadastro a corrigir, não algo a inventar);
    `Data Base X` e `AAAAMM` são criadas se faltarem. O id resolvido fica em `PastaCompetencia` (pode ser corrigido
    à mão no admin).
  - A pasta da competência que já tem OUTRA planilha é tratada como o populador trata ("Arquivo já existe"):
    `DestinoJaExiste`, a menos que `forcar`. Mesmo conteúdo = reaproveita (idempotente, sem novo upload).
  - Depois do upload o arquivo é baixado de volta e o SHA-256 é comparado com o local.
  - `dry_run` só LÊ (resolve pastas sem criar e lista o destino); nunca cria nem envia.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

from contabilidade_mensal.core.dominio import caminho_relativo_competencia
from contabilidade_mensal.core.models import Competencia, Fundo, PastaCompetencia
from contabilidade_mensal.storage.hashing import sha256_arquivo

from ..britech.erros import ArquivoInvalido
from .cliente import MIME_PASTA, DestinoJaExiste, DriveApiCliente, PastaDriveNaoEncontrada

logger = logging.getLogger(__name__)


@dataclass
class PublicacaoFeita:
    file_id: str
    sha256: str
    tamanho: int
    pasta_id: str
    caminho_relativo: str
    reaproveitada: bool = False  # já estava lá com o mesmo conteúdo
    avisos: list[str] = field(default_factory=list)


@dataclass
class PrevisaoPublicacao:
    """Resultado do dry-run: o que aconteceria, sem ter feito nada."""

    caminho_relativo: str
    pasta_existe: bool
    acao: str  # "criar pastas e enviar" | "enviar" | "reaproveitar" | "conflito"


def _sha256_bytes(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def _e_planilha(item: dict) -> bool:
    return item.get("mimeType") != MIME_PASTA and ".xls" in item.get("name", "").lower()


class PublicadorDrive:
    def __init__(self, cliente: DriveApiCliente, raiz_id: str) -> None:
        if not raiz_id:
            raise PastaDriveNaoEncontrada("defina DRIVE_RAIZ_ID (id da pasta que contém as pastas de tipo)")
        self._cliente = cliente
        self._raiz_id = raiz_id

    # --- resolução de pastas ------------------------------------------------------------------------------------

    def _nomes(self, fundo: Fundo, competencia: Competencia) -> tuple[str, ...]:
        return caminho_relativo_competencia(fundo.tipo, fundo.nome, fundo.exercicio_mes, competencia.ano, competencia.mes)

    def resolver_pasta(self, fundo: Fundo, competencia: Competencia, *, criar: bool) -> tuple[str | None, str]:
        """(id da pasta AAAAMM ou None se ainda não existe e `criar=False`, caminho legível)."""
        nomes = self._nomes(fundo, competencia)
        caminho = "/".join(nomes)
        # competência ainda não gravada (ex.: o mês anterior, só consultado) não usa nem alimenta o cache
        em_cache = (
            PastaCompetencia.objects.filter(fundo=fundo, competencia=competencia).first() if competencia.pk else None
        )
        if em_cache:
            return em_cache.drive_folder_id, em_cache.caminho_relativo or caminho

        atual = self._raiz_id
        for indice, nome in enumerate(nomes):
            achada = self._cliente.buscar_pasta(nome, atual)
            if achada is None:
                obrigatoria = indice < 2  # Tipo e Fundo
                if obrigatoria:
                    raise PastaDriveNaoEncontrada(
                        f"não existe a pasta {nome!r} dentro de {'/'.join(nomes[:indice]) or 'a raiz'}; "
                        "confira o nome no Drive ou informe o id em PastaCompetencia (admin)"
                    )
                if not criar:
                    return None, caminho
                achada = self._cliente.criar_pasta(nome, atual)
                logger.info("pasta criada no Drive", extra={"pasta": nome})
            atual = achada["id"]
        if criar and competencia.pk:
            PastaCompetencia.objects.update_or_create(
                fundo=fundo, competencia=competencia, defaults={"drive_folder_id": atual, "caminho_relativo": caminho}
            )
        return atual, caminho

    # --- publicação ---------------------------------------------------------------------------------------------

    def prever(self, fundo: Fundo, competencia: Competencia, boleta: Path) -> PrevisaoPublicacao:
        pasta_id, caminho = self.resolver_pasta(fundo, competencia, criar=False)
        if pasta_id is None:
            return PrevisaoPublicacao(caminho, False, "criar pastas e enviar")
        planilhas = [i for i in self._cliente.listar(pasta_id) if _e_planilha(i)]
        if not planilhas:
            return PrevisaoPublicacao(caminho, True, "enviar")
        mesmo_nome = [i for i in planilhas if i["name"] == boleta.name]
        if mesmo_nome and self._conteudo_igual(mesmo_nome[0]["id"], boleta):
            return PrevisaoPublicacao(caminho, True, "reaproveitar")
        return PrevisaoPublicacao(caminho, True, "conflito")

    def _conteudo_igual(self, arquivo_id: str, local: Path) -> bool:
        return _sha256_bytes(self._cliente.baixar(arquivo_id)) == sha256_arquivo(local)

    def publicar(self, fundo: Fundo, competencia: Competencia, boleta: Path, *, forcar: bool = False) -> PublicacaoFeita:
        boleta = Path(boleta)
        sha_local, tamanho = sha256_arquivo(boleta), boleta.stat().st_size
        pasta_id, caminho = self.resolver_pasta(fundo, competencia, criar=True)
        planilhas = [i for i in self._cliente.listar(pasta_id) if _e_planilha(i)]

        mesmo_nome = next((i for i in planilhas if i["name"] == boleta.name), None)
        if mesmo_nome and self._conteudo_igual(mesmo_nome["id"], boleta):
            return PublicacaoFeita(mesmo_nome["id"], sha_local, tamanho, pasta_id, caminho, reaproveitada=True)
        if planilhas and not forcar:
            nomes = ", ".join(sorted(i["name"] for i in planilhas))
            raise DestinoJaExiste(f"a pasta {caminho} já tem planilha(s) diferente(s): {nomes}. Use forçar para sobrescrever.")

        if mesmo_nome:  # forçar sobre o mesmo nome
            arquivo = self._cliente.sobrescrever(mesmo_nome["id"], boleta)
        else:
            arquivo = self._cliente.enviar(pasta_id, boleta, boleta.name)

        if _sha256_bytes(self._cliente.baixar(arquivo["id"])) != sha_local:  # uma segunda chance, depois falha
            arquivo = self._cliente.sobrescrever(arquivo["id"], boleta)
            if _sha256_bytes(self._cliente.baixar(arquivo["id"])) != sha_local:
                raise ArquivoInvalido(f"o arquivo enviado ao Drive ({arquivo['id']}) não confere com o local (SHA-256)")
        return PublicacaoFeita(arquivo["id"], sha_local, tamanho, pasta_id, caminho)
