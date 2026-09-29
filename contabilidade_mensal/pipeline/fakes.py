"""Handlers do pipeline de brinquedo (Fase 1): as 5 etapas sobre o gateway/backend FAKE.

Mostram o contrato que os handlers reais (Fases 2–6) seguirão:
  - falam com a Britech só por `BritechGateway`;
  - consomem o que as etapas anteriores produziram pelos ARTEFATOS VIGENTES (não pelo
    diretório da execução atual — a etapa anterior pode ter sido `pulado` por idempotência);
  - guardam estado entre tentativas em `ctx.payload` (ex.: "já disparei o processamento").
"""

from __future__ import annotations

import datetime as dt
import shutil
from collections.abc import Mapping
from pathlib import Path

from contabilidade_mensal.core.choices import Etapa, TipoArtefato
from contabilidade_mensal.integrations.britech.erros import BritechErro, ProcessamentoPendente
from contabilidade_mensal.integrations.britech.factory import BritechGateway
from contabilidade_mensal.integrations.britech.interface import (
    INSUMOS_DO_LOTE,
    AdministradoraRef,
    CarteiraRef,
    CompetenciaRef,
    StatusProcessamento,
)
from contabilidade_mensal.storage import staging
from contabilidade_mensal.storage.hashing import sha256_arquivo

from . import artefatos
from .tipos import ArtefatoNovo, ContextoEtapa, Handler, ResultadoEtapa


class ErroProcessamentoBritech(BritechErro):
    """A Britech terminou o processamento com erro."""

    codigo = "erro_processamento"


def _refs(ctx: ContextoEtapa) -> tuple[AdministradoraRef, CarteiraRef, CompetenciaRef]:
    adm = ctx.fundo.administradora
    return (
        AdministradoraRef(adm.nome, adm.url_adm, adm.segredo_ref),
        CarteiraRef(ctx.fundo.codigo_britech, ctx.fundo.cnpj, ctx.fundo.nome, ctx.fundo.exercicio_mes),
        CompetenciaRef(ctx.competencia.ano, ctx.competencia.mes),
    )


def montar_handlers(
    gateway: BritechGateway,
    raiz_staging: Path,
    *,
    dry_run_processar: bool = False,
    dry_run_publicar: bool = False,
) -> Mapping[str, Handler]:
    raiz = Path(raiz_staging)

    def baixar_insumos(ctx: ContextoEtapa) -> ResultadoEtapa:
        adm, carteira, comp = _refs(ctx)
        pasta = staging.pasta_insumos(raiz, comp.aaaamm, ctx.execucao.pk, ctx.fundo.pk)
        novos: list[ArtefatoNovo] = []
        with gateway.sessao(adm) as sessao:
            for tipo in INSUMOS_DO_LOTE:
                baixado = gateway.baixar_insumo(sessao, carteira, comp, tipo, pasta)
                novos.append(ArtefatoNovo(baixado.tipo, baixado.caminho))
                novos.extend(ArtefatoNovo(c.tipo, c.caminho) for c in baixado.complementos)
        return ResultadoEtapa(novos)

    def processar_contabil(ctx: ContextoEtapa) -> ResultadoEtapa:
        adm, carteira, comp = _refs(ctx)
        if not ctx.payload.get("disparado"):
            with gateway.sessao(adm) as sessao:
                disparo = gateway.processar_contabil(sessao, [carteira], comp, dry_run=dry_run_processar)
            ctx.payload["disparado"] = True
            if disparo.dry_run:
                return ResultadoEtapa(dados={"dry_run": True})  # não clicou; não há o que aguardar
            ctx.payload["disparado_em"] = ctx.agora.isoformat()
            raise ProcessamentoPendente("processamento disparado; aguardando conclusão")

        # Como saber que terminou (Q4): confirmação humana > política configurada
        if ctx.payload.get("confirmado_manual"):
            return ResultadoEtapa(dados={"conclusao": "manual"})
        p = ctx.parametros
        if p.processamento_conclusao == "manual":
            raise ProcessamentoPendente("aguardando confirmação manual no admin")
        if p.processamento_conclusao == "espera":
            decorrido = (ctx.agora - dt.datetime.fromisoformat(ctx.payload["disparado_em"])).total_seconds()
            faltam = p.processamento_espera_s - decorrido
            if faltam > 0:
                raise ProcessamentoPendente(
                    f"faltam {faltam:.0f}s da espera mínima", espera_s=max(1.0, min(faltam, p.polling_intervalo_s))
                )
            return ResultadoEtapa(dados={"conclusao": "espera"})
        with gateway.sessao(adm) as sessao:
            status = gateway.status_processamento(sessao, carteira, comp)
        if status is StatusProcessamento.ERRO:
            raise ErroProcessamentoBritech("a Britech terminou o processamento com erro")
        if status is not StatusProcessamento.CONCLUIDO:
            raise ProcessamentoPendente(f"status atual: {status.value}")
        return ResultadoEtapa()

    def baixar_balancete(ctx: ContextoEtapa) -> ResultadoEtapa:
        adm, carteira, comp = _refs(ctx)
        pasta = staging.pasta_insumos(raiz, comp.aaaamm, ctx.execucao.pk, ctx.fundo.pk)
        with gateway.sessao(adm) as sessao:
            balancete = gateway.baixar_balancete(sessao, carteira, comp, pasta)
        return ResultadoEtapa(
            [ArtefatoNovo(TipoArtefato.BALANCETE_PDF, balancete.pdf), ArtefatoNovo(TipoArtefato.BALANCETE_XLS, balancete.xls)]
        )

    def popular_excel(ctx: ContextoEtapa) -> ResultadoEtapa:
        insumos = artefatos.artefatos_vigentes(ctx.fundo.pk, ctx.competencia.pk, Etapa.BAIXAR_INSUMOS)
        balancete = artefatos.artefatos_vigentes(ctx.fundo.pk, ctx.competencia.pk, Etapa.BAIXAR_BALANCETE)
        entradas = [Path(a.caminho_local) for a in insumos + balancete]
        if len(entradas) < len(INSUMOS_DO_LOTE) + 2 or not all(p.is_file() for p in entradas):
            from contabilidade_mensal.integrations.britech.erros import ArquivoInvalido

            raise ArquivoInvalido("faltam insumos/balancete íntegros para popular o Excel")
        pasta = staging.pasta_saida(raiz, ctx.competencia.aaaamm, ctx.execucao.pk, ctx.fundo.pk)
        boleta = pasta / f"{ctx.fundo.nome} {ctx.competencia.aaaamm}.xlsb"
        boleta.write_bytes(("fake-boleta|" + "|".join(sha256_arquivo(p) for p in sorted(entradas))).encode())
        return ResultadoEtapa([ArtefatoNovo(TipoArtefato.BOLETA, boleta)])

    def publicar_drive(ctx: ContextoEtapa) -> ResultadoEtapa:
        boletas = [
            a
            for a in artefatos.artefatos_vigentes(ctx.fundo.pk, ctx.competencia.pk, Etapa.POPULAR_EXCEL)
            if a.tipo == TipoArtefato.BOLETA
        ]
        if not boletas:
            from contabilidade_mensal.integrations.britech.erros import ArquivoInvalido

            raise ArquivoInvalido("não há boleta para publicar")
        if dry_run_publicar:
            return ResultadoEtapa(dados={"dry_run": True})
        origem = Path(boletas[0].caminho_local)
        destino = raiz / "_drive_fake" / ctx.competencia.aaaamm / str(ctx.fundo.pk) / origem.name
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origem, destino)
        sha = sha256_arquivo(destino)
        return ResultadoEtapa(
            [
                ArtefatoNovo(
                    TipoArtefato.BOLETA,
                    destino,
                    drive_file_id=f"fake-drive-{sha[:12]}",
                    drive_checksum=sha,
                    verificado_em=ctx.agora,
                )
            ]
        )

    return {
        Etapa.BAIXAR_INSUMOS: baixar_insumos,
        Etapa.PROCESSAR_CONTABIL: processar_contabil,
        Etapa.BAIXAR_BALANCETE: baixar_balancete,
        Etapa.POPULAR_EXCEL: popular_excel,
        Etapa.PUBLICAR_DRIVE: publicar_drive,
    }
