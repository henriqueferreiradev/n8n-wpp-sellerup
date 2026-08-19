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
