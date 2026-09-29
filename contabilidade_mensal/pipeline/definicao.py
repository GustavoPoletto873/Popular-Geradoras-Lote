"""Definição estática do pipeline: grafo de etapas, filas, locks e chave do disjuntor."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from contabilidade_mensal.core.choices import Backend, Etapa

# etapa -> etapas das quais ela depende (mesmo fundo e competência)
DEPENDENCIAS: dict[str, tuple[str, ...]] = {
    Etapa.BAIXAR_INSUMOS: (),
    Etapa.PROCESSAR_CONTABIL: (),
    Etapa.BAIXAR_BALANCETE: (Etapa.PROCESSAR_CONTABIL,),
    Etapa.POPULAR_EXCEL: (Etapa.BAIXAR_INSUMOS, Etapa.BAIXAR_BALANCETE),
    Etapa.PUBLICAR_DRIVE: (Etapa.POPULAR_EXCEL,),
}

ORDEM: tuple[str, ...] = (
    Etapa.BAIXAR_INSUMOS,
    Etapa.PROCESSAR_CONTABIL,
    Etapa.BAIXAR_BALANCETE,
    Etapa.POPULAR_EXCEL,
    Etapa.PUBLICAR_DRIVE,
)  # ordem topológica válida

# fila "lógica" de cada etapa; a fila real segue o backend configurado (api/browser)
FILA_LOGICA: dict[str, str] = {
    Etapa.BAIXAR_INSUMOS: "api",
    Etapa.PROCESSAR_CONTABIL: "browser",
    Etapa.BAIXAR_BALANCETE: "browser",
    Etapa.POPULAR_EXCEL: "excel",
    Etapa.PUBLICAR_DRIVE: "drive",
}

# operação da Britech (chave em settings.BRITECH_BACKENDS) que decide o backend da etapa
OPERACAO_BRITECH: dict[str, str] = {
    Etapa.BAIXAR_INSUMOS: "baixar_insumo",
    Etapa.PROCESSAR_CONTABIL: "processar_contabil",
    Etapa.BAIXAR_BALANCETE: "baixar_balancete",
}

FILAS = ("api", "browser", "excel", "drive")


@dataclass(frozen=True)
class PlanoEtapa:
    backend: str
    fila: str
    lock_key: str


def a_jusante(etapas: set[str] | frozenset[str] | list[str]) -> set[str]:
    """Fecho transitivo das etapas que dependem (direta ou indiretamente) das dadas, excluindo as próprias."""
    origem = set(etapas)
    resultado: set[str] = set()
    mudou = True
    while mudou:
        mudou = False
        for etapa, deps in DEPENDENCIAS.items():
            if etapa in resultado or etapa in origem:
                continue
            if any(d in origem or d in resultado for d in deps):
                resultado.add(etapa)
                mudou = True
    return resultado


def chave_disjuntor(etapa: str, backend: str, administradora_id: int) -> str:
    return f"{etapa}:{backend}:{administradora_id}"


def planejar_etapa(etapa: str, administradora_id: int) -> PlanoEtapa:
    """Backend, fila e lock de uma etapa, a partir da configuração vigente."""
    if etapa in OPERACAO_BRITECH:
        backend = settings.BRITECH_BACKENDS[OPERACAO_BRITECH[etapa]]
    elif etapa == Etapa.POPULAR_EXCEL:
        backend = Backend.EXCEL.value
    else:
        backend = Backend.DRIVE.value
    fila = backend if backend in (Backend.API, Backend.BROWSER) else FILA_LOGICA[etapa]
    # uma única sessão por credencial na PAS: o que roda no navegador serializa por administradora
    lock_key = f"britech:{administradora_id}" if fila == "browser" else ""
    return PlanoEtapa(backend=backend, fila=fila, lock_key=lock_key)
