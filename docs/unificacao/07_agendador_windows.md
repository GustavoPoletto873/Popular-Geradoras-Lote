# 07 — Agendador de Tarefas do Windows (sem n8n)

Tudo roda na VM Windows dedicada (sessão de usuário sempre logada, por causa do Excel/COM). O Agendador só **liga comandos**; estado e regras ficam no Django/Postgres. Ajuste `C:\cm` (código) e `C:\cm\.venv` (Python) ao que for instalado. As variáveis de ambiente (`DJANGO_SETTINGS_MODULE`, `DB_*`, `BRITECH_*`, `MONDAY_API_TOKEN`, `STORAGE_ROOT`…) ficam nas **variáveis de ambiente do usuário** da tarefa — nunca em arquivo na pasta compartilhada.

## Tarefas

| Tarefa | Quando | Comando |
|---|---|---|
| `cm-sincronizar-cadastro` | diária, 06:30 | `manage.py sincronizar_cadastro` |
| `cm-iniciar-execucao` | diária, 07:00 (o comando é idempotente) | `manage.py iniciar_execucao --competencia auto --disparada-por agendador` |
| `cm-limpar-orfaos` | a cada 10 min | `manage.py limpar_orfaos --matar` |
| `cm-resumo-diario` | diária, 18:00 | `manage.py resumo_diario` |
| `cm-worker-api` | ao logon + repetir a cada 5 min | `manage.py run_worker --fila api` |
| `cm-worker-browser` | ao logon + repetir a cada 5 min | `manage.py run_worker --fila browser` |
| `cm-worker-excel` | ao logon (sessão do usuário, com Excel) + repetir a cada 5 min | `manage.py run_worker --fila excel` (com `EXCEL_BACKEND=com`) |
| `cm-worker-drive` | ao logon + repetir a cada 5 min | `manage.py run_worker --fila drive` (com `DRIVE_BACKEND=api`) |

Regras que fazem isso funcionar:

- **`iniciar_execucao --competencia auto`** usa o mês anterior ao de hoje e, sem `--forcar`, só inclui fundos que ainda não concluíram tudo e que não têm etapa em andamento. Rodar todo dia até o fim do mês é seguro: depois de concluído imprime "nada a fazer".
- **Workers:** cada instância processa a fila até esvaziar e fica consultando (`--intervalo`). Configure a tarefa com "Não iniciar nova instância se já estiver em execução"; se o processo cair, a repetição de 5 min o reinicia, e o *lease* devolve à fila a etapa que estava em andamento.
- **Um worker por fila** basta no começo. A concorrência por credencial já é garantida pela trava (`britech:<administradora>`), então subir dois workers `browser` não abre duas sessões da mesma credencial.
- **Excel e Drive:** `EXCEL_BACKEND=com` e `DRIVE_BACKEND=api` ligam os reais; em `stub` (padrão) a fila só sobe com `PERMITIR_STUBS_EXCEL_DRIVE=true` (homologação; o stub não toca Excel nem Drive) e a **produção recusa stubs**. O worker `excel` precisa rodar na sessão de um usuário logado com Office.

## Criar as tarefas (exemplo, PowerShell como o usuário da VM)

```powershell
$py  = "C:\cm\.venv\Scripts\python.exe"
$cmd = "C:\cm\manage.py"

# início do mês / gatilho diário
schtasks /Create /TN "cm-iniciar-execucao" /SC DAILY /ST 07:00 /RL LIMITED `
  /TR "`"$py`" `"$cmd`" iniciar_execucao --competencia auto --disparada-por agendador"

# worker: ao logon e repetindo a cada 5 min (o Agendador não duplica a instância)
schtasks /Create /TN "cm-worker-browser" /SC ONLOGON /RL LIMITED `
  /TR "`"$py`" `"$cmd`" run_worker --fila browser"
# depois, no Agendador (taskschd.msc): Propriedades > Gatilhos > repetir a cada 5 minutos;
# Configurações > "Não iniciar uma nova instância" quando já estiver em execução.
```

Parar tudo (manutenção/deploy): `schtasks /End /TN "cm-worker-browser"` (e demais) — as etapas em andamento voltam à fila quando o lease vencer (300 s por padrão).

## Ordem segura para ligar em produção

1. `DRY_RUN_PROCESSAR_CONTABIL=true` (padrão) e `ALLOWLIST_PROCESSAR_CONTABIL` vazia: o pipeline seleciona mas **não clica** em Processar.
2. `BRITECH_BACKEND_BAIXAR_INSUMO=api`, `…_PROCESSAR_CONTABIL=browser`, `…_BAIXAR_BALANCETE=browser`.
3. Um fundo de baixo risco na allowlist com `PIPELINE={"processamento_conclusao": "manual"}` (Q30).
4. Só depois ampliar allowlist e trocar para `espera`.

## Pendente

- Alertas: o Django envia por e-mail/Slack se `ALERTAS_*` estiverem configurados (Q24). Runbook e deploy: `09_runbook.md`.
