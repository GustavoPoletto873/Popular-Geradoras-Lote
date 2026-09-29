"""Exceções tipadas da camada Britech (contrato de erros: docs/unificacao/05_arquitetura.md §2.2).

Cada classe declara:
  - `codigo`: slug gravado em `EtapaExecucao.erro_tipo`;
  - `retentavel`: o pipeline pode tentar de novo (com backoff)?
  - `conta_para_disjuntor`: entra na contagem do circuit breaker?
"""

from __future__ import annotations


class BritechErro(Exception):
    codigo = "erro_britech"
    retentavel = False
    conta_para_disjuntor = False

    def __init__(self, mensagem: str = "", *, espera_s: float | None = None) -> None:
        super().__init__(mensagem or self.codigo)
        self.espera_s = espera_s  # sugestão de espera antes da próxima tentativa


class AutenticacaoFalhou(BritechErro):
    """Usuário/senha recusados. Nunca retentar (evita bloquear a conta)."""

    codigo = "autenticacao_falhou"
    conta_para_disjuntor = True


class SessaoBloqueada(BritechErro):
    """Login barrado por sessão presa / logout não confirmado."""

    codigo = "sessao_bloqueada"
    retentavel = True
    conta_para_disjuntor = True

    def __init__(self, mensagem: str = "", *, espera_s: float | None = 300.0) -> None:
        super().__init__(mensagem, espera_s=espera_s)


class TelaMudou(BritechErro):
    """Seletor/estrutura inesperada — repetir não adianta."""

    codigo = "tela_mudou"
    conta_para_disjuntor = True


class EstruturaInesperada(BritechErro):
    """A resposta da API (planilha/JSON) não tem a estrutura que a transformação espera.
    Repetir não adianta; se vários fundos falham assim, o disjuntor abre (provável mudança da Britech)."""

    codigo = "estrutura_inesperada"
    conta_para_disjuntor = True


class CadastroIncompleto(BritechErro):
    """Faltam dados do fundo necessários para a consulta (ex.: mês do exercício, CNPJ)."""

    codigo = "cadastro_incompleto"


class CarteiraNaoEncontrada(BritechErro):
    """Busca retornou 0 ou mais de 1 resultado — problema de cadastro, específico do fundo."""

    codigo = "carteira_nao_encontrada"


class ProcessamentoPendente(BritechErro):
    """A Britech ainda está processando. Não é falha: o pipeline entra em `aguardando_britech`."""

    codigo = "processamento_pendente"
    retentavel = True


class TimeoutBritech(BritechErro):
    codigo = "timeout_britech"
    retentavel = True
    conta_para_disjuntor = True


class ArquivoInvalido(BritechErro):
    """Download vazio ou em formato inesperado."""

    codigo = "arquivo_invalido"
    retentavel = True


class ErroApiBritech(BritechErro):
    """Falha da API REST. 5xx/timeout e 429 são retentáveis; os demais 4xx não."""

    codigo = "erro_api_britech"
    conta_para_disjuntor = True

    def __init__(self, mensagem: str = "", *, status_http: int | None = None, espera_s: float | None = None) -> None:
        super().__init__(mensagem, espera_s=espera_s)
        self.status_http = status_http
        self.retentavel = status_http is None or status_http >= 500 or status_http == 429


class LimiteTaxa(ErroApiBritech):
    """HTTP 429 — respeita `Retry-After` e não conta para o disjuntor."""

    codigo = "limite_taxa"
    conta_para_disjuntor = False

    def __init__(self, mensagem: str = "", *, espera_s: float | None = 60.0) -> None:
        super().__init__(mensagem, status_http=429, espera_s=espera_s)


class ProcessamentoNaoAutorizado(BritechErro):
    """Tentativa de clicar em "Processar" (altera dados na Britech) fora da allowlist. Nunca retentar."""

    codigo = "processamento_nao_autorizado"


class OperacaoNaoSuportada(BritechErro):
    """O backend escolhido para a operação não a implementa."""

    codigo = "operacao_nao_suportada"


class BackendNaoDisponivel(BritechErro):
    """Configuração aponta para um backend que ainda não existe (ex.: `api` antes da Fase 2)."""

    codigo = "backend_nao_disponivel"
