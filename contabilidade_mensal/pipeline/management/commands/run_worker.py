"""`python manage.py run_worker --fila api|browser|excel|drive [--once]`

Fase 1: só existem os handlers FAKE, então o comando exige que todos os backends estejam
em `fake`. Os handlers reais entram nas Fases 2–6.
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
        fora_do_fake = {op: b for op, b in settings.BRITECH_BACKENDS.items() if b != "fake"}
        if fora_do_fake:
            raise CommandError(
                f"handlers reais ainda não existem (Fases 2–6); backends configurados fora do fake: {fora_do_fake}"
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
