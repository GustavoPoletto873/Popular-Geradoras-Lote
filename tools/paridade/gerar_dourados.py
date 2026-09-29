"""ORÁCULO de paridade: roda o código ORIGINAL do Simplifica (pandas 2) sobre as entradas sintéticas
e grava o que ele produziu (planilhas + URLs chamadas) em tests/dourados/<cenario>/.

Uso (com a venv-oráculo, Python 3.12 + pandas<3 — o original não roda em pandas 3):

    C:\\Users\\<voce>\\.venvs\\oraculo312\\Scripts\\python.exe tools\\paridade\\gerar_dourados.py ^
        --simplifica "G:\\...\\PEDRÃO\\Erro mensal contabilidade\\britech_mensal_contabilidade" ^
        --frank "G:\\...\\FRANK\\PYTHON\\carteira_britech_V2"

O código original NÃO é copiado para este repositório: é lido direto das pastas indicadas.
Streamlit é substituído por um dublê e `requests.get` devolve as respostas sintéticas.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from tests.paridade import cenarios  # noqa: E402

URLS: list[str] = []
CENARIO_ATUAL: dict = {}


class Resposta:
    def __init__(self, conteudo: bytes = b"", dados=None, status: int = 200) -> None:
        self.status_code = status
        self.content = conteudo
        self._dados = dados
        self.text = conteudo[:80].decode("latin-1")

    def json(self):
        return self._dados


def _rotear(url: str, auth=None, **_):
    URLS.append(url)
    if "TipoArquivo=PDF" in url:
        return Resposta(b"%PDF-1.4 sintetico")
    if "BuscaListaFundos" in url:
        raise AssertionError("o oráculo não chama o cadastro")
    achado = re.search(r"(?:IdCarteira|IdCliente|IdsCarteira|idCarteira)=(\d+)", url)
    id_classe = achado.group(1) if achado else "111"
    tipo, dados = cenarios.entrada(CENARIO_ATUAL["nome"], id_classe)
    return Resposta(dados) if tipo == "bytes" else Resposta(b"[]", dados)


def carregar(nome: str, caminho: Path):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _linhas_base(classes=None):
    f = cenarios.FUNDO
    comum = {
        "CNPJ": f["cnpj"], "Fundo": f["fundo"], "Tipo": f["tipo"], "Mês Exercício": f["exercicio_nome"],
        "ANO_EXERCICIO_PROXIMO": f["ano_exercicio_proximo"], "MES_EXERCICIO": cenarios.FIM_ANTERIOR,
        "DATA_INICIO_EXERCICIO": cenarios.INICIO_EXERCICIO, "CarteiraFinal_X": "X",
    }  # fmt: skip
    if classes is None:
        return pd.DataFrame([{**comum, "Carteira": "111"}])
    return pd.DataFrame([{**comum, "ID_CLIENTE": cid, "NOME_CARTEIRA": nome} for cid, nome in classes])


def executar(nome: str, simplifica: Path, frank: Path, destino: Path) -> None:
    c = cenarios.CENARIOS[nome]
    CENARIO_ATUAL.clear()
    CENARIO_ATUAL["nome"] = nome
    URLS.clear()
    tmp = Path(tempfile.mkdtemp(prefix="oraculo_"))
    kind = c["kind"]

    if kind == "carteira":
        carregar("carteira_ctb_britech", simplifica / "carteira_ctb_britech.py").main(
            cenarios.DATA_FINAL, _linhas_base(), str(tmp), "id", "u", "p", carteira_inicio=c["inicial"]
        )
    elif kind == "extrato":
        carregar("caixa_ctb_britech", simplifica / "caixa_ctb_britech.py").main(
            cenarios.DATA_FINAL, _linhas_base(), str(tmp), "id", "u", "p"
        )
    else:
        passivo = _linhas_base(c["classes"])
        if kind == "mov":
            carregar("mov_cotista_ctb_britech", simplifica / "mov_cotista_ctb_britech.py").main(
                cenarios.DATA_FINAL, passivo, str(tmp), "id", "u", "p"
            )
        elif kind == "posicao":
            carregar("posicao_cotista_ctb_britech1", simplifica / "posição_cotista_ctb_britech1.py").main(
                cenarios.DATA_FINAL, passivo, str(tmp), "id", "u", "p", c["inicial"]
            )
        else:
            carregar("historico_cota_ctb_britech", simplifica / "histórico_cota_ctb_britech.py").main(
                cenarios.DATA_FINAL, passivo, str(tmp), "id", "u", "p"
            )
        # empilhamento das classes (passo seguinte do fluxo do Simplifica)
        carregar("empilhar_relatorios_passivo", simplifica / "empilhar_relatorios_passivo.py").main(
            cenarios.DATA_FINAL, _linhas_base(), str(tmp)
        )

    pasta_saida = destino / nome / "saida"
    if pasta_saida.exists():
        shutil.rmtree(pasta_saida)
    pasta_saida.mkdir(parents=True)
    for insumos in tmp.rglob("Insumos"):
        for arquivo in insumos.rglob("*"):
            if arquivo.is_file() and arquivo.suffix in (".xlsx", ".pdf"):
                alvo = pasta_saida / arquivo.relative_to(insumos)
                alvo.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(arquivo, alvo)
    (destino / nome / "urls.json").write_text(json.dumps(URLS, indent=1, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    gerados = sorted(str(p.relative_to(pasta_saida)) for p in pasta_saida.rglob("*") if p.is_file())
    print(f"[{nome}] {len(URLS)} chamada(s); arquivos: {gerados}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simplifica", required=True, type=Path)
    ap.add_argument("--frank", required=True, type=Path, help="pasta com carteira_britech_idV2.py")
    ap.add_argument("--destino", type=Path, default=RAIZ / "tests" / "dourados")
    ap.add_argument("cenarios", nargs="*", help="padrão: todos")
    args = ap.parse_args()

    sys.modules["streamlit"] = MagicMock()  # o original usa st.write/st.error como log
    requests.get = _rotear  # nenhuma chamada de rede real
    sys.path.insert(0, str(args.frank))

    print(f"pandas {pd.__version__} | oráculo lendo {args.simplifica}")
    for nome in args.cenarios or cenarios.CENARIOS:
        executar(nome, args.simplifica, args.frank, args.destino)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
