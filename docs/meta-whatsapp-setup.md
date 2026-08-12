# Setup do app da Meta (WhatsApp Cloud API)

Passo a passo manual, feito uma vez. No fim você terá quatro valores para colar
no N8N: **App ID**, **App Secret**, **Access Token** e **Business Account ID**.

---

## ⚠️ Leia isto antes de começar

### Números de teste só falam com destinatários pré-verificados

O número de teste que a Meta dá de graça **só consegue enviar mensagem para uma
lista curta de destinatários cadastrados à mão** — normalmente até **5 números**.

Isso é assimétrico e engana: uma mensagem vinda de um número não cadastrado
**chega no seu webhook normalmente**, o workflow roda inteiro sem erro, mas a
resposta do bot **não é entregue** (a API devolve erro no node de envio). Você vê
o fluxo verde no N8N e nada no celular.

Cada número que for testar o bot — o seu e o do amigo — precisa ser adicionado em
**WhatsApp → API Setup → "To"**, no seletor de destinatários (*Manage phone
number list*). A Meta manda um código por SMS/WhatsApp que precisa ser digitado
ali para confirmar. Faça isso para os **dois números do seed** antes de testar.

### Um webhook por app

A Meta permite registrar **apenas uma URL de webhook por app**. Se você tiver
outro projeto apontando para o mesmo app/número, **um sobrescreve o webhook do
outro** silenciosamente — o projeto antigo simplesmente para de receber mensagem.
Se já usa esse app em outro teste, crie um app novo para este projeto.

### O Access Token de teste dura 24h

O token que aparece em *API Setup* é **temporário: expira em 24 horas**. Quando o
bot parar de responder do nada e o node de envio começar a dar erro 401, é isso.
Volte em API Setup, gere um token novo e atualize a credencial de envio no N8N.

Enquanto for teste interno, renovar à mão está de bom tamanho. Para um token
permanente é preciso criar um System User em *Business Settings → System Users*
com permissão `whatsapp_business_messaging` — fora do escopo desta fase.

---

## 1. Criar o app

1. Entre em <https://developers.facebook.com/apps> → **Create App**.
2. Tipo: **Business**.
3. Dê um nome (ex: `score-li-bot`) e associe a um Business Portfolio (crie um se
   não tiver — a Meta pede).
4. Na tela de produtos, procure **WhatsApp** e clique em **Set up**.

## 2. Usar o número de teste

Ao adicionar o produto WhatsApp, a Meta já provisiona um **número de teste**
automaticamente. Não é preciso número dedicado, nem verificação de negócio, nem
cartão de crédito nesta fase.

Em **WhatsApp → API Setup** você verá:

- **From**: o número de teste e, logo abaixo, o **Phone number ID**.
- **To**: o seletor de destinatários — é aqui que você cadastra os números de
  teste (veja o aviso no topo deste documento).

## 3. Cadastrar os números destinatários

1. **WhatsApp → API Setup → To → Manage phone number list**.
2. **Add phone number** → digite o número em formato internacional
   (ex: `+55 21 98951-1871`).
3. A Meta envia um código por WhatsApp/SMS → digite para confirmar.
4. Repita para o segundo número de teste.

Confira que os números batem exatamente com os de
[seeds/001_test_sellers.sql](../seeds/001_test_sellers.sql). Se não baterem, o bot
responde *"Esse número ainda não está liberado"* — o vendedor não existe no banco.

## 4. Pegar App ID e App Secret

**App Settings → Basic**:

- **App ID** → vira o *Client ID* da credencial OAuth2 do Trigger.
- **App Secret** → clique em *Show*, digite sua senha do Facebook → vira o
  *Client Secret*.

## 5. Pegar Access Token e Business Account ID

**WhatsApp → API Setup**:

- **Temporary access token** → botão de copiar (lembre: 24h).
- **WhatsApp Business Account ID** → aparece logo abaixo do seletor de número.

> Não confunda **WhatsApp Business Account ID** com **Phone number ID**. São dois
> valores diferentes na mesma tela. A credencial do N8N pede o *Business Account
> ID*; o *Phone number ID* o workflow já lê sozinho do payload do webhook.

## 6. Criar as duas credenciais no N8N

São **duas credenciais separadas**, uma para receber e outra para enviar. É assim
mesmo — não é redundância.

### a) `WhatsApp OAuth (trigger)` — tipo **WhatsApp OAuth API**

Usada pelo node **WhatsApp Trigger**.

| Campo | Valor |
|---|---|
| Client ID | App ID (passo 4) |
| Client Secret | App Secret (passo 4) |

Clique em **Connect my account** e conclua o login com o Facebook. O N8N
**registra o webhook na Meta sozinho** quando o workflow é ativado — você não
precisa configurar Callback URL nem Verify Token à mão.

### b) `WhatsApp Business Cloud (envio)` — tipo **WhatsApp API**

Usada pelos nodes de envio de mensagem.

| Campo | Valor |
|---|---|
| Access Token | token temporário (passo 5) |
| Business Account ID | WhatsApp Business Account ID (passo 5) |

> **Use exatamente esses dois nomes** ao criar as credenciais. O JSON do workflow
> referencia as credenciais por nome, então o import já liga tudo sozinho. Se
> usar outro nome, você terá que reselecionar a credencial em cada node à mão.

## 7. Ativar e conferir o registro do webhook

Ative o workflow no N8N (toggle *Active*). Depois volte em **WhatsApp →
Configuration → Webhook** no painel da Meta e confirme que:

- a **Callback URL** aponta para a URL de produção do seu N8N Cloud;
- o campo **`messages`** está com *Subscribe* marcado.

Se o campo `messages` não estiver assinado, nada chega — é o erro mais comum
depois do problema dos destinatários não cadastrados.

---

## Diagnóstico rápido

| Sintoma | Causa provável |
|---|---|
| Nada chega no N8N | Workflow inativo, ou campo `messages` sem subscribe, ou outro app sobrescreveu o webhook |
| Workflow roda verde, mensagem não chega no celular | Número destinatário não cadastrado em *API Setup → To* |
| Node de envio dá 401 / `access token expired` | Token de 24h venceu — gere outro e atualize a credencial |
| Bot responde "número não liberado" para um número seu | Número do banco ≠ número que a Meta manda; confira o seed |
| Workflow dispara sozinho depois de cada resposta | Status callbacks (`sent`/`delivered`) — o node `parse-mensagem` já filtra; confira se ele não foi alterado |
