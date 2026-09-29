"""Drive em memória com a MESMA interface de `DriveApiCliente` (pastas/arquivos por id), para testar publicador e origem."""

from __future__ import annotations

from pathlib import Path

from contabilidade_mensal.integrations.drive.cliente import MIME_PASTA, PastaDriveNaoEncontrada


class DriveFalso:
    def __init__(self) -> None:
        self.itens: dict[str, dict] = {"raiz": {"id": "raiz", "name": "RAIZ", "mimeType": MIME_PASTA, "parents": []}}
        self.conteudos: dict[str, bytes] = {}
        self._n = 0
        self.envios = 0
        self.sobrescritas = 0
        self.corromper_proximo_envio = 0  # quantos envios/sobrescritas saem com conteúdo errado

    def _id(self) -> str:
        self._n += 1
        return f"id{self._n}"

    # --- montagem de cenário -----------------------------------------------------------------------------------
    def pasta(self, nome: str, pai: str = "raiz") -> str:
        item = {"id": self._id(), "name": nome, "mimeType": MIME_PASTA, "parents": [pai]}
        self.itens[item["id"]] = item
        return item["id"]

    def arquivo(self, nome: str, pai: str, conteudo: bytes) -> str:
        item = {"id": self._id(), "name": nome, "mimeType": "application/octet-stream", "parents": [pai]}
        self.itens[item["id"]] = item
        self.conteudos[item["id"]] = conteudo
        return item["id"]

    def caminho(self, *nomes: str) -> str:
        """Cria (se preciso) a cadeia de pastas e devolve o id da última."""
        atual = "raiz"
        for nome in nomes:
            achada = self.buscar_pasta(nome, atual)
            atual = achada["id"] if achada else self.pasta(nome, atual)
        return atual

    # --- interface do cliente ----------------------------------------------------------------------------------
    def buscar_pasta(self, nome: str, pai_id: str):
        return next(
            (i for i in self.itens.values() if i["mimeType"] == MIME_PASTA and i["name"] == nome and pai_id in i["parents"]),
            None,
        )

    def criar_pasta(self, nome: str, pai_id: str) -> dict:
        if pai_id not in self.itens:
            raise PastaDriveNaoEncontrada(f"pasta pai {pai_id} não existe")
        return self.itens[self.pasta(nome, pai_id)]

    def listar(self, pasta_id: str) -> list[dict]:
        return [i for i in self.itens.values() if pasta_id in i["parents"]]

    def _conteudo_gravado(self, caminho: Path) -> bytes:
        dados = Path(caminho).read_bytes()
        if self.corromper_proximo_envio > 0:
            self.corromper_proximo_envio -= 1
            return dados + b"!corrompido"
        return dados

    def enviar(self, pasta_id: str, caminho: Path, nome: str | None = None) -> dict:
        if pasta_id not in self.itens:
            raise PastaDriveNaoEncontrada(f"pasta {pasta_id} não existe")
        self.envios += 1
        novo = self.arquivo(nome or Path(caminho).name, pasta_id, self._conteudo_gravado(caminho))
        return self.itens[novo]

    def sobrescrever(self, arquivo_id: str, caminho: Path) -> dict:
        self.sobrescritas += 1
        self.conteudos[arquivo_id] = self._conteudo_gravado(caminho)
        return self.itens[arquivo_id]

    def baixar(self, arquivo_id: str) -> bytes:
        return self.conteudos[arquivo_id]
