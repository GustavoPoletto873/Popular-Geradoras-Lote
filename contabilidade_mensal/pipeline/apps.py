from django.apps import AppConfig


class PipelineConfig(AppConfig):
    name = "contabilidade_mensal.pipeline"
    label = "pipeline"
    verbose_name = "Contabilidade mensal — pipeline"
