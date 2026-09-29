"""`python manage.py sincronizar_cadastro [--dry-run]` — copia o cadastro de fundos do Monday para o banco."""

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from contabilidade_mensal.integrations.monday.cliente import ClienteMonday, ColunasMonday, ErroMonday
from contabilidade_mensal.integrations.monday.sincronizacao import sincronizar


class Command(BaseCommand):
    help = "Sincroniza os fundos do Monday (sistema Britech) com a tabela Fundo. Token em MONDAY_API_TOKEN."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="mostra o que faria e desfaz tudo")

    def handle(self, *args, **opcoes):
        try:
            cliente = ClienteMonday(os.environ.get("MONDAY_API_TOKEN", ""))
            registros = cliente.buscar_fundos(
                board_id=settings.MONDAY["board_id"],
                grupos=settings.MONDAY["grupos"],
                colunas=ColunasMonday(**settings.MONDAY["colunas"]),
            )
        except ErroMonday as exc:
            raise CommandError(str(exc)) from exc

        r = sincronizar(registros, dry_run=opcoes["dry_run"])
        prefixo = "[dry-run] " if opcoes["dry_run"] else ""
        self.stdout.write(
            f"{prefixo}{len(registros)} itens no Monday → {r.criados} criados, {r.atualizados} atualizados, "
            f"{r.sem_alteracao} sem alteração, {r.fora_do_sistema_britech} fora do sistema Britech."
        )
        if r.administradoras_fora_do_catalogo:
            self.stdout.write(f"Administradoras fora do catálogo (ignoradas): {sorted(r.administradoras_fora_do_catalogo)}")
        for titulo, itens in (("sem CNPJ válido", r.sem_cnpj_valido), ("sem mês de exercício", r.sem_exercicio), ("duplicados", r.duplicados)):
            if itens:
                self.stdout.write(f"Atenção — {len(itens)} fundo(s) {titulo}: {itens[:10]}{' …' if len(itens) > 10 else ''}")
