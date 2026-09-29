"""Backend `browser` do gateway: sessão (login/logout confirmados) + fluxos de Processar Contábil e Balancete.

`status_processamento` NÃO é implementado: não se conhece um sinal de conclusão na PAS (Q4). O pipeline decide a
conclusão por `PIPELINE["processamento_conclusao"]` (espera mínima ou confirmação manual).
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from pathlib import Path

from playwright.sync_api import BrowserContext

from ..api_backend.credenciais import ProvedorCredenciais
from ..erros import OperacaoNaoSuportada, ProcessamentoNaoAutorizado
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
from .flows.baixar_balancete import baixar_balancete
from .flows.processar_contabil import disparar_processamento
from .session import SessaoNavegador


class BrowserBackend:
    def __init__(
        self,
        credenciais: ProvedorCredenciais,
        config: ConfigNavegador | None = None,
        *,
        preparar_contexto: Callable[[BrowserContext], None] | None = None,
        allowlist_processar: Collection[str] | None = None,
    ) -> None:
        self._credenciais = credenciais
        self._config = config
        self._preparar_contexto = preparar_contexto
        self._allowlist = None if allowlist_processar is None else frozenset(str(c) for c in allowlist_processar)

    def _carteiras_autorizadas(self) -> frozenset[str]:
        if self._allowlist is not None:
            return self._allowlist
        from django.conf import settings

        return frozenset(str(c) for c in settings.ALLOWLIST_PROCESSAR_CONTABIL)

    def abrir_sessao(self, administradora: AdministradoraRef) -> SessaoNavegador:
        credencial = self._credenciais.obter(administradora.segredo_ref)
        config = self._config or ConfigNavegador.do_django()
        return SessaoNavegador(
            administradora, credencial.usuario, credencial.senha, config, preparar_contexto=self._preparar_contexto
        ).abrir()

    def baixar_insumo(self, sessao, carteira: CarteiraRef, competencia: CompetenciaRef, tipo: TipoInsumo, destino: Path) -> ArquivoBaixado:
        raise OperacaoNaoSuportada("baixar_insumo não é feito pelo navegador; use o backend 'api'")

    def processar_contabil(
        self, sessao: SessaoNavegador, carteiras: Sequence[CarteiraRef], competencia: CompetenciaRef, *, dry_run: bool
    ) -> ResultadoDisparo:
        codigos = [c.codigo_britech for c in carteiras]
        if not dry_run:
            fora = sorted(set(codigos) - self._carteiras_autorizadas())
            if fora:  # conferido ANTES de abrir qualquer tela: sem allowlist não há clique real
                raise ProcessamentoNaoAutorizado(f"carteira(s) fora da allowlist de processamento: {fora}")
        timeout = sessao.config.timeout_ms
        return sessao.executar(
            "processar_contabil",
            lambda page, base: disparar_processamento(page, base, codigos, dry_run=dry_run, timeout_ms=timeout),
        )

    def status_processamento(self, sessao, carteira: CarteiraRef, competencia: CompetenciaRef) -> StatusProcessamento:
        raise OperacaoNaoSuportada(
            "a PAS não tem sinal de conclusão conhecido (Q4): configure "
            "PIPELINE['processamento_conclusao'] = 'espera' ou 'manual'"
        )

    def baixar_balancete(
        self, sessao: SessaoNavegador, carteira: CarteiraRef, competencia: CompetenciaRef, destino: Path
    ) -> BalanceteBaixado:
        cfg = sessao.config
        return sessao.executar(
            "baixar_balancete",
            lambda page, base: baixar_balancete(
                page,
                base,
                codigo_carteira=carteira.codigo_britech,
                cnpj=carteira.cnpj,
                competencia=competencia,
                destino=destino,
                timeout_ms=cfg.timeout_ms,
                timeout_download_ms=cfg.timeout_download_ms,
            ),
        )
