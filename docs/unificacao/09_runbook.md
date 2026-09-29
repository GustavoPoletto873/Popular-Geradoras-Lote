# 09 — Runbook (operação, incidentes, deploy e rollback)

Tudo roda na VM Windows dedicada (ver `07_agendador_windows.md`). Comandos são `python manage.py …` na pasta do app, com as variáveis de ambiente do usuário do Agendador.

## 1. Rotina do início do mês

1. O Agendador roda `sincronizar_cadastro` (06:30) e `iniciar_execucao --competencia auto` (07:00): cria as etapas dos fundos que faltam. Pode rodar todo dia; é idempotente.
2. Acompanhe no admin: **Competências › fundo × etapa**. Mostra o resumo por estado, disjuntores abertos, etapas aguardando confirmação e os últimos alertas. Em texto: `mostrar_matriz --competencia AAAA-MM`.
3. `resumo_diario` (sugestão: 18:00) manda o resumo por e-mail/Slack. Alerta de "competência concluída" chega sozinho quando a execução termina.
4. **Processar Contábil** (enquanto a Q4 estiver aberta e o modo for `manual`): chega o aviso "Confirmar processamento". Confira na PAS; no admin, em *Etapas de execução*, selecione as etapas *aguardando_britech* e use **Confirmar que a Britech terminou o processamento**.

## 2. Incidentes (o que o alerta significa e o que fazer)

| Alerta | Causa provável | O que fazer |
|---|---|---|
| **Login recusado na Britech** (`autenticacao_falhou`) | Senha trocada/expirada, usuário bloqueado, sessão presa de outro usuário | **Não repetir sozinho** (o disjuntor já pausou a fila). Confirme a credencial fora do sistema, corrija a variável `BRITECH_<REF>_USER/_SENHA`, feche o disjuntor (abaixo) e reprocesse |
| **Sessão presa** (`sessao_bloqueada`) | Logout não confirmado; a PAS aceita 1 sessão por usuário | Aguarde a expiração da sessão na Britech (ou peça a liberação); depois feche o disjuntor. Nunca tente em laço |
| **Uma tela da Britech mudou** (`tela_mudou`) | Seletor deixou de existir (atualização da PAS) | Abra o trace da falha (`BROWSER_EVIDENCIAS`, `playwright show-trace arquivo.zip`), ajuste **só** `browser_backend/seletores.py` / a Page, rode `testar_navegador_britech`/`testar_fluxos_britech`, faça deploy, feche o disjuntor |
| **Disjuntor ABERTO: `<etapa>:<backend>:<adm>`** | N falhas seguidas do mesmo tipo | A fila daquela chave está pausada e libera uma tentativa de teste por resfriamento (15 min). Corrija a causa e feche: admin › *Disjuntores* (zerar campos) ou `disjuntor.fechar(chave, por="seu-nome")` |
| **Falha em `<etapa>`: `<erro>`** | Erro não crítico repetido | Veja `erro_msg` da etapa. Corrigido, use a ação **Reprocessar selecionadas** (refaz também o que depende) |
| `destino_ja_existe` | A pasta do Drive já tem outra planilha | Confira quem colocou; se for para sobrescrever, reprocesse `publicar_drive` com `--forcar` |
| `pasta_drive_nao_encontrada` | Nome de Tipo/Fundo no Monday ≠ pasta do Drive | Corrija o nome ou informe o id em admin › *Pastas de competência* |
| `boleta_anterior_ausente` | Sem modelo do mês anterior | Publique/localize a boleta do mês anterior e reprocesse `popular_excel` |
| `erro_excel` | Excel travado/arquivo bloqueado | É retentável; se persistir, rode `limpar_orfaos --matar` (Excel de automação órfão) e reprocesse |
| `lease_expirado` | Worker morreu no meio | Volta à fila sozinho; verifique se o Agendador reiniciou o worker |

**Reprocessar:** `iniciar_execucao --competencia AAAA-MM --fundos <códigos> --etapas <etapas> --forcar --cascata` (ou a ação no admin).

## 3. Segurança

- Screenshots e traces (`BROWSER_EVIDENCIAS`) mostram dados de fundos: pasta com acesso restrito, apagar depois de 30 dias, **não anexar a tickets/e-mails**.
- Nenhuma senha/token em arquivo do repositório ou em pasta compartilhada. Ao trocar credenciais, atualize a variável de ambiente do usuário do Agendador e reinicie as tarefas.
- O webhook do Slack (`ALERTAS_SLACK_WEBHOOK`) é um segredo.
- Clique real em "Processar": só com `DRY_RUN_PROCESSAR_CONTABIL=false` **e** a carteira em `ALLOWLIST_PROCESSAR_CONTABIL`.

## 4. Deploy versionado e rollback

Versões são **tags do Git**; as dependências estão fixadas em `requirements.lock`.

```powershell
.\deploy\windows\implantar.ps1 -Tag v0.7.0 -Python C:\cm\.venv\Scripts\python.exe   # para as tarefas cm-*, troca o código, migra, reinicia
.\deploy\windows\reverter.ps1  -Python C:\cm\.venv\Scripts\python.exe                # volta à versão anterior registrada
```

- `implantar.ps1` recusa árvore suja, para as tarefas, faz `checkout`, `pip install -r requirements.lock`, `manage.py check` e `migrate`; se **qualquer** passo depois do checkout falhar, volta sozinho para a versão anterior e reinicia as tarefas.
- **Rollback não desfaz o banco.** Regra de migração: *expandir → migrar → contrair*. Só coloque em uma versão migrações que o código da versão anterior aguente: colunas novas com `db_default`/`null=True`, tabelas novas; **nunca** renomear/remover coluna na mesma versão que deixa de usá-la (isso vira uma versão seguinte). Antes de uma versão com migração destrutiva: backup do banco.
- **Ensaiado (2026-09-29, clone temporário):** deploy A→B com migração aditiva (`db_default`), rollback B→A, e o código antigo gravou um alerta no esquema novo sem erro; deploy de uma tag inexistente recusado sem tocar em nada; deploy de uma versão com migração quebrada foi revertido sozinho para A. **Não ensaiado:** o caminho com as tarefas reais do Agendador (`-SemTarefas` foi usado) e Postgres.
- Regerar `requirements.lock` ao mudar `requirements.txt`: venv limpo → `pip install -r requirements.txt` → `pip freeze`; rode a suíte nesse venv antes de etiquetar.

## 5. Antes de ligar em produção (checklist)

- [ ] Credenciais expostas rotacionadas (Q11/Q25) e movidas para variáveis de ambiente/cofre.
- [ ] `testar_navegador_britech --repeticoes 20` e `testar_fluxos_britech` OK num fundo de baixo risco.
- [ ] `baixar_insumos_api` + `comparar_insumos` iguais ao Simplifica em um fundo real.
- [ ] `testar_drive` numa pasta HOMOLOG; nomes de Tipo/Fundo conferidos (Q33).
- [ ] Um fundo de ponta a ponta em homologação com `manual` e allowlist de 1 carteira.
- [ ] Canal de alertas definido e testado (Q24): `resumo_diario` chega.
- [ ] Postgres em uso e teste de concorrência (`test_concorrencia_postgres.py`) executado.
- [ ] Tarefas do Agendador criadas, com "não iniciar nova instância"; `limpar_orfaos --matar` a cada 10 min.
