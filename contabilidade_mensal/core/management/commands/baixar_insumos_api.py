"""`python manage.py baixar_insumos_api --administradora "ID CORRETORA" --carteira 44680491 --ano 2026 --mes 8 --destino C:\\tmp\\api`

Baixa os insumos de UM fundo pelo backend `api` (Britech WS/api) e imprime o que gerou (com SHA-256). Só lê da Britech.
É o jeito de validar com dados reais antes de ligar o pipeline: depois rode `comparar_insumos` contra a pasta do Simplifica.

Credenciais: variáveis `BRITECH_<segredo_ref>_USER` / `_SENHA` (ex.: BRITECH_ID_CORRETORA_USER). Rode antes
`sincronizar_cadastro` para o fundo existir no banco (com CNPJ e mês do exercício).
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from contabilidade_mensal.core.models import Fundo
from contabilidade_mensal.integrations.britech.api_backend.backend import ApiBackend
from contabilidade_mensal.integrations.britech.api_backend.credenciais import CredenciaisDoAmbiente
from contabilidade_mensal.integrations.britech.erros import BritechErro
from contabilidade_mensal.integrations.britech.interface import (
    INSUMOS_DO_LOTE,
    AdministradoraRef,
    CarteiraRef,
    CompetenciaRef,
    TipoInsumo,
)
from contabilidade_mensal.storage.hashing import descrever


def criar_backend() -> ApiBackend:  # ponto de troca para os testes
    return ApiBackend(CredenciaisDoAmbiente())


class Command(BaseCommand):
    help = "Baixa os insumos de um fundo pelo backend API da Britech (somente leitura)."

    def add_arguments(self, parser):
        parser.add_argument("--administradora", required=True)
        parser.add_argument("--carteira", required=True, help="id da carteira na Britech (Fundo.codigo_britech)")
        parser.add_argument("--ano", required=True, type=int)
        parser.add_argument("--mes", required=True, type=int)
        parser.add_argument("--destino", required=True, type=Path)
        parser.add_argument(
            "--tipos", nargs="*", choices=[t.value for t in TipoInsumo], help="padrão: todos os insumos do lote"
        )

    def handle(self, *args, **opcoes):
        try:
            fundo = Fundo.objects.select_related("administradora").get(
                administradora__nome=opcoes["administradora"], codigo_britech=opcoes["carteira"]
            )
        except Fundo.DoesNotExist as exc:
            raise CommandError("fundo não encontrado no banco; rode antes `sincronizar_cadastro`") from exc

        tipos = [TipoInsumo(v) for v in opcoes["tipos"]] if opcoes["tipos"] else list(INSUMOS_DO_LOTE)
        adm = fundo.administradora
        carteira = CarteiraRef(fundo.codigo_britech, fundo.cnpj, fundo.nome, fundo.exercicio_mes)
        competencia = CompetenciaRef(opcoes["ano"], opcoes["mes"])
        backend = criar_backend()

        falhas = 0
        try:
            sessao = backend.abrir_sessao(AdministradoraRef(adm.nome, adm.url_adm, adm.segredo_ref))
        except BritechErro as exc:
            raise CommandError(f"[{exc.codigo}] {exc}") from exc
        try:
            for tipo in tipos:
                try:
                    r = backend.baixar_insumo(sessao, carteira, competencia, tipo, opcoes["destino"])
                except BritechErro as exc:
                    falhas += 1
                    self.stderr.write(f"  ✗ {tipo.value}: [{exc.codigo}] {exc}")
                    continue
                for arquivo in (r, *r.complementos):
                    sha, tamanho = descrever(arquivo.caminho)
                    self.stdout.write(f"  ✓ {arquivo.caminho.name}  {tamanho} bytes  sha256={sha[:16]}…")
        finally:
            sessao.fechar()

        if falhas:
            raise CommandError(f"{falhas} insumo(s) falharam")
        self.stdout.write(f"Arquivos em {opcoes['destino']}. Compare com: manage.py comparar_insumos --a <esta pasta> --b <Insumos do Simplifica>")
