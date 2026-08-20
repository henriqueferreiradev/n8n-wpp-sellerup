# sellerup v3 — instruções para o Claude Code

Protótipo de bot de WhatsApp que monta e publica anúncios no Mercado Livre.
A orquestração fica num **n8n self-hosted (Docker)**; o banco é um Postgres do
Supabase. Não há backend próprio neste repo — ele guarda o workflow do n8n,
migrations, seeds e docs.

## 🔴 REGRA CRÍTICA — credenciais do workflow do n8n

Ao editar `n8n-workflows/bot-whatsapp-estados.json`:

1. Para **qualquer node que já exista no arquivo antes da sua edição** e cujo
   bloco `credentials` tenha valores reais (id/name que **não** são
   `REPLACE_ME_*`): **preserve esse bloco `credentials` exatamente como está**,
   byte a byte. Não regenere, não normalize, não troque por placeholder —
   **mesmo que você esteja reescrevendo o node inteiro por outro motivo**
   (query, prompt, parâmetro, posição).
2. `REPLACE_ME_*` só pode aparecer em nodes **genuinamente novos**, que nunca
   existiram no arquivo. Aí é inevitável: o Henrique vincula na UI uma vez.
3. **Na dúvida se um node é novo ou já existia, PERGUNTE** antes de decidir.
   Não assuma.

Motivo: reimportar o workflow com placeholder derruba a vinculação de
credencial e obriga a reselecionar a credencial na UI em ~15 nodes, toda vez.

Detalhes, comandos de verificação e o passo pendente de versionar os ids reais:
[docs/AVISO-credenciais.md](docs/AVISO-credenciais.md).

Sempre que terminar uma edição nesse arquivo, confira o diff:

```bash
git diff n8n-workflows/bot-whatsapp-estados.json | grep -E '^[+-].*"(id|name)":'
```

Nenhum id real pode ter virado `REPLACE_ME_*`.

## Segredos em Code nodes: `$env`, não `$vars`

Os Code nodes leem segredos das variáveis de ambiente do container
(`$env.NOME`), definidas no `.env` do Docker — **não** de N8N Variables
(`$vars`), que só podem ser criadas uma a uma pela UI. As 5 chaves esperadas
(`GEMINI_API_KEY`, `OPENAI_API_KEY`, `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET`) e o requisito de
`N8N_BLOCK_ENV_ACCESS_IN_NODE` ficar `false` estão em
[docs/gemini-supabase-storage-setup.md](docs/gemini-supabase-storage-setup.md).

Ao adicionar um Code node novo que precise de segredo, use `$env.NOME` e
documente a chave nesse doc.

## 🔴 Chamada HTTP a API externa NÃO mora em Code node

Com **Task Runners** habilitado (o n8n roda Code nodes num processo externo),
`this.helpers.httpRequest` dentro de um Code node é proxied por **RPC** para o
processo principal. Isso já causou **dois bugs distintos**, os dois caros de
diagnosticar:

1. **`Buffer` não sobrevive à serialização RPC** — chega do outro lado como
   objeto JSON comum. O arquivo gravado no Supabase Storage era o texto literal
   `{"type":"Buffer","data":[...]}` (poucos bytes) em vez da imagem, o que por
   tabela gerava o `400 "Unable to process input image"` do Gemini, porque a
   foto de referência relida do Storage estava corrompida.
2. **O corpo do erro é apagado** — o Task Runner limpa `config`/`response` do
   erro do Axios antes dele sair do runner. Quando uma cena falhava (bloqueio de
   segurança do Gemini, parâmetro inválido, 503), o erro chegava vazio
   (`config: {}`) e só dava pra descobrir o motivo reproduzindo a chamada com
   curl/Python **fora do n8n**. Num HTTP Request nativo, a UI mostra
   "Full message"/"Request" com a resposta real — igual sempre funcionou em
   `buscar-info-produto` e `gerar-titulo-descricao`.

**Regra:** toda chamada a API externa — e todo POST de conteúdo binário — usa
**HTTP Request node nativo**. Para binário, `Body Content Type = n8n Binary
File` (`contentType: "binaryData"` + `inputDataFieldName`), que lê a propriedade
binária direto do item. Nunca reintroduza `Buffer.from(...)` nem
`this.helpers.httpRequest` num Code node.

Code node continua ótimo para o que é só transformação de dados (montar
prompt, extrair campo de JSON, agregar items) — inclusive devolver binário no
formato nativo (`{ data: <base64>, mimeType, fileName }`) é seguro.

Nodes que existem por causa disso — **não** colapsar de volta num Code node só
porque "daria pra simplificar":

| Node | Tipo | Papel |
|---|---|---|
| `montar-itens-cenas` | Code | monta os 8 items (prompt + foto), sem HTTP |
| `gerar-foto-cena` | HTTP Request | chama o Gemini, 1 request por cena |
| `extrair-imagem-cena` | Code | extrai o base64 da resposta e vira binário |
| `upload-foto-original-storage` | HTTP Request | sobe a foto original |
| `montar-url-foto-original` | Code | só monta a URL pública, não sobe nada |
| `upload-fotos-storage` | HTTP Request | sobe as 8 geradas, 1 request por item |
| `montar-lista-fotos-storage` | Code | agrega os 8 uploads em `generated_photos` |

Os pares Code→HTTP→Code parecem verbosos de propósito: o Code node de antes só
prepara, o de depois só interpreta, e a chamada fica no meio, nativa e visível.

### Pendência conhecida: `gerar-prompts-gpt`

`gerar-prompts-gpt` **ainda chama a OpenAI de dentro de um Code node** e por
isso continua sujeito ao problema (2): se a chamada falhar (billing, rate
limit, modelo inexistente), o erro vem sem corpo. Não foi convertido junto
porque estava fora do escopo pedido, não porque seja seguro.

O motivo original de ele ser Code node — montar um prompt gigante em JS é mais
seguro contra erro de escaping do que encaixar tudo num body JSON — já não vale
mais: o par `montar-itens-cenas` → `gerar-foto-cena` resolve exatamente isso,
montando o texto no Code node e injetando com
`{{ JSON.stringify($json.campo).slice(1, -1) }}` no body do HTTP Request.
Quando for mexer nesse node, converta no mesmo padrão.

Checagem rápida antes de commitar:

```bash
grep -c 'Buffer.from' n8n-workflows/bot-whatsapp-estados.json         # tem que dar 0
grep -c 'helpers.httpRequest' n8n-workflows/bot-whatsapp-estados.json # 2 = só gerar-prompts-gpt; subiu = regressão
```

## 🔴 Ordem de entrega no WhatsApp ≠ ordem de execução no n8n

As 8 fotos são enviadas como `"image": { "link": "<url do Supabase>" }`. A Graph
API responde **200 assim que ACEITA** a mensagem — o download da imagem a partir
da URL acontece depois, do lado da Meta. Então:

> encadear os nodes em série garante a ordem das *chamadas*, **não** a ordem em
> que as mensagens chegam no aparelho do vendedor.

Foi exatamente isso que fez a mensagem "💡 Dica pra Mercado Livre" aparecer entre
a foto 2 e a foto 3 em produção: a cadeia `envio-foto-1 → … → envio-foto-8 →
envio-dica-capa` estava correta, sem nenhuma ramificação paralela — mas um texto
não tem nada pra baixar e ultrapassou as fotos ainda em download.

**Ao investigar uma mensagem fora de ordem, cheque as conexões primeiro, mas não
pare aí:** se a cadeia já for uma linha reta, a causa é esta e nenhuma mudança
de wiring resolve.

Mitigação atual: o node `aguardar-entrega-fotos` (Wait, 15s) entre
`envio-foto-8` e `envio-dica-capa`. É uma folga, não uma garantia.

**Correção definitiva, se voltar a escapar:** subir cada foto em
`POST /{phone_number_id}/media` e mandar por `media_id` em vez de `link` — aí a
Meta já tem os bytes e não há download pendente. Custa 8 uploads a mais e mexe
na cadeia de envio, por isso não foi feito ainda.

> ⚠️ O node Wait tem `unit` default **`hours`**. Sempre declare
> `"unit": "seconds"` explicitamente — sem isso, `amount: 15` vira 15 horas.

## Comandos globais têm precedência sobre o estado

`rotear-comando-global` roda **antes** de `rotear-por-estado` e intercepta
comandos que valem em qualquer `conversation_state` (hoje: o texto `menu` e as
respostas da lista do menu). O fallback dele, `fluxo_normal`, segue pro
`rotear-por-estado`, então mensagem comum não muda de comportamento.

É a saída de emergência de um vendedor travado — antes disso, quem ficasse preso
em `aguardando_aprovacao` esperando um clique só saía com `UPDATE` manual no
banco. Comando global novo entra **nesse switch**, não no de estado.

## Limites da Graph API em mensagens interativas

Mensagem de lista é rejeitada inteira (400) se qualquer campo estourar. A Meta
conta em **unidades UTF-16** (emoji fora do BMP contam 2):

| Campo | Limite |
|---|---|
| `header.text` | 60 |
| `body.text` | 1024 |
| `action.button` | 20 |
| `sections[].title` | 24 |
| `rows[].title` | **24** |
| `rows[].description` | 72 |
| total de `rows` | 10 |

O título `🛒 Publicar no Mercado Livre` (27) já estourou uma vez e virou
`🛒 Publicar no ML`, com o nome completo movido pra `description`. Ao mexer no
menu, confira os títulos antes de importar.

## Decisões tomadas — não reabrir sem pedido explícito

- Nodes nativos de envio de WhatsApp (`n8n-nodes-base.whatsApp`) ficam como
  estão, com Credential normal. **Não** converter para HTTP Request: já
  validados em produção, o risco não compensa o ganho. (As mensagens
  interativas — Reply Buttons — são a exceção que já usa HTTP Request, porque
  o node nativo não suporta.)
- Bucket do Supabase Storage é **público**, de propósito: as URLs precisam
  sobreviver entre execuções e servir o bloco (d). Tradeoff documentado no doc
  de setup.

## Notas de mecânica

- `n8n-workflows/bot-whatsapp-estados.json` é **JSON estrito** — não aceita
  comentários. Avisos de processo vão em `docs/`, não dentro do arquivo.
- Os comentários explicativos dentro dos `jsCode` dos Code nodes são
  intencionais e devem ser mantidos/atualizados junto com o código.
- Comentários, nomes de node e mensagens do bot são em **português**. Mantenha.
