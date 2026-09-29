from io import StringIO

import pytest
from django.core.management import call_command

from contabilidade_mensal.core.choices import Etapa
from contabilidade_mensal.core.models import TravaRecurso
from contabilidade_mensal.pipeline import fila, servicos, watchdog


def proc(pid, nome, exe="", cmd=(), criado=0.0):
    return {"pid": pid, "name": nome, "exe": exe, "cmdline": list(cmd), "create_time": criado}


AGORA = 10_000.0
PROCESSOS = [
    proc(1, "EXCEL.EXE", cmd=["C:\\Office\\EXCEL.EXE", "/automation", "-Embedding"], criado=AGORA - 2000),  # órfão de automação
    proc(2, "EXCEL.EXE", cmd=["C:\\Office\\EXCEL.EXE", "C:\\planilha.xlsx"], criado=AGORA - 9000),  # Excel do usuário
    proc(3, "chrome.exe", exe="C:\\Users\\x\\AppData\\Local\\ms-playwright\\chromium-1243\\chrome-win\\chrome.exe", criado=AGORA - 3000),
    proc(4, "chrome.exe", exe="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", criado=AGORA - 9000),  # Chrome do usuário
    proc(5, "EXCEL.EXE", cmd=["EXCEL.EXE", "/Automation", "-Embedding"], criado=AGORA - 10),  # novo demais
]


_LISTAR_ORIGINAL = watchdog.listar_processos


def listar():
    return _LISTAR_ORIGINAL(lambda: PROCESSOS, agora=AGORA)


def test_so_reconhece_o_que_e_inequivocamente_nosso():
    assert {(p.pid, p.tipo) for p in listar()} == {(1, "excel"), (3, "chromium"), (5, "excel")}


def test_orfao_exige_idade_minima(db):
    assert {p.pid for p in watchdog.orfaos(listar(), idade_min_s=900)} == {1, 3}


def test_com_etapa_excel_em_andamento_o_excel_nao_e_orfao(criar_fundo, competencia, relogio, db):
    fundo = criar_fundo(1)
    servicos.criar_execucao(competencia, [fundo], etapas=[Etapa.BAIXAR_INSUMOS, Etapa.POPULAR_EXCEL], agora=relogio())
    from contabilidade_mensal.core.models import EtapaExecucao

    EtapaExecucao.objects.filter(etapa=Etapa.POPULAR_EXCEL).update(status="em_andamento")
    assert {p.pid for p in watchdog.orfaos(listar(), idade_min_s=900)} == {3}  # o chromium ainda é órfão


def test_encerrar_devolve_os_pids_e_tolera_falha():
    mortos = []

    def matar(pid):
        if pid == 3:
            raise PermissionError("negado")
        mortos.append(pid)

    assert watchdog.encerrar(listar(), matar=matar) == [1, 5] and mortos == [1, 5]


def test_travas_vencidas_sao_removidas(db):
    import datetime as dt

    from django.utils import timezone

    agora = timezone.now()
    TravaRecurso.objects.create(chave="a", dono="w", lease_ate=agora - dt.timedelta(minutes=1), adquirida_em=agora)
    TravaRecurso.objects.create(chave="b", dono="w", lease_ate=agora + dt.timedelta(minutes=5), adquirida_em=agora)
    assert watchdog.limpar_travas_vencidas() == 1 and list(TravaRecurso.objects.values_list("chave", flat=True)) == ["b"]


def test_comando_sem_matar_so_relata(monkeypatch, db):
    monkeypatch.setattr(watchdog, "listar_processos", listar)
    matou = []
    monkeypatch.setattr(watchdog, "encerrar", lambda ps, matar=None: matou.append(ps) or [p.pid for p in ps])
    saida = StringIO()
    call_command("limpar_orfaos", stdout=saida)
    assert "órfão: pid 1" in saida.getvalue() and "--matar" in saida.getvalue() and matou == []
    call_command("limpar_orfaos", matar=True, stdout=StringIO())
    assert len(matou) == 1


def test_comando_devolve_etapa_orfa_a_fila(criar_fundo, competencia, relogio, db, monkeypatch):
    import datetime as dt

    monkeypatch.setattr(watchdog, "listar_processos", lambda: [])
    fundo = criar_fundo(1)
    servicos.criar_execucao(competencia, [fundo], etapas=[Etapa.BAIXAR_INSUMOS])
    etapa = fila.reivindicar("api", "morto", limite=1)[0]
    from contabilidade_mensal.core.models import EtapaExecucao
    from django.utils import timezone

    EtapaExecucao.objects.filter(pk=etapa.pk).update(lease_ate=timezone.now() - dt.timedelta(seconds=1))
    saida = StringIO()
    call_command("limpar_orfaos", stdout=saida)
    assert "1 etapa(s) órfã(s)" in saida.getvalue() and EtapaExecucao.objects.get(pk=etapa.pk).status == "pendente"
