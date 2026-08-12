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
.env.example                             variáveis de conexão com o Supabase
```

| Bloco | Escopo | Situação |
|---|---|---|
| **(a)** | Camada de dados: Supabase + tabelas | ✅ pronto |
| **(b)** | Recebimento do WhatsApp + máquina de estados | ✅ pronto |
| (c) | Geração de fotos, título, descrição e score | — |
| (d) | OAuth e publicação no Mercado Livre | — |
| (e) | Créditos e cobrança | — |

Ainda não existe backend/API próprio, nem chamada ao Gemini, nem ao Mercado
Livre. As respostas do bot nos estados dos blocos (c) em diante são placeholders
que dizem explicitamente que a etapa não foi implementada.

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
| Uma foto | *"Recebi sua foto! 📸 …essa parte ainda não está implementada."* | nova linha em `listings` com `original_photo_url = 'whatsapp_media:<id>'`; vendedor vai para `aguardando_geracao` |
| Qualquer coisa depois disso | *"Você já está numa etapa mais avançada do fluxo (aguardando_geracao)…"* | nada muda |
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
