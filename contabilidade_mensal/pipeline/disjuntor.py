"""Circuit breaker por `etapa:backend:administradora` (ver docs/unificacao/05_arquitetura.md §8).

- Fechado: tudo passa. Cada falha "estrutural" incrementa o contador do MESMO tipo de erro;
  ao atingir o limite daquele tipo, o disjuntor ABRE e a fila daquela chave pausa.
- Aberto: `permite()` só libera UMA tentativa de teste (meia-abertura) a cada período de resfriamento.
- Um sucesso fecha o disjuntor; também pode ser fechado manualmente.
"""

from __future__ import annotations

import datetime as dt
import logging

from django.db import transaction
from django.utils import timezone

from contabilidade_mensal.core.models import Disjuntor

from . import parametros

logger = logging.getLogger(__name__)


def permite(chave: str, *, agora: dt.datetime | None = None) -> bool:
    agora = agora or timezone.now()
    d = Disjuntor.objects.filter(chave=chave).first()
    if d is None or not d.aberto:
        return True
    p = parametros.obter()
    if d.proxima_tentativa_em is not None and agora >= d.proxima_tentativa_em:
        # meia-abertura: compare-and-set garante que só um worker leva a tentativa de teste
        proxima = agora + dt.timedelta(seconds=p.disjuntor_resfriamento_s)
        ganhou = Disjuntor.objects.filter(pk=d.pk, proxima_tentativa_em=d.proxima_tentativa_em).update(
            proxima_tentativa_em=proxima
        )
        return ganhou == 1
    return False


def registrar_falha(chave: str, erro_tipo: str, *, agora: dt.datetime | None = None) -> bool:
    """Contabiliza uma falha estrutural. Devolve True se ESTA falha abriu o disjuntor."""
    agora = agora or timezone.now()
    p = parametros.obter()
    limite = p.disjuntor_limites.get(erro_tipo, p.disjuntor_limites["default"])
    with transaction.atomic():
        d, _ = Disjuntor.objects.select_for_update().get_or_create(chave=chave)
        d.falhas_consecutivas = d.falhas_consecutivas + 1 if d.ultimo_erro_tipo == erro_tipo else 1
        d.ultimo_erro_tipo = erro_tipo
        abriu = False
        if d.aberto:
            d.proxima_tentativa_em = agora + dt.timedelta(seconds=p.disjuntor_resfriamento_s)  # teste falhou
        elif d.falhas_consecutivas >= limite:
            d.aberto_desde = agora
            d.motivo = f"{d.falhas_consecutivas} falha(s) seguida(s) do tipo {erro_tipo}"
            d.proxima_tentativa_em = agora + dt.timedelta(seconds=p.disjuntor_resfriamento_s)
            abriu = True
        d.save()
    if abriu:
        logger.critical("disjuntor aberto", extra={"chave_disjuntor": chave, "erro_tipo": erro_tipo})
    return abriu


def registrar_sucesso(chave: str) -> None:
    Disjuntor.objects.filter(chave=chave).update(
        falhas_consecutivas=0, ultimo_erro_tipo="", aberto_desde=None, proxima_tentativa_em=None, motivo=""
    )


def fechar(chave: str, *, por: str) -> None:
    """Fechamento manual (ex.: depois de corrigir o Page Object)."""
    Disjuntor.objects.filter(chave=chave).update(
        falhas_consecutivas=0,
        ultimo_erro_tipo="",
        aberto_desde=None,
        proxima_tentativa_em=None,
        motivo="",
        reaberto_por=por,
    )
