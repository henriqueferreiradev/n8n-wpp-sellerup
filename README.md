# score.li

Protótipo de ferramenta para vendedores do Mercado Livre, operada por um bot de
WhatsApp. A orquestração do fluxo fica no N8N Cloud; o banco é um Postgres do
Supabase.

```
migrations/001_initial_schema.sql        4 tabelas + índices + triggers de updated_at
seeds/001_test_sellers.sql               2 vendedores de teste com crédito liberado
n8n-workflows/bot-whatsapp-estados.json  workflow de recebimento + máquina de estados
docs/data-model.md                       descrição de cada tabela e campo
docs/state-machine.md                    estados da conversa e quem implementa cada um
docs/meta-whatsapp-setup.md              passo a passo do app da Meta e credenciais
docs/gemini-supabase-storage-setup.md    passo a passo do Gemini, OpenAI e Supabase Storage (bloco c)
ml_test/                                 scripts de teste prático que validaram os prompts/modelos usados no bloco (c)
.env.example                             variáveis de conexão com o Supabase, Gemini, OpenAI e Storage
```

| Bloco | Escopo | Situação |
|---|---|---|
| **(a)** | Camada de dados: Supabase + tabelas | ✅ pronto |
| **(b)** | Recebimento do WhatsApp + máquina de estados | ✅ pronto |
| **(c)** | Nome do produto, busca real, título/descrição, 8 fotos, aprovação | ✅ pronto |
| (d) | OAuth e publicação no Mercado Livre | — |
| (e) | Créditos e cobrança | — |

Ainda não existe backend/API próprio, nem OAuth com o Mercado Livre, nem
verificação de crédito, nem score de mercado. As respostas do bot nos estados
dos blocos (d) e (e) continuam placeholders que dizem explicitamente que a
etapa não foi implementada — inclusive a análise de mercado/score (bloco f,
fora do escopo atual) e a edição manual real do título/descrição.

---

## 1. Criar o projeto no Supabase (manual)

Isso precisa ser feito à mão no painel; não dá para automatizar daqui.

1. Entre em <https://supabase.com/dashboard> e clique em **New project**.
2. Escolha a organização, dê um nome (ex: `score-li`) e defina uma **database
   password** — guarde essa senha, ela não é exibida de novo.
3. Região: escolha a mais próxima (ex: `South America (São Paulo)`), menor latência
   para o N8N e para você.
4. Plano: **Free**.
5. Espere o provisionamento terminar (~2 min).
6. Vá em **Project Settings → Database → Connection string**:
   - aba **URI**: copie a connection string completa;
   - a senha aparece como `[YOUR-PASSWORD]` — substitua pela senha do passo 2.
7. Na raiz do repo: `cp .env.example .env` e cole os valores.

> **Direct connection vs. pooler:** o Supabase mostra mais de uma string. Para
> rodar as migrations, prefira a **conexão direta** (porta `5432`). Para o N8N,
> qualquer uma funciona; o **pooler** (porta `6543`, modo transaction) aguenta
> melhor várias execuções de workflow em paralelo.

## 2. Rodar a migration

Não há ORM nem ferramenta de migration aqui de propósito — `psql` basta para o
protótipo.

```bash
# carrega DATABASE_URL do .env
set -a; source .env; set +a

psql "$DATABASE_URL" -f migrations/001_initial_schema.sql
```

No **PowerShell** (Windows):

```powershell
$env:DATABASE_URL = (Select-String -Path .env -Pattern '^DATABASE_URL=').Line -replace '^DATABASE_URL=', ''
psql $env:DATABASE_URL -f migrations/001_initial_schema.sql
```

Sem `psql` instalado? Dá para colar o conteúdo do arquivo direto no **SQL Editor**
do painel do Supabase e clicar em *Run* — o resultado é o mesmo.

Conferir:

```bash
psql "$DATABASE_URL" -c "\dt"
```

Devem aparecer `sellers`, `listings`, `credit_transactions` e `market_analysis`.
A migration é idempotente — rodar de novo não quebra nada.

## 3. Rodar a seed

**Antes:** abra [seeds/001_test_sellers.sql](seeds/001_test_sellers.sql) e troque
os dois números de WhatsApp fictícios pelos reais (E.164, ex: `+5511987654321`).
Eles aparecem em dois lugares no arquivo — no `INSERT` e no `WHERE` da transação
de crédito. Troque nos dois.

```bash
psql "$DATABASE_URL" -f seeds/001_test_sellers.sql
```

Conferir:

```bash
psql "$DATABASE_URL" -c "select whatsapp_number, credit_balance from sellers;"
psql "$DATABASE_URL" -c "select seller_id, credits_added, source from credit_transactions;"
```

Esperado: 2 vendedores com `credit_balance = 1000` e 2 transações com
`source = 'manual_test'`. A seed também é idempotente.

## 4. Configurar a credencial de Postgres no N8N Cloud

1. No N8N Cloud, vá em **Settings → Credentials → Add credential** e escolha
   **Postgres**. Dê a ela exatamente o nome **`Supabase Postgres`** — o workflow
   do bloco (b) referencia as credenciais por nome, e com o nome certo o import
   já liga tudo sozinho.
2. Preencha com os dados do Supabase (os mesmos do `.env`):

   | Campo | Valor |
   |---|---|
   | Host | `SUPABASE_DB_HOST` (ex: `aws-0-sa-east-1.pooler.supabase.com`) |
   | Database | `postgres` |
   | User | `SUPABASE_DB_USER` (ex: `postgres.abcdefghijklm`) |
   | Password | a senha do banco |
   | Port | `5432` (ou `6543` se usar o pooler em modo transaction) |
   | SSL | `Require` — o Supabase exige TLS |

3. Clique em **Save**; o N8N testa a conexão sozinho e mostra o resultado.

### Teste de ponta a ponta

Confirme que a conexão funciona **antes** de avançar para o bloco (b):

1. Novo workflow → adicione um node **Manual Trigger**.
2. Adicione um node **Postgres**, selecione a credencial criada, operation
   **Execute Query**:
   ```sql
   select * from sellers;
   ```
3. **Execute workflow**. Devem voltar os 2 vendedores da seed.

Se der erro de conexão: confira a porta, o `SSL: Require`, e se o usuário está no
formato `postgres.<project-ref>` (o pooler do Supabase exige o project-ref no
nome do usuário).

---

# Bloco (b) — recebimento do WhatsApp e máquina de estados

O workflow [n8n-workflows/bot-whatsapp-estados.json](n8n-workflows/bot-whatsapp-estados.json)
recebe as mensagens, identifica o vendedor pelo telefone e roteia pelo
`conversation_state`. A única transição implementada de verdade é
`novo → aguardando_geracao`; os demais estados respondem placeholder. Detalhes em
[docs/state-machine.md](docs/state-machine.md).

```
WhatsApp Trigger → parse-mensagem → buscar-vendedor → vendedor-existe?
                                                       ├── não → "número não liberado"
                                                       └── sim → rotear-por-estado
                                                                  ├── novo → é imagem?
                                                                  │           ├── sim → criar-listing → atualizar-estado → resposta
                                                                  │           └── não → "manda uma foto"
                                                                  ├── (5 estados futuros) → placeholder de etapa avançada
                                                                  └── desconhecido → placeholder de estado não reconhecido
```

## 5. Configurar o app da Meta

Siga [docs/meta-whatsapp-setup.md](docs/meta-whatsapp-setup.md) inteiro antes de
importar o workflow. Ele cobre a criação do app, o cadastro dos números
destinatários de teste (**o ponto que mais trava**) e as duas credenciais do N8N.

Nomeie as credenciais exatamente assim, para o import ligar tudo sozinho:

| Credencial | Tipo no N8N | Usada por |
|---|---|---|
| `WhatsApp OAuth (trigger)` | WhatsApp OAuth API | WhatsApp Trigger |
| `WhatsApp Business Cloud (envio)` | WhatsApp API | os 4 nodes de resposta |
| `Supabase Postgres` | Postgres | os 3 nodes de banco |

## 6. Importar e ativar o workflow

1. No N8N Cloud: menu **⋯ → Import from File** e escolha
   `n8n-workflows/bot-whatsapp-estados.json`. (Se preferir, **Import from URL**
   com o link raw do arquivo no seu Git.)
2. Abra os nodes que aparecerem com aviso de credencial e selecione a credencial
   correta. Com os nomes acima, isso normalmente já vem resolvido.
3. Ative o workflow no toggle **Active** do canto superior direito. É a ativação
   que faz o N8N registrar o webhook na Meta — enquanto estiver inativo, nada
   chega.
4. Confirme no painel da Meta (**WhatsApp → Configuration → Webhook**) que o
   campo `messages` está com *Subscribe* marcado.

## 7. Testar

Do seu número (o mesmo que está em `sellers`), mandando mensagem para o número de
teste da Meta:

| Você manda | Esperado no WhatsApp | Esperado no banco |
|---|---|---|
| Um texto qualquer | *"Manda uma foto do produto que você quer anunciar pra eu começar."* | nada muda |
| Uma foto | *"Recebi sua foto! 📸 Antes de gerar o anúncio, me conta: qual é o nome do produto?"*, seguido do fluxo completo do bloco (c) — ver [seção de teste do bloco (c)](#9-testar-o-bloco-c) abaixo | nova linha em `listings`; vendedor vai para `aguardando_nome_produto` e segue dali |
| Mensagem de um número fora da tabela | *"Esse número ainda não está liberado…"* | nada muda |

Conferindo no Supabase:

```sql
select whatsapp_number, conversation_state from sellers;
select seller_id, original_photo_url, status, created_at from listings order by created_at desc;
```

Para repetir o teste, devolva o vendedor ao estado inicial:

```sql
update sellers set conversation_state = 'novo' where whatsapp_number = '+55...';
```

## Notas de implementação

Três coisas no workflow que não são óbvias e é bom saber antes de mexer nele:

- **`parse-mensagem` aceita dois formatos de payload.** Conforme a versão, o
  WhatsApp Trigger entrega o envelope cru da Meta
  (`entry[0].changes[0].value`) ou já desembrulhado em `value`. O código trata os
  dois e documenta a estrutura assumida em comentário. Se o seu n8n entregar algo
  diferente, olhe a saída crua do trigger e ajuste a função `extrairValue()`.
- **Status callbacks são descartados ali também.** A Meta manda
  `sent`/`delivered`/`read` no mesmo campo `messages`; sem esse filtro, cada
  resposta do bot dispararia o workflow de novo.
- **Números brasileiros chegam com ou sem o 9º dígito.** A Meta às vezes entrega
  `+552189511871` para um número salvo como `+5521989511871`. O parse gera as duas
  variantes e o `SELECT` procura por ambas (`WHERE whatsapp_number IN ($1, $2)`),
  senão o vendedor "não existiria". Todas as queries usam parâmetros do node
  Postgres, não concatenação de string.

---

# Bloco (c) — nome do produto, busca real, título/descrição, 8 fotos, aprovação

Quando uma foto chega no estado `novo`, o workflow baixa a foto de verdade,
salva no Storage, e pergunta o nome do produto. A partir daí: pesquisa
informação real sobre o produto (Grounding with Google Search do Gemini) ou,
se não achar nada confiável, pergunta detalhes direto pro vendedor; gera
título e descrição; manda o GPT escrever 8 prompts de imagem customizados
pra esse produto específico; gera as 8 fotos com o Gemini; sobe tudo pro
Supabase Storage; manda título, descrição e as 8 fotos no WhatsApp, seguidos
de um menu de aprovação. Ainda sem OAuth/publicação no Mercado Livre
(bloco d) nem verificação de crédito (bloco e).

```
eh-imagem(sim) → criar-listing → buscar-url-media → baixar-foto
                                                          │
                                            salvar-foto-original-storage
                                                          │
                                            atualizar-listing-foto-original
                                                          │
                                              perguntar-nome-produto
                                                          │
                                          atualizar-estado-nome-produto (→ aguardando_nome_produto)


rotear-por-estado ─(aguardando_nome_produto)─→ salvar-nome-produto → ack-processando-1
                                                                            │
                                                                  buscar-info-produto (Grounding)
                                                                            │
                                                                    avaliar-grounding
                                                                            │
                                                                  grounding-confiavel?
                                                    ┌─── sim ────────────────┴──── não ───┐
                                                    ▼                                     ▼
                                        gerar-titulo-descricao          perguntar-detalhes-produto
                                                    ▲                                     │
                                                    │                          atualizar-estado-detalhes
                                                    │                        (→ aguardando_detalhes_produto)
                                                    │
rotear-por-estado ─(aguardando_detalhes_produto)─→ salvar-detalhes-produto → ack-processando-2 → preparar-conteudo-vendedor


gerar-titulo-descricao → montar-titulo-descricao-final → atualizar-listing-titulo-descricao
                                                                          │
                                                            envio-titulo → envio-descricao
                                                                          │
                                                              preparar-para-imagens ◄──── buscar-listing-para-regeneracao
                                                                          │                (a partir do botão "gerar de novo")
                                                            baixar-foto-para-gerar
                                                                          │
                                                              gerar-prompts-gpt (OpenAI, 1x)
                                                                          │
                                                        gerar-8-fotos-customizadas (Gemini, 8x paralelo)
                                                                          │
                                                              salvar-fotos-storage (8x paralelo)
                                                                          │
                                                              atualizar-listing-fotos
                                                                          │
                                            8x envio-foto → enviar-botoes-aprovacao → atualizar-estado-aprovacao
                                                                                        (→ aguardando_aprovacao)

rotear-por-estado ─(aguardando_aprovacao)─→ rotear-botao-aprovacao
                                              ├── aprovar         → placeholder + aguardando_oauth_ml
                                              ├── gerar_novamente → buscar-listing-para-regeneracao (mesma cauda de imagens acima)
                                              ├── editar          → placeholder
                                              └── (não é botão)   → "usa os botões da mensagem anterior"
```

Dois pontos de convergência fazem o grafo acima parecer mais complexo do que
é: `gerar-titulo-descricao` recebe tanto do caminho de busca confiável quanto
do caminho "vendedor informou detalhes" (mesmo formato de entrada nos dois);
`preparar-para-imagens` recebe tanto de uma geração nova (título/descrição
recém-criados) quanto do botão "gerar de novo" (título/descrição já
existentes, lidos de volta do banco) — dali pra frente é a mesma cauda de
nodes nos dois casos, sem duplicar Gemini/GPT/Storage/WhatsApp.

## 8. Configurar as credenciais novas

Siga [docs/gemini-supabase-storage-setup.md](docs/gemini-supabase-storage-setup.md)
inteiro: API key do Gemini, API key da OpenAI (+ billing), bucket
`listing-photos` no Supabase Storage, e a `service_role` key. Resumo do que
precisa existir no n8n antes de testar:

| Tipo | Nome | Usado por |
|---|---|---|
| Credential (Header Auth) | `Gemini API (HTTP)` | `buscar-info-produto`, `gerar-titulo-descricao` |
| Env var (`.env` do Docker) | `GEMINI_API_KEY` | `gerar-8-fotos-customizadas` |
| Env var (`.env` do Docker) | `OPENAI_API_KEY` | `gerar-prompts-gpt` |
| Env var (`.env` do Docker) | `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_URL`, `SUPABASE_STORAGE_BUCKET` | `salvar-foto-original-storage`, `salvar-fotos-storage` |

As env vars vão no `.env` do host onde o n8n roda, seguidas de
`docker compose up -d --force-recreate n8n` (um `restart` simples não relê o
`.env`). Detalhes e verificação em
[docs/gemini-supabase-storage-setup.md](docs/gemini-supabase-storage-setup.md).

As credenciais do bloco (b) continuam as mesmas — os nodes que falam com a
Graph API (`buscar-url-media`, `baixar-foto`, `envio-foto-1..8`,
`enviar-botoes-aprovacao`) reaproveitam a credencial `WhatsApp Business Cloud
(envio)` já existente.

## 9. Testar o bloco (c)

Devolva o vendedor para `novo` antes de começar (comando no fim da seção do
bloco b) e mande uma foto de produto:

| Você faz | Esperado no WhatsApp | Esperado no banco |
|---|---|---|
| Manda uma foto | *"Recebi sua foto! 📸 …qual é o nome do produto?"* | `listings` criada, `original_photo_url` já com a URL do Storage; `sellers.conversation_state = 'aguardando_nome_produto'` |
| Responde com o nome de um produto com presença online real (ex: um produto de marca conhecida) | *"Show! 🔎 Já estou pesquisando…"*, depois (alguns minutos) o título, a descrição, as 8 fotos (em ordem, 1 a 8) e os 3 botões | `generated_title` (≤60 caracteres), `generated_description` (3 seções + bloco fixo de garantia) e `generated_photos` (8 URLs, a `1-foto-principal` com `is_cover: true`) preenchidos; a descrição reflete informação real e pesquisável, sem número inventado |
| Responde com o nome de um produto sem presença online (ex: algo genérico/inventado) | *"Não achei muita informação sobre esse produto na internet. Pode me contar rapidinho as principais características dele? …"* | `sellers.conversation_state = 'aguardando_detalhes_produto'` |
| Responde essa pergunta com as características | *"Show! ✍️ Já estou montando o anúncio…"*, depois título + descrição + 8 fotos + botões, usando o que você descreveu como base | mesmo resultado da linha 2, mas com a descrição batendo com o que você informou, não com uma busca |
| Clica em **Aprovar** | *"Aprovado! ✅ …ainda não está implementada…"* | `sellers.conversation_state = 'aguardando_oauth_ml'` |
| Clica em **Gerar de novo** | Um novo conjunto de 8 fotos + botões — **sem reenviar título/descrição, sem pedir a foto nem o nome de novo** | `listings.generated_photos` sobrescrito; `generated_title`/`generated_description` continuam os mesmos |
| Clica em **Editar manualmente** | *"Edição manual …ainda não está implementada…"* | nada muda |
| Manda um texto solto em vez de clicar num botão (estando em `aguardando_aprovacao`) | *"Usa um dos botões da mensagem anterior…"* | nada muda |

Nenhuma das 8 fotos deve trazer número, medida ou certificação inventada — a
cena `8-medidas-reais` deve usar uma referência de escala visual (produto ao
lado de um objeto cotidiano) quando não houver medida confirmada, nunca um
número inventado.

Conferindo no Supabase:

```sql
select id, generated_title, jsonb_array_length(generated_photos) as n_fotos, status
from listings order by created_at desc limit 1;

select conversation_state, conversation_context from sellers where whatsapp_number = '+55...';
```

## Custo estimado por listing gerado

Estimativa grosseira, baseada em preços públicos no momento da implementação
(agosto/2026) — **confira os valores atuais** em
[ai.google.dev/pricing](https://ai.google.dev/pricing) e
[openai.com/api/pricing](https://openai.com/api/pricing) antes de levar isso a
sério, principalmente a parte de geração de imagem, que é a maior fatia:

| Etapa | Chamadas | Estimativa |
|---|---|---|
| Busca real (Grounding with Google Search) | 1 | ~US$ 0,03-0,04 (grounding tem custo por prompt acima da cota gratuita, além do custo normal de tokens) |
| Título/descrição (Gemini, texto) | 1 | < US$ 0,01 |
| Prompts de imagem (GPT, texto) | 1 | ~US$ 0,01-0,02 |
| 8 fotos (Gemini, imagem) | 8 | ~US$ 0,25-0,40 (pode ser mais se a resolução 2K custar mais que o padrão — não confirmado) |
| **Total por geração completa** | | **~US$ 0,30-0,45** |

Um "gerar de novo" **não** repete a busca nem o título/descrição — só as 8
fotos (~US$ 0,25-0,40 de novo, sem o custo de busca/GPT).

## ⚠️ Categoria regulada — sem validação automática de compliance

Este bot **não verifica** se o produto pertence a uma categoria regulada
(saneantes, cosméticos, alimentos, produtos de saúde, etc.) nem valida se o
texto gerado atende exigências de rotulagem/compliance da ANVISA ou de
qualquer outro órgão. A regra de "nunca inventar número" reduz o risco de uma
alegação falsa (ex: um percentual de eficácia inventado), mas **não é
suficiente sozinha** — um texto pode ser tecnicamente "sem números inventados"
e ainda assim usar uma alegação de saúde/segurança que a categoria não permite
sem registro. Antes de publicar um anúncio gerado pra um produto desse tipo, é
responsabilidade do vendedor revisar o texto manualmente.

## Decisões tomadas neste bloco

- **A foto é baixada da Meta e salva no Storage assim que chega**, antes de
  perguntar o nome do produto — não junto com o resto da geração. A URL
  temporária da Meta expira em minutos, mas o vendedor pode demorar bem mais
  que isso pra responder o nome; uma URL do Storage não expira.
- **`gerar-prompts-gpt` e `gerar-8-fotos-customizadas` reaproveitam a
  estrutura e as regras do script de teste já validado**
  (`ml_test/test_pipeline_gpt_gemini.py`) — nome/ordem/`regras_fixas` das
  8 cenas, nome dos dois modelos (`gpt-4.1`, `gemini-3.1-flash-image`), e a
  lógica de "GPT escreve os prompts, Gemini gera as imagens" — copiados, não
  recriados de memória. Única adaptação deliberada: o script de teste manda
  pro GPT a descrição *crua* do produto (vinda direto da busca); aqui, o
  bloco (c) pediu explicitamente pra mandar o título/descrição *já gerados*
  (o anúncio pronto) — então é isso que o node `gerar-prompts-gpt` usa como
  "descrição do produto" na mesma estrutura de prompt do script.
- **`image_size: "2K"` com fallback silencioso pra sem esse parâmetro.** Cada
  uma das 8 chamadas ao Gemini tenta primeiro com `imageSize: "2K"`; se a API
  rejeitar o parâmetro, tenta de novo sem ele (fica em resolução padrão/1K,
  que já supera o mínimo de 1200×1200 recomendado pelo Mercado Livre de
  qualquer forma).
- **Modelo de busca (grounding) assumido como `gemini-3.1-flash`** — o script
  citado como referência pro grounding (`test_gemini_grounding.py`) não está
  neste repositório/ambiente, só é mencionado em comentário dentro do script
  de imagem. Se o nome do modelo certo for outro, é uma troca de uma linha no
  node `buscar-info-produto`.
- **"Grounding confiável" = `groundingMetadata.groundingChunks` não vazio E
  texto não vazio** na resposta do Gemini — é o sinal disponível na API pra
  saber se a busca realmente ancorou a resposta em algo, em vez de só
  "alucinar" uma resposta sem fonte.
- **GARANTIA E ENVIO é texto fixo, colado por código**, nunca passa pelo
  Gemini — garante que esse bloco nunca varia nem inclui uma promessa que não
  foi combinada.
- **Regenerar ("gerar de novo") não regera título/descrição**, só as 8
  fotos — como pedido explicitamente: lê o título/descrição já salvos na
  listing em vez de gerar de novo, e pula a etapa de busca.
- **Segredos do Gemini/OpenAI/Supabase em Code nodes vêm de variáveis de
  ambiente do container** (`$env`), não de Credentials — Code node não tem como
  anexar uma Credential pela UI. Só os nodes de chamada única
  (`buscar-info-produto`, `gerar-titulo-descricao`) usam Credential de verdade.
  `SUPABASE_URL`/`SUPABASE_STORAGE_BUCKET` também são env vars (não-secretas,
  mas evita duplicar o valor hardcoded em dois Code nodes diferentes).
  Antes eram N8N Variables (`$vars`); como o n8n é self-hosted, `.env` do
  Docker ganha — as 5 chaves são coladas de uma vez e carregadas com um
  recreate do container, em vez de criadas uma a uma pela UI. Requer
  `N8N_BLOCK_ENV_ACCESS_IN_NODE` não setada ou `false` (o default é `false`).
- **As 8 chamadas ao Gemini e os 8 uploads ao Storage rodam em paralelo**
  (`Promise.all`), e o `executionTimeout` do workflow foi desabilitado
  explicitamente (`-1`) — a execução completa (busca + texto + GPT + 8
  imagens + uploads) pode passar de alguns minutos.
- **As 8 fotos são enviadas por 8 nodes HTTP Request encadeados em
  sequência** (não um Code node em loop) — usa a credencial do WhatsApp
  normalmente e garante a ordem de chegada (cenas 1 a 8) no WhatsApp.

## ⚠️ Partes não testadas contra uma instância N8N ao vivo

Este bloco foi escrito e validado logicamente (JSON bem formado, todas as
conexões resolvem, todo Code node com sintaxe JS válida), mas **sem uma
instância N8N rodando neste ambiente** pra confirmar em execução real. Riscos
reais de precisar de um ajuste pequeno no primeiro teste:

- **Formato de resposta binária dos nodes HTTP Request** (`baixar-foto`,
  `baixar-foto-para-gerar`): `options.response.response.responseFormat: "file"`
  pode variar entre versões do N8N — se o binário não vier populado, confirme
  "Response Format: File" na UI do node.
- **Nome do modelo de grounding** (`gemini-3.1-flash`, ver decisões acima) e
  **casing dos campos da resposta do Gemini** (`inline_data` vs `inlineData`,
  já tratado defensivamente no Code node de geração de imagem).
- **Formato exato de `groundingMetadata`** na resposta do Gemini — o campo
  `groundingChunks` é o documentado publicamente, mas não pôde ser conferido
  contra uma chamada real aqui; se o node `avaliar-grounding` estiver sempre
  concluindo "não confiável", esse é o primeiro lugar a inspecionar (logue
  `$json` inteiro do node `buscar-info-produto` pra ver o formato real).
- **`image_size: "2K"`**: não pôde ser confirmado se o modelo
  `gemini-3.1-flash-image` aceita esse valor exatamente assim (o script de
  teste usa o SDK Python, que pode mapear o parâmetro de forma diferente da
  REST API crua usada aqui) — o fallback sem esse parâmetro deve cobrir o
  caso de erro, mas vale conferir o log da primeira execução.

## ⚠️ Segurança — revisar antes de sair do círculo de teste

Este protótipo roda **sem RLS e sem policies** no Supabase: qualquer chave com
acesso ao banco lê e escreve tudo. Tokens do Mercado Livre (`ml_access_token`,
`ml_refresh_token`) ficam em texto puro na tabela `sellers`.

Isso é aceitável enquanto os únicos usuários somos eu e amigos.

O webhook do WhatsApp também roda **sem validação de assinatura**: o header
`X-Hub-Signature-256` que a Meta envia não é conferido, então qualquer um que
descubra a URL do webhook consegue forjar uma mensagem em nome de um número
cadastrado. Pular isso é aceitável num protótipo interno, mas é pendência
obrigatória antes de qualquer uso real.

**Antes de qualquer uso com vendedores reais**, é preciso:

- validar `X-Hub-Signature-256` com o App Secret em toda requisição do webhook;
- habilitar RLS nas 4 tabelas e escrever policies por vendedor;
- criptografar (ou mover para um secret manager) os tokens do ML;
- parar de usar a senha do usuário `postgres` no N8N e criar um role dedicado
  com permissões mínimas;
- rotacionar a senha do banco, que a essa altura já circulou em `.env` e no painel do N8N.
