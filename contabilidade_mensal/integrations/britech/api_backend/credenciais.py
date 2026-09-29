"""Credenciais da Britech por administradora.

Nunca em código nem em banco: `Administradora.segredo_ref` guarda só o NOME do segredo.
Esta implementação lê variáveis de ambiente `BRITECH_<segredo_ref>_USER` / `_SENHA` (mesmo
padrão do projeto do Lucas). A implementação com Secret Manager entra na Fase 0/7 sem mexer
em quem usa `ProvedorCredenciais`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Protocol

from ..erros import AutenticacaoFalhou


@dataclass(frozen=True)
class Credencial:
    usuario: str
    senha: str = field(repr=False)  # nunca aparece em repr/log


class ProvedorCredenciais(Protocol):
    def obter(self, segredo_ref: str) -> Credencial: ...


class CredenciaisDoAmbiente:
    def __init__(self, ambiente: Mapping[str, str] | None = None) -> None:
        self._ambiente = ambiente if ambiente is not None else os.environ

    def obter(self, segredo_ref: str) -> Credencial:
        if not segredo_ref:
            raise AutenticacaoFalhou("administradora sem `segredo_ref` configurado")
        prefixo = f"BRITECH_{segredo_ref}"
        usuario = self._ambiente.get(f"{prefixo}_USER", "")
        senha = self._ambiente.get(f"{prefixo}_SENHA", "")
        if not usuario or not senha:
            # a mensagem cita o NOME das variáveis esperadas, nunca valores
            raise AutenticacaoFalhou(f"credencial ausente: defina {prefixo}_USER e {prefixo}_SENHA")
        return Credencial(usuario=usuario, senha=senha)
