"""De onde vem a boleta do MÊS ANTERIOR (o modelo que o Excel copia, limpa e repopula).

- `OrigemDrive`: baixa da pasta `Tipo/Fundo/Data Base X/AAAAMM-anterior` pelo `drive_api` (caminho definitivo).
- `OrigemLocal`: lê da árvore montada em `G:\\` (a mesma que o populador usa hoje). Somente leitura.

A escolha do arquivo é a do populador: o primeiro (ordem alfabética) cujo nome contém ".xls".
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol

from contabilidade_mensal.core.dominio import caminho_relativo_competencia
from contabilidade_mensal.core.models import Competencia, Fundo
from contabilidade_mensal.integrations.drive.cliente import DriveApiCliente
from contabilidade_mensal.integrations.drive.publicador import PublicadorDrive, _e_planilha

from ..britech.erros import BritechErro


class BoletaAnteriorAusente(BritechErro):
    """Sem a boleta do mês anterior não há modelo para copiar. Não adianta repetir."""

    codigo = "boleta_anterior_ausente"


def competencia_anterior(competencia: Competencia) -> tuple[int, int]:
    return (competencia.ano - 1, 12) if competencia.mes == 1 else (competencia.ano, competencia.mes - 1)


class OrigemBoleta(Protocol):
    def obter(self, fundo: Fundo, competencia: Competencia, destino: Path) -> Path:
        """Coloca a boleta anterior em `destino` (pasta) e devolve o caminho local."""


class OrigemDrive:
    def __init__(self, cliente: DriveApiCliente, publicador: PublicadorDrive) -> None:
        self._cliente = cliente
        self._publicador = publicador

    def obter(self, fundo: Fundo, competencia: Competencia, destino: Path) -> Path:
        ano, mes = competencia_anterior(competencia)
        anterior = Competencia(ano=ano, mes=mes)
        pasta_id, caminho = self._publicador.resolver_pasta(fundo, anterior, criar=False)
        planilhas = sorted((i for i in self._cliente.listar(pasta_id) if _e_planilha(i)), key=lambda i: i["name"]) if pasta_id else []
        if not planilhas:
            raise BoletaAnteriorAusente(f"não há planilha em {caminho} no Drive")
        destino.mkdir(parents=True, exist_ok=True)
        alvo = destino / planilhas[0]["name"]
        alvo.write_bytes(self._cliente.baixar(planilhas[0]["id"]))
        return alvo


class OrigemLocal:
    def __init__(self, raiz: Path) -> None:
        self._raiz = Path(raiz)

    def obter(self, fundo: Fundo, competencia: Competencia, destino: Path) -> Path:
        ano, mes = competencia_anterior(competencia)
        pasta = self._raiz.joinpath(*caminho_relativo_competencia(fundo.tipo, fundo.nome, fundo.exercicio_mes, ano, mes))
        candidatos = sorted(p for p in pasta.iterdir() if p.is_file() and ".xls" in p.name.lower()) if pasta.is_dir() else []
        if not candidatos:
            raise BoletaAnteriorAusente(f"não há planilha em {pasta}")
        destino.mkdir(parents=True, exist_ok=True)
        alvo = destino / candidatos[0].name
        shutil.copy2(candidatos[0], alvo)
        return alvo
