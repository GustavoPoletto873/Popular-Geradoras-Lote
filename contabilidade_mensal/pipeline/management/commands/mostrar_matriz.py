"""`python manage.py mostrar_matriz --competencia AAAA-MM` — matriz fundo × etapa (estado vigente)."""

from django.core.management.base import BaseCommand, CommandError

from contabilidade_mensal.core.models import Competencia
from contabilidade_mensal.pipeline import servicos
from contabilidade_mensal.pipeline.definicao import ORDEM


class Command(BaseCommand):
    help = "Mostra a matriz fundo × etapa de uma competência."

    def add_arguments(self, parser):
        parser.add_argument("--competencia", required=True, help="AAAA-MM")

    def handle(self, *args, **o):
        try:
            ano, mes = (int(x) for x in o["competencia"].split("-"))
            competencia = Competencia.objects.get(ano=ano, mes=mes)
        except (ValueError, Competencia.DoesNotExist) as exc:
            raise CommandError("competência inexistente (use AAAA-MM)") from exc
        linhas = servicos.matriz(competencia)
        self.stdout.write(f"{'fundo':34}" + "".join(f"{e:20}" for e in ORDEM))
        for linha in linhas:
            texto = ""
            for c in linha["celulas"]:
                rotulo = (c["status"] or "-") + (f" ({c['erro']})" if c["erro"] else "")
                texto += f"{rotulo[:19]:20}"
            self.stdout.write(f"{linha['fundo'].nome[:33]:34}{texto}")
        if not linhas:
            self.stdout.write("(nenhuma execução nesta competência)")
