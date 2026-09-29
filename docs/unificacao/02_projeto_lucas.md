# 02 — Projeto do Lucas (Britech + Playwright)

Local: `G:\Drives compartilhados\Inteligência e Inovação\Projetos\LUCAS\Projeto britech playwright` — **inventário somente leitura**. Nada foi alterado ali. O arquivo `.env` **não foi aberto**: só contei linhas preenchidas com `grep -c`, sem imprimir valores.

## 1. Resumo

Automação **Python + Playwright (Chromium, API síncrona)** de duas telas da Britech (PAS): *Processo Contábil* (seleciona carteiras) e *Balancete Contábil* (baixa PDF e Excel). Busca a lista de fundos/carteiras no **Monday** (GraphQL). Tem uma interface Flask simples para escolher administradora/fundos. Está em **desenvolvimento ativo** (arquivos e logs de 24/09/2026 mostram várias iterações no mesmo dia).

Ponto crítico: **o clique em "Processar" está desativado** (`PERMITIR_CLIQUE_PROCESSAR = False`). Hoje o fluxo *seleciona* as carteiras e *baixa o balancete*, mas **não processa a contabilidade**.

## 2. Estrutura (3 níveis, sem `.venv`)

```
Projeto britech playwright/
├── main.py                 # CLI: Monday → executa todas as administradoras
├── app.py                  # Flask (porta 5000): UI para escolher fundos e executar
├── requirements.txt        # playwright==1.60.0, python-dotenv, loguru, requests, flask==3.0.3
├── .env                    # ⚠ credenciais reais (não lido)
├── .env.example            # modelo (variáveis por administradora)
├── .gitignore              # .env, __pycache__, *.pyc, erros/
├── .venv/                  # ⚠ ambiente virtual dentro do Shared Drive
├── britech/
│   ├── __init__.py         # configura loguru (arquivo diário, retenção 30 dias)
│   ├── settings.py         # flags, datas do balancete, IDs do Monday, timeouts
│   ├── administradoras.py  # catálogo de 12 administradoras → subdomínio + prefixo de env
│   ├── orquestrador.py     # loop por administradora: login → seleciona → (processa) → balancete → logout
│   ├── pas.py              # login, logout, abrir Processo Contábil, selecionar carteira, botão Processar
│   ├── balancete.py        # tela de Balancete: marca carteira, preenche datas, baixa PDF/Excel
│   ├── monday_client.py    # busca fundos no Monday, agrupa por administradora
│   └── utils.py            # busca de elemento em iframes, sessão ativa, screenshot de erro
├── templates/index.html    # UI (3 chamadas: /api/administradoras, /api/fundos, /api/executar)
├── logs/execucao_2026-09-24.log
└── erros/                  # 6 screenshots de falha (24/09)
```

Sem `.git` (sem controle de versão), sem testes, sem CI, sem README.

## 3. Stack e execução

- **Linguagem:** Python (venv local). **Playwright** 1.60.0, sync API, `chromium.launch(headless=HEADLESS)`, **um** browser/context/page reaproveitado por todas as administradoras (sequencial).
- **Dependências:** `pip` + `requirements.txt`. Outras libs: `loguru`, `requests`, `python-dotenv`, `flask`.
- **Como roda:** `python main.py` (CLI, todas as administradoras com carteira Britech no Monday) ou `python app.py` (UI). **Nenhum agendador** encontrado. Caminhos de log/evidência (`erros\...`) e `G:\` indicam execução **local em Windows** (provavelmente estação de desenvolvimento).
- **Timeouts/retries:** `DEFAULT_TIMEOUT_MS=30 000`, `MAX_TENTATIVAS=3`, espera fixa de 2 s entre tentativas; download com timeout de 60 s.

## 4. Fluxos automatizados na Britech

### 4.1 Login (`pas.login`)
- URL: `https://{url_adm}.britech.com.br/PAS` (o subdomínio vem do catálogo).
- Ações: `page.fill('#Login1_UserName')`, `page.fill('#Login1_Password')`, `Enter`. Sucesso = aparecer `span.dx-vam:has-text('Processamento')` (30 s).
- **Sem MFA tratado. Sem reuso de sessão** (`storage_state` não é usado): loga a cada execução/administradora.

### 4.2 Processo Contábil (`pas.abrir_processo_contabil`, `selecionar_carteira`, `clicar_botao_processar`)
- Navega `Processamento` → `Processo Contábil` por texto de menu.
- Localiza o campo de filtro `#gridConsulta_DXFREditorcol1_I` **na página e nos iframes** (`encontrar_frame_com_elemento`, polling de 500 ms).
- Digita o id da carteira, confere o valor digitado, espera `td.dxgv[title='{id}']`, exige **exatamente 1 resultado** e marca `#gridConsulta_DXSelBtn0_D` (verifica `aria-checked`). Seleções são **cumulativas** no grid.
- Botão `#btnRun` ("Processar") clicado **uma vez** para o lote — **mas desativado por flag**.
- **Não há espera pela conclusão do processamento** nem leitura de status.

### 4.3 Balancete (`balancete.baixar_balancete`)
- Vai direto para `{base}/Relatorios/Legais/Contabil/FiltroReportBalanceteContabil.aspx`.
- Por carteira (uma de cada vez — marcar várias gera `.zip`): abre o dropdown `#dropCliente_B-1Img`, filtra em `#dropCliente_DDD_gv_DXFREditorcol1_I`, marca `#dropCliente_DDD_gv_DXSelBtn0_D`, preenche `#textDataInicio_I` e `#textDataFim_I`, baixa via `#btnPDF` e `#btnExcel` (`expect_download`).
- **Datas fixas no código:** `BALANCETE_DATA_INICIO = "01/01/2025"`, `BALANCETE_DATA_FIM = "31/01/2025"` — não seguem a competência.
- Salva com o **nome sugerido pela Britech** (`BalanceteContabil_<cnpj>.pdf`, `BalanceteContabil_<idcarteira>_<cnpj>_.xls`) em **uma única pasta** (`BALANCETE_PASTA_DESTINO`, via `.env`).

### 4.4 Logout (`pas.sair`, no `finally` do orquestrador)
- Clica `#LinkButtonSair` e **confirma** que `#Login1_UserName` reapareceu (3 tentativas). Se falhar, loga `CRITICAL`: *a sessão pode ficar presa e bloquear novo login* → **a PAS parece permitir uma sessão por usuário**, o que limita paralelismo por credencial.

### 4.5 Fonte de fundos: Monday (`monday_client`)
- GraphQL em `api.monday.com/v2`, board e 4 grupos fixos em `settings.py` (grupo → tipo: FIF / FIDC / FII / FIP), paginação por cursor.
- Colunas usadas: administrador, id da carteira (pontos removidos), sistema. Mantém só `sistema` contendo "Britech" **e** carteira preenchida.
- Números do log de 24/09: **1 298 registros**, **761** com sistema Britech + carteira, **468** da administradora ID CORRETORA. (Registros são carteiras, não necessariamente fundos distintos.)

### 4.6 Catálogo de administradoras
12 nomes → 8 subdomínios distintos (`id`, `america`, `mfpepper`, `rji`, `libertasasset`, `DOMEADMINISTRADORA`, `denvercontabil`, `ativa`); várias administradoras **compartilham o subdomínio** mas têm credenciais próprias. O escopo do Lucas é **multi-administradora**, não só ID Corretora.

## 5. Onde salva, nomes, logs, evidências

- **Arquivos:** só o balancete, em pasta única e com nome sugerido pela Britech; nos logs de 24/09 o destino era `...\Projetos\BRUNA\Balancete\teste\` (pasta de teste de outra pessoa). **Sem organização por fundo/competência, sem hash, sem upload por API.**
- **Logs:** `loguru`, `logs/execucao_AAAA-MM-DD.log`, rotação diária, retenção 30 dias, nível DEBUG. Conferi por contagem: **nenhum padrão de segredo** no log de 24/09 (356 linhas).
- **Evidências:** screenshot full-page em `erros/` (gitignored). **Sem trace, sem HAR, sem vídeo.**

## 6. Qualidade dos seletores

| Seletor / técnica | Onde | Avaliação | Sugestão |
|---|---|---|---|
| `#Login1_UserName`, `#Login1_Password`, `#LinkButtonSair` | login/logout | OK (IDs ASP.NET WebForms), mas atrelados ao markup | `get_by_label`/`get_by_role`, mantendo ID como fallback |
| `span.dx-vam:has-text('Processamento')` / `'Processo Contábil'` | menu | **Frágil**: depende de texto/idioma e de classe genérica do DevExpress | `get_by_role("menuitem", name=…)` ou navegação direta pela URL da tela, se estável |
| `#gridConsulta_DXFREditorcol1_I`, `#btnRun` | Processo Contábil | Razoável (IDs DevExpress), busca em iframes é boa prática | manter helper de frames; centralizar em Page Object |
| `#gridConsulta_DXSelBtn0_D` | checkbox da 1ª linha | Assume 1 linha filtrada — mitigado por `count()==1` | manter a validação |
| `td.dxgv[title='{id}']` | resultado do filtro | OK | — |
| `#dropCliente_DDD_gv_*` | dropdown do balancete | IDs dinâmicos do DevExpress; **o log mostra o overlay `#dropCliente_DDD_gv_LD` (loading) interceptando cliques** e timeouts | esperar o overlay ficar `hidden` antes de clicar |
| `wait_for_timeout(200/300/500/800/2000)` | vários | **Esperas fixas** | trocar por `expect(...)`, `wait_for_response` e espera de overlay |

## 7. Riscos

1. **Credenciais reais em `.env` dentro de um Shared Drive**, sem `.git` e com `.venv` na mesma pasta. Contagem (sem valores): **3 pares usuário/senha preenchidos + token do Monday preenchido**. `.gitignore` cobre `.env`, mas não há repositório. → tratar como incidente de segurança a resolver antes da migração (mover para cofre, rotacionar).
2. **Processar contábil desativado** (`PERMITIR_CLIQUE_PROCESSAR=False`) e **sem espera de conclusão** → balancete pode sair desatualizado ou de contabilidade não processada.
3. **Datas do balancete fixas** (jan/2025) → não parametrizam a competência.
4. **`app.py` com `debug=True`, sem autenticação**, executando o Playwright **dentro da requisição HTTP** (bloqueante, sem fila/status). Aceitável só em `localhost`; inadequado para servidor.
5. **Sessão única por usuário** na PAS + logout que pode falhar → risco de bloquear a conta (o próprio código avisa; o log de 24/09 registra 2 ocorrências `CRITICAL`).
6. **Retry simples** (3×, 2 s fixos, sem backoff, sem distinguir tipo de erro).
7. **Configuração hardcoded**: IDs do board/grupos/colunas do Monday e (parcialmente) caminhos de teste.
8. **Sem testes, sem controle de versão, sem README** — e código ainda em mudança.

## 8. O que vale reaproveitar

- Login/logout **com confirmação** e alerta `CRITICAL` de sessão presa.
- `encontrar_frame_com_elemento` (busca em iframes) e a checagem de `aria-checked` após clicar.
- Screenshot em falha (evoluir para trace).
- Cliente do Monday com paginação por cursor e o catálogo de administradoras → base para o modelo `Fundo`.
