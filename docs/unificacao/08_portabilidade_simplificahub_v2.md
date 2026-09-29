# 08 — Portabilidade para o SimplificaHub_V2

Informação nova: depois de pronto, o app será **movido para o SimplificaHub_V2**. Não encontrei o código nem a descrição do V2 no Drive (só o `NOVOSIMPLIFICA.md`, que é uma lista de status de migração de apps do hub atual), então **não sei qual é a stack do V2** (Q31). Este documento registra o que já favorece a mudança, o que pode atrapalhar e o que eu faria em cada cenário — sem mudar nada antes da resposta.

## O que já ajuda

- **Tudo mora em pacotes independentes:** `contabilidade_mensal/` (Django: `core`, `pipeline`, `integrations`, `storage`, `observability`) e `populador/` (biblioteca do Excel). Não há dependência do resto do repositório.
- **Sem estado escondido:** configuração só por variáveis de ambiente/`settings` (lista abaixo); credenciais nunca no código.
- **Fronteiras por interface:** Britech (`BritechGateway`), Excel (`PopuladorExcel`), Drive (`PublicadorDrive`) e cadastro (Monday) são adapters trocáveis. Se o V2 já tiver seu próprio jeito de falar com o Drive ou de guardar segredos, troca-se o adapter, não o pipeline.
- **A "interface" do app são comandos de gerenciamento** (`iniciar_execucao`, `run_worker`, `mostrar_matriz`…) e o admin. Isso vale para qualquer casca: o V2 pode chamá-los por agendador ou embrulhá-los em telas.

## Configuração de que o app depende (contrato com o V2)

`DATABASES` (Postgres em produção), `STORAGE_ROOT`, `BRITECH_BACKENDS`, `DRY_RUN_*`, `ALLOWLIST_PROCESSAR_CONTABIL`, `PIPELINE`, `BROWSER`, `MONDAY`, `DRIVE_API`, `EXCEL_BACKEND`, `DRIVE_BACKEND`, `EXCEL_ORIGEM`, `BOLETA_RAIZ_LOCAL`, `PERMITIR_STUBS_EXCEL_DRIVE`; variáveis `BRITECH_<REF>_USER/_SENHA`, `MONDAY_API_TOKEN`, `DRIVE_API_TOKEN`.

## O que pode atrapalhar

| Risco | Por quê | O que fazer |
|---|---|---|
| **Nomes de app genéricos** (`core`, `pipeline`) | Se o V2 for Django, `core`/`pipeline` provavelmente colidem (rótulo do app e prefixo das tabelas `core_*`). Trocar depois, com dados em produção, é doloroso. | Se o V2 for Django: renomear agora os *labels* para algo como `cm_core`/`cm_pipeline` (migração inicial ainda não foi para produção). |
| **V2 não é Django** (ex.: Streamlit, FastAPI, Flask) | Os modelos, o admin e a fila dependem do ORM do Django. | Opção A: manter o Django como serviço próprio (workers + admin) e o V2 só embrulha (tela que chama os comandos/lê a matriz). Opção B: reescrever a camada de persistência — cara e desnecessária se A servir. |
| **Excel só roda em Windows** | O worker `excel` (COM) precisa de sessão de usuário na VM Windows, seja qual for o V2. | O V2 pode ficar em Linux; a fila `excel` continua na VM. Já é assim no desenho. |
| **Banco compartilhado ou separado** | Tabelas próprias no Postgres do V2 vs. banco dedicado. | Banco/esquema dedicado é o mais simples; se for compartilhado, usar prefixo de tabela. |
| **Autenticação/permissões** | Quem pode reprocessar, confirmar processamento, ver traces (sensíveis)? | Hoje só o admin do Django. No V2, mapear para o modelo de papéis dele. |
| **Segredos** | Hoje variáveis de ambiente; o V2 pode ter cofre/Secret Manager. | Trocar `CredenciaisDoAmbiente` (uma classe) pela implementação do cofre. |
| **Reuso do `drive_api`** | O V2 pode incorporar ou substituir esse serviço. | O app só conhece o contrato HTTP (`integrations/drive/cliente.py`). |

## Perguntas

- **Q31:** qual é a stack do SimplificaHub_V2 (Django? Streamlit? outra) e onde está o repositório/desenho? Ele terá banco, autenticação e agendador próprios?
- **Q32:** o "mover para o V2" é copiar o código para dentro do repositório dele, ou o V2 apenas *chama* este app como serviço?

Até responderem, o app continua **autônomo**, sem nada específico do V2.
