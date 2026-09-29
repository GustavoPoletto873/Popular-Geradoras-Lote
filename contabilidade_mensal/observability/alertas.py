"""Alertas enviados pelo próprio Django (sem n8n): e-mail (SMTP) e/ou webhook do Slack.

- Todo alerta é GRAVADO (`Alerta`) — mesmo sem canal configurado, para auditoria e para o painel.
- Deduplicação por `chave` dentro de uma janela (`dedup_s`): repetições não reenviam, só incrementam `repeticoes`.
  Isso evita 400 e-mails quando um mesmo erro derruba os 400 fundos.
- Enviar NUNCA levanta exceção: falha de canal é registrada no próprio alerta e no log.
- O conteúdo vem só de mensagens do pipeline (já sem segredos); não anexe credenciais, tokens nem traces.

Configuração (`settings.ALERTAS`): `email_para` (lista), `email_de`, `slack_webhook`, `prefixo`.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import requests
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from contabilidade_mensal.core.models import Alerta

logger = logging.getLogger(__name__)

INFO, AVISO, CRITICO = "info", "aviso", "critico"
_ICONE = {INFO: "ℹ️", AVISO: "⚠️", CRITICO: "🚨"}


def _config() -> dict[str, Any]:
    return dict(getattr(settings, "ALERTAS", {}) or {})


def canais_configurados() -> list[str]:
    cfg = _config()
    return [c for c, ativo in (("email", cfg.get("email_para")), ("slack", cfg.get("slack_webhook"))) if ativo]


def _enviar_email(cfg: dict, assunto: str, corpo: str) -> None:
    send_mail(assunto, corpo, cfg.get("email_de") or None, list(cfg["email_para"]), fail_silently=False)


def _enviar_slack(cfg: dict, texto: str, sessao: Any) -> None:
    resposta = sessao.post(cfg["slack_webhook"], json={"text": texto}, timeout=5)
    if resposta.status_code >= 300:
        raise RuntimeError(f"Slack respondeu HTTP {resposta.status_code}")


def enviar(
    chave: str,
    titulo: str,
    corpo: str = "",
    *,
    severidade: str = AVISO,
    dedup_s: float = 3600,
    agora: dt.datetime | None = None,
    sessao_http: Any = None,
) -> Alerta | None:
    """Devolve o `Alerta` criado, ou None se foi suprimido por duplicidade."""
    agora = agora or timezone.now()
    recente = (
        Alerta.objects.filter(chave=chave, criado_em__gte=agora - dt.timedelta(seconds=dedup_s)).order_by("-criado_em").first()
    )
    if recente is not None:
        Alerta.objects.filter(pk=recente.pk).update(repeticoes=recente.repeticoes + 1)
        return None

    cfg = _config()
    canais = canais_configurados()
    alerta = Alerta.objects.create(
        chave=chave, severidade=severidade, titulo=titulo, corpo=corpo, criado_em=agora, canais=",".join(canais)
    )
    log = {INFO: logger.info, AVISO: logger.warning, CRITICO: logger.critical}[severidade]
    log("alerta: %s", titulo, extra={"alerta_chave": chave, "severidade": severidade, "canais": canais})

    prefixo = cfg.get("prefixo", "[Contabilidade mensal]")
    assunto = f"{prefixo} {titulo}"
    erros: list[str] = []
    enviado = False
    if "email" in canais:
        try:
            _enviar_email(cfg, assunto, corpo or titulo)
            enviado = True
        except Exception as exc:  # noqa: BLE001 - alerta nunca derruba o pipeline
            erros.append(f"email: {type(exc).__name__}")
    if "slack" in canais:
        try:
            _enviar_slack(cfg, f"{_ICONE[severidade]} *{assunto}*\n{corpo}", sessao_http or requests)
            enviado = True
        except Exception as exc:  # noqa: BLE001
            erros.append(f"slack: {type(exc).__name__}")
    if erros:
        logger.error("falha ao enviar alerta", extra={"alerta_chave": chave, "erros": erros})
    Alerta.objects.filter(pk=alerta.pk).update(
        enviado_em=timezone.now() if enviado else None, erro_envio="; ".join(erros)
    )
    alerta.refresh_from_db()
    return alerta
