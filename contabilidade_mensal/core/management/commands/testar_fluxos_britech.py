"""`python manage.py testar_fluxos_britech --administradora "ID CORRETORA" --carteira 101 --cnpj 12345678000190 --ano 2026 --mes 8 --destino C:\\tmp\\bal --selecionar --balancete`

Valida os fluxos do navegador na Britech REAL sem alterar nada:
  --selecionar  entra no Processo Contábil e seleciona a carteira (DRY-RUN: o "Processar" NUNCA é clicado aqui);
  --balancete   baixa o PDF e o Excel do balancete da competência (leitura).
O clique real em "Processar" só existe pelo pipeline, com dry-run desligado e a carteira na allowlist.
Credenciais: BRITECH_<REF>_USER / _SENHA.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from contabilidade_mensal.core.administradoras import CATALOGO
from contabilidade_mensal.integrations.britech.api_backend.credenciais import CredenciaisDoAmbiente
from contabilidade_mensal.integrations.britech.browser_backend.backend import BrowserBackend
from contabilidade_mensal.integrations.britech.browser_backend.config import ConfigNavegador
from contabilidade_mensal.integrations.britech.erros import BritechErro
from contabilidade_mensal.integrations.britech.interface import AdministradoraRef, CarteiraRef, CompetenciaRef
from contabilidade_mensal.storage.hashing import descrever


class Command(BaseCommand):
    help = "Valida seleção (dry-run) e balancete na Britech real, sem processar nada."

    def add_arguments(self, parser):
        parser.add_argument("--administradora", required=True)
        parser.add_argument("--carteira", required=True, help="id da carteira na Britech")
        parser.add_argument("--cnpj", default="", help="só dígitos; necessário para nomear o balancete")
        parser.add_argument("--ano", type=int, required=True)
        parser.add_argument("--mes", type=int, required=True)
        parser.add_argument("--destino", type=Path)
        parser.add_argument("--selecionar", action="store_true")
        parser.add_argument("--balancete", action="store_true")
        parser.add_argument("--headed", action="store_true")

    def handle(self, *args, **o):
        if not (o["selecionar"] or o["balancete"]):
            raise CommandError("escolha --selecionar e/ou --balancete")
        if o["balancete"] and not (o["destino"] and o["cnpj"]):
            raise CommandError("--balancete exige --destino e --cnpj")
        catalogo = {nome: (url, ref) for nome, url, ref in CATALOGO}
        if o["administradora"] not in catalogo:
            raise CommandError(f"administradora fora do catálogo: {sorted(catalogo)}")
        url_adm, ref = catalogo[o["administradora"]]
        config = ConfigNavegador(
            headless=not o["headed"] and settings.BROWSER["headless"],
            timeout_ms=settings.BROWSER["timeout_ms"],
            pasta_evidencias=settings.BROWSER["pasta_evidencias"],
        )
        backend = BrowserBackend(CredenciaisDoAmbiente(), config, allowlist_processar=())  # allowlist vazia: nunca clica
        carteira = CarteiraRef(o["carteira"], o["cnpj"])
        competencia = CompetenciaRef(o["ano"], o["mes"])
        try:
            sessao = backend.abrir_sessao(AdministradoraRef(o["administradora"], url_adm, ref))
            try:
                if o["selecionar"]:
                    r = backend.processar_contabil(sessao, [carteira], competencia, dry_run=True)
                    self.stdout.write(f"  ✓ carteira {o['carteira']} selecionada (dry-run={r.dry_run}; Processar NÃO clicado)")
                if o["balancete"]:
                    b = backend.baixar_balancete(sessao, carteira, competencia, o["destino"])
                    for arquivo in (b.pdf, b.xls):
                        sha, tamanho = descrever(arquivo)
                        self.stdout.write(f"  ✓ {arquivo.name}  {tamanho} bytes  sha256={sha[:16]}…")
            finally:
                sessao.fechar()
        except BritechErro as exc:
            raise CommandError(f"[{exc.codigo}] {exc}. Evidências (se houver) em {config.pasta_evidencias}") from exc
        self.stdout.write("Sessão encerrada com logout confirmado.")
