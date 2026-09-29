"""Cliente HTTP da API REST da Britech (`https://<adm>.britech.com.br/WS/api/...`, HTTP Basic).

- Mantém as URLs exatamente como o downloader do Simplifica as monta (query string pronta,
  sem `params=`), para não alterar o que o servidor recebe.
- Traduz falhas de rede/HTTP para a taxonomia de `erros.py`:

    timeout / sem conexão   → TimeoutBritech / ErroApiBritech (retentáveis)
    401, 403                → AutenticacaoFalhou (nunca retenta; abre o disjuntor)
    429                     → LimiteTaxa (respeita Retry-After)
    5xx                     → ErroApiBritech retentável;   outros 4xx → não retentável
"""

from __future__ import annotations

import logging

import requests

from ..erros import AutenticacaoFalhou, ErroApiBritech, LimiteTaxa, TimeoutBritech

logger = logging.getLogger(__name__)

TIMEOUT_PADRAO = (10.0, 180.0)  # (conexão, leitura) em segundos — relatórios Excel podem demorar


def _espera_do_retry_after(resposta: requests.Response, padrao: float = 60.0) -> float:
    bruto = resposta.headers.get("Retry-After", "")
    try:
        return max(1.0, float(bruto))
    except ValueError:
        return padrao


class ClienteBritech:
    def __init__(
        self,
        url_adm: str,
        usuario: str,
        senha: str,
        *,
        sessao: requests.Session | None = None,
        timeout: tuple[float, float] = TIMEOUT_PADRAO,
    ) -> None:
        self.base = f"https://{url_adm}.britech.com.br/WS/api"
        self._auth = (usuario, senha)
        self._sessao = sessao or requests.Session()
        self._timeout = timeout

    def fechar(self) -> None:
        self._sessao.close()

    def get(self, caminho_e_query: str) -> requests.Response:
        """GET em `<base>/<caminho_e_query>`; só devolve respostas 2xx."""
        url = f"{self.base}/{caminho_e_query.lstrip('/')}"
        try:
            resposta = self._sessao.get(url, auth=self._auth, timeout=self._timeout)
        except requests.Timeout as exc:
            raise TimeoutBritech(f"tempo esgotado em {caminho_e_query.split('?')[0]}") from exc
        except requests.ConnectionError as exc:
            raise ErroApiBritech(f"sem conexão com a Britech ({type(exc).__name__})") from exc
        self._validar(resposta, caminho_e_query)
        return resposta

    def get_bytes(self, caminho_e_query: str) -> bytes:
        return self.get(caminho_e_query).content

    def get_json(self, caminho_e_query: str):
        resposta = self.get(caminho_e_query)
        try:
            return resposta.json()
        except ValueError as exc:
            raise ErroApiBritech(
                f"resposta não é JSON em {caminho_e_query.split('?')[0]}", status_http=resposta.status_code
            ) from exc

    @staticmethod
    def _validar(resposta: requests.Response, caminho_e_query: str) -> None:
        status = resposta.status_code
        if 200 <= status < 300:
            return
        endpoint = caminho_e_query.split("?")[0]
        if status in (401, 403):
            raise AutenticacaoFalhou(f"HTTP {status} em {endpoint}")
        if status == 429:
            raise LimiteTaxa(f"HTTP 429 em {endpoint}", espera_s=_espera_do_retry_after(resposta))
        raise ErroApiBritech(f"HTTP {status} em {endpoint}", status_http=status)
