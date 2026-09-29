"""`python manage.py run_worker --fila api|browser|excel|drive [--once]`

Os handlers de `baixar_insumos`, `processar_contabil` e `baixar_balancete` falam com o gateway e usam o backend
configurado em `BRITECH_BACKEND_<OPERACAO>` (fake | api | browser). `popular_excel` usa o Excel real com
EXCEL_BACKEND=com e `publicar_drive` o drive_api com DRIVE_BACKEND=api; em `stub` (padrão) a fila só sobe com
PERMITIR_STUBS_EXCEL_DRIVE=true. Ver `pipeline/wiring.py`.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from contabilidade_mensal.pipeline import wiring
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
        if wiring.fila_exige_stub(opcoes["fila"]) and not settings.PERMITIR_STUBS_EXCEL_DRIVE:
            raise CommandError(
                f"a fila {opcoes['fila']!r} está em modo STUB (EXCEL_BACKEND/DRIVE_BACKEND); use EXCEL_BACKEND=com / "
                "DRIVE_BACKEND=api, ou PERMITIR_STUBS_EXCEL_DRIVE=true em homologação (não toca Excel nem Drive)"
            )
        try:
            handlers = wiring.montar_handlers_do_ambiente(opcoes["fila"])
        except ImproperlyConfigured as exc:
            raise CommandError(str(exc)) from exc
        worker = Worker(opcoes["fila"], handlers, worker_id=opcoes["worker_id"], lote=opcoes["lote"])
        total = worker.rodar(intervalo_s=opcoes["intervalo"], parar_quando_vazio=opcoes["once"])
        self.stdout.write(f"{total} etapa(s) executada(s) na fila {opcoes['fila']}")
