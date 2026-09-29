"""
Configuração e constantes do populador em lote.

Todos os nomes de aba/coluna/célula abaixo foram confirmados lendo o VBA real
(Sub_Main.bas / Functions.bas) do arquivo:
    Painel Populador ID CORRETORA - Contabilidade de Fundos.xlsm
via oletools/olevba, e conferidos contra dados reais da aba "Painel" e pastas
de fundos no disco (fundo de teste: "FII LAZIO II"). Não foram inventados.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- Aba e layout do painel -------------------------------------------------

SHEET_PAINEL = "Painel"

FIRST_ROW = 8  # ProcessarEmLoop começa em "linha = 8"

COL_FUNDO = "B"       # nome do fundo
COL_STATUS = "C"      # status escrito de volta pela macro
COL_PROCESSA = "D"    # marcador "X"
COL_TIPO = "F"        # tipo do fundo / subpasta sob a raiz (ex.: "FII", "FIDC")
COL_EXERCICIO = "H"   # "Data Base {exercicio}", ex.: "Junho 2026"

# Parâmetros fixos no topo da aba Painel.
# ATENÇÃO: apesar do nome que a descrição original usava ("subpasta de
# destino/origem"), o rótulo real na planilha é período (AAAAMM), não um nome
# de negócio. Confirmado lendo a aba: B4="Data Formatada"/C4="202509",
# B5="Data Anterior"/C5="202508". A lógica de path do VBA não muda por causa
# disso, só o significado do conteúdo dessas células.
CELL_PASTA_RAIZ = "C2"           # pasta raiz (ex.: "G:\\...\\Contabilidade de Fundos - ID Corretora\\")
CELL_PERIODO_DESTINO = "C4"      # nomePastaDestino no VBA ("Data Formatada")
CELL_PERIODO_ORIGEM = "C5"       # nomePastaProcurada no VBA ("Data Anterior")

MARCADOR_PROCESSAR = "X"

# Nome da subpasta de insumos dentro da pasta de destino (fixo no VBA).
SUBPASTA_INSUMOS = "Insumos"

# Extensões que, se já existirem na pasta de destino, fazem a linha ser
# pulada com status "Arquivo já existe" (Dir(...) checado em ProcessarEmLoop).
EXTENSOES_SAIDA_EXISTENTE = (".bat", ".xlsm", ".xlsx", ".xls", ".xlsb")

# Planilhas que são limpas (ClearContents) no arquivo recém-copiado, antes de
# repopular — mesma lista do array `planilhasLimpar` em CopiarArquivoOrigem.
ABAS_PARA_LIMPAR = (
    "Carteira final",
    "Balancete",
    "Extrato",
    "Mov_Cotista",
    "Posicao_Cotista",
    "Posicao_Cotista_antigo",
)

ABA_MAPA_CONTABIL = "Mapa_Contábil"  # ativada e salva ao final, igual ao VBA


# --- Escopo do processamento em lote (ProcessarEmLoop) ----------------------
#
# O fluxo manual (uma planilha por vez, funções chamadas por botão fora do
# loop) chega a popular também Op.BMF, Op.Bolsa, PL/Cota (via HistóricoCota)
# e Balancete_anterior. NENHUMA dessas é chamada por ProcessarEmLoop hoje —
# confirmado lendo o Sub_Main.bas inteiro.
#
# IMPORTANTE (achado durante a investigação, não confirmado com quem mantém
# a planilha): as funções Popula_Mov_BMF, Popula_Mov_Bolsa, Popula_PL_Cota,
# Popula_Posicao_Cotista_Inicial, Popula_Balancete("Inicial", ...) e
# Formata_Carteira_Inicial/Final NÃO têm nenhum chamador em lugar nenhum do
# projeto (nenhuma outra Sub as invoca, e os únicos botões da planilha
# disparam "ProcessarEmLoop" e "Lista_Pastas"). Ou é código morto de uma
# versão anterior, ou existe um jeito de acioná-las que não está neste
# arquivo. Por isso ficam de fora do escopo abaixo.
#
# Para reativar/ajustar o que o lote processa, mexa só nesta lista.
BATCH_STEPS = (
    "carteira_final",
    "carteira_inicial",
    "extrato",
    "balancete_final",
    "posicao_cotista",
    "mov_cotista",
)


# --- Padrões de nome de arquivo de insumo -----------------------------------
#
# Substrings usadas com InStr() no VBA original (Option Compare Binary =
# comparação sensível a maiúsculas/minúsculas, replicada aqui como está).
#
# ACHADO: para o fundo de teste "FII LAZIO II" (tipo FII), os arquivos reais
# de insumo NÃO batem exatamente com esses padrões:
#   - real: "..._SaldoAplicacaoCotistaFinal.xlsx"  vs. padrão "SaldoAplicacaoCotista.xlsx"
#   - real: "Balancete 30.09.xls"                   vs. padrão "Balancete Contábil.xls"
# Isso já acontece hoje no VBA (falha em silêncio: a função varre a pasta,
# não acha nada, e sai sem preencher nada e sem avisar). Aqui replicamos a
# MESMA busca (mesmos padrões, mesma lógica), mas emitimos um aviso no
# relatório quando nada bate — decisão confirmada com o usuário — em vez de
# aceitar variações de nome sem confirmação (isso seria mudança de regra de
# negócio, não port).
INSUMO_PATTERNS = {
    "carteira_final": "Carteira.xlsx",
    "carteira_inicial": "CarteiraInicial.xlsx",
    "extrato": "ExtratoCC.xlsx",
    "balancete_final": "Balancete Contábil.xls",
    "posicao_cotista": "SaldoAplicacaoCotista.xlsx",
    "mov_cotista": "MovCotista.xls",
}

SHEET_DESTINO = {
    "carteira_final": "Carteira final",
    "carteira_inicial": "Carteira inicial",
    "extrato": "Extrato",
    "balancete_final": "Balancete",
    "posicao_cotista": "Posicao_Cotista",
    "mov_cotista": "Mov_Cotista",
}


# --- Fallback de reconhecimento de insumo (camada 2) ------------------------
#
# Usado SÓ quando o padrão exato acima (INSUMO_PATTERNS) não encontra nada.
# Cada regra é: tokens obrigatórios + tokens proibidos, comparados contra o
# nome do arquivo "canonicalizado" (minúsculo, sem acento, só alfanumérico —
# ver matching.canonicalizar), mais as extensões aceitas.
#
# Cada padrão abaixo tem evidência real de disco (comparei 4 fundos:
# FII LAZIO II, FII KRONOS, FII OCTO, FIDC ALPHA em 3 períodos diferentes).
# NÃO adicione um padrão aqui sem ver o nome real de um arquivo em produção.
#
#   Carteira final:
#     - "Carteira_558338_31-12-2025.xlsx" (FII KRONOS)
#     - "Carteira_44177538_31-12-2025.xlsx" (FII OCTO)
#     - "CarteiraFinal.xlsx" (FIDC ALPHA, período recente)
#     - "Carteira_566391_31-1-2023.xlsx" (FIDC ALPHA, 2023)
#   Carteira inicial:
#     - "..._CarteiraInicial.xlsx" (FII KRONOS, FII LAZIO II)
#   Balancete final:
#     - "Balancete 31.12.2025.xls" (FII KRONOS, FII OCTO)
#     - "BalanceteContabil_566391_....xls" (FIDC ALPHA)
#   Posição_Cotista (SaldoAplicacaoCotista):
#     - "SaldoAplicacaoCotista558338_31-12-2025.xlsx" (FII KRONOS)
#     - "SaldoAplicacaoCotista44177538_...xlsx" (FII OCTO)
#     - "..._SaldoAplicacaoCotistaFinal.xlsx" (FII LAZIO II, FIDC ALPHA recente)
#   Mov_Cotista:
#     - "ReportMovimentacaoCotista.xls" (FIDC ALPHA, 2022/2023)
#
# Quando mais de um arquivo bate a mesma regra (ex.: FII OCTO tem
# "Carteira_..._2024.xlsx" E "Carteira_..._2025.xlsx", nenhum com "Inicial"
# no nome), o resultado fica "ambíguo" — ver matching.resolver_insumo — e
# NÃO é escolhido sozinho.
@dataclass(frozen=True)
class RegraFallback:
    obrigatorias: tuple[str, ...]  # todos esses tokens (canônicos) devem aparecer
    proibidas: tuple[str, ...]     # nenhum desses pode aparecer
    extensoes: tuple[str, ...]     # extensões aceitas (com ponto, minúsculo)


INSUMO_FALLBACK: dict[str, tuple[RegraFallback, ...]] = {
    "carteira_final": (
        RegraFallback(obrigatorias=("carteira",), proibidas=("inicial",), extensoes=(".xlsx",)),
    ),
    "carteira_inicial": (
        RegraFallback(obrigatorias=("carteira", "inicial"), proibidas=(), extensoes=(".xlsx",)),
    ),
    "extrato": (
        RegraFallback(obrigatorias=("extrato",), proibidas=(), extensoes=(".xlsx", ".xls")),
    ),
    "balancete_final": (
        RegraFallback(obrigatorias=("balancete",), proibidas=("inicial",), extensoes=(".xls", ".xlsx")),
    ),
    "posicao_cotista": (
        RegraFallback(obrigatorias=("saldoaplicacaocotista",), proibidas=("inicial",), extensoes=(".xlsx",)),
    ),
    "mov_cotista": (
        RegraFallback(obrigatorias=("movcotista",), proibidas=(), extensoes=(".xls", ".xlsx")),
        RegraFallback(obrigatorias=("movimentacao", "cotista"), proibidas=(), extensoes=(".xls", ".xlsx")),
    ),
}


# --- Status escritos na coluna C (mesmo texto do VBA) -----------------------

STATUS_JA_EXISTE = "Arquivo já existe"
STATUS_NAO_PROCESSADO = "Não processado"
STATUS_PASTA_NAO_ENCONTRADA = "Pasta não encontrada"
STATUS_SALVO = "Conciliação salva na pasta"
STATUS_ERRO = "Erro"  # não existe no VBA original; usado aqui para isolar falhas por fundo
