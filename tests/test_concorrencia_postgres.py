"""Concorrência real: várias threads/conexões disputando a mesma fila e a mesma trava.

Só roda em Postgres (marcador `postgres`). Para executar localmente:

    docker run -d --name cm-pg -e POSTGRES_PASSWORD=cm -e POSTGRES_DB=cm_test -p 5433:5432 postgres:16
    set DB_ENGINE=postgres&& set DB_NAME=cm_test&& set DB_USER=postgres&& set DB_PASSWORD=cm&& set DB_HOST=localhost&& set DB_PORT=5433
    python -m pytest tests/test_concorrencia_postgres.py -v
"""

import datetime as dt
import threading

import pytest
from django.db import connection

from contabilidade_mensal.core.models import Administradora, Competencia, EtapaExecucao, Fundo
from contabilidade_mensal.pipeline import fila, servicos, travas

pytestmark = [pytest.mark.postgres, pytest.mark.django_db(transaction=True)]

AGORA = dt.datetime(2026, 9, 1, 8, 0, tzinfo=dt.timezone.utc)


def _em_threads(alvo, quantidade):
    resultados, erros = [], []
    barreira = threading.Barrier(quantidade)

    def rodar(i):
        try:
            barreira.wait()
            resultados.append(alvo(i))
        except Exception as exc:  # noqa: BLE001
            erros.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=rodar, args=(i,)) for i in range(quantidade)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not erros, erros
    return resultados


def test_cada_etapa_e_reivindicada_por_exatamente_um_worker():
    adm = Administradora.objects.create(nome="ADM", url_adm="adm")
    fundos = [
        Fundo.objects.create(administradora=adm, codigo_britech=str(i), nome=f"F{i}", cnpj=f"{i:014d}")
        for i in range(1, 31)
    ]
    comp = Competencia.objects.create(ano=2026, mes=8)
    servicos.criar_execucao(comp, fundos, etapas=["baixar_insumos"], agora=AGORA)

    def worker(i):
        pegas = []
        while True:
            lote = fila.reivindicar("api", f"w{i}", limite=1, agora=AGORA)
            if not lote:
                return pegas
            pegas.extend(e.pk for e in lote)

    todas = [pk for pegas in _em_threads(worker, 8) for pk in pegas]
    assert len(todas) == 30 and len(set(todas)) == 30  # nenhuma etapa reivindicada duas vezes
    assert EtapaExecucao.objects.filter(status="em_andamento").count() == 30


def test_so_um_worker_leva_a_trava_da_credencial():
    ganhadores = _em_threads(lambda i: travas.adquirir("britech:1", f"w{i}", lease_s=60, agora=AGORA), 8)
    assert sum(ganhadores) == 1
