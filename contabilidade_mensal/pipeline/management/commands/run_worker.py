"""`python manage.py run_worker --fila api|browser|excel|drive [--once]`

Os handlers de `baixar_insumos`, `processar_contabil` e `baixar_balancete` falam com o gateway e usam o backend
configurado em `BRITECH_BACKEND_<OPERACAO>` (fake | api | browser). `popular_excel` e `publicar_drive` ainda são
STUBS (Fase 6): as filas `excel` e `drive` só sobem com PERMITIR_STUBS_EXCEL_DRIVE=true.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from contabilidade_mensal.integrations.britech.factory import montar_gateway
from contabilidade_mensal.pipeline import fakes
from contabilidade_mensal.pipeline.definicao import FILAS
from contabilidade_mensal.pipeline.worker import Worker


class Command(BaseCommand):
    help = "Executa um worker de uma fila do pipeline."

    def add_arguments(self, parser):
        parser.add_argument("--fila", required=True, choices=FILAS)
        parser.add_argument("--once", action="store_true", help="para quando a fila esvaziar")
        parser.add_argument("--intervalo", type=float, default=5.0, help="segundos entre consultas com a fila vazia")
        parser.add_argument("--lote", type=int, default=1, help="etapas por ciclo (mesma credencial)")
        parser.add_argument("--worker-id", default=None)

    def handle(self, *args, **opcoes):
        if opcoes["fila"] in ("excel", "drive") and not settings.PERMITIR_STUBS_EXCEL_DRIVE:
            raise CommandError(
                f"a fila {opcoes['fila']!r} ainda roda um STUB (Fase 6); defina PERMITIR_STUBS_EXCEL_DRIVE=true "
                "para usá-lo em homologação (não toca Excel nem Drive)"
            )
        handlers = fakes.montar_handlers(
            montar_gateway(),
            settings.STORAGE_ROOT,
            dry_run_processar=settings.DRY_RUN_PROCESSAR_CONTABIL,
            dry_run_publicar=settings.DRY_RUN_PUBLICAR_DRIVE,
        )
        worker = Worker(opcoes["fila"], handlers, worker_id=opcoes["worker_id"], lote=opcoes["lote"])
        total = worker.rodar(intervalo_s=opcoes["intervalo"], parar_quando_vazio=opcoes["once"])
        self.stdout.write(f"{total} etapa(s) executada(s) na fila {opcoes['fila']}")
