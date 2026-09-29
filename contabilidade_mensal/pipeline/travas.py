"""Exclusão mútua com lease, sobre a tabela `TravaRecurso` (unique em `chave`).

Usada para garantir 1 sessão por credencial na Britech: só quem detém a trava
`britech:<administradora>` reivindica etapas de navegador dessa administradora.
Portável entre SQLite e Postgres: a unicidade da chave é quem decide a corrida.
"""

from __future__ import annotations

import datetime as dt

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from contabilidade_mensal.core.models import TravaRecurso


def adquirir(chave: str, dono: str, *, lease_s: float, agora: dt.datetime | None = None) -> bool:
    """True se `dono` passou a deter a trava (nova, sua mesma, ou de outro com lease vencido)."""
    agora = agora or timezone.now()
    lease_ate = agora + dt.timedelta(seconds=lease_s)
    try:
        with transaction.atomic():
            TravaRecurso.objects.create(chave=chave, dono=dono, lease_ate=lease_ate, adquirida_em=agora)
        return True
    except IntegrityError:
        pass
    atualizadas = (
        TravaRecurso.objects.filter(chave=chave)
        .filter(Q(dono=dono) | Q(lease_ate__lt=agora))
        .update(dono=dono, lease_ate=lease_ate)
    )
    return atualizadas == 1


def renovar(chave: str, dono: str, *, lease_s: float, agora: dt.datetime | None = None) -> bool:
    agora = agora or timezone.now()
    return (
        TravaRecurso.objects.filter(chave=chave, dono=dono).update(lease_ate=agora + dt.timedelta(seconds=lease_s)) == 1
    )


def liberar(chave: str, dono: str) -> bool:
    apagadas, _ = TravaRecurso.objects.filter(chave=chave, dono=dono).delete()
    return apagadas == 1
