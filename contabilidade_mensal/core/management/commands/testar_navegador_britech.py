"""`python manage.py testar_navegador_britech --administradora "ID CORRETORA" [--repeticoes 20] [--headed]`

Critério de pronto da Fase 3, com a Britech REAL: login, abre Processo Contábil e Balancete, logout confirmado, N vezes,
sem deixar sessão presa. Não seleciona carteira e NÃO clica em "Processar". Credenciais: BRITECH_<REF>_USER/_SENHA.
Falhas deixam screenshot e trace em BROWSER_EVIDENCIAS (dados sensíveis: não compartilhe).
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from contabilidade_mensal.core.administradoras import CATALOGO
from contabilidade_mensal.integrations.britech.api_backend.credenciais import CredenciaisDoAmbiente
from contabilidade_mensal.integrations.britech.browser_backend.backend import BrowserBackend
from contabilidade_mensal.integrations.britech.browser_backend.config import ConfigNavegador
from contabilidade_mensal.integrations.britech.browser_backend.diagnostico import verificar_sessao
from contabilidade_mensal.integrations.britech.erros import BritechErro
from contabilidade_mensal.integrations.britech.interface import AdministradoraRef


class Command(BaseCommand):
    help = "Verifica login, abertura das telas e logout confirmado na Britech real (somente leitura)."

    def add_arguments(self, parser):
        parser.add_argument("--administradora", required=True, help="nome do catálogo, ex.: 'ID CORRETORA'")
        parser.add_argument("--repeticoes", type=int, default=1)
        parser.add_argument("--headed", action="store_true", help="abre o navegador visível")

    def handle(self, *args, **opcoes):
        catalogo = {nome: (url_adm, ref) for nome, url_adm, ref in CATALOGO}
        if opcoes["administradora"] not in catalogo:
            raise CommandError(f"administradora fora do catálogo: {sorted(catalogo)}")
        url_adm, ref = catalogo[opcoes["administradora"]]
        config = ConfigNavegador(
            headless=not opcoes["headed"] and settings.BROWSER["headless"],
            timeout_ms=settings.BROWSER["timeout_ms"],
            pasta_evidencias=settings.BROWSER["pasta_evidencias"],
        )
        backend = BrowserBackend(CredenciaisDoAmbiente(), config)
        try:
            resultados = verificar_sessao(
                backend,
                AdministradoraRef(opcoes["administradora"], url_adm, ref),
                repeticoes=opcoes["repeticoes"],
                timeout_ms=config.timeout_ms,
            )
        except BritechErro as exc:
            raise CommandError(f"[{exc.codigo}] {exc}. Evidências (se houver) em {config.pasta_evidencias}") from exc
        for r in resultados:
            self.stdout.write(f"  ✓ repetição {r.numero}: login, telas e logout confirmados em {r.segundos}s")
        self.stdout.write(f"{len(resultados)} repetição(ões) sem sessão presa.")
