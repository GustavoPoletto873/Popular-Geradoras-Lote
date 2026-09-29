"""`python manage.py iniciar_execucao --competencia auto|AAAA-MM [opções]`

É o que o Agendador de Tarefas do Windows chama no início do mês (e todo dia até esgotar as pendências) e o que o
operador usa para reprocessar. Só CRIA a execução (linhas na fila); quem executa são os `run_worker`.

Idempotente com `--somente-pendentes` (padrão quando a competência é `auto`): fundos que já concluíram todas as
etapas pedidas, ou que já têm etapa em andamento, não entram numa nova execução.
"""

import argparse
import datetime as dt

from django.core.management.base import BaseCommand, CommandError

from contabilidade_mensal.core.choices import Etapa
from contabilidade_mensal.pipeline import servicos
from contabilidade_mensal.pipeline.definicao import ORDEM


class Command(BaseCommand):
    help = "Cria uma execução do pipeline para uma competência (idempotente com --somente-pendentes)."

    def add_arguments(self, parser):
        parser.add_argument("--competencia", required=True, help="AAAA-MM, ou 'auto' = mês anterior ao de hoje")
        parser.add_argument("--administradora", help="nome exato no cadastro, ex.: 'ID CORRETORA'")
        parser.add_argument("--fundos", nargs="*", help="códigos Britech (carteira) a incluir; padrão: todos os ativos")
        parser.add_argument("--etapas", nargs="*", choices=Etapa.values, help="padrão: todas")
        parser.add_argument("--forcar", action="store_true", help="ignora a idempotência nas etapas pedidas (reprocesso)")
        parser.add_argument("--cascata", action="store_true", help="refaz também o que depende das etapas pedidas")
        parser.add_argument("--somente-pendentes", action="store_true")
        parser.add_argument("--disparada-por", default="manual", help="rótulo gravado na execução (o Agendador usa 'agendador')")
        parser.add_argument("--dry-run", action="store_true", help="mostra o que criaria, sem criar")
        parser.add_argument("--hoje", help=argparse.SUPPRESS, default=None)  # só para testes

    def handle(self, *args, **o):
        hoje = dt.date.fromisoformat(o["hoje"]) if o["hoje"] else dt.date.today()
        auto = o["competencia"] == "auto"
        if auto:
            ano, mes = servicos.competencia_anterior(hoje)
        else:
            try:
                ano, mes = (int(x) for x in o["competencia"].split("-"))
                dt.date(ano, mes, 1)
            except ValueError as exc:
                raise CommandError("competência deve ser AAAA-MM ou 'auto'") from exc
        etapas = o["etapas"] or list(ORDEM)
        somente_pendentes = o["somente_pendentes"] or (auto and not o["forcar"])
        if o["forcar"] and somente_pendentes:
            raise CommandError("--forcar e --somente-pendentes se contradizem")

        aptos, incompletos = servicos.fundos_elegiveis(administradora=o["administradora"], codigos=o["fundos"])
        for fundo, motivo in incompletos:
            self.stdout.write(f"  ! ignorado: {fundo.nome} ({fundo.codigo_britech}) — cadastro incompleto: {motivo}")
        if o["fundos"]:
            faltando = sorted(set(map(str, o["fundos"])) - {f.codigo_britech for f in aptos} - {f.codigo_britech for f, _ in incompletos})
            if faltando:
                raise CommandError(f"fundos não encontrados/ativos: {faltando}")

        competencia = servicos.obter_competencia(ano, mes) if not o["dry_run"] else None
        if competencia is None:
            from contabilidade_mensal.core.models import Competencia

            competencia = Competencia.objects.filter(ano=ano, mes=mes).first() or Competencia(ano=ano, mes=mes)
        fundos = servicos.fundos_pendentes(competencia, aptos, etapas) if somente_pendentes and competencia.pk else aptos
        if not fundos:
            self.stdout.write(f"Competência {ano:04d}-{mes:02d}: nada a fazer ({len(aptos)} fundo(s) aptos, todos concluídos ou em andamento).")
            return
        if o["dry_run"]:
            self.stdout.write(f"[dry-run] criaria execução de {ano:04d}-{mes:02d} para {len(fundos)} fundo(s), etapas {etapas}:")
            for f in fundos:
                self.stdout.write(f"  - {f.nome} ({f.administradora.nome} / {f.codigo_britech})")
            return
        execucao = servicos.criar_execucao(
            competencia,
            fundos,
            etapas=etapas,
            disparada_por=o["disparada_por"],
            forcar=o["forcar"],
            cascata=o["cascata"],
        )
        self.stdout.write(
            f"Execução {execucao.pk} criada: competência {competencia}, {len(fundos)} fundo(s) × {len(etapas)} etapa(s), "
            f"correlation_id={execucao.correlation_id}"
        )

