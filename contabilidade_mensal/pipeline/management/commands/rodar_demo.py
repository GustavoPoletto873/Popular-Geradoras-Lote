"""`python manage.py rodar_demo` — pipeline de brinquedo ponta a ponta, sem Britech, Excel ou Playwright.

Cria uma administradora e 3 fundos de mentira, injeta uma falha estrutural no 3º fundo
(tela da Britech "mudou" ao baixar o balancete) e mostra a matriz fundo × etapa.
Usa um relógio simulado: backoff e polling não esperam de verdade.
"""

import datetime as dt
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand

from contabilidade_mensal.core.choices import StatusEtapa
from contabilidade_mensal.core.models import Administradora, EtapaExecucao, Fundo
from contabilidade_mensal.integrations.britech.erros import TelaMudou
from contabilidade_mensal.integrations.britech.factory import OPERACOES, BritechGateway
from contabilidade_mensal.integrations.britech.fake import FakeBackend
from contabilidade_mensal.pipeline import fakes, servicos
from contabilidade_mensal.pipeline.definicao import FILAS, ORDEM
from contabilidade_mensal.pipeline.relogio import RelogioSimulado
from contabilidade_mensal.pipeline.worker import drenar


class Command(BaseCommand):
    help = "Roda o pipeline de brinquedo (backend fake) e imprime a matriz fundo x etapa."

    def add_arguments(self, parser):
        hoje = dt.date.today()
        anterior = hoje.replace(day=1) - dt.timedelta(days=1)
        parser.add_argument("--ano", type=int, default=anterior.year)
        parser.add_argument("--mes", type=int, default=anterior.month)

    def handle(self, *args, **opcoes):
        adm, _ = Administradora.objects.get_or_create(nome="DEMO ADMINISTRADORA", defaults={"url_adm": "demo"})
        fundos = []
        for i, sufixo in enumerate("ABC", start=1):
            fundo, _ = Fundo.objects.get_or_create(
                administradora=adm,
                codigo_britech=str(1000 + i),
                defaults={"nome": f"FII DEMO {sufixo}", "cnpj": f"{i:014d}", "tipo": "FII", "exercicio_mes": 12},
            )
            fundos.append(fundo)

        fake = FakeBackend()
        fake.programar("baixar_balancete", "1003", TelaMudou("botão de Excel não encontrado"))
        gateway = BritechGateway({"fake": fake}, {op: "fake" for op in OPERACOES})

        with tempfile.TemporaryDirectory(prefix="cm_demo_") as tmp:
            handlers = fakes.montar_handlers(gateway, Path(tmp))
            relogio = RelogioSimulado()
            competencia = servicos.obter_competencia(opcoes["ano"], opcoes["mes"])
            execucao = servicos.criar_execucao(competencia, fundos, disparada_por="rodar_demo", agora=relogio())
            executadas = drenar(FILAS, handlers, relogio)

        execucao.refresh_from_db()
        self.stdout.write(f"\nExecução {execucao.pk} — {competencia} — {executadas} etapa(s) rodadas — {execucao.status}\n")
        cabecalho = f"{'fundo':14}" + "".join(f"{e[:14]:16}" for e in ORDEM)
        self.stdout.write(cabecalho)
        for fundo in fundos:
            linha = f"{fundo.nome:14}"
            for etapa in ORDEM:
                status = EtapaExecucao.objects.get(execucao=execucao, fundo=fundo, etapa=etapa).status
                linha += f"{status:16}"
            self.stdout.write(linha)
        self.stdout.write(
            f"\nLegenda: {StatusEtapa.SUCESSO.value} ok · {StatusEtapa.FALHA.value} erro · "
            f"{StatusEtapa.PULADO.value} = dependência falhou ou já concluída"
        )
