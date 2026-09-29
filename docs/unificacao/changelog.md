# Changelog da unificação

## Fase 3 — Playwright: sessão e Page Objects · 2026-09-29

Plano: `06_plano_migracao.md` (Fase 3). Só a base do backend `browser`; os fluxos (processar, polling, baixar balancete por competência) são a Fase 4.

### O que mudou

- **`integrations/britech/browser_backend/`**
  - `seletores.py` — **todos** os seletores num só arquivo (portados do projeto do Lucas). Mudou a tela da Britech → só este arquivo (e o Page Object) muda.
  - `pages/login_page.py`, `processo_contabil_page.py`, `balancete_page.py` — Page Objects. Falhas viram erros tipados: login recusado → `AutenticacaoFalhou` (nunca retentar), menu/campo ausente → `TelaMudou`, 0 ou 2+ resultados → `CarteiraNaoEncontrada`, sessão que cai → `SessaoBloqueada`, download vazio → `ArquivoInvalido`.
  - `session.py` — `SessaoNavegador`: login e logout **confirmados** (a tela de login tem que reaparecer), `fechar()` idempotente, screenshot + trace em falha (`evidencias`), trace **iniciado só depois do login** e descartado em sucesso.
  - `backend.py` — `BrowserBackend` registrado no factory (`BRITECH_BACKEND_<OP>=browser`). Nesta fase só abre/fecha a sessão; as demais operações levantam `OperacaoNaoSuportada`.
  - `diagnostico.py` + comando **`testar_navegador_britech`** (`--repeticoes N`, `--headed`): login → abre Processo Contábil e Balancete → logout, N vezes. **Não seleciona carteira e não clica em Processar.**
- **Config:** `settings.BROWSER` (`BROWSER_HEADLESS`, `BROWSER_TIMEOUT_MS`, `BROWSER_EVIDENCIAS`); `playwright>=1.60` em `requirements.txt` (depois: `playwright install chromium`).

### Decisões e desvios em relação ao projeto do Lucas

1. **Thread dedicada para o Playwright.** A API síncrona deixa um event loop ativo na thread, e o ORM do Django recusa consultas nessa situação; o worker grava no banco entre as ações. Todo acesso ao navegador passa por `SessaoNavegador.executar(...)`, que roda numa thread própria (há teste com o ORM em uso e a sessão aberta).
2. **Sem pausa fixa.** Nenhum `wait_for_timeout`/`sleep` (há teste que varre o pacote). Esperas são por estado: célula do grid com o id (prova de que o filtro refletiu), `aria-checked`, tela de login reaparecendo. A busca no iframe reavalia a lista de frames e espera cada candidato por estado.
3. **Senha nunca em mensagem de erro/traceback:** o log de chamadas do Playwright inclui o argumento do `fill(...)`; o login relança `TelaMudou` com a senha removida e `from None`. Teste dedicado. O trace só cobre o que vem depois do login (verificado: a senha não aparece em nenhum arquivo do zip).
4. **Login recusado vs. tela mudou:** se o menu "Processamento" não aparece e a tela de login **continua** aberta → `AutenticacaoFalhou`; senão → `TelaMudou`. Não sei qual mensagem a Britech mostra para senha errada nem para sessão presa (Q12); os dois casos caem em `AutenticacaoFalhou`.
5. **Balancete:** no Lucas o filtro era aplicado com `Enter` + 800 ms de espera. Aqui espera-se a célula `td.dxgv[title=<id>]` dentro da lista do balancete. **Suposição não verificada:** que o grid do balancete usa o mesmo padrão de `title` do Processo Contábil.
6. **Checkbox sem `aria-checked`:** o Lucas tolerava; mantive, mas com aviso no log (não dá para confirmar a seleção).

### Testes

- **PAS falsa** (`tests/pas_falsa.py`): HTML mínimo com os mesmos ids, interceptado por `context.route`; qualquer requisição que não seja `*.britech.com.br` é abortada e o teste confere que nada escapou. **26 testes** (`tests/test_browser_backend.py`): login/logout, senha errada, logout preso, sessão que cai, 5 sessões seguidas sem sessão presa, seleção cumulativa, carteira inexistente/ambígua, evidência (png + trace sem a senha), download do balancete, troca de carteira, ORM com sessão aberta. Rodam por padrão se o Chromium do Playwright estiver instalado (~2 min).
- **Britech real:** `tests/test_browser_real.py` (`--run-browser` + credenciais) e o comando acima. **Ainda não executados** — sem credenciais aqui.
- Suíte completa: **311 passando, 3 pulados** (2 Postgres + o teste real).

### Como validar com a Britech real (critério de pronto — **ainda não executado**)

```
set BRITECH_ID_CORRETORA_USER=...  &  set BRITECH_ID_CORRETORA_SENHA=...      (nunca em arquivo)
playwright install chromium
python manage.py testar_navegador_britech --administradora "ID CORRETORA" --repeticoes 20 --headed
```

### Pendente / não verificado

- Os seletores só foram exercitados contra a PAS **falsa**; a PAS real pode divergir (DevExpress, iframes, tempos). O comando acima é o teste de verdade.
- Sessão única por usuário (Q12) e MFA/IP (Q10) continuam sem resposta.
- **Nada foi commitado.**

## Fase 2 — Insumos por API · 2026-09-29

Plano: `06_plano_migracao.md` (Fase 2). Mudança de rumo junto com esta fase: **não usaremos n8n**; agendamento e disparo passam a ser do **Agendador de Tarefas do Windows** chamando *management commands* (`05_arquitetura.md` §4.1, plano Fases 5 e 7, Q24).

### O que mudou

- **`integrations/britech/api_backend/`** — `ClienteBritech` (HTTP Basic, timeouts, mapeamento de status → erros tipados: 401/403 `AutenticacaoFalhou`, 429 `LimiteTaxa` com `Retry-After`, 5xx retentável, timeout), `CredenciaisDoAmbiente` (`BRITECH_<SEGREDO_REF>_USER/_SENHA`, senha nunca no `repr`), construtores de URL idênticos aos do Simplifica, leitura do cadastro (`BuscaListaFundos`) e `ApiBackend.baixar_insumo` para os 7 insumos. Fundos com mais de uma classe geram os arquivos por classe em `Arquivos separados/` e o consolidado empilhado. PDFs de evidência saem como complementos (`insumo_pdf`) e **não** derrubam a etapa se falharem.
- **`api_backend/transformacoes/`** — funções puras (carteira, extrato, mov. cotista, posição do cotista, histórico de cota, empilhar) portadas do código original, compatíveis com pandas 3.
- **`core/calendario.py`** — dias úteis (feriados nacionais + Carnaval, Sexta Santa, Corpus Christi), data final, fim do exercício anterior e início.
- **Monday** — `integrations/monday/` (cliente GraphQL paginado, sincronização idempotente com relatório) e `core/administradoras.py` (catálogo das 12 administradoras). Comando `sincronizar_cadastro [--dry-run]`; token só por `MONDAY_API_TOKEN`. Grava CNPJ e mês do exercício em `Fundo` (avanço em Q7).
- **Comandos de validação manual:** `baixar_insumos_api` (um fundo, só leitura, imprime nome/tamanho/SHA-256) e `comparar_insumos` (compara duas pastas célula a célula; pareia por competência + CNPJ + tipo ignorando o id da carteira no nome; sai com erro se diferir). Biblioteca em `storage/comparacao.py`.
- **`requirements.txt`** ganhou `requests`, `pandas`, `openpyxl`, `holidays`; `.env.example` ganhou as variáveis de credencial e do Monday.

### Paridade com o código original

O original (Simplifica) **não roda em pandas 3** (`fillna(method=)`, `dtype=='object'`, atribuição em `columns.values`). Por isso: um **oráculo** executa o código original numa venv isolada (Python 3.12 + pandas 2.3.3) sobre entradas sintéticas e grava o resultado em `tests/dourados/`; os testes comparam a nossa saída célula a célula (`assert_frame_equal(..., atol=0)`) e as URLs chamadas. O código original não é copiado para este repositório.

Regenerar os dourados (só se as entradas em `tests/paridade/` mudarem):

```
C:\Users\gustavo.guerios_denv\.venvs\oraculo312\Scripts\python.exe tools\paridade\gerar_dourados.py --simplifica "<pasta britech_mensal_contabilidade>" --frank "<pasta carteira_britech_V2>"
```

### Como validar com um fundo real (critério de pronto — **ainda não executado**)

```
set BRITECH_ID_CORRETORA_USER=...   &  set BRITECH_ID_CORRETORA_SENHA=...     (nunca em arquivo)
set MONDAY_API_TOKEN=...
python manage.py migrate
python manage.py sincronizar_cadastro
python manage.py baixar_insumos_api --administradora "ID CORRETORA" --carteira <id> --ano 2026 --mes 8 --destino C:\tmp\api
python manage.py comparar_insumos --a C:\tmp\api --b "<Insumos gerado pelo Simplifica>"
```

### Quirks do original preservados de propósito

`MovCotista`: a URL sai com `{data_inicio}`/`{DataFimArquivo}` literais; histórico de cota: `DataFim=str(datetime)`; posição empilhada perde a coluna `'Valor Pendente Liquidação.'` (com ponto final no nome); datas com `dayfirst=True`.

### Desvios em relação ao original

1. Fundo de classe única: nome **canônico sem o id** (o original às vezes o deixava no nome); o comparador ignora essa diferença.
2. PDFs viram complementos não fatais.
3. Resposta inválida/estrutura inesperada levanta `ArquivoInvalido`/`EstruturaInesperada` (conta para o disjuntor) em vez de devolver `None` e seguir.
4. Aba de posição vazia devolve "Sem dados aplicação" em vez de quebrar.
5. **Administradora América não portada** (lê cadastro de um Excel local; Q26).

### Testes

285 passando, 2 pulados (Postgres). Novos: calendário (24), paridade das transformações (20), backend API e cliente HTTP (37), Monday (22), comparação/comandos (12).

### Pendente / não verificado

- **Nenhuma chamada real à Britech** (sem credenciais neste ambiente): a comparação real acima é sua, e os limites de taxa continuam desconhecidos.
- Fase 0 (rotação de credenciais, Q11/Q25), Postgres concorrente, Excel/Drive/Playwright reais.
- **Nada foi commitado**; as Fases 1 e 2 estão na mesma árvore de trabalho.

## Fase 1 — Esqueleto · branch `unificacao/fase-1-esqueleto` · 2026-09-29

Plano: `06_plano_migracao.md` (Fase 1). Critério de pronto atendido: `pytest` verde e um pipeline de brinquedo (etapas fake) rodando com falha injetada, retry, `pulado` por idempotência e reprocesso `forcar`, **sem nenhuma dependência de Britech, Excel ou Playwright**.

### O que mudou

- **Projeto Django** (`manage.py`, `config/settings/{base,dev,homolog,prod,test}.py`) com feature flags por operação (`BRITECH_BACKEND_<OPERACAO>`), dry-run e allowlist para as operações que alteram dados (`processar_contabil`, `publicar_drive`). `prod` recusa subir com backend `fake`.
- **`contabilidade_mensal.core`** — modelos da seção 3 do doc de arquitetura (`Administradora`, `Fundo`, `Competencia`, `Execucao`, `EtapaExecucao`, `EstadoEtapa`, `Artefato`, `PastaCompetencia`, `Disjuntor`, `TravaRecurso`), migração `0001`, admin (com ação "reprocessar") e `dominio.py` (nome da pasta `Data Base <mês> <ano>` / `AAAAMM`).
- **`contabilidade_mensal.pipeline`** — grafo de dependências e filas (`definicao`), máquina de estados validada (`estados`), fila com lease sobre `EtapaExecucao` (`fila`), travas por credencial (`travas`), disjuntor com meia-abertura (`disjuntor`), backoff com jitter (`backoff`), idempotência por artefatos íntegros (`artefatos`), criação de execução com `forcar`/`cascata` (`servicos`), executor com tradução de erro → transição (`executor`), worker (`worker`) e relógio simulado (`relogio`).
- **`contabilidade_mensal.integrations.britech`** — `BritechGateway` (roteia cada operação para o backend configurado, sessões preguiçosas, logout garantido), DTOs e `Protocol` do backend (`interface`), exceções tipadas com `retentavel`/`conta_para_disjuntor` (`erros`), **backend `fake` roteirizável** (`fake`) e nomes canônicos de arquivo (`nomes`).
- **`observability/logging.py`** — log JSON com contexto por `contextvars` (`execucao_id`, `correlation_id`, `fundo`, `competencia`, `etapa`, `backend`, `tentativa`, `worker_id`) e máscara de valores sensíveis.
- **`storage/`** — SHA-256 e diretório de staging por execução.
- **Comandos:** `run_worker --fila api|browser|excel|drive [--once]` (só com backends `fake` nesta fase) e `rodar_demo` (pipeline de brinquedo com matriz fundo × etapa).
- **Testes:** 169 passando + 2 de concorrência em Postgres (pulados sem Postgres). Marcadores `browser` (só com `--run-browser`) e `postgres` (só com `DB_ENGINE=postgres`). Os 26 testes do populador continuam passando.
- **Infra do repositório:** `.gitignore` (segredos, `var/`, `staging/`…), `requirements*.txt`, `pytest.ini`, `.env.example`, `README.md`.

### Como testar

```bash
pip install -r requirements-dev.txt
python -m pytest -q                      # 169 passed, 2 skipped
python manage.py migrate
python manage.py rodar_demo              # A e B completos; C falha no balancete e o resto vira "pulado"
python manage.py run_worker --fila api --once
```

Concorrência em Postgres (não executada neste ambiente): instruções no docstring de `tests/test_concorrencia_postgres.py`.

### Decisões e desvios em relação a `05_arquitetura.md`

1. **Trava em tabela própria (`TravaRecurso`, unique em `chave`) em vez de "não existir outra `em_andamento` com o mesmo `lock_key`".** O segundo desenho tem corrida (dois workers passam no `NOT EXISTS` ao mesmo tempo); a unicidade da chave resolve a corrida e ainda permite o lote (vários fundos da mesma credencial na mesma sessão). Acrescentado ao modelo.
2. **Fila por compare-and-set** (`UPDATE … WHERE status=<esperado>`), não `SKIP LOCKED`: igual em SQLite e Postgres, e suficiente para o volume. `SKIP LOCKED` fica como otimização se aparecer contenção.
3. **`pulado` também significa "dependência falhou"** (`erro_tipo=dependencia_falhou`): sem isso a execução nunca fecharia. Ela termina `concluida_com_falhas`. A transição `pulado → pendente` foi acrescentada para o reprocesso.
4. **Idempotência decidida ao reivindicar** (`pendente → pulado`, `erro_tipo=idempotencia`), antes de pegar trava ou disjuntor: etapa já concluída *e* com artefatos íntegros (arquivo local com mesmo SHA-256, ou verificado no Drive).
5. **Exceção que não é `BritechErro` → falha imediata (`erro_inesperado`), sem retry:** bug não se conserta repetindo.
6. **Polling:** consultas de status não contam como tentativa e cada consulta é uma sessão curta (login → consulta → logout), liberando a credencial entre elas (validado no teste: 1 disparo + 3 consultas = 4 sessões, todas fechadas).
7. **Dry-run do "Processar":** a etapa termina `sucesso` na hora (com `dados.dry_run`) e não espera; o balancete seguinte rodaria sobre contabilidade não processada — só serve para teste/ensaio.
8. **Heartbeat automático não foi implementado** (Fase 7). O lease padrão é 300 s; `renovar_lease` já existe.
9. **Nomes canônicos:** insumos seguem o downloader do Simplifica (`AAAAMM_<cnpj>_CarteiraFinal.xlsx` …, testado contra nomes reais). **Proposta nova:** balancete como `AAAAMM_<cnpj>_BalanceteContabilFinal.(pdf|xls)`; um teste garante que o populador o reconhece.
10. **Regra do exercício** (`Data Base <mês> <ano>` = ano em que *termina* o exercício que contém a competência) inferida de 4 fundos reais (ACELERA CASH, LAZIO II, KRONOS, ALPHA) e coberta por 11 casos de teste. **A fonte de `exercicio_mes` por fundo continua em aberto (Q7).**
11. **Git:** a pasta não era um repositório. Criei com `git init --separate-git-dir` apontando para `C:\Users\gustavo.guerios_denv\.git-dirs\popular-geradoras-em-lote.git` (para não sincronizar objetos do Git pelo Google Drive). **Nada foi commitado.**

### Pendente / não verificado

- **Concorrência em Postgres:** escrita, mas não executada (sem Postgres e com o Docker Desktop desligado).
- **Fase 0 (segurança):** rotacionar credenciais expostas continua sendo ação sua/do time (Q11).
- Nenhuma chamada real à Britech, ao Excel, ao Drive ou ao Playwright; `api`/`browser` só existem como nomes reservados no `factory`.
- O populador (`populador/`, `cli.py`) segue como está; vira `integrations/excel` na Fase 6.

### Próximo passo

Fase 2 (feita — ver acima).
