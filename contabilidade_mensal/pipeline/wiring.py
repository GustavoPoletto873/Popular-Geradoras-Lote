"""Monta os handlers do ambiente a partir das settings (quem é real e quem é stub).

    EXCEL_BACKEND=com  + EXCEL_ORIGEM=drive|local   -> Excel real (Windows)
    DRIVE_BACKEND=api  + DRIVE_API_URL/TOKEN/RAIZ   -> publicação real no Drive (drive_api)
    o que estiver `stub` só sobe com PERMITIR_STUBS_EXCEL_DRIVE=true.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from contabilidade_mensal.integrations.britech.factory import montar_gateway

from . import fakes
from .tipos import Handler


def _cliente_drive():
    from contabilidade_mensal.integrations.drive.cliente import DriveApiCliente

    return DriveApiCliente(settings.DRIVE_API["url"] or "", os.environ.get("DRIVE_API_TOKEN", ""))


def _publicador_drive(cliente=None):
    from contabilidade_mensal.integrations.drive.publicador import PublicadorDrive

    return PublicadorDrive(cliente or _cliente_drive(), settings.DRIVE_API["raiz_id"] or "")


def _populador_excel(publicador=None):
    from contabilidade_mensal.integrations.excel.adapter import PopuladorExcel
    from contabilidade_mensal.integrations.excel.origem import OrigemDrive, OrigemLocal

    if settings.EXCEL_ORIGEM == "local":
        if not settings.BOLETA_RAIZ_LOCAL:
            raise ImproperlyConfigured("EXCEL_ORIGEM=local exige BOLETA_RAIZ_LOCAL")
        origem = OrigemLocal(settings.BOLETA_RAIZ_LOCAL)
    elif settings.EXCEL_ORIGEM == "drive":
        publicador = publicador or _publicador_drive()
        origem = OrigemDrive(publicador._cliente, publicador)
    else:
        raise ImproperlyConfigured(f"EXCEL_ORIGEM inválido: {settings.EXCEL_ORIGEM!r} (drive | local)")
    return PopuladorExcel(origem)


def montar_handlers_do_ambiente(fila: str | None = None) -> Mapping[str, Handler]:
    """`fila` opcional: só monta o adapter da fila pedida (um worker de `api` não precisa de Excel nem de token do Drive)."""
    populador = publicador = None
    if fila in (None, "drive", "excel") and settings.DRIVE_BACKEND == "api":
        publicador = _publicador_drive() if fila != "excel" or settings.EXCEL_ORIGEM == "drive" else None
    if fila in (None, "excel") and settings.EXCEL_BACKEND == "com":
        populador = _populador_excel(publicador if settings.EXCEL_ORIGEM == "drive" else None)
    return fakes.montar_handlers(
        montar_gateway(),
        settings.STORAGE_ROOT,
        dry_run_processar=settings.DRY_RUN_PROCESSAR_CONTABIL,
        dry_run_publicar=settings.DRY_RUN_PUBLICAR_DRIVE,
        populador=populador,
        publicador=publicador,
    )


def fila_exige_stub(fila: str) -> bool:
    return (fila == "excel" and settings.EXCEL_BACKEND != "com") or (fila == "drive" and settings.DRIVE_BACKEND != "api")
