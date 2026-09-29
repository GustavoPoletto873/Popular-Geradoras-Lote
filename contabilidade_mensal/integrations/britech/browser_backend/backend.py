"""Backend `browser` do gateway. Fase 3: só abre/fecha a sessão (e expõe as telas); os fluxos entram na Fase 4."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from playwright.sync_api import BrowserContext

from ..api_backend.credenciais import ProvedorCredenciais
from ..erros import OperacaoNaoSuportada
from ..interface import (
    AdministradoraRef,
    ArquivoBaixado,
    BalanceteBaixado,
    CarteiraRef,
    CompetenciaRef,
    ResultadoDisparo,
    StatusProcessamento,
    TipoInsumo,
)
from .config import ConfigNavegador
from .session import SessaoNavegador


class BrowserBackend:
    def __init__(
        self,
        credenciais: ProvedorCredenciais,
        config: ConfigNavegador | None = None,
        *,
        preparar_contexto: Callable[[BrowserContext], None] | None = None,
    ) -> None:
        self._credenciais = credenciais
        self._config = config
        self._preparar_contexto = preparar_contexto

    def abrir_sessao(self, administradora: AdministradoraRef) -> SessaoNavegador:
        credencial = self._credenciais.obter(administradora.segredo_ref)
        config = self._config or ConfigNavegador.do_django()
        return SessaoNavegador(
            administradora, credencial.usuario, credencial.senha, config, preparar_contexto=self._preparar_contexto
        ).abrir()

    def baixar_insumo(self, sessao, carteira: CarteiraRef, competencia: CompetenciaRef, tipo: TipoInsumo, destino: Path) -> ArquivoBaixado:
        raise OperacaoNaoSuportada("baixar_insumo não é feito pelo navegador; use o backend 'api'")

    def processar_contabil(self, sessao, carteiras: Sequence[CarteiraRef], competencia: CompetenciaRef, *, dry_run: bool) -> ResultadoDisparo:
        raise OperacaoNaoSuportada("processar_contabil por navegador entra na Fase 4")

    def status_processamento(self, sessao, carteira: CarteiraRef, competencia: CompetenciaRef) -> StatusProcessamento:
        raise OperacaoNaoSuportada("status_processamento por navegador entra na Fase 4")

    def baixar_balancete(self, sessao, carteira: CarteiraRef, competencia: CompetenciaRef, destino: Path) -> BalanceteBaixado:
        raise OperacaoNaoSuportada("baixar_balancete por navegador entra na Fase 4")
