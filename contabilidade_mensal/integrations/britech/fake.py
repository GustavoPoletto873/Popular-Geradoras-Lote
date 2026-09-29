"""Backend FAKE da Britech, para testes e para o pipeline de brinquedo.

Não fala com rede nenhuma. Comportamento roteirizável por (operação, código da carteira):

    fake.programar("baixar_insumo", "123", TimeoutBritech("lento"), None)
    # 1ª chamada levanta TimeoutBritech; a 2ª segue o caminho feliz.

Passos aceitos: exceção (instância ou classe) → é levantada; `None` → caminho feliz;
`StatusProcessamento` → devolvido por `status_processamento`.
"""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Sequence

from .interface import (
    TIPO_ARTEFATO_DO_INSUMO,
    AdministradoraRef,
    ArquivoBaixado,
    BalanceteBaixado,
    CarteiraRef,
    CompetenciaRef,
    ResultadoDisparo,
    StatusProcessamento,
    TipoInsumo,
)
from .nomes import nome_balancete_canonico, nome_insumo_canonico



class FakeSessao:
    def __init__(self, administradora: AdministradoraRef) -> None:
        self.administradora = administradora
        self.fechada = False

    def fechar(self) -> None:
        self.fechada = True


class FakeBackend:
    def __init__(self) -> None:
        self._roteiro: dict[tuple[str, str], deque[Any]] = defaultdict(deque)
        self.chamadas: list[tuple[str, str]] = []
        self.sessoes: list[FakeSessao] = []
        self.disparos: list[tuple[tuple[str, ...], bool]] = []

    # --- roteiro -------------------------------------------------------------
    def programar(self, operacao: str, chave: str, *passos: Any) -> None:
        self._roteiro[(operacao, chave)].extend(passos)

    def _proximo(self, operacao: str, chave: str) -> Any:
        self.chamadas.append((operacao, chave))
        fila = self._roteiro.get((operacao, chave))
        if not fila:
            return None
        passo = fila.popleft()
        if isinstance(passo, BaseException):
            raise passo
        if isinstance(passo, type) and issubclass(passo, BaseException):
            raise passo()
        return passo

    # --- protocolo BritechBackend -------------------------------------------
    def abrir_sessao(self, administradora: AdministradoraRef) -> FakeSessao:
        self._proximo("abrir_sessao", administradora.nome)
        sessao = FakeSessao(administradora)
        self.sessoes.append(sessao)
        return sessao

    def baixar_insumo(
        self,
        sessao: FakeSessao,
        carteira: CarteiraRef,
        competencia: CompetenciaRef,
        tipo: TipoInsumo,
        destino: Path,
    ) -> ArquivoBaixado:
        self._proximo("baixar_insumo", carteira.codigo_britech)
        destino.mkdir(parents=True, exist_ok=True)
        caminho = destino / nome_insumo_canonico(tipo, competencia, carteira.cnpj)
        caminho.write_bytes(f"fake|{carteira.codigo_britech}|{tipo.value}|{competencia.aaaamm}".encode())
        return ArquivoBaixado(TIPO_ARTEFATO_DO_INSUMO[tipo], caminho)

    def processar_contabil(
        self,
        sessao: FakeSessao,
        carteiras: Sequence[CarteiraRef],
        competencia: CompetenciaRef,
        *,
        dry_run: bool,
    ) -> ResultadoDisparo:
        for carteira in carteiras:
            self._proximo("processar_contabil", carteira.codigo_britech)
        codigos = tuple(c.codigo_britech for c in carteiras)
        self.disparos.append((codigos, dry_run))
        return ResultadoDisparo(carteiras=codigos, dry_run=dry_run)

    def status_processamento(
        self, sessao: FakeSessao, carteira: CarteiraRef, competencia: CompetenciaRef
    ) -> StatusProcessamento:
        passo = self._proximo("status_processamento", carteira.codigo_britech)
        return passo if isinstance(passo, StatusProcessamento) else StatusProcessamento.CONCLUIDO

    def baixar_balancete(
        self, sessao: FakeSessao, carteira: CarteiraRef, competencia: CompetenciaRef, destino: Path
    ) -> BalanceteBaixado:
        self._proximo("baixar_balancete", carteira.codigo_britech)
        destino.mkdir(parents=True, exist_ok=True)
        pdf = destino / nome_balancete_canonico(competencia, carteira.cnpj, "pdf")
        xls = destino / nome_balancete_canonico(competencia, carteira.cnpj, "xls")
        pdf.write_bytes(f"fake-pdf|{carteira.codigo_britech}|{competencia.aaaamm}".encode())
        xls.write_bytes(f"fake-xls|{carteira.codigo_britech}|{competencia.aaaamm}".encode())
        return BalanceteBaixado(pdf=pdf, xls=xls)

