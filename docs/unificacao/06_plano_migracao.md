# 06 — Plano de migração

Fases incrementais, cada uma com **critério de pronto**. Esforço relativo: **P** (dias), **M** (1–2 semanas), **G** (mais de 2 semanas), para uma pessoa dedicada. "Depende de" lista respostas do negócio em `perguntas_abertas.md`.

Ordem baseada na sugerida no prompt, com duas mudanças de acordo com o que descobri: (a) **Fase 0** de segurança/decisões, porque há credenciais reais expostas em Shared Drive; (b) uma fase própria para o **cliente de API dos insumos**, que já existe no downloader do Simplifica e é o exemplo mais barato de "API primeiro".

| Fase | Nome | Esforço | Depende de |
|---|---|---|---|
| 0 | Segurança e decisões | P | Q1, Q3, Q5, Q11 |
| 1 | Esqueleto, modelos, config e `BritechGateway` | M | Fase 0 |
| 2 | Insumos por API (`api_backend`) | M | Q10 |
| 3 | Playwright: sessão, login/logout e Page Objects | M | Q10, Q12 |
| 4 | Fluxos `processar_contabil` e `baixar_balancete` | **G** | **Q4**, Q7, Q8 |
| 5 | Pipeline de **um fundo** ponta a ponta | M | Fases 1–4 |
| 6 | Etapa Excel e publicação no Drive | M | Q5, Q6 |
| 7 | Paralelização, disjuntor, alertas e painel | **G** | Q9 |
| 8 | Execução assistida em produção e desligamento do manual | M | Q15 |

---

## Fase 0 — Segurança e decisões (P)

- **Entregas:** credenciais do projeto do Lucas e do `drive_api` rotacionadas e movidas para o cofre; `.env` e `drive-service-account.json` fora do Shared Drive; decisão registrada sobre a base do projeto (Q1), escopo (Q3) e formato/nome da boleta (Q5).
- **Critério de pronto:** nenhum segredo em texto puro em pasta compartilhada; respostas de Q1/Q3/Q5 no `perguntas_abertas.md`.
- **Riscos:** rotação quebrar o que roda hoje (Streamlit do Simplifica usa credenciais por parâmetro; avisar o Lucas/Pedrão).

## Fase 1 — Esqueleto (M)

- **Entregas:** projeto Django `contabilidade_mensal/` com modelos da seção 3, migrações, admin, `config` por ambiente com *feature flags* por operação; `BritechGateway` (interface, DTOs, exceções tipadas) com **implementação falsa** para testes; fila em Postgres (claim/lease/backoff) e máquina de estados com testes; logging JSON com contexto.
- **Critério de pronto:** `pytest` verde; um pipeline de brinquedo (etapas fake) roda com falha injetada, retry, `pulado` por idempotência e reprocesso `forcar`; nenhuma dependência de Britech/Excel/Playwright.
- **Riscos:** superdimensionar; manter a Fase 1 enxuta e só com o que a seção 3 pede.

## Fase 2 — Insumos por API (M)

- **Entregas:** `api_backend` portado do downloader do Simplifica (`RelatorioComposicaoCarteira`, `RelatorioExtratoContaCorrente`, `OperacaoCotistaAnalitico_PorCarteiraCotista`, `RelatorioSaldoAplicacoesCotista`, `BuscaHistoricoCotaRentabilidade`), com nomes canônicos (`AAAAMM_<cnpj>_CarteiraFinal.xlsx` etc.), sha256 por arquivo, mapeamento de erros HTTP para a taxonomia; cliente do Monday para `Fundo`.
- **Critério de pronto:** para **um fundo real** (leitura apenas), os insumos gerados pelo pipeline têm o mesmo conteúdo dos gerados pelo Simplifica (comparação célula a célula); testes com *fixtures* gravadas (sem rede).
- **Riscos:** limites de taxa desconhecidos; credencial única (Basic) compartilhada com o navegador → cuidado com bloqueio de conta.

## Fase 3 — Playwright: sessão e Page Objects (M)

- **Entregas:** `browser_backend/session.py` (login e logout **confirmados**, lock por credencial, trace só depois do login, screenshot/trace em falha) e `pages/` (login, Processo Contábil, Balancete) com **seletores centralizados** e preferência por `get_by_role/label`; esperas por estado (inclusive o overlay de loading do DevExpress).
- **Critério de pronto:** teste `@pytest.mark.browser` loga, abre as duas telas e faz logout limpo, repetido 20× sem deixar sessão presa; nenhum `sleep` fixo; nenhum segredo em log/trace.
- **Riscos:** sessão única por usuário; trace vazar senha; seletores DevExpress dinâmicos.

## Fase 4 — Fluxos de processar e baixar balancete (G)

- **Entregas:** `flows/processar_contabil` (seleção em lote por credencial, **dry-run** por padrão, clique real só com flag + allowlist), `status_processamento` (polling), `flows/baixar_balancete` **parametrizado pela competência** (fim das datas fixas), arquivos salvos com nome canônico em `Insumos/` do staging, com sha256.
- **Critério de pronto:** em **um fundo de teste** (Q8), o fluxo processa, detecta a conclusão e baixa PDF+XLS corretos para a data-base pedida; falhas injetadas (carteira inexistente, sessão presa) geram o erro tipado esperado; investigação de API concluída (captura de tráfego / Swagger) e decisão registrada sobre trocar navegador por API.
- **Riscos:** **não sabemos se o processamento é assíncrono nem como detectar o fim (Q4)** — se não houver sinal confiável, a etapa fica com espera configurável + confirmação humana; reprocessar pode alterar dados reais.

## Fase 5 — Pipeline de um fundo, ponta a ponta, em homologação (M)

- **Entregas:** grafo de dependências ligando `baixar_insumos` ‖ `processar_contabil` → `baixar_balancete` → `popular_excel` → `publicar_drive` (as duas últimas ainda com *stubs*); execução disparada pelo comando `manage.py iniciar_execucao` (chamado pelo Agendador de Tarefas do Windows ou pela ação do admin; **sem n8n**); matriz fundo × etapa no admin.
- **Critério de pronto:** um fundo percorre todas as etapas até `sucesso`; reexecutar não duplica nada (`pulado`); reprocessar uma etapa invalida as seguintes (`cascata`); logs correlacionados por `correlation_id`.

## Fase 6 — Etapa Excel e Drive (M)

- **Entregas:** populador refatorado em **biblioteca** (`popular_fundo(...)` sem Painel; o CLI atual vira invólucro) e `integrations/excel` (staging local, boleta do mês anterior baixada do Drive, nomes canônicos na camada exata do matching); `integrations/drive` chamando o `drive_api` (resolve/cria `Tipo/Fundo/Data Base X/AAAAMM`, upload, verificação de checksum); watchdog de `EXCEL.EXE`.
- **Critério de pronto:** no fundo de teste, a boleta gerada é publicada em pasta `HOMOLOG` do Drive com hash conferido; a comparação com a boleta gerada manualmente para a mesma competência mostra **diferença zero nos dados** das abas populadas (leitura de `.xlsb` com `pyxlsb`).
- **Riscos:** Excel/COM sem suporte oficial em servidor; arquivo do mês anterior ausente; formato/nome final indefinido (Q5); funções da macro sem chamador (Q6).

## Fase 7 — Paralelização, disjuntor, alertas e painel (G)

- **Entregas:** workers por fila com as regras de concorrência da seção 4.3; *token bucket* na API; disjuntor; alertas enviados pelo próprio Django, sem n8n (falha de login, `TelaMudou`, N falhas, competência concluída; canal em Q24); tarefas do Agendador do Windows para `run_worker`, watchdog e resumo diário; painel de acompanhamento (view Django; endpoint `/api/competencias/<id>/matriz` só se a integração com o app de contabilidade pedir), com integração ao app de contabilidade (Hemera Reorganizado) como passo seguinte; runbook completo; *deploy* versionado com rollback ensaiado.
- **Critério de pronto:** competência de teste com dezenas de fundos processa em paralelo respeitando 1 sessão por credencial; um erro estrutural injetado abre o disjuntor e dispara alerta; rollback de versão ensaiado com sucesso.

## Fase 8 — Execução assistida em produção (M)

- **Entregas:** rodar o pipeline em produção **em paralelo ao processo manual por uma competência**, sem sobrescrever o que o time faz; relatório de diferenças (insumos, balancete, boleta); correções; então desligar o manual por administradora, gradualmente.
- **Critério de pronto:** uma competência inteira com diferença zero (ou explicada) entre manual e pipeline, sem incidente de sessão presa; time treinado para o runbook.
- **Riscos:** processar contábil pelo pipeline e pelas pessoas ao mesmo tempo; definir quem é a "fonte" na competência de teste.

---

## Riscos transversais

| Risco | Fases | Mitigação |
|---|---|---|
| Sem API para processar/balancete | 4, 7 | backend por operação; investigação de tráfego; Page Objects |
| Credenciais/sessão (1 por usuário, MFA/IP desconhecidos) | 0, 3, 7 | cofre, lock por credencial, usuário de serviço (Q10) |
| Formato/nome da boleta indefinidos | 6 | fechar Q5 antes |
| Processar contábil altera dados reais | 4, 8 | dry-run, allowlist, rollout gradual |
| Escopo cresce para 12 administradoras | 7+ | `Administradora` já é entidade; cada uma entra por configuração |

## O que depende de resposta do negócio

Q1, Q3, Q5 (Fase 0) · **Q4** (Fase 4) · Q7, Q8 (Fase 4) · Q6 (Fase 6) · Q9 (Fase 7) · Q10, Q11, Q12 (Fases 0 e 3) · Q15 (Fase 8).
