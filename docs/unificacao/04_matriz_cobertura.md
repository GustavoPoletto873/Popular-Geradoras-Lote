# 04 — Matriz de cobertura

Legenda de "Existe endpoint?": **Sim (evidência)** = usado em código que roda; **Desconhecido** = sem evidência nos dois projetos (vira pergunta aberta). Nada foi testado contra a Britech nesta fase.

| # | Etapa | Coberto pelo nosso (API) | Coberto pelo Lucas (Playwright) | Existe endpoint de API Britech/Simplifica? | Mecanismo recomendado | Justificativa | Risco |
|---|---|---|---|---|---|---|---|
| 0 | Cadastro de fundos/carteiras (quais processar) | Parcial — `Fundo/BuscaListaFundos` aparece no downloader; Painel usa varredura de pastas (`Lista_Pastas`) | Sim, via **Monday** (não Playwright): 1 298 registros, 761 Britech, 468 ID Corretora | **Sim** — Monday GraphQL; Britech `Fundo/BuscaListaFundos` | **API** — Monday como cadastro mestre, validado contra a Britech | Já existe, com tipo (FIF/FIDC/FII/FIP), administradora e id da carteira | Board/colunas hardcoded; falta `exercício` (col. H do Painel) e CNPJ como campo garantido |
| 1a | Insumo: Carteira Final/Início | **Sim** (Simplifica) | Não | **Sim (evidência)** — `Relatorio/RelatorioComposicaoCarteira` | **API** | Já roda; gera XLSX+PDF com nome canônico | Credencial única (Basic); versões duplicadas do código |
| 1b | Insumo: ExtratoCC | **Sim** | Não | **Sim (evidência)** — `Relatorio/RelatorioExtratoContaCorrente` | **API** | idem | idem |
| 1c | Insumo: Mov. Cotista | **Sim** | Não | **Sim (evidência)** — `Fundo/OperacaoCotistaAnalitico_PorCarteiraCotista` | **API** | idem | idem |
| 1d | Insumo: Posição Cotista Final/Início | **Sim** | Não | **Sim (evidência)** — `Relatorio/RelatorioSaldoAplicacoesCotista` | **API** | idem | idem |
| 1e | Insumo: Histórico de Cota | **Sim** (fora do lote atual do populador) | Não | **Sim (evidência)** — `Fundo/BuscaHistoricoCotaRentabilidade` | **API** | Já roda | Só entra no fluxo manual do Excel |
| 2 | **Processar Contábil** | **Não** | **Parcial** — seleciona carteiras; clique em "Processar" **desativado** | **Desconhecido** | **Browser (fallback)** até provar API; capturar tráfego para descobrir o postback | Só existe hoje na tela; a API conhecida cobre relatórios, não processamento | Tela DevExpress instável (overlay de loading); sessão única por usuário |
| 3 | Aguardar conclusão do processamento | Não | **Não** (o log mostra uma espera fixa de 30 s numa versão anterior; a atual não espera) | **Desconhecido** | **Polling** por estado (API se existir; senão leitura da tela) | Balancete depende do processamento concluído | Balancete sair desatualizado; não sabemos se o processamento é assíncrono |
| 4 | **Baixar balancete** (PDF + Excel) | **Não** | **Sim** (datas fixas jan/2025; uma pasta única) | **Desconhecido** — há API de relatórios para outros 5 insumos, então vale testar a família `Relatorio/*` | **Browser por ora; investigar API** | Se existir endpoint como os outros relatórios, elimina o navegador nesta etapa | Datas hardcoded; nome do arquivo é o sugerido pela Britech |
| 5 | Organizar o balancete em `Insumos/` do fundo/mês com nome canônico | Não | Não (salva em pasta única, sem fundo/competência) | n/a | **Código nosso** (storage + hash) | Hoje é feito à mão; sem isso o populador precisa de reconhecimento por heurística | Duplicidade "(3)", sobrescrita, arquivo no fundo errado |
| 6 | **Popular fundos (Excel)** | **Sim** — este repo (COM), validado em sandbox e em modo redirecionado | Não | n/a (Excel) | **Excel/COM em Windows dedicado** | `.xlsb` só é gravado pelo Excel; reimplementar a lógica foi desnecessário — é cópia 1:1 de faixas | Depende de Windows + Excel + arquivo do mês anterior; bugs corrigidos vs. macro original |
| 7 | Salvar boleta no Drive | **Parcial** — grava direto em `G:\`; `drive_api` faz upload auditado | Não | **Sim (evidência)** — Google Drive API (`drive_api`) | **API do Drive** (`drive_api`) + verificação de hash | Evita depender de `G:` montado; já tem auditoria | Padrão de nome do arquivo final indefinido |
| 8 | Orquestração, estado, idempotência | **Não** (só CSV do populador; `RegistroDrive`/`JobLote` cobrem só Drive) | Não (só logs) | n/a | **Novo** (`pipeline/`) | Requisito central da unificação | Escopo novo |
| 9 | Alertas e painel de acompanhamento | Não | Não | n/a | alertas enviados pelo Django (e-mail/webhook) + painel simples; agendamento pelo Agendador do Windows | Padrão do time | — |

## Leitura rápida

- **Etapas 0–1 (cadastro e insumos): resolvidas por API**, com evidência de código.
- **Etapas 2–4 (Processar Contábil, espera, Balancete): só existem via navegador** e são o coração do trabalho do Lucas — e as **menos maduras** (processar desativado, datas fixas, sem espera).
- **Etapa 6 (Excel): resolvida** por este repositório.
- **Etapa 7 (Drive): peça existente** (`drive_api`) a integrar.
- **Etapa 8 (orquestração/estado): lacuna total.**

## Como descobrir se as etapas 2–4 têm API (apenas documentar, sem implementar)

1. **Documentação da API `WS/api`** (Swagger/help, se publicada) — procurar por `Contabil`, `Balancete`, `Processo`. O downloader já prova que a API existe e aceita as credenciais da PAS.
2. **Capturar o tráfego durante a execução do Playwright** (HAR via `browser.new_context(record_har_path=...)` ou `page.on("request")`) nas telas *Processo Contábil* e *Balancete Contábil* para ver se há chamadas a `/WS/api/...` ou apenas *postbacks* `.aspx`.
3. **Perguntar ao suporte/contato da Britech** se há endpoint para processamento contábil e para o relatório legal de balancete.
