# 03 — Nosso projeto (inventário)

## 0. Achado principal: "nosso projeto" não está num único lugar

O prompt descreve o nosso projeto como um app (possivelmente Django) com clientes de API do Simplifica, da Britech e do Google Drive. O **repositório onde estou (`Popular geradoras em lote`) não é isso**: contém apenas a **etapa 4** (popular o Excel). Procurei o resto na pasta compartilhada e encontrei **três peças separadas**, sem repositório comum:

| Peça | Onde | O que cobre | Tecnologia | Controle de versão |
|---|---|---|---|---|
| **A. Populador em lote** | este repositório | Etapa 4 (e 5 parcial) | Python CLI + Excel COM (`pywin32`) | não (sem `.git`) |
| **B. Downloader de insumos via API Britech** (`britech_mensal_contabilidade`, SimplificaHub) | `Projetos\PEDRÃO\Erro mensal contabilidade\britech_mensal_contabilidade` (e cópia divergente em `PEDRÃO\ERRO BRITECH\...`) | Etapa 1 | Python + Streamlit + `requests` | não evidente; ≥2 cópias diferentes |
| **C. Serviço de Drive** (`drive_api`) | `Projetos\Teste Api Drive\API` | Base para a etapa 5 (upload no Drive) | Django + DRF + RQ/Redis + Postgres + Google Drive API | há indício de git remoto (arquivo `git clone httpsgithub.comDenverCont.txt`) |

> **Pergunta aberta nº 1:** qual é a base oficial da unificação? Minha leitura: um novo pacote `contabilidade_mensal/` que reaproveita A (como etapa Excel), porta B (cliente Britech WS/api) e chama C (Drive). Preciso da sua confirmação antes da Fase 2.

## A. Populador em lote (este repositório)

- **Função:** substitui o botão `ProcessarEmLoop` do Painel Populador. Para cada fundo marcado com "X" na aba Painel: copia o arquivo do mês anterior, limpa 6 abas, repopula Carteira final/inicial, Extrato, Balancete, Posicao_Cotista e Mov_Cotista a partir de `Insumos/`, salva e escreve o status na coluna C.
- **Tecnologia:** Python 3.14, `pywin32` (Excel COM). Escolhido porque **openpyxl não grava `.xlsb`** e o formato real de saída é `.xlsb` (também há `.xlsm`).
- **Estrutura:**
  ```
  cli.py                       # --dry-run, --apenas-fundo, --pasta-saida, --interativo, --relatorio-csv
  populador/config.py          # nomes de aba/célula (confirmados no VBA real), escopo do lote, regras de fallback
  populador/paths.py           # montagem de caminhos (origem/insumos/saída) — pura, testável
  populador/matching.py        # reconhecimento de insumo em 2 camadas (exato do VBA → palavra-chave); ambíguo não é adivinhado
  populador/excel_app.py       # sessão COM, helpers de copiar/colar/desmesclar
  populador/copiar.py          # copia o arquivo do mês anterior e limpa as abas
  populador/populate.py        # 6 passos de população
  populador/painel.py          # leitura/escrita da aba Painel
  populador/runner.py          # orquestração por fundo, isolamento de erro, CSV
  tests/                       # 27 testes (lógica pura + mocks; sem Excel)
  ```
- **Estado validado:** lote com **2 fundos reais juntos** (FII LAZIO II e FII KRONOS), lendo insumos reais de produção com a **saída redirecionada** (`--pasta-saida`) e a planilha do Painel usada em **cópia** — produção não foi alterada. Ainda **não** rodou escrevendo em produção.
- **Correções em relação à macro VBA original** (achadas na leitura/teste): (1) extensão do arquivo nunca atribuída ao reabrir o arquivo copiado; (2) células mescladas no template quebravam a colagem em fundos como o KRONOS; (3) erro em um fundo travava o resto do lote.
- **Achado importante:** o casamento por nome fixo da macro só funcionava numa minoria dos fundos (nomes dos insumos mudaram ao longo do tempo/origem); resolvido com reconhecimento em duas camadas.
- **Persistência/estado:** nenhum banco; status na coluna C do Painel e CSV por execução.
- **Lacunas para a unificação:** sem modelo de dados, sem idempotência por (fundo, competência, etapa), sem integração com Simplifica/Britech/Drive, roda só em Windows com Excel.

## B. Downloader de insumos via API Britech (Simplifica)

Conteúdo do módulo `britech_mensal_contabilidade` (app **Streamlit** do SimplificaHub). O orquestrador `main(DataFim, df_ativo, df_passivo, caminho, url_adm, username, password)` executa **9 passos**:

1. Carteira **Final** · 2. Carteira **Início** · 3. **Caixa** (extrato de conta corrente) · 4. Merge passivo × ativo · 5. **Movimentação de cotistas** · 6. **Posição de cotistas** (Final) · 7. **Posição de cotistas** (Início) · 8. **Histórico de cotas** · 9. **Empilhar relatórios de passivo** e gerar *sheet* do Monday.

- **Como fala com a Britech:** **API REST** em `https://{url_adm}.britech.com.br/WS/api/...` com **HTTP Basic** (`requests.get(..., auth=(usuario, senha))`), usando as mesmas credenciais da PAS. Endpoints citados no código:

  | Endpoint | Insumo gerado |
  |---|---|
  | `Relatorio/RelatorioComposicaoCarteira` | CarteiraFinal / CarteiraInicial (+ PDF) |
  | `Relatorio/RelatorioExtratoContaCorrente` | ExtratoCC (+ PDF) |
  | `Fundo/OperacaoCotistaAnalitico_PorCarteiraCotista` | MovCotista |
  | `Relatorio/RelatorioSaldoAplicacoesCotista` | SaldoAplicacaoCotistaFinal / Inicial (+ PDF) |
  | `Fundo/BuscaHistoricoCotaRentabilidade` | Histórico de Cota |
  | `Fundo/BuscaListaFundos` | lista de fundos |

- **Nomes de saída (versão mais recente):** `AAAAMM_<cnpj>_CarteiraFinal.xlsx`, `AAAAMM_<cnpj>_CarteiraInicial.xlsx`, `AAAAMM_<cnpj>_ExtratoCC.xlsx`, `AAAAMM_<idcarteira>_<cnpj>_MovCotista.xlsx`, `..._SaldoAplicacaoCotistaFinal|Inicial.xlsx`, `..._Histórico de Cota.xlsx`. Bate exatamente com os `Insumos/` mais recentes em disco (ex.: ACELERA CASH 202608).
- **Não cobre:** *Processar Contábil* e *Balancete* (nenhuma menção no módulo).
- **Credenciais:** recebidas por **parâmetro** (`username`, `password`) — vêm da UI/hub; não li de onde. Há pelo menos 6 cópias de `posição_cotista_ctb_britech.py` espalhadas em `ERRO BRITECH/*` e `Formatador Balancete DF/` (além da variante `..._britech1.py` usada aqui) — **código duplicado e sem versionamento evidente**.
- **Mesma lista do inventário de testes** (`TESTE NOVO SIMPLIFICA/NOVOSIMPLIFICA.md`): `britech_mensal_contabilidade: Ok`; `Maps_Mensal_Contabilidade: Revisar (API não funciona)`.

## C. Serviço de Drive (`drive_api`)

- **Stack:** Django ≥4.2, DRF, drf-spectacular, RQ + Redis (workers escaláveis: `docker compose up --scale worker=3`), Postgres (`db_denvercontabifi`), `google-api-python-client`, Secret Manager, gunicorn, whitenoise. `Dockerfile`, `docker-compose.yml`/`.local.yml`, `autoscaler.py`, `worker.py`.
- **Endpoints:** `arquivos/` (listar/criar), `arquivos/lote/` (upload em lote assíncrono), `arquivos/<id>/` (detalhe), `.../conteudo/`, `.../copiar/`, `pastas/`, `pastas/buscar/`, `unidades/`, `jobs/<id>/`, `saude/`.
- **Modelos:** `RegistroDrive` (auditoria de cada operação que muda algo no Drive: usuário, app de origem, operação, alvo, tamanho, sucesso, erro) e `JobLote` (status de cada arquivo do upload em lote).
- **Serviços:** `drive_client` (retry/erro de cota, credenciais por papel via Secret Manager), `pastas`, `arquivos`, `lotes`, `unidades`.
- **Relevância:** já resolve, de forma auditável, "salvar/organizar arquivo no Shared Drive por API" — a alternativa recomendável ao caminho `G:\` montado.
- **⚠ Riscos vistos (sem abrir):** existem `drive-service-account.json` e três `.env*` dentro da pasta compartilhada.

## D. Como o Painel Populador e a boleta são tratados hoje

- **Painel (`.xlsm`):** a macro `ProcessarEmLoop` é disparada por botão; o Painel também tem `Lista_Pastas` (varre pastas e lista fundos por tipo). O substituto Python lê a mesma aba (colunas B/C/D/F/H e células C2/C4/C5).
- **Boleta (`.xlsb`/`.xlsm`):** é uma **cópia do arquivo do mês anterior** com as abas de dados limpas e repopuladas; a extensão é herdada. O nome final varia (`<fundo> AAAAMM.<ext>` vs `Boleta <fundo> MMAAAA.xlsb`).
- **Código possivelmente morto no VBA:** funções de BMF, Op.Bolsa (busca o arquivo errado), PL/Cota, Balancete inicial e formatação de carteira não têm chamador → fora do escopo do lote (não confirmado com o mantenedor).

## E. Cobertura por etapa (resumo)

| Etapa | Cobertura em "nosso" lado |
|---|---|
| 1 Baixar insumos | **Sim** — peça B (API Britech) |
| 2 Processar Contábil | **Não** |
| 3 Baixar balancete | **Não** |
| 4 Popular fundos | **Sim** — peça A (COM/Excel) |
| 5 Salvar boleta | **Parcial** — A grava em `G:\`; C oferece upload por API |
