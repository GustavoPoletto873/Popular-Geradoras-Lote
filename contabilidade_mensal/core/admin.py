from django.contrib import admin

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
    list_display = ("aaaamm", "status")


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
    actions = ["reprocessar"]

    @admin.action(description="Reprocessar selecionadas (e o que depende delas)")
    def reprocessar(self, request, queryset):
        from contabilidade_mensal.pipeline import fila

        total = 0
        for etapa_exec in queryset:
            total += fila.reprocessar_etapa(etapa_exec, cascata=True)
        self.message_user(request, f"{total} etapa(s) voltaram para a fila.")


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
