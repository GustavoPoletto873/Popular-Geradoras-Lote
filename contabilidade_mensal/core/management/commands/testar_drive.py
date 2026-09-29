"""`python manage.py testar_drive --administradora "ID CORRETORA" --carteira 101 --competencia 2026-08 [--boleta arq.xlsb]`

Valida o `drive_api` com o Drive REAL sem alterar nada: resolve `Tipo/Fundo/Data Base X/AAAAMM` (sem criar pastas),
lista o conteúdo do destino e, com `--boleta`, diz o que a publicação faria (enviar / reaproveitar / conflito).
Variáveis: DRIVE_API_URL, DRIVE_API_TOKEN, DRIVE_RAIZ_ID (em homologação, uma pasta HOMOLOG).
"""

import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from contabilidade_mensal.core.models import Competencia, Fundo
from contabilidade_mensal.integrations.britech.erros import BritechErro
from contabilidade_mensal.integrations.drive.cliente import DriveApiCliente
from contabilidade_mensal.integrations.drive.publicador import PublicadorDrive, _e_planilha


class Command(BaseCommand):
    help = "Confere o drive_api e o caminho de publicação de um fundo, somente leitura."

    def add_arguments(self, parser):
        parser.add_argument("--administradora", required=True)
        parser.add_argument("--carteira", required=True)
        parser.add_argument("--competencia", required=True, help="AAAA-MM")
        parser.add_argument("--boleta", type=Path)

    def handle(self, *args, **o):
        try:
            fundo = Fundo.objects.get(administradora__nome=o["administradora"], codigo_britech=o["carteira"])
            ano, mes = (int(x) for x in o["competencia"].split("-"))
        except (Fundo.DoesNotExist, ValueError) as exc:
            raise CommandError("fundo não encontrado (rode sincronizar_cadastro) ou competência inválida (AAAA-MM)") from exc
        competencia = Competencia.objects.filter(ano=ano, mes=mes).first() or Competencia(ano=ano, mes=mes)
        try:
            cliente = DriveApiCliente(settings.DRIVE_API["url"] or "", os.environ.get("DRIVE_API_TOKEN", ""))
            publicador = PublicadorDrive(cliente, settings.DRIVE_API["raiz_id"] or "")
            pasta_id, caminho = publicador.resolver_pasta(fundo, competencia, criar=False)
            if pasta_id is None:
                self.stdout.write(f"  ✓ {caminho}: Tipo e Fundo existem; Data Base/AAAAMM seriam criadas na publicação")
            else:
                itens = cliente.listar(pasta_id)
                self.stdout.write(f"  ✓ {caminho} (id {pasta_id}): {len(itens)} item(ns), {sum(_e_planilha(i) for i in itens)} planilha(s)")
            if o["boleta"]:
                self.stdout.write(f"  → publicação faria: {publicador.prever(fundo, competencia, o['boleta']).acao}")
        except BritechErro as exc:
            raise CommandError(f"[{exc.codigo}] {exc}") from exc
