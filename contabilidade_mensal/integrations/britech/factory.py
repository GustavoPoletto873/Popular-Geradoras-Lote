"""`BritechGateway`: fachada única que roteia cada operação para o backend configurado.

Backend por operação vem de `settings.BRITECH_BACKENDS` (variáveis
`BRITECH_BACKEND_<OPERACAO>`), então trocar API ↔ navegador não exige deploy de código.
As sessões dos backends são abertas de forma preguiçosa: uma execução 100% por API
nunca sobe o Chromium.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

from .erros import BackendNaoDisponivel, SessaoBloqueada
from .fake import FakeBackend
from .interface import (
    AdministradoraRef,
    ArquivoBaixado,
    BalanceteBaixado,
    BritechBackend,
    CarteiraRef,
    CompetenciaRef,
    ResultadoDisparo,
    SessaoBritech,
    StatusProcessamento,
    TipoInsumo,
)

logger = logging.getLogger(__name__)

OPERACOES = ("baixar_insumo", "processar_contabil", "status_processamento", "baixar_balancete")

def _fabrica_api() -> BritechBackend:
    """Import preguiçoso: só carrega pandas/requests/holidays quando o backend `api` é realmente usado."""
    from .api_backend.backend import ApiBackend
    from .api_backend.credenciais import CredenciaisDoAmbiente

    return ApiBackend(CredenciaisDoAmbiente())


def _fabrica_browser() -> BritechBackend:
    """Import preguiçoso: só carrega o Playwright quando o backend `browser` é realmente usado."""
    from .api_backend.credenciais import CredenciaisDoAmbiente
    from .browser_backend.backend import BrowserBackend

    return BrowserBackend(CredenciaisDoAmbiente())


_FABRICAS: dict[str, Callable[[], BritechBackend]] = {
    "fake": FakeBackend,
    "api": _fabrica_api,
    "browser": _fabrica_browser,
}


def registrar_backend(nome: str, fabrica: Callable[[], BritechBackend]) -> None:
    _FABRICAS[nome] = fabrica


class SessaoComposta:
    """Conjunto de sessões (uma por backend usado), abertas sob demanda e fechadas juntas."""

    def __init__(self, administradora: AdministradoraRef, backends: Mapping[str, BritechBackend]) -> None:
        self.administradora = administradora
        self._backends = backends
        self._abertas: dict[str, SessaoBritech] = {}

    def obter(self, nome_backend: str) -> SessaoBritech:
        if nome_backend not in self._abertas:
            self._abertas[nome_backend] = self._backends[nome_backend].abrir_sessao(self.administradora)
        return self._abertas[nome_backend]

    def fechar(self) -> None:
        erros: list[Exception] = []
        for nome, sessao in reversed(list(self._abertas.items())):
            try:
                sessao.fechar()
            except Exception as exc:  # noqa: BLE001 - tenta fechar todas antes de reportar
                logger.error("falha ao fechar sessão do backend %s", nome, exc_info=True)
                erros.append(exc)
        self._abertas.clear()
        if erros:
            raise SessaoBloqueada(f"{len(erros)} sessão(ões) não puderam ser encerradas: {erros[0]}") from erros[0]


class BritechGateway:
    def __init__(self, backends: Mapping[str, BritechBackend], config: Mapping[str, str]) -> None:
        ausentes = [op for op in OPERACOES if op not in config]
        if ausentes:
            raise ValueError(f"configuração sem backend para: {ausentes}")
        for operacao, nome in config.items():
            if nome not in backends:
                raise BackendNaoDisponivel(f"operação {operacao!r} aponta para o backend {nome!r}, que não foi fornecido")
        self._backends = dict(backends)
        self._config = dict(config)

    def backend_de(self, operacao: str) -> str:
        return self._config[operacao]

    @contextmanager
    def sessao(self, administradora: AdministradoraRef) -> Iterator[SessaoComposta]:
        """Login … trabalho … logout garantido, mesmo em erro."""
        composta = SessaoComposta(administradora, self._backends)
        try:
            yield composta
        finally:
            composta.fechar()

    def _chamar(self, operacao: str, sessao: SessaoComposta, *args, **kwargs):
        nome = self._config[operacao]
        return getattr(self._backends[nome], operacao)(sessao.obter(nome), *args, **kwargs)

    def baixar_insumo(
        self, sessao: SessaoComposta, carteira: CarteiraRef, competencia: CompetenciaRef, tipo: TipoInsumo, destino: Path
    ) -> ArquivoBaixado:
        return self._chamar("baixar_insumo", sessao, carteira, competencia, tipo, destino)

    def processar_contabil(
        self, sessao: SessaoComposta, carteiras: Sequence[CarteiraRef], competencia: CompetenciaRef, *, dry_run: bool
    ) -> ResultadoDisparo:
        return self._chamar("processar_contabil", sessao, carteiras, competencia, dry_run=dry_run)

    def status_processamento(
        self, sessao: SessaoComposta, carteira: CarteiraRef, competencia: CompetenciaRef
    ) -> StatusProcessamento:
        return self._chamar("status_processamento", sessao, carteira, competencia)

    def baixar_balancete(
        self, sessao: SessaoComposta, carteira: CarteiraRef, competencia: CompetenciaRef, destino: Path
    ) -> BalanceteBaixado:
        return self._chamar("baixar_balancete", sessao, carteira, competencia, destino)


def montar_gateway(config: Mapping[str, str] | None = None) -> BritechGateway:
    """Monta o gateway a partir de `settings.BRITECH_BACKENDS` (ou de `config`)."""
    if config is None:
        from django.conf import settings

        config = settings.BRITECH_BACKENDS
    backends: dict[str, BritechBackend] = {}
    for nome in sorted(set(config.values())):
        if nome not in _FABRICAS:
            raise BackendNaoDisponivel(
                f"backend {nome!r} não existe. Disponíveis: {sorted(_FABRICAS)}"
            )
        backends[nome] = _FABRICAS[nome]()
    return BritechGateway(backends, config)
