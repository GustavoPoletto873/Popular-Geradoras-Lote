import datetime as dt

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction

from contabilidade_mensal.core.models import Competencia, Execucao, EtapaExecucao, Fundo


def test_migracoes_estao_em_dia(db):
    """Falha se alguém mudar um modelo sem gerar a migração."""
    call_command("makemigrations", "--check", "--dry-run", verbosity=0)


def test_competencia_datas(db):
    c = Competencia.objects.create(ano=2028, mes=2)
    assert c.aaaamm == "202802"
    assert c.data_base == dt.date(2028, 2, 29)  # ano bissexto
    assert Competencia(ano=2026, mes=8).data_base == dt.date(2026, 8, 31)


def test_competencia_unica_por_ano_mes(db):
    Competencia.objects.create(ano=2026, mes=8)
    with pytest.raises(IntegrityError), transaction.atomic():
        Competencia.objects.create(ano=2026, mes=8)


def test_fundo_unico_por_administradora_e_codigo(criar_fundo):
    criar_fundo(1001)
    with pytest.raises(IntegrityError), transaction.atomic():
        criar_fundo(1001, nome="OUTRO NOME", cnpj="99999999999999")


def test_mesmo_codigo_em_administradoras_diferentes_e_permitido(criar_fundo, administradora):
    from contabilidade_mensal.core.models import Administradora

    outra = Administradora.objects.create(nome="OUTRA", url_adm="outra")
    criar_fundo(1001)
    criar_fundo(1001, administradora=outra, cnpj="11111111111111")
    assert Fundo.objects.filter(codigo_britech="1001").count() == 2


def test_etapa_unica_por_execucao_fundo_etapa(criar_fundo, competencia):
    fundo = criar_fundo(1001)
    execucao = Execucao.objects.create(competencia=competencia)
    EtapaExecucao.objects.create(execucao=execucao, fundo=fundo, etapa="baixar_insumos", fila="api", backend="fake")
    with pytest.raises(IntegrityError), transaction.atomic():
        EtapaExecucao.objects.create(execucao=execucao, fundo=fundo, etapa="baixar_insumos", fila="api", backend="fake")
