# Perguntas abertas

Status: 🔴 bloqueia a Fase 2 · 🟡 bloqueia uma fase de implementação · 🟢 informativa.
"O que já sei" traz a evidência encontrada; nada abaixo foi testado contra a Britech.

## Bloqueiam a Fase 2

**Q1 🔴 Qual é a base oficial da unificação ("nosso projeto")?**
O repositório aberto só tem a etapa 4 (populador Excel). Os outros pedaços estão em `PEDRÃO\...\britech_mensal_contabilidade` (insumos via API Britech, app Streamlit do SimplificaHub) e `Teste Api Drive\API` (Django + Drive). Proposta: novo pacote `contabilidade_mensal/` que reaproveita o populador, porta o cliente Britech WS/api e chama o `drive_api`. **Confirmar** ou indicar outro repositório. *(A Fase 2 foi escrita assumindo esta proposta.)*

**Q2 🔴 A Britech tem API para "Processar Contábil" e para o balancete? Há documentação/credenciais?**
*O que já sei:* a API `https://{adm}.britech.com.br/WS/api/...` existe, aceita **HTTP Basic com as credenciais da PAS** e cobre 5 relatórios de insumo + `BuscaListaFundos`. **Sem evidência** de endpoint para processamento contábil nem para o balancete. Sugestão: ler o Swagger/help do `WS/api` e/ou capturar o tráfego (ver `04_matriz_cobertura.md`).

**Q3 🔴 Qual o escopo: só ID Corretora ou as 12 administradoras do catálogo do Lucas?**
O projeto do Lucas é multi-administradora (ID Corretora, ID Serviços Fiduciários, América, MF Pepper, RJI, Actual, Libertas, Dome, Amicorp, Ouro Preto, Finhealth, Ativa). O prompt e a imagem falam só de ID Corretora. *(A Fase 2 assume ID Corretora primeiro, com `Administradora` como entidade para não exigir retrabalho depois.)*

**Q4 🔴 "Processar Contábil": por que o clique está desativado, é assíncrono e como saber que terminou?**
`PERMITIR_CLIQUE_PROCESSAR=False`. Não sei se reprocessar sobrescreve dados, se exige data/período, nem quanto tempo leva. Sem isso não dá para desenhar a espera (`aguardando_britech`).

## Bloqueiam fases de implementação

**Q5 🟡 A boleta precisa ser `.xlsb`? Qual o padrão de nome do arquivo final?**
*O que já sei:* em disco a maioria é `.xlsb`, mas há `.xlsm` (FII KRONOS). Nomes: `<fundo> AAAAMM.<ext>` (macro/populador) **vs.** `Boleta <fundo> MMAAAA.xlsb` (exemplo da imagem, ACELERA CASH). Alguém a jusante depende do formato ou do nome?

**Q6 🟡 A lógica do Painel está toda na macro VBA? Quem mantém?**
*O que já sei:* li os 7 módulos. Sem chamador (possível código morto): BMF, Op.Bolsa (que busca `MovCotista.xls` em vez de um arquivo de bolsa), PL/Cota, Balancete inicial, formatação de carteira. Ninguém confirmou.

**Q7 🟡 Como se define a competência e o "exercício" (Data Base)?**
Balancete do Lucas usa datas fixas (jan/2025). O Painel usa `C3` (data base), `C4` (AAAAMM atual), `C5` (AAAAMM anterior) e, por fundo, a coluna H (`Data Base <mês> <ano>`, ex.: "Novembro 2026"). De onde vem o exercício de cada fundo (não está no Monday que o Lucas lê)? O balancete é do mês fechado (1º ao último dia)?
*Avanço da Fase 1:* a **regra** que liga fundo + competência ao nome da pasta foi inferida de 4 fundos reais e está testada (`core/dominio.py`): `Data Base <mês> <ano>` = ano em que *termina* o exercício que contém a competência (ex.: exercício em novembro → 202512 a 202608 ficam em "Data Base Novembro 2026"). Falta só saber **de onde vem o mês de encerramento de cada fundo** (`Fundo.exercicio_mes`).
*Avanço da Fase 2:* o board do Monday **tem** CNPJ (`texto`) e mês do exercício (`exerc_cio_social__1`); a sincronização (`manage.py sincronizar_cadastro`) já grava os dois em `Fundo`. Resta confirmar que a coluna está preenchida e correta para os fundos (o comando lista os que vieram sem CNPJ ou sem exercício).

**Q8 🟡 Existe ambiente de homologação da Britech ou um fundo de teste?**
*O que já sei:* os testes do Lucas em 24/09 rodaram em carteiras reais da ID Corretora (44680491, 42754444, 101), gravando numa pasta "teste". Nenhum indício de homologação.

**Q9 🟡 Quantos fundos por competência e qual o prazo máximo?**
*O que já sei:* Monday tem 468 registros (carteiras) da ID Corretora e 761 Britech no total; o Painel lista 44 FIIs na tela atual. Prazo: desconhecido. "Registros" ≠ "fundos" (pode haver mais de uma carteira por fundo).

## Segurança e acesso

**Q10 🟡 A Britech exige MFA ou restringe por IP? Existe usuário de serviço (não pessoal)?**
*O que já sei:* nem o Playwright do Lucas nem o downloader tratam MFA; nos logs de 24/09 o login do Playwright concluiu só com usuário/senha, e a API aceita Basic auth. **Não sei** se as 3 credenciais preenchidas no `.env` do Lucas são pessoais ou de serviço, nem se há restrição de IP (o downloader é um app do hub; o Playwright roda localmente — de onde cada um sai para a Britech não foi verificado).

**Q11 🔴 Credenciais expostas no Shared Drive — quem resolve e quando?**
Sem abrir os arquivos: `.env` do projeto do Lucas (3 pares usuário/senha + token do Monday preenchidos), e `drive-service-account.json` + `.env`, `.env.production` em `Teste Api Drive\API`. Recomendo rotacionar e mover para cofre **antes** de migrar qualquer coisa. Isso é decisão sua/do time.

**Q12 🟡 A PAS aceita mais de uma sessão simultânea por usuário?**
O código do Lucas trata falha de logout como crítica ("pode bloquear novo login"). Isso define a concorrência máxima (uma sessão de navegador por credencial).

## Operação

**Q13 🟡 Qual máquina roda o projeto do Lucas e ele segue na manutenção?**
*O que já sei:* Windows com `G:` montado (caminhos `G:\` e `erros\`), aparentemente a estação de desenvolvimento; código alterado em 24/09/2026.

**Q14 🟡 Podemos padronizar o nome dos insumos (incluindo o balancete)?**
Hoje há 3 famílias de nome (downloader do Simplifica, nome sugerido pela Britech, renomeado à mão). Com o pipeline baixando tudo, proponho **nomes canônicos** e manter o reconhecimento por palavra-chave só como rede de segurança para arquivos legados. Alguém depende dos nomes atuais?

**Q15 🟡 Posso rodar o populador Python em produção, em paralelo ao manual, por uma competência?**
Já validado em sandbox e com leitura real de produção + saída redirecionada; nunca gravou nas pastas reais.

**Q16 🟢 O Monday é o cadastro mestre de fundos?**
O Lucas o usa como fonte (board com grupos FIF/FIDC/FII/FIP). Confirmar se pode ser a fonte oficial do modelo `Fundo`, e quem mantém as colunas (administrador, carteira, sistema).

**Q17 🟢 Painel de acompanhamento: tela no app de contabilidade de fundos (layout Hemera Reorganizado) ou algo simples por ora?**

## Surgiram na Fase 2 (arquitetura)

**Q18 🟡 Pode ser uma VM Windows dedicada com Excel para os workers?**
Quem provê, com licença do Office e sessão de usuário sempre logada (a Microsoft não suporta automação do Office em serviço não interativo). Sem isso a etapa Excel só roda em estação de alguém.

**Q19 🟡 Aprovam fila em Postgres (sem Redis/Celery) para o orquestrador?**
*Decisão já tomada: sem n8n; o agendamento é do Agendador de Tarefas do Windows (§4.1).* Motivos da fila em `05_arquitetura.md` §4.2 (volume baixo, worker Windows, estado transacional). O `drive_api` já usa RQ/Redis; se preferirem manter um único padrão, o custo é o worker Windows.

**Q20 🟡 Como os outros apps autenticam no `drive_api` e o que ele devolve após upload?**
As views exigem autenticação DRF (a classe está configurada, não investiguei o esquema). Preciso saber: (a) como obter credencial de serviço para o pipeline; (b) se a resposta inclui checksum (MD5/SHA-256) para a verificação pós-upload; (c) se resolve/cria pasta por caminho (`Tipo/Fundo/Data Base X/AAAAMM`) ou só por id.

**Q21 🟢 O pipeline deve escrever status de volta no Monday (por fundo/competência)?**
Hoje o Monday é só leitura no código do Lucas e do downloader. Escrever status seria um segundo painel a manter.

**Q22 🟡 Retenção e sensibilidade dos artefatos.**
Balancetes, carteiras e traces do Playwright são dados sensíveis. Por quanto tempo guardar (staging local, Drive, traces), e onde? Traces podem conter a senha digitada — precisam de acesso restrito.

**Q23 🟡 Rollout do "Processar Contábil" automático.**
Quem autoriza, e com que allowlist inicial de fundos? A operação altera dados reais na Britech e não sabemos se é reversível.

**Q24 🟡 Sem n8n, por qual canal o Django envia os alertas e quem recebe?**
E-mail (SMTP: qual servidor/conta de serviço?) e/ou webhook de canal do Slack (quem cria?). Quem é o responsável de plantão no início do mês?

## Surgiram na Fase 2 (insumos por API)

**Q25 🔴 Mais credenciais em texto claro no código do Lucas.**
Além do `.env` (Q11): o token do Monday está no arquivo `monday_ctb_britech2.py` e há 9 pares usuário/senha em `config_adm_britech_ctb_mensal.py`. Sem abrir/copiar os valores: ao rotacionar (Q11), incluir estes arquivos. O nosso código só lê `MONDAY_API_TOKEN` e `BRITECH_<REF>_USER/_SENHA` do ambiente.

**Q26 🟡 Administradora América lê o cadastro de um Excel local, não da API.**
O downloader do Simplifica trata a América à parte (planilha local no lugar de `BuscaListaFundos`). **Não portei** esse caso; só entra se a América estiver no escopo (Q3).

**Q27 🟡 Comparação real dos insumos ainda pendente (critério de pronto da Fase 2).**
Os testes de paridade usam o código original como oráculo em dados sintéticos; **nenhuma chamada real à Britech foi feita**. Para fechar: rodar `sincronizar_cadastro`, `baixar_insumos_api` e `comparar_insumos` para um fundo real, com suas credenciais (passo a passo no changelog).

**Q28 🟢 Quirks do código original preservados de propósito.**
Ver o changelog da Fase 2 (URL literal do `MovCotista`, `DataFim` como `str(datetime)`, coluna `'Valor Pendente Liquidação.'`, `dayfirst`). Se o Lucas/Simplifica corrigir algum deles, ajustamos junto para manter a paridade.

## Surgiram na Fase 3 (Playwright)

**Q29 🟡 Validar os seletores na PAS real.**
Só foram testados contra uma PAS falsa. Rodar `testar_navegador_britech --repeticoes 20 --headed` com a credencial de um fundo de baixo risco (Q8) e me passar o resultado (ou a pasta de evidências, ciente de que é sensível). Duas suposições a confirmar: (a) o grid da tela de Balancete usa `td.dxgv[title=<id>]` como o do Processo Contábil; (b) a mensagem/comportamento da PAS para senha errada e para sessão presa (hoje ambos = `AutenticacaoFalhou`).

