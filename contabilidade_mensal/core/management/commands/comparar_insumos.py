"""`python manage.py comparar_insumos --a PASTA_A --b PASTA_B`

Critério de aceite da Fase 2: para um fundo real, os insumos gerados pelo pipeline (`baixar_insumos_api`) têm que
ser iguais, célula a célula, aos gerados pelo Simplifica. Termina com erro (código ≠ 0) se houver qualquer diferença.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from contabilidade_mensal.storage.comparacao import comparar_pastas


class Command(BaseCommand):
    help = "Compara, célula a célula, os .xlsx de duas pastas de Insumos."

    def add_arguments(self, parser):
        parser.add_argument("--a", required=True, type=Path, help="ex.: pasta gerada pelo pipeline")
        parser.add_argument("--b", required=True, type=Path, help="ex.: pasta Insumos gerada pelo Simplifica")
        parser.add_argument("--limite", type=int, default=20, help="máximo de células diferentes mostradas por arquivo")

    def handle(self, *args, **opcoes):
        for pasta in (opcoes["a"], opcoes["b"]):
            if not pasta.is_dir():
                raise CommandError(f"pasta não encontrada: {pasta}")
        r = comparar_pastas(opcoes["a"], opcoes["b"], limite=opcoes["limite"])

        self.stdout.write(f"{len(r.iguais)} arquivo(s) iguais")
        for nome in r.iguais:
            self.stdout.write(f"  = {nome}")
        for nome in r.so_em_a:
            self.stdout.write(f"  só em A: {nome}")
        for nome in r.so_em_b:
            self.stdout.write(f"  só em B: {nome}")
        for nome, detalhe in r.diferentes.items():
            self.stdout.write(f"  ≠ {nome}")
            if isinstance(detalhe, str):
                self.stdout.write(f"      {detalhe}")
            else:
                for d in detalhe:
                    self.stdout.write(f"      linha {d.linha}, coluna {d.coluna!r}: A={d.a!r}  B={d.b!r}")
        if not r.ok:
            raise CommandError("as pastas NÃO são equivalentes")
        self.stdout.write("As pastas são equivalentes.")
