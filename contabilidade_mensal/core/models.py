"""Modelos do domínio — ver docs/unificacao/05_arquitetura.md §3.

`EtapaExecucao` é ao mesmo tempo o registro de auditoria e a fila de trabalho.
`EstadoEtapa` é o snapshot vigente por (fundo, competência, etapa) e sustenta a
idempotência e o painel.
"""

from __future__ import annotations

import calendar
import datetime as dt
import uuid

from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

from .choices import (
    Backend,
    Etapa,
    StatusCompetencia,
    StatusEtapa,
    StatusExecucao,
    TipoArtefato,
    TipoFundo,
)


class Administradora(models.Model):
    """Administradora com login próprio na Britech. Guarda só a *referência* ao segredo."""

    nome = models.CharField(max_length=120, unique=True)
    url_adm = models.CharField(max_length=80, help_text="Subdomínio: https://<url_adm>.britech.com.br/PAS")
    segredo_ref = models.CharField(
        max_length=200, blank=True, help_text="Nome do segredo no cofre. Nunca o valor."
    )
    max_sessoes = models.PositiveSmallIntegerField(default=1)
    ativa = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.nome


class Fundo(models.Model):
    administradora = models.ForeignKey(Administradora, on_delete=models.PROTECT, related_name="fundos")
    codigo_britech = models.CharField(max_length=30, help_text="Id da carteira na Britech")
    cnpj = models.CharField(
        max_length=14, blank=True, db_index=True, validators=[RegexValidator(r"^\d{14}$", "14 dígitos")]
    )
    nome = models.CharField(max_length=200)
    tipo = models.CharField(max_length=10, choices=TipoFundo.choices, default=TipoFundo.OUTRO)
    exercicio_mes = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Mês de encerramento do exercício (define a pasta 'Data Base <mês> <ano>')",
    )
    pasta_drive_id = models.CharField(max_length=128, blank=True)
    monday_item_id = models.CharField(max_length=40, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["administradora", "codigo_britech"], name="uniq_fundo_adm_codigo")
        ]
        indexes = [models.Index(fields=["tipo"])]
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class Competencia(models.Model):
    ano = models.PositiveSmallIntegerField()
    mes = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    status = models.CharField(max_length=24, choices=StatusCompetencia.choices, default=StatusCompetencia.ABERTA)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["ano", "mes"], name="uniq_competencia_ano_mes")]
        ordering = ["-ano", "-mes"]

    @property
    def aaaamm(self) -> str:
        return f"{self.ano:04d}{self.mes:02d}"

    @property
    def data_base(self) -> dt.date:
        return dt.date(self.ano, self.mes, calendar.monthrange(self.ano, self.mes)[1])

    def __str__(self) -> str:
        return self.aaaamm


class Execucao(models.Model):
    competencia = models.ForeignKey(Competencia, on_delete=models.PROTECT, related_name="execucoes")
    disparada_por = models.CharField(max_length=120, default="manual")
    escopo = models.JSONField(default=dict, blank=True)
    forcar = models.BooleanField(default=False)
    cascata = models.BooleanField(default=False)
    iniciada_em = models.DateTimeField(default=timezone.now)
    finalizada_em = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=24, choices=StatusExecucao.choices, default=StatusExecucao.EM_ANDAMENTO)
    correlation_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["competencia", "iniciada_em"])]
        ordering = ["-iniciada_em"]

    def __str__(self) -> str:
        return f"Execucao {self.pk} ({self.competencia})"


class EtapaExecucao(models.Model):
    execucao = models.ForeignKey(Execucao, on_delete=models.CASCADE, related_name="etapas")
    fundo = models.ForeignKey(Fundo, on_delete=models.PROTECT, related_name="etapas")
    etapa = models.CharField(max_length=24, choices=Etapa.choices)
    fila = models.CharField(max_length=20, help_text="api | browser | excel | drive")
    backend = models.CharField(max_length=10, choices=Backend.choices)
    status = models.CharField(max_length=20, choices=StatusEtapa.choices, default=StatusEtapa.PENDENTE)
    tentativas = models.PositiveSmallIntegerField(default=0)
    max_tentativas = models.PositiveSmallIntegerField(default=3)
    forcar = models.BooleanField(default=False, help_text="Ignora a idempotência (reprocesso)")
    erro_tipo = models.CharField(max_length=60, blank=True)
    erro_msg = models.TextField(blank=True)
    iniciado_em = models.DateTimeField(null=True, blank=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)
    duracao_ms = models.PositiveIntegerField(null=True, blank=True)
    disponivel_em = models.DateTimeField(default=timezone.now)
    lock_key = models.CharField(max_length=120, blank=True)
    worker_id = models.CharField(max_length=120, blank=True)
    lease_ate = models.DateTimeField(null=True, blank=True)
    aguardando_desde = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["execucao", "fundo", "etapa"], name="uniq_etapa_por_execucao_fundo")
        ]
        indexes = [
            models.Index(fields=["fila", "status", "disponivel_em"]),
            models.Index(fields=["status", "disponivel_em"]),
            models.Index(fields=["lock_key", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.etapa} / {self.fundo_id} / {self.status}"


class EstadoEtapa(models.Model):
    fundo = models.ForeignKey(Fundo, on_delete=models.CASCADE, related_name="estados")
    competencia = models.ForeignKey(Competencia, on_delete=models.CASCADE, related_name="estados")
    etapa = models.CharField(max_length=24, choices=Etapa.choices)
    status = models.CharField(max_length=20, choices=StatusEtapa.choices)
    ultima_etapa_execucao = models.ForeignKey(
        EtapaExecucao, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["fundo", "competencia", "etapa"], name="uniq_estado_fundo_comp_etapa")
        ]


class Artefato(models.Model):
    etapa_execucao = models.ForeignKey(EtapaExecucao, on_delete=models.CASCADE, related_name="artefatos")
    tipo = models.CharField(max_length=40, choices=TipoArtefato.choices)
    nome = models.CharField(max_length=300)
    caminho_local = models.CharField(max_length=600, blank=True)
    sha256 = models.CharField(max_length=64)
    tamanho_bytes = models.BigIntegerField()
    drive_file_id = models.CharField(max_length=128, blank=True)
    drive_checksum = models.CharField(max_length=64, blank=True)
    verificado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["sha256"]), models.Index(fields=["etapa_execucao", "tipo"])]

    def __str__(self) -> str:
        return f"{self.tipo}: {self.nome}"


class PastaCompetencia(models.Model):
    """Cache da pasta `Tipo/Fundo/Data Base X/AAAAMM` no Drive."""

    fundo = models.ForeignKey(Fundo, on_delete=models.CASCADE, related_name="pastas")
    competencia = models.ForeignKey(Competencia, on_delete=models.CASCADE, related_name="pastas")
    drive_folder_id = models.CharField(max_length=128)
    caminho_relativo = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["fundo", "competencia"], name="uniq_pasta_fundo_competencia")
        ]


class Disjuntor(models.Model):
    """Circuit breaker por `etapa:backend:administradora`."""

    chave = models.CharField(max_length=200, unique=True)
    aberto_desde = models.DateTimeField(null=True, blank=True)
    motivo = models.TextField(blank=True)
    falhas_consecutivas = models.PositiveIntegerField(default=0)
    ultimo_erro_tipo = models.CharField(max_length=60, blank=True)
    proxima_tentativa_em = models.DateTimeField(null=True, blank=True)
    reaberto_por = models.CharField(max_length=120, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    @property
    def aberto(self) -> bool:
        return self.aberto_desde is not None

    def __str__(self) -> str:
        return f"{self.chave} ({'aberto' if self.aberto else 'fechado'})"


class TravaRecurso(models.Model):
    """Exclusão mútua com lease (ex.: 1 sessão por credencial na Britech)."""

    chave = models.CharField(max_length=200, unique=True)
    dono = models.CharField(max_length=120)
    lease_ate = models.DateTimeField()
    adquirida_em = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return f"{self.chave} -> {self.dono}"


class Alerta(models.Model):
    """Todo alerta gerado (enviado ou não): auditoria e painel. Repetições dentro da janela só incrementam `repeticoes`."""

    chave = models.CharField(max_length=160, db_index=True)
    severidade = models.CharField(max_length=10, default="aviso")
    titulo = models.CharField(max_length=250)
    corpo = models.TextField(blank=True)
    criado_em = models.DateTimeField(default=timezone.now)
    canais = models.CharField(max_length=40, blank=True, help_text="canais configurados quando foi gerado")
    enviado_em = models.DateTimeField(null=True, blank=True)
    erro_envio = models.TextField(blank=True)
    repeticoes = models.PositiveIntegerField(default=0, help_text="ocorrências suprimidas por duplicidade")

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self) -> str:
        return self.titulo
