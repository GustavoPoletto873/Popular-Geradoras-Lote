"""Backend `api`: baixa os insumos pelos endpoints REST da Britech (`WS/api`).

Só implementa `baixar_insumo`. Processar contábil e balancete não têm endpoint conhecido e
seguem no navegador (`OperacaoNaoSuportada` aqui).

Datas (regras do Simplifica, ver core/calendario.py), dada a competência e o mês de exercício do fundo:
    final        = último dia útil do mês da competência
    fim anterior = último dia útil do mês de encerramento do exercício anterior  (carteira/posição INICIAL)
    início       = max(dia útil seguinte ao fim anterior, implantação da carteira) (extrato, movimentação)
"""

from __future__ import annotations

import datetime as dt
import logging
from io import BytesIO
from pathlib import Path
from typing import Callable, Sequence

import pandas as pd

from contabilidade_mensal.core import calendario
from contabilidade_mensal.core.choices import TipoArtefato

from ..erros import (
    ArquivoInvalido,
    AutenticacaoFalhou,
    BritechErro,
    CadastroIncompleto,
    CarteiraNaoEncontrada,
    OperacaoNaoSuportada,
)
from ..interface import (
    TIPO_ARTEFATO_DO_INSUMO,
    AdministradoraRef,
    ArquivoBaixado,
    BalanceteBaixado,
    CarteiraRef,
    CompetenciaRef,
    ResultadoDisparo,
    StatusProcessamento,
    TipoInsumo,
)
from ..nomes import nome_insumo_canonico
from . import urls
from .cadastro import ClasseDeCotas, ler_cadastro, normalizar_cnpj
from .cliente import ClienteBritech
from .credenciais import ProvedorCredenciais
from .transformacoes.carteira import transformar_composicao_carteira
from .transformacoes.empilhar import empilhar
from .transformacoes.extrato import transformar_extrato
from .transformacoes.historico_cota import transformar_historico_cota
from .transformacoes.mov_cotista import transformar_mov_cotista
from .transformacoes.posicao_cotista import transformar_posicao_cotista

logger = logging.getLogger(__name__)

PASTA_SEPARADOS = "Arquivos separados"


class _Datas:
    """Datas da consulta. `inicio` (dia útil seguinte ao fim do exercício anterior, ou a implantação se for
    depois) precisa do cadastro da Britech e só é calculada por quem a usa (extrato e movimentação)."""

    def __init__(self, sessao: "SessaoApi", id_carteira: str, final: dt.date, fim_anterior: dt.date) -> None:
        self._sessao, self._id = sessao, id_carteira
        self.final, self.fim_anterior = final, fim_anterior
        self._inicio: dt.date | None = None

    @property
    def inicio(self) -> dt.date:
        if self._inicio is None:
            implantacao = self._sessao.implantacao_da_carteira(self._id)
            self._inicio = calendario.inicio_exercicio(self.fim_anterior, implantacao)
        return self._inicio


class SessaoApi:
    """Cliente autenticado + cadastro de carteiras da administradora (carregado uma vez por sessão)."""

    def __init__(self, cliente: ClienteBritech) -> None:
        self.cliente = cliente
        self._cadastro: list[ClasseDeCotas] | None = None

    def cadastro(self) -> list[ClasseDeCotas]:
        if self._cadastro is None:
            self._cadastro = ler_cadastro(self.cliente.get_json(urls.CADASTRO_FUNDOS))
        return self._cadastro

    def classes_do_fundo(self, cnpj: str) -> list[ClasseDeCotas]:
        alvo = normalizar_cnpj(cnpj)
        return [c for c in self.cadastro() if c.cnpj == alvo]

    def implantacao_da_carteira(self, id_carteira: str) -> dt.date | None:
        for classe in self.cadastro():
            if classe.id_cliente == str(id_carteira).strip():
                return classe.implantacao
        return None

    def fechar(self) -> None:
        self.cliente.fechar()


def _ler_excel(conteudo: bytes, o_que: str) -> pd.DataFrame:
    if not conteudo:
        raise ArquivoInvalido(f"{o_que}: resposta vazia da Britech")
    try:
        return pd.read_excel(BytesIO(conteudo))
    except Exception as exc:  # noqa: BLE001 - qualquer falha de leitura = arquivo inválido
        raise ArquivoInvalido(f"{o_que}: a resposta não é uma planilha legível ({type(exc).__name__})") from exc


class ApiBackend:
    def __init__(
        self,
        credenciais: ProvedorCredenciais,
        *,
        fabrica_cliente: Callable[..., ClienteBritech] = ClienteBritech,
    ) -> None:
        self._credenciais = credenciais
        self._fabrica_cliente = fabrica_cliente

    # --- protocolo BritechBackend ---------------------------------------------------

    def abrir_sessao(self, administradora: AdministradoraRef) -> SessaoApi:
        credencial = self._credenciais.obter(administradora.segredo_ref)
        return SessaoApi(self._fabrica_cliente(administradora.url_adm, credencial.usuario, credencial.senha))

    def processar_contabil(self, sessao, carteiras: Sequence[CarteiraRef], competencia, *, dry_run: bool) -> ResultadoDisparo:
        raise OperacaoNaoSuportada("processar_contabil não tem endpoint na API; use o backend 'browser'")

    def status_processamento(self, sessao, carteira, competencia) -> StatusProcessamento:
        raise OperacaoNaoSuportada("status_processamento não tem endpoint na API; use o backend 'browser'")

    def baixar_balancete(self, sessao, carteira, competencia, destino: Path) -> BalanceteBaixado:
        raise OperacaoNaoSuportada("baixar_balancete não tem endpoint na API; use o backend 'browser'")

    def baixar_insumo(
        self,
        sessao: SessaoApi,
        carteira: CarteiraRef,
        competencia: CompetenciaRef,
        tipo: TipoInsumo,
        destino: Path,
    ) -> ArquivoBaixado:
        if not carteira.exercicio_mes:
            raise CadastroIncompleto(f"fundo {carteira.codigo_britech}: mês do exercício não informado")
        if not carteira.cnpj:
            raise CadastroIncompleto(f"fundo {carteira.codigo_britech}: CNPJ não informado")

        datas = self._datas(sessao, carteira, competencia)
        destino.mkdir(parents=True, exist_ok=True)
        alvo = destino / nome_insumo_canonico(tipo, competencia, carteira.cnpj)

        if tipo in (TipoInsumo.CARTEIRA_FINAL, TipoInsumo.CARTEIRA_INICIAL):
            return self._carteira(sessao, carteira, tipo, alvo, datas)
        if tipo is TipoInsumo.EXTRATO_CC:
            return self._extrato(sessao, carteira, alvo, datas)
        return self._passivo(sessao, carteira, competencia, tipo, alvo, datas)

    # --- datas ----------------------------------------------------------------------

    @staticmethod
    def _datas(sessao: SessaoApi, carteira: CarteiraRef, competencia: CompetenciaRef) -> "_Datas":
        final = calendario.data_final_carteira(competencia.ano, competencia.mes)
        fim_anterior = calendario.fim_exercicio_anterior(carteira.exercicio_mes, final)
        return _Datas(sessao, carteira.codigo_britech, final, fim_anterior)

    # --- ativo -----------------------------------------------------------------------

    def _carteira(self, sessao, carteira, tipo, alvo: Path, datas: _Datas) -> ArquivoBaixado:
        data = (datas.final if tipo is TipoInsumo.CARTEIRA_FINAL else datas.fim_anterior).isoformat()
        id_ = carteira.codigo_britech
        bruto = _ler_excel(
            sessao.cliente.get_bytes(urls.composicao_carteira(id_, data, tipo_arquivo="ExcelAlinhado")),
            f"composição da carteira {id_}",
        )
        df = transformar_composicao_carteira(bruto, id_carteira=id_, data_ref=data)
        df.to_excel(alvo, index=False)
        pdf = self._pdf(sessao, urls.composicao_carteira(id_, data, tipo_arquivo="PDF"), alvo.with_suffix(".pdf"))
        return ArquivoBaixado(TIPO_ARTEFATO_DO_INSUMO[tipo], alvo, complementos=pdf)

    def _extrato(self, sessao, carteira, alvo: Path, datas) -> ArquivoBaixado:
        id_ = carteira.codigo_britech
        inicio, fim = datas.inicio.isoformat(), datas.final.isoformat()
        bruto = _ler_excel(
            sessao.cliente.get_bytes(urls.extrato_conta_corrente(id_, inicio, fim, tipo_arquivo="Excel")),
            f"extrato da carteira {id_}",
        )
        transformar_extrato(bruto, id_carteira=id_).to_excel(alvo, index=False)
        pdf = self._pdf(
            sessao, urls.extrato_conta_corrente(id_, inicio, fim, tipo_arquivo="PDF"), alvo.with_suffix(".pdf")
        )
        return ArquivoBaixado(TipoArtefato.INSUMO_EXTRATO_CC, alvo, complementos=pdf)

    # --- passivo (por classe de cotas; depois empilhado) --------------------------------

    def _passivo(self, sessao, carteira, competencia, tipo, alvo: Path, datas) -> ArquivoBaixado:
        classes = sessao.classes_do_fundo(carteira.cnpj)
        if not classes:
            raise CarteiraNaoEncontrada(f"nenhuma carteira com o CNPJ {carteira.cnpj} no cadastro da Britech")

        por_classe: list[pd.DataFrame] = []
        pdfs: list[ArquivoBaixado] = []
        for classe in classes:
            df, pdf = self._passivo_da_classe(sessao, tipo, classe, datas, alvo.parent, competencia, carteira.cnpj)
            por_classe.append(df)
            pdfs.extend(pdf)

        if len(por_classe) > 1:  # preserva as planilhas por classe, como o Simplifica ("Arquivos separados")
            separados = alvo.parent / PASTA_SEPARADOS
            separados.mkdir(exist_ok=True)
            for classe, df in zip(classes, por_classe):
                df.to_excel(separados / f"{competencia.aaaamm}_{classe.id_cliente}_{carteira.cnpj}_{tipo.value}.xlsx", index=False)

        empilhar(por_classe, tipo.value).to_excel(alvo, index=False)
        return ArquivoBaixado(TIPO_ARTEFATO_DO_INSUMO[tipo], alvo, complementos=tuple(pdfs))

    def _passivo_da_classe(self, sessao, tipo, classe: ClasseDeCotas, datas, pasta: Path, competencia, cnpj: str):
        cliente = sessao.cliente
        id_ = classe.id_cliente
        if tipo is TipoInsumo.MOV_COTISTA:
            registros = cliente.get_json(urls.mov_cotista(id_))
            df = transformar_mov_cotista(
                registros,
                id_carteira=id_,
                nome_classe=classe.nome,
                data_inicio=datas.inicio.isoformat(),
                data_fim=datas.final.isoformat(),
            )
            return df, []
        if tipo is TipoInsumo.HISTORICO_COTA:
            fim_como_datetime = str(dt.datetime.combine(datas.final, dt.time()))
            registros = cliente.get_json(urls.historico_cota(id_, datas.fim_anterior.isoformat(), fim_como_datetime))
            return transformar_historico_cota(registros, id_carteira=id_, nome_classe=classe.nome), []

        # posição de cotistas: final na data final, inicial no fim do exercício anterior
        data = (datas.final if tipo is TipoInsumo.POSICAO_COTISTA_FINAL else datas.fim_anterior).isoformat()
        bruto = _ler_excel(
            cliente.get_bytes(urls.saldo_aplicacoes_cotista(id_, data, tipo_arquivo="Excel")),
            f"posição de cotistas da carteira {id_}",
        )
        df = transformar_posicao_cotista(bruto, id_carteira=id_, nome_classe=classe.nome)
        nome_pdf = pasta / f"{competencia.aaaamm}_{id_}_{cnpj}_{tipo.value}.pdf"  # PDF por classe, como no Simplifica
        pdf = self._pdf(sessao, urls.saldo_aplicacoes_cotista(id_, data, tipo_arquivo="PDF"), nome_pdf)
        return df, list(pdf)

    # --- PDFs de evidência (falha não derruba o insumo, exceto credencial) -------------------

    def _pdf(self, sessao: SessaoApi, url: str, destino: Path) -> tuple[ArquivoBaixado, ...]:
        try:
            conteudo = sessao.cliente.get_bytes(url)
        except AutenticacaoFalhou:
            raise
        except BritechErro as exc:
            logger.warning("PDF de evidência não baixado", extra={"erro_tipo": exc.codigo, "arquivo": destino.name})
            return ()
        destino.write_bytes(conteudo)
        return (ArquivoBaixado(TipoArtefato.INSUMO_PDF, destino),)
