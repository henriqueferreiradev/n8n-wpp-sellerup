# Setup do Gemini, da OpenAI e do Supabase Storage (bloco c)

Passo a passo manual das credenciais novas que o bloco (c) precisa: Gemini
(busca real, título/descrição, geração de imagem), OpenAI (escreve os 8
prompts de imagem customizados) e Supabase Storage (onde as fotos ficam
hospedadas). As credenciais do Postgres e do WhatsApp já foram cobertas em
[meta-whatsapp-setup.md](meta-whatsapp-setup.md) e no [README](../README.md)
— este documento só cobre o que é novo aqui.

> **Como os segredos chegam nos Code nodes:** este n8n é **self-hosted em
> Docker**, então os Code nodes leem os segredos das **variáveis de ambiente do
> container**, via `$env.NOME`. Não são mais N8N Variables (`$vars`) — as
> Variables só podem ser criadas uma a uma pela UI, enquanto as 5 chaves abaixo
> podem ser coladas de uma vez no `.env` do Docker e carregadas com um restart.
> Ver [seção 5](#5-as-5-chaves-no-env-do-docker).

---

## 1. Gemini API Key

1. Entre em <https://aistudio.google.com/apikey> (você já tem uma chave —
   se precisar gerar outra, é **Create API key** ali).
2. Essa chave é usada em **três lugares diferentes** do workflow, porque dois
   são nodes HTTP Request comuns (aceitam Credential) e um é um Code node
   (não aceita):

   | Onde | O que faz | Como configurar |
   |---|---|---|
   | Node `buscar-info-produto` (HTTP Request) | Busca real (Grounding with Google Search) | Credential **Header Auth**, nome exato **`Gemini API (HTTP)`** — Header Name: `x-goog-api-key`, Header Value: sua chave. |
   | Node `gerar-titulo-descricao` (HTTP Request) | Escreve título + descrição | Mesma credential `Gemini API (HTTP)` acima. |
   | Node `gerar-8-fotos-customizadas` (Code node, 8 chamadas em paralelo) | Gera as 8 imagens | Variável de ambiente `GEMINI_API_KEY` no `.env` do Docker — Code node não tem como anexar uma Credential pela UI do n8n, então ele lê a chave via `$env.GEMINI_API_KEY`. |

3. Criar a credencial: **Settings → Credentials → Add credential → Header Auth**.
4. Adicionar a variável de ambiente: coloque `GEMINI_API_KEY=<sua-chave>` no
   `.env` do Docker (mesmo valor da credential) e recrie o container — ver
   [seção 5](#5-as-5-chaves-no-env-do-docker).

## 2. OpenAI API Key (GPT escreve os prompts de imagem)

1. Entre em <https://platform.openai.com/api-keys> e crie uma chave nova
   (**Create new secret key**) se ainda não tiver uma.
2. **Billing:** a API da OpenAI só funciona com um método de pagamento
   cadastrado (mesmo que o uso fique em centavos) — confira em
   **Settings → Billing** no painel da OpenAI. Sem isso, as chamadas do node
   `gerar-prompts-gpt` retornam erro de billing/quota, não de autenticação —
   se aparecer um erro assim, é o primeiro lugar a olhar.
3. Modelo usado: **`gpt-4.1`** (copiado de `MODEL_TEXTO_OPENAI` no script de
   referência `ml_test/test_pipeline_gpt_gemini.py`; o próprio script já
   avisa que pode ser preciso trocar se esse nome deixar de existir na sua
   conta — nesse caso, troque a constante `MODEL_TEXTO_OPENAI` no topo do
   Code node `gerar-prompts-gpt`). Confira os modelos disponíveis na sua conta
   em <https://platform.openai.com/docs/models>.
4. Configure como **variável de ambiente do container**: `OPENAI_API_KEY` no
   `.env` do Docker — lida pelo Code node `gerar-prompts-gpt` via
   `$env.OPENAI_API_KEY`, mesma razão dos outros Code nodes deste bloco
   (não anexam Credential pela UI).

## 3. Bucket do Supabase Storage

1. No painel do Supabase do projeto já criado no bloco (a): **Storage → New bucket**.
2. Nome do bucket: **`listing-photos`**.
3. **Public bucket: sim.** Decisão tomada e o tradeoff:
   - Signed URLs (com expiração) pareciam a opção "mais segura" à primeira
     vista, mas quebrariam a visualização das fotos no WhatsApp depois que a
     URL vencesse, e o bloco (d) (publicação no Mercado Livre) também vai
     precisar de uma URL estável pra cadastrar as fotos do anúncio. Além
     disso, neste bloco a foto original precisa ser **relida do Storage** em
     pelo menos duas execuções diferentes do workflow (quando o vendedor
     responde o nome do produto, e de novo se clicar em "gerar de novo")
     — uma URL que expira quebraria esse relacionamento.
   - Bucket público significa que qualquer um com a URL exata (que inclui o
     `listing_id`, um UUID) consegue ver a foto — não é indexado nem
     listável, mas também não tem controle de acesso nenhum. Aceitável pro
     protótipo, no mesmo espírito do restante da seção de segurança do
     README (sem RLS, sem policies).
4. **Free tier (1GB)** confirmado suficiente para o protótipo — cada listing
   grava 9 imagens (1 original + 8 geradas). Se as 8 geradas saírem em 2K
   (~2048×2048, ver nota sobre `image_size` no README) em vez de 1K, cada
   imagem fica mais pesada — ainda assim, dá pra várias dezenas de testes
   antes de chegar perto do limite.

## 4. Service role key

1. **Project Settings → API** no painel do Supabase.
2. Copie a **`service_role` key** (⚠️ **não** é a mesma coisa que a connection
   string do Postgres do bloco (a), nem a `anon` key). Ela dá acesso total ao
   projeto, ignorando RLS — necessária aqui porque o upload é feito pelo n8n,
   não pelo usuário final.
3. Configure como variável de ambiente: `SUPABASE_SERVICE_ROLE_KEY` no `.env`
   do Docker.
4. Configure também **duas outras variáveis de ambiente**, não-secretas mas
   usadas pelos mesmos Code nodes (evita ter a URL do projeto/nome do bucket
   hardcoded e duplicado em mais de um node):
   - `SUPABASE_URL` — ex: `https://SEU-PROJETO.supabase.co`
   - `SUPABASE_STORAGE_BUCKET` — `listing-photos`

## 5. As 5 chaves no `.env` do Docker

Cole este bloco no `.env` que o seu `docker-compose.yml` do n8n usa (ou, se o
compose declara as variáveis inline, no `environment:` do serviço `n8n`),
preenchendo os valores:

```dotenv
GEMINI_API_KEY=
OPENAI_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_STORAGE_BUCKET=
```

Depois **recrie o container** pra ele carregar as variáveis novas:

```bash
docker compose up -d --force-recreate n8n
```

Um `docker restart` simples **não** relê o `.env` se as variáveis foram
adicionadas depois de o container ter sido criado — o ambiente de um container
é fixado na criação. Por isso é `up -d --force-recreate` (ou
`docker compose down && docker compose up -d`), não `restart`.

**Como conferir se chegou:**

```bash
docker compose exec n8n printenv | grep -E 'GEMINI|OPENAI|SUPABASE'
```

Deve listar as 5. Se listar menos, o `.env` não está sendo lido pelo serviço
certo — confira `env_file:` / `environment:` no compose.

### `N8N_BLOCK_ENV_ACCESS_IN_NODE` precisa ficar `false`

O acesso a `$env` dentro de Code nodes e expressões é controlado por essa
variável do próprio n8n. Segundo a
[documentação oficial](https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/security/),
ela é booleana com **default `false`**, e o significado é: *"Whether to allow
users to access environment variables in expressions and the Code node (false)
or not (true)"*. Ou seja:

- **`false` ou não setada (default): `$env` funciona.** É o caso normal de uma
  instância self-hosted que não mexeu nisso — não precisa fazer nada.
- **`true`: `$env` fica bloqueado nos Code nodes** e os 4 Code nodes deste
  bloco quebram em runtime. Se estiver assim, remova a linha do `.env` (ou
  troque para `false`) e recrie o container.

Conferir:

```bash
docker compose exec n8n printenv | grep N8N_BLOCK_ENV_ACCESS_IN_NODE
```

Sem saída = não setada = default `false` = `$env` liberado.

## Resumo do que precisa existir antes de testar o bloco (c)

| Tipo | Nome | Usado por |
|---|---|---|
| Credential (Header Auth) | `Gemini API (HTTP)` | `buscar-info-produto`, `gerar-titulo-descricao` |
| Env var (`.env` do Docker) | `GEMINI_API_KEY` | `gerar-8-fotos-customizadas` |
| Env var (`.env` do Docker) | `OPENAI_API_KEY` | `gerar-prompts-gpt` |
| Env var (`.env` do Docker) | `SUPABASE_SERVICE_ROLE_KEY` | `salvar-foto-original-storage`, `salvar-fotos-storage` |
| Env var (`.env` do Docker) | `SUPABASE_URL` | idem |
| Env var (`.env` do Docker) | `SUPABASE_STORAGE_BUCKET` | idem |

> **Nota de segurança:** as 3 chaves secretas (`GEMINI_API_KEY`,
> `OPENAI_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`) ficam em texto puro no `.env`
> do host e visíveis via `docker inspect` / `printenv` pra quem tiver acesso ao
> host. É o mesmo nível de exposição que a senha do Postgres já tem hoje —
> documentado, não ideal, aceitável enquanto o círculo de uso é só você e
> amigos (ver aviso de segurança no README).

As credenciais do bloco (b) continuam as mesmas — os nodes que falam com a
Graph API (`buscar-url-media`, `baixar-foto`, `envio-foto-1..8`,
`enviar-botoes-aprovacao`) reaproveitam a credencial `WhatsApp Business Cloud
(envio)` já existente (via *Predefined Credential Type* no HTTP Request node),
sem precisar de nada novo ali.

> ⚠️ Ao editar `n8n-workflows/bot-whatsapp-estados.json`, os blocos
> `credentials` de nodes que já existem no arquivo **nunca** devem ser
> regenerados nem trocados por placeholder. Ver
> [AVISO-credenciais.md](AVISO-credenciais.md).
