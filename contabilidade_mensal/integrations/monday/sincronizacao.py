"""Sincroniza o cadastro do Monday para `Fundo` (o Monday é a fonte mestre; o banco é uma cópia operacional).

Regras (as do projeto do Lucas): só entram itens do sistema "Britech" com id de carteira preenchido, e a
administradora precisa estar no catálogo (`core/administradoras.py`). Campos que o Monday deixar em branco
NÃO apagam o que já existe no banco.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from django.db import transaction

from contabilidade_mensal.core.administradoras import garantir_administradora
from contabilidade_mensal.core.choices import TipoFundo
from contabilidade_mensal.core.models import Fundo
from contabilidade_mensal.integrations.britech.api_backend.cadastro import normalizar_cnpj

from .cliente import RegistroMonday


@dataclass
class ResumoSincronizacao:
    criados: int = 0
    atualizados: int = 0
    sem_alteracao: int = 0
    fora_do_sistema_britech: int = 0
    administradoras_fora_do_catalogo: set[str] = field(default_factory=set)
    sem_cnpj_valido: list[str] = field(default_factory=list)
    sem_exercicio: list[str] = field(default_factory=list)
    duplicados: list[str] = field(default_factory=list)

    @property
    def total_processados(self) -> int:
        return self.criados + self.atualizados + self.sem_alteracao


def _tipo(valor: str) -> str:
    return valor if valor in TipoFundo.values else TipoFundo.OUTRO


def sincronizar(
    registros: Iterable[RegistroMonday], *, dry_run: bool = False, apenas_britech: bool = True
) -> ResumoSincronizacao:
    resumo = ResumoSincronizacao()
    vistos: set[tuple[str, str]] = set()

    with transaction.atomic():
        for r in registros:
            if apenas_britech and ("britech" not in r.sistema.lower() or not r.carteira):
                resumo.fora_do_sistema_britech += 1
                continue
            administradora = garantir_administradora(r.administrador)
            if administradora is None:
                resumo.administradoras_fora_do_catalogo.add(r.administrador or "(vazio)")
                continue
            chave = (administradora.nome, r.carteira)
            if chave in vistos:
                resumo.duplicados.append(f"{r.administrador}/{r.carteira} ({r.fundo})")
            vistos.add(chave)

            cnpj = normalizar_cnpj(r.cnpj)
            if len(cnpj) != 14:
                resumo.sem_cnpj_valido.append(r.fundo)
                cnpj = ""
            if r.exercicio_mes is None:
                resumo.sem_exercicio.append(r.fundo)

            desejado = {"nome": r.fundo, "tipo": _tipo(r.tipo), "monday_item_id": r.item_id, "ativo": True}
            if cnpj:
                desejado["cnpj"] = cnpj
            if r.exercicio_mes is not None:
                desejado["exercicio_mes"] = r.exercicio_mes

            fundo, criado = Fundo.objects.get_or_create(
                administradora=administradora, codigo_britech=r.carteira, defaults=desejado
            )
            if criado:
                resumo.criados += 1
                continue
            mudou = {campo: valor for campo, valor in desejado.items() if getattr(fundo, campo) != valor}
            if mudou:
                for campo, valor in mudou.items():
                    setattr(fundo, campo, valor)
                fundo.save(update_fields=list(mudou))
                resumo.atualizados += 1
            else:
                resumo.sem_alteracao += 1

        if dry_run:
            transaction.set_rollback(True)
    return resumo
