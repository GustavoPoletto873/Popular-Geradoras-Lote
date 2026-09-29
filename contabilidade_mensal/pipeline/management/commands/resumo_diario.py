"""`python manage.py resumo_diario [--competencia AAAA-MM|auto]` — resumo por e-mail/Slack (tarefa diária do Agendador).

Mostra, para a competência, quantas etapas estão em cada estado, os fundos com falha e o que está esperando
confirmação humana, além dos disjuntores abertos. Sai mesmo sem canal configurado (só grava o Alerta).
"""

import collections
import datetime as dt

from django.core.management.base import BaseCommand, CommandError

from contabilidade_mensal.core.choices import StatusEtapa
from contabilidade_mensal.core.models import Competencia, Disjuntor, EtapaExecucao
from contabilidade_mensal.observability import alertas
from contabilidade_mensal.pipeline import servicos


class Command(BaseCommand):
    help = "Envia o resumo diário da competência."

    def add_arguments(self, parser):
        parser.add_argument("--competencia", default="auto")
        parser.add_argument("--hoje", help="AAAA-MM-DD (testes)")

    def handle(self, *args, **o):
        hoje = dt.date.fromisoformat(o["hoje"]) if o["hoje"] else dt.date.today()
        try:
            ano, mes = servicos.competencia_anterior(hoje) if o["competencia"] == "auto" else map(int, o["competencia"].split("-"))
        except ValueError as exc:
            raise CommandError("competência deve ser AAAA-MM ou 'auto'") from exc
        competencia = Competencia.objects.filter(ano=ano, mes=mes).first()
        if competencia is None:
            self.stdout.write(f"Competência {ano:04d}-{mes:02d}: nenhuma execução ainda.")
            return

        vigentes = list(servicos.matriz(competencia))
        contagem = collections.Counter(c["status"] or "sem execução" for linha in vigentes for c in linha["celulas"])
        falhas = [
            f"{linha['fundo'].nome}/{c['etapa']}: {c['erro'] or 'falha'}"
            for linha in vigentes
            for c in linha["celulas"]
            if c["status"] == StatusEtapa.FALHA
        ]
        aguardando = EtapaExecucao.objects.filter(
            execucao__competencia=competencia, status=StatusEtapa.AGUARDANDO_BRITECH
        ).count()
        abertos = list(Disjuntor.objects.filter(aberto_desde__isnull=False).values_list("chave", flat=True))

        linhas = [f"Competência {competencia.aaaamm}: " + ", ".join(f"{n} {s}" for s, n in sorted(contagem.items()))]
        if aguardando:
            linhas.append(f"{aguardando} etapa(s) aguardando a Britech/confirmação.")
        if abertos:
            linhas.append("Disjuntores abertos: " + ", ".join(abertos))
        if falhas:
            linhas.append("Falhas:\n- " + "\n- ".join(falhas[:20]) + (f"\n… e mais {len(falhas) - 20}" if len(falhas) > 20 else ""))
        texto = "\n".join(linhas)
        alertas.enviar(
            f"resumo:{competencia.aaaamm}:{hoje.isoformat()}",
            f"Resumo diário {competencia.aaaamm}",
            texto,
            severidade=alertas.AVISO if (falhas or abertos) else alertas.INFO,
            dedup_s=20 * 3600,
        )
        self.stdout.write(texto)
