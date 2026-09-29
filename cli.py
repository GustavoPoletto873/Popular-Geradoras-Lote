"""
CLI do populador em lote — substitui o clique no botão "ProcessarEmLoop" da
planilha "Painel Populador ID CORRETORA - Contabilidade de Fundos.xlsm".

Exemplos:
    python cli.py --dry-run
    python cli.py --apenas-fundo "FII LAZIO II"
    python cli.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from populador import config
from populador.matching import extrair_data_provavel
from populador.runner import processar_em_lote

CAMINHO_PAINEL_PADRAO = Path(
    r"G:\Drives compartilhados\Contabilidade de Fundos - ID Corretora"
    r"\Painel Populador ID CORRETORA - Contabilidade de Fundos.xlsm"
)


def prompt_resolver_ambiguidade(fundo: str, step: str, candidatos: list[Path]) -> Path | None:
    """Resolução interativa de ambiguidade (--interativo): mostra os
    candidatos com a melhor data que der pra extrair do nome (só pra
    referência do humano, nunca decide sozinho) e deixa a pessoa escolher.
    """
    print(f"\n[{fundo}] Ambiguidade em '{step}' — não deu pra saber qual arquivo é o certo:")
    for i, candidato in enumerate(candidatos, 1):
        data = extrair_data_provavel(candidato.name)
        data_str = data.isoformat() if data else "data não identificada"
        print(f"  {i}) {candidato.name}  (data provável: {data_str})")
    print("  0) pular (deixar em branco, com aviso no relatório)")

    while True:
        escolha = input("Escolha o número do arquivo correto [0]: ").strip()
        if escolha in ("", "0"):
            return None
        if escolha.isdigit() and 1 <= int(escolha) <= len(candidatos):
            return candidatos[int(escolha) - 1]
        print("Entrada inválida, digite um número da lista.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--painel",
        type=Path,
        default=CAMINHO_PAINEL_PADRAO,
        help="Caminho do .xlsm do Painel Populador (padrão: arquivo real na pasta compartilhada).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Só mostra o que seria processado, sem copiar/abrir/salvar nada.",
    )
    parser.add_argument(
        "--apenas-fundo",
        default=None,
        help="Processa só o fundo com esse nome exato (útil para validar antes de rodar o lote todo).",
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Mostra a janela do Excel durante o processamento (útil para depurar).",
    )
    parser.add_argument(
        "--relatorio-csv",
        type=Path,
        default=Path("logs") / "relatorio_populador.csv",
        help="Arquivo CSV (append) com o resultado por fundo. Passe vazio para desativar.",
    )
    parser.add_argument(
        "--pasta-saida",
        type=Path,
        default=None,
        help=(
            "Redireciona SÓ a escrita da conciliação gerada pra essa pasta (mesma "
            "estrutura de subpastas), sem tocar a pasta real do fundo. A leitura do "
            "arquivo anterior e dos insumos continua sempre na pasta real (C2 do "
            "Painel), só leitura. Útil pra testar contra dados de produção sem "
            "escrever neles."
        ),
    )
    parser.add_argument(
        "--interativo",
        action="store_true",
        help=(
            "Quando um insumo tiver mais de um candidato ambíguo (ex.: duas Carteiras "
            "datadas sem 'Inicial'/'Final' no nome), pergunta no terminal qual usar em "
            "vez de só avisar e deixar em branco. Deixa o lote parado esperando resposta "
            "quando isso acontece — não use em execução desatendida."
        ),
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Log detalhado (DEBUG).")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    if not args.painel.exists():
        print(f"Arquivo não encontrado: {args.painel}", file=sys.stderr)
        return 2

    resultados = processar_em_lote(
        caminho_painel=args.painel,
        dry_run=args.dry_run,
        apenas_fundo=args.apenas_fundo,
        visible=args.visible,
        relatorio_csv=args.relatorio_csv,
        resolver_ambiguidade=prompt_resolver_ambiguidade if args.interativo else None,
        pasta_raiz_saida=str(args.pasta_saida) if args.pasta_saida else None,
    )

    if not resultados:
        print("Nenhum fundo marcado com 'X' foi encontrado para processar.")
        return 0

    print(f"\n{'Fundo':40} {'Status':30} Avisos")
    for r in resultados:
        avisos = f"{len(r.avisos)} aviso(s)" if r.avisos else ""
        print(f"{r.fundo:40} {r.status:30} {avisos}")
        if r.erro:
            print(f"    erro: {r.erro}")
        for aviso in r.avisos:
            print(f"    aviso: {aviso}")

    erros = sum(1 for r in resultados if r.status == config.STATUS_ERRO)
    return 1 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
