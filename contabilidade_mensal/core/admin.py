from django.contrib import admin
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from . import models


@admin.register(models.Administradora)
class AdministradoraAdmin(admin.ModelAdmin):
    list_display = ("nome", "url_adm", "max_sessoes", "ativa")


@admin.register(models.Fundo)
class FundoAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "administradora", "codigo_britech", "cnpj", "exercicio_mes", "ativo")
    list_filter = ("tipo", "administradora", "ativo")
    search_fields = ("nome", "cnpj", "codigo_britech")


@admin.register(models.Competencia)
class CompetenciaAdmin(admin.ModelAdmin):
    list_display = ("aaaamm", "status", "matriz_link")

    @admin.display(description="Matriz")
    def matriz_link(self, obj):
        return format_html('<a href="{}">fundo × etapa</a>', reverse("admin:core_competencia_matriz", args=[obj.pk]))

    def get_urls(self):
        return [
            path("<int:pk>/matriz/", self.admin_site.admin_view(self.matriz_view), name="core_competencia_matriz"),
            *super().get_urls(),
        ]

    def matriz_view(self, request, pk):
        from contabilidade_mensal.pipeline import servicos
        from contabilidade_mensal.pipeline.definicao import ORDEM

        competencia = get_object_or_404(models.Competencia, pk=pk)
        contexto = {
            **self.admin_site.each_context(request),
            "title": f"Matriz fundo × etapa — {competencia.aaaamm}",
            "competencia": competencia,
            "etapas": ORDEM,
            "linhas": servicos.matriz(competencia),
        }
        return TemplateResponse(request, "admin/core/matriz.html", contexto)


@admin.register(models.Execucao)
class ExecucaoAdmin(admin.ModelAdmin):
    list_display = ("id", "competencia", "disparada_por", "status", "forcar", "iniciada_em", "finalizada_em")
    list_filter = ("status", "competencia")
    readonly_fields = ("correlation_id",)


@admin.register(models.EtapaExecucao)
class EtapaExecucaoAdmin(admin.ModelAdmin):
    list_display = ("id", "execucao", "fundo", "etapa", "backend", "status", "tentativas", "erro_tipo", "disponivel_em")
    list_filter = ("status", "etapa", "backend", "fila")
    search_fields = ("fundo__nome", "erro_tipo")
    actions = ["reprocessar", "confirmar_processamento"]

    @admin.action(description="Reprocessar selecionadas (e o que depende delas)")
    def reprocessar(self, request, queryset):
        from contabilidade_mensal.pipeline import fila

        total = 0
        for etapa_exec in queryset:
            total += fila.reprocessar_etapa(etapa_exec, cascata=True)
        self.message_user(request, f"{total} etapa(s) voltaram para a fila.")

    @admin.action(description="Confirmar que a Britech terminou o processamento (etapas aguardando)")
    def confirmar_processamento(self, request, queryset):
        from contabilidade_mensal.pipeline import fila

        total = sum(fila.confirmar_processamento(e) for e in queryset)
        self.message_user(request, f"{total} etapa(s) confirmadas; serão consultadas na próxima rodada do worker.")


@admin.register(models.EstadoEtapa)
class EstadoEtapaAdmin(admin.ModelAdmin):
    list_display = ("fundo", "competencia", "etapa", "status", "atualizado_em")
    list_filter = ("status", "etapa", "competencia")


@admin.register(models.Artefato)
class ArtefatoAdmin(admin.ModelAdmin):
    list_display = ("tipo", "nome", "tamanho_bytes", "sha256", "drive_file_id", "verificado_em")
    list_filter = ("tipo",)
    search_fields = ("nome", "sha256")


@admin.register(models.PastaCompetencia)
class PastaCompetenciaAdmin(admin.ModelAdmin):
    list_display = ("fundo", "competencia", "drive_folder_id")


@admin.register(models.Disjuntor)
class DisjuntorAdmin(admin.ModelAdmin):
    list_display = ("chave", "aberto_desde", "falhas_consecutivas", "ultimo_erro_tipo", "proxima_tentativa_em")


@admin.register(models.TravaRecurso)
class TravaRecursoAdmin(admin.ModelAdmin):
    list_display = ("chave", "dono", "lease_ate")
