# score.li — camada de dados (bloco a)

Protótipo de ferramenta para vendedores do Mercado Livre, operada por um bot de
WhatsApp. Este repositório contém, por enquanto, **só a camada de dados**: as
migrations SQL, uma seed de teste e a documentação do modelo. A orquestração do
fluxo fica no N8N Cloud; o banco é um Postgres do Supabase.

```
migrations/001_initial_schema.sql   4 tabelas + índices + triggers de updated_at
seeds/001_test_sellers.sql          2 vendedores de teste com crédito liberado
docs/data-model.md                  descrição de cada tabela e campo
.env.example                        variáveis de conexão com o Supabase
```

Nenhum backend/API próprio, nenhum workflow de N8N com lógica de negócio, nenhuma
integração com WhatsApp/Gemini/Mercado Livre/Pix — isso vem nos próximos blocos.

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
   **Postgres**.
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

## ⚠️ Segurança — revisar antes de sair do círculo de teste

Este protótipo roda **sem RLS e sem policies** no Supabase: qualquer chave com
acesso ao banco lê e escreve tudo. Tokens do Mercado Livre (`ml_access_token`,
`ml_refresh_token`) ficam em texto puro na tabela `sellers`.

Isso é aceitável enquanto os únicos usuários somos eu e amigos. **Antes de
qualquer uso com vendedores reais**, é preciso:

- habilitar RLS nas 4 tabelas e escrever policies por vendedor;
- criptografar (ou mover para um secret manager) os tokens do ML;
- parar de usar a senha do usuário `postgres` no N8N e criar um role dedicado
  com permissões mínimas;
- rotacionar a senha do banco, que a essa altura já circulou em `.env` e no painel do N8N.
