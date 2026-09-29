# Contabilidade mensal — automação (ID Corretora)

Este repositório reúne duas coisas:

1. **`populador/` + `cli.py`** — substituto em Python do botão `ProcessarEmLoop` do *Painel Populador* (etapa Excel). Funciona hoje; ver "Populador" abaixo.
2. **`contabilidade_mensal/`** — esqueleto do pipeline unificado (Britech por API/navegador → Excel → Drive), em construção. **Fases 1–3 prontas** (orquestração, fila, gateway fake; insumos por API, cadastro do Monday; sessão e telas do Playwright). Ainda não validado com a Britech real (ver changelog). Agendamento: **Agendador de Tarefas do Windows** (sem n8n).

Documentação de projeto: [`docs/unificacao/`](docs/unificacao/) (processo, arquitetura, plano, perguntas abertas, changelog).

## Configurar

```bash
python -m venv .venv && .venv\Scripts\activate      # fora do Shared Drive, de preferência
pip install -r requirements-dev.txt
copy .env.example .env                              # NUNCA em pasta compartilhada; não coloque segredos no Git
```

Banco: SQLite em `var/` por padrão (dev/teste). Homologação/produção exigem Postgres (`DB_ENGINE=postgres`, ver `.env.example`).

## Rodar

```bash
python -m pytest -q                       # suíte completa (Postgres e navegador são pulados por padrão)
python manage.py migrate
python manage.py rodar_demo               # pipeline de brinquedo: matriz fundo × etapa, com uma falha injetada
python manage.py run_worker --fila api --once
python manage.py sincronizar_cadastro --dry-run      # precisa de MONDAY_API_TOKEN
python manage.py baixar_insumos_api --administradora "ID CORRETORA" --carteira <id> --ano 2026 --mes 8 --destino C:\tmp\api
python manage.py comparar_insumos --a C:\tmp\api --b "<pasta Insumos do Simplifica>"
```

Credenciais da Britech: variáveis de ambiente `BRITECH_<REF>_USER` / `BRITECH_<REF>_SENHA` (ex.: `BRITECH_ID_CORRETORA_USER`). Nunca em arquivo versionado ou em pasta compartilhada.

- `--run-browser` liga os testes marcados `@pytest.mark.browser` (Fase 3 em diante).
- Testes de concorrência em Postgres: ver o docstring de `tests/test_concorrencia_postgres.py`.
- **Reprocessar uma etapa/fundo:** no admin do Django, selecione as `EtapaExecucao` e use a ação *Reprocessar selecionadas*; por código, `pipeline.servicos.criar_execucao(..., etapas=[...], forcar=True, cascata=True)`. O comando `iniciar_execucao` (chamado pelo Agendador do Windows) chega na Fase 5.
- **Depurar falha do Playwright (trace):** cada falha deixa `erro_*.png` e `trace_*.zip` em `BROWSER_EVIDENCIAS` (dados sensíveis; retenção curta). Abrir com `playwright show-trace <arquivo>.zip`. O trace só começa depois do login.

## Estrutura

```
config/                      # settings por ambiente e feature flags por operação
contabilidade_mensal/
  core/                      # modelos, admin, regras de domínio
  pipeline/                  # grafo, estados, fila, trava, disjuntor, executor, worker, fakes
  integrations/britech/      # BritechGateway, erros tipados, backends fake e api, nomes canônicos
  integrations/britech/browser_backend/  # Playwright: seletores, pages/, session (login/logout confirmados)
  integrations/monday/       # cadastro de fundos (Monday → Fundo)
  observability/             # log JSON com contexto
  storage/                   # hash e staging
populador/ , cli.py          # populador Excel (etapa 4)
tests/                       # pytest
docs/unificacao/             # documentação da unificação
```

## Populador (etapa Excel)

Requer Windows com Excel instalado (COM). Por padrão lê o Painel real e escreve nas pastas reais.

```bash
python cli.py --dry-run                              # só lista o que processaria
python cli.py --apenas-fundo "FII LAZIO II"
python cli.py --pasta-saida "C:\saida_teste"         # lê produção, escreve em outro lugar
python cli.py --interativo                           # pergunta quando o insumo é ambíguo
```

Marque "X" na coluna D do Painel para os fundos a processar. O resultado por fundo vai para `logs/relatorio_populador.csv`.
