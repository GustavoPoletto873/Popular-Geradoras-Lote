"""`python manage.py limpar_orfaos [--matar] [--idade-min 900]` — tarefa do Agendador a cada 10 minutos.

1. devolve à fila as etapas `em_andamento` cujo lease venceu (worker morto);
2. apaga travas de credencial vencidas;
3. lista (e, com `--matar`, encerra) EXCEL.EXE de automação e Chromium do Playwright órfãos.
Sem `--matar` é só relatório.
"""

from django.core.management.base import BaseCommand

from contabilidade_mensal.pipeline import fila, watchdog


class Command(BaseCommand):
    help = "Recupera etapas órfãs, limpa travas vencidas e (opcional) encerra Excel/Chromium órfãos."

    def add_arguments(self, parser):
        parser.add_argument("--matar", action="store_true", help="encerra os processos órfãos (padrão: só lista)")
        parser.add_argument("--idade-min", type=float, default=900, help="idade mínima do processo, em segundos")

    def handle(self, *args, **o):
        recuperadas = fila.recuperar_orfas()
        travas = watchdog.limpar_travas_vencidas()
        candidatos = watchdog.orfaos(watchdog.listar_processos(), idade_min_s=o["idade_min"])
        self.stdout.write(f"{recuperadas} etapa(s) órfã(s) devolvida(s) à fila; {travas} trava(s) vencida(s) removida(s).")
        for p in candidatos:
            self.stdout.write(f"  órfão: pid {p.pid} {p.nome} ({p.tipo}) há {int(p.idade_s)}s")
        if candidatos and o["matar"]:
            encerrados = watchdog.encerrar(candidatos)
            self.stdout.write(f"{len(encerrados)} processo(s) encerrado(s).")
        elif candidatos:
            self.stdout.write("(use --matar para encerrá-los)")
