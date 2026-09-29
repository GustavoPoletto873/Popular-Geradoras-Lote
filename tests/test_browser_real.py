"""Critério de pronto da Fase 3 na Britech REAL. Só roda com `--run-browser` e credenciais no ambiente:

    set BRITECH_ID_CORRETORA_USER=...  &  set BRITECH_ID_CORRETORA_SENHA=...
    set BROWSER_REAL_REPETICOES=20      (opcional; padrão 3)
    python -m pytest tests/test_browser_real.py --run-browser -q

Não seleciona carteira nem clica em "Processar".
"""

import os

import pytest

from contabilidade_mensal.integrations.britech.api_backend.credenciais import CredenciaisDoAmbiente
from contabilidade_mensal.integrations.britech.browser_backend.backend import BrowserBackend
from contabilidade_mensal.integrations.britech.browser_backend.config import ConfigNavegador
from contabilidade_mensal.integrations.britech.browser_backend.diagnostico import verificar_sessao
from contabilidade_mensal.integrations.britech.interface import AdministradoraRef

pytestmark = pytest.mark.browser


def test_login_telas_e_logout_repetidos_sem_sessao_presa(tmp_path):
    if not (os.environ.get("BRITECH_ID_CORRETORA_USER") and os.environ.get("BRITECH_ID_CORRETORA_SENHA")):
        pytest.skip("defina BRITECH_ID_CORRETORA_USER e BRITECH_ID_CORRETORA_SENHA")
    repeticoes = int(os.environ.get("BROWSER_REAL_REPETICOES", "3"))
    backend = BrowserBackend(CredenciaisDoAmbiente(), ConfigNavegador(pasta_evidencias=tmp_path / "evidencias"))
    resultados = verificar_sessao(backend, AdministradoraRef("ID CORRETORA", "id", "ID_CORRETORA"), repeticoes=repeticoes)
    assert len(resultados) == repeticoes
