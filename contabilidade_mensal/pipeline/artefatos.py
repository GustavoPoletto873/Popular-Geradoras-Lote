"""Consulta de artefatos vigentes e verificação de integridade (base da idempotência)."""

from __future__ import annotations

from pathlib import Path

from contabilidade_mensal.core.choices import StatusEtapa
from contabilidade_mensal.core.models import Artefato, EstadoEtapa
from contabilidade_mensal.storage.hashing import sha256_arquivo


def estado_vigente(fundo_id: int, competencia_id: int, etapa: str) -> EstadoEtapa | None:
    return (
        EstadoEtapa.objects.select_related("ultima_etapa_execucao")
        .filter(fundo_id=fundo_id, competencia_id=competencia_id, etapa=etapa)
        .first()
    )


def artefatos_vigentes(fundo_id: int, competencia_id: int, etapa: str) -> list[Artefato]:
    """Artefatos da última execução bem-sucedida da etapa (vazio se não houver)."""
    estado = estado_vigente(fundo_id, competencia_id, etapa)
    if estado is None or estado.status != StatusEtapa.SUCESSO or estado.ultima_etapa_execucao is None:
        return []
    return list(estado.ultima_etapa_execucao.artefatos.all())


def artefato_integro(artefato: Artefato) -> bool:
    """Íntegro se já foi verificado no Drive OU o arquivo local existe com o mesmo sha256."""
    if artefato.drive_file_id and artefato.verificado_em:
        return True
    if artefato.caminho_local:
        caminho = Path(artefato.caminho_local)
        return caminho.is_file() and sha256_arquivo(caminho) == artefato.sha256
    return False


def etapa_ja_concluida(fundo_id: int, competencia_id: int, etapa: str) -> bool:
    """A etapa já foi concluída com sucesso e todos os seus artefatos continuam íntegros?"""
    estado = estado_vigente(fundo_id, competencia_id, etapa)
    if estado is None or estado.status != StatusEtapa.SUCESSO or estado.ultima_etapa_execucao is None:
        return False
    return all(artefato_integro(a) for a in estado.ultima_etapa_execucao.artefatos.all())
