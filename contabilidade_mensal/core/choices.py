"""Enumerações do domínio (valores gravados no banco — não renomear sem migração)."""

from django.db import models


class Etapa(models.TextChoices):
    BAIXAR_INSUMOS = "baixar_insumos", "Baixar insumos"
    PROCESSAR_CONTABIL = "processar_contabil", "Processar Contábil"
    BAIXAR_BALANCETE = "baixar_balancete", "Baixar balancete"
    POPULAR_EXCEL = "popular_excel", "Popular Excel"
    PUBLICAR_DRIVE = "publicar_drive", "Publicar no Drive"


class StatusEtapa(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    EM_ANDAMENTO = "em_andamento", "Em andamento"
    SUCESSO = "sucesso", "Sucesso"
    FALHA = "falha", "Falha"
    AGUARDANDO_BRITECH = "aguardando_britech", "Aguardando Britech"
    PULADO = "pulado", "Pulado"


class StatusExecucao(models.TextChoices):
    EM_ANDAMENTO = "em_andamento", "Em andamento"
    CONCLUIDA = "concluida", "Concluída"
    CONCLUIDA_COM_FALHAS = "concluida_com_falhas", "Concluída com falhas"


class StatusCompetencia(models.TextChoices):
    ABERTA = "aberta", "Aberta"
    EM_EXECUCAO = "em_execucao", "Em execução"
    CONCLUIDA = "concluida", "Concluída"
    CONCLUIDA_COM_FALHAS = "concluida_com_falhas", "Concluída com falhas"


class TipoFundo(models.TextChoices):
    FIF = "FIF", "FIF"
    FIDC = "FIDC", "FIDC"
    FII = "FII", "FII"
    FIP = "FIP", "FIP"
    FIAGRO = "FIAGRO", "FIAGRO"
    FUNCINE = "FUNCINE", "FUNCINE"
    OUTRO = "OUTRO", "Outro"


class Backend(models.TextChoices):
    API = "api", "API"
    BROWSER = "browser", "Navegador (Playwright)"
    EXCEL = "excel", "Excel (COM)"
    DRIVE = "drive", "Drive"
    FAKE = "fake", "Fake (testes)"


class TipoArtefato(models.TextChoices):
    INSUMO_CARTEIRA_FINAL = "insumo_carteira_final", "Insumo: carteira final"
    INSUMO_CARTEIRA_INICIAL = "insumo_carteira_inicial", "Insumo: carteira inicial"
    INSUMO_EXTRATO_CC = "insumo_extrato_cc", "Insumo: extrato conta corrente"
    INSUMO_MOV_COTISTA = "insumo_mov_cotista", "Insumo: movimentação de cotistas"
    INSUMO_POSICAO_COTISTA_FINAL = "insumo_posicao_cotista_final", "Insumo: posição de cotistas (final)"
    INSUMO_POSICAO_COTISTA_INICIAL = "insumo_posicao_cotista_inicial", "Insumo: posição de cotistas (inicial)"
    INSUMO_HISTORICO_COTA = "insumo_historico_cota", "Insumo: histórico de cota"
    INSUMO_PDF = "insumo_pdf", "Insumo: PDF de evidência"
    BALANCETE_PDF = "balancete_pdf", "Balancete (PDF)"
    BALANCETE_XLS = "balancete_xls", "Balancete (Excel)"
    BOLETA = "boleta", "Boleta populada"
    SCREENSHOT = "screenshot", "Screenshot de falha"
    TRACE = "trace", "Trace do Playwright"
    LOG = "log", "Log"
