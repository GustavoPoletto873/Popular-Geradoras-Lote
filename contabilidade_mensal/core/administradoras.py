"""Catálogo de administradoras com login próprio na Britech (portado do projeto do Lucas: `britech/administradoras.py`).

`nome` tem que bater EXATAMENTE com o texto da coluna "Administrador" no Monday. `segredo_ref` é o NOME do
segredo (variáveis `BRITECH_<segredo_ref>_USER` / `_SENHA`), nunca o valor. Várias administradoras compartilham o
subdomínio (`url_adm`) mas têm credenciais próprias.
"""

from __future__ import annotations

from .models import Administradora

CATALOGO: tuple[tuple[str, str, str], ...] = (
    ("ID CORRETORA", "id", "ID_CORRETORA"),
    ("ID SERVIÇOS FIDUCIÁRIOS", "id", "ID_SERVICOS_FIDUCIARIOS"),
    ("AMÉRICA", "america", "AMERICA"),
    ("MF PEPPER", "mfpepper", "MFPEPPER"),
    ("RJI", "rji", "RJI"),
    ("ACTUAL", "libertasasset", "ACTUAL"),
    ("LIBERTAS", "libertasasset", "LIBERTAS"),
    ("DOME", "DOMEADMINISTRADORA", "DOME"),
    ("AMICORP", "denvercontabil", "AMICORP"),
    ("OURO PRETO", "denvercontabil", "OUROPRETO"),
    ("FINHEALTH", "denvercontabil", "FINHEALTH"),
    ("ATIVA", "ativa", "ATIVA"),
)

_POR_NOME = {nome: (url_adm, segredo_ref) for nome, url_adm, segredo_ref in CATALOGO}


def garantir_administradora(nome: str) -> Administradora | None:
    """Devolve a Administradora do catálogo (criando se preciso); None se o nome não está no catálogo."""
    dados = _POR_NOME.get((nome or "").strip())
    if dados is None:
        return None
    url_adm, segredo_ref = dados
    administradora, _ = Administradora.objects.get_or_create(
        nome=nome.strip(), defaults={"url_adm": url_adm, "segredo_ref": segredo_ref}
    )
    return administradora
