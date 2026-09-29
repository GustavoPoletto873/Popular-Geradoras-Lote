"""
Construção de caminhos e busca de arquivos — porte 1:1 da lógica de path do
VBA (ProcessarEmLoop / CopiarArquivoOrigem), sem nenhuma dependência de COM/
Excel. Isso é testável sem abrir planilha nenhuma.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import config


@dataclass(frozen=True)
class CaminhosFundo:
    pasta_origem: Path   # onde buscar o arquivo do período anterior — sempre a pasta real
    pasta_insumos: Path  # onde buscar os insumos do período atual — sempre a pasta real
    pasta_saida: Path    # onde escrever a conciliação gerada — pode ser redirecionada


def montar_caminhos(
    pasta_raiz: str,
    tipo: str,
    fundo: str,
    exercicio: str,
    periodo_origem: str,
    periodo_destino: str,
    pasta_raiz_saida: str | None = None,
) -> CaminhosFundo:
    """
    Réplica exata de:
        pastaRaiz = Range("C2") & "\\" & Range("F" & linha)
        caminhoCompletoArquivoOrigem = pastaRaiz & "\\" & nomeFundo & "\\" &
            "Data Base " & exercicio & "\\" & nomePastaProcurada & "\\"
        caminhoCompletoArquivoDestino = pastaRaiz & "\\" & nomeFundo & "\\" &
            "Data Base " & exercicio & "\\" & nomePastaDestino & "\\"

    `pasta_raiz_saida`, quando informada, redireciona SÓ a escrita da
    conciliação gerada para uma raiz diferente (mesma estrutura de
    subpastas), mantendo a leitura do arquivo anterior e dos insumos sempre
    na pasta real — usado para testar contra produção sem escrever nela
    (ver cli.py `--pasta-saida`).
    """
    base_real = Path(pasta_raiz) / tipo / fundo / f"Data Base {exercicio}"
    pasta_destino_real = base_real / periodo_destino

    if pasta_raiz_saida is not None:
        pasta_saida = (
            Path(pasta_raiz_saida) / tipo / fundo / f"Data Base {exercicio}" / periodo_destino
        )
    else:
        pasta_saida = pasta_destino_real

    return CaminhosFundo(
        pasta_origem=base_real / periodo_origem,
        pasta_insumos=pasta_destino_real / config.SUBPASTA_INSUMOS,
        pasta_saida=pasta_saida,
    )


def saida_ja_existe(pasta_destino: Path) -> bool:
    """
    Réplica de:
        Dir(caminhoCompletoArquivoDestino & "*.BAT*") <> "" Or
        Dir(...*.xlsm) <> "" Or Dir(...*.xlsx) <> "" Or
        Dir(...*.xls) <> "" Or Dir(...*.xlsb) <> ""

    Nota: "*.xls" no VBA também casa .xlsx/.xlsm/.xlsb por serem prefixo,
    então o teste abaixo é equivalente: qualquer arquivo cuja extensão
    comece com uma das extensões configuradas, case-insensitive (Windows).
    """
    if not pasta_destino.exists():
        return False
    for item in pasta_destino.iterdir():
        if not item.is_file():
            continue
        nome = item.name.lower()
        if any(ext in nome for ext in config.EXTENSOES_SAIDA_EXISTENTE):
            return True
    return False


def encontrar_arquivo_origem(pasta_origem: Path) -> Path | None:
    """
    Réplica de:
        nomeArquivo = Dir(caminhoOrigem & "*" & "*.xls*")

    Isto é: primeiro arquivo da pasta de origem cujo nome contenha ".xls"
    (cobre .xls/.xlsx/.xlsm/.xlsb). Ordenação alfabética para ser
    determinístico — o VBA usa a ordem que o SO devolver, que não é
    garantida; normalmente só existe um candidato válido.
    """
    if not pasta_origem.exists():
        return None
    candidatos = sorted(
        p for p in pasta_origem.iterdir() if p.is_file() and ".xls" in p.name.lower()
    )
    return candidatos[0] if candidatos else None


def encontrar_insumos(pasta_insumos: Path, padrao: str) -> list[Path]:
    """
    Réplica de `InStr(Arquivo, padrao)` percorrendo a pasta de insumos.

    Sensível a maiúsculas/minúsculas, igual ao VBA (Option Compare Binary é
    o padrão nos módulos originais — não há `Option Compare Text`).
    """
    if not pasta_insumos.exists():
        return []
    return sorted(
        p for p in pasta_insumos.iterdir() if p.is_file() and padrao in p.name
    )


def nome_arquivo_destino(fundo: str, periodo_destino: str, extensao: str) -> str:
    """
    Réplica de:
        novoNomeArquivo = nomeFundo & " " & Range("C4").Value & "." & extensaoArquivo

    (extensaoArquivo aqui é sempre passado explicitamente pelo chamador —
    ver nota sobre o bug em runner.py.)
    """
    extensao = extensao.lstrip(".")
    return f"{fundo} {periodo_destino}.{extensao}"
