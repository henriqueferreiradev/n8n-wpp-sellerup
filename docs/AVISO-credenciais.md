# ⚠️ AVISO — nunca sobrescrever credenciais já vinculadas no workflow

Regra de processo permanente para **qualquer agente ou pessoa** que edite
`n8n-workflows/bot-whatsapp-estados.json`. Vale para toda edição futura, não só
para a que criou este documento.

## O problema que isso resolve

Cada node de WhatsApp e de Postgres do workflow tem um bloco `credentials` que
aponta para uma credencial real da instância do n8n:

```json
"credentials": {
  "postgres": { "id": "aBcD1234EfGh5678", "name": "Supabase Postgres" }
}
```

Quando o workflow era regerado/reescrito, esse bloco voltava a ser um
placeholder (`"id": "REPLACE_ME_POSTGRES"`). Reimportar o arquivo assim
**derruba a vinculação de credencial**, e alguém tem que reselecionar a
credencial na UI em ~15 nodes, um por um, a cada rodada. Isso não pode mais
acontecer.

## A regra

1. **Node que já existia no arquivo ANTES da edição, com `credentials`
   preenchido com valores reais** (id/name que não são `REPLACE_ME_*`):
   preserve o bloco `credentials` **exatamente como está**, byte a byte. Não
   regenere, não normalize, não troque por placeholder — **mesmo que você esteja
   reescrevendo o node inteiro por outro motivo** (mudança de query, de prompt,
   de parâmetro, de posição, o que for).

2. **`REPLACE_ME_*` só é aceitável em nodes genuinamente NOVOS**, que nunca
   existiram no arquivo antes. Nesse caso o placeholder é inevitável: o
   Henrique vai ter que criar/vincular a credencial na UI uma vez.

3. **Na dúvida se um node é "novo" ou "já existia", PERGUNTE antes de decidir.**
   Não assuma. `git log`/`git show HEAD:n8n-workflows/bot-whatsapp-estados.json`
   costuma responder, mas se não responder, pergunte.

## Como verificar antes e depois de editar

Listar todas as vinculações de credencial do arquivo:

```bash
python -c "import io,json; d=json.loads(io.open('n8n-workflows/bot-whatsapp-estados.json',encoding='utf-8').read()); [print('%-42s %-22s id=%s' % (n['name'],t,c.get('id'))) for n in d['nodes'] for t,c in (n.get('credentials') or {}).items()]"
```

Comparar contra a versão commitada — nenhum id real pode ter virado placeholder:

```bash
git diff n8n-workflows/bot-whatsapp-estados.json | grep -E '^[+-].*"(id|name)":' 
```

Se aparecer um `-` com um id real e um `+` com `REPLACE_ME_*` na mesma posição,
a regra foi violada: reverta esse bloco.

## Pré-requisito importante (estado atual do arquivo)

Hoje, **todos os 39 blocos `credentials` do arquivo commitado ainda estão como
`REPLACE_ME_*`** — nenhum id real foi versionado ainda. Ou seja: a regra acima
está no lugar, mas **ainda não há nada para ela proteger**.

Para a regra passar a ter efeito de verdade, é preciso fazer isso **uma vez**:

1. Importar o workflow no n8n e vincular as credenciais na UI (a rodada
   manual que já acontece hoje).
2. Exportar o workflow de volta do n8n (**⋯ → Download**) e substituir
   `n8n-workflows/bot-whatsapp-estados.json` por esse export.
3. Commitar. A partir daí o arquivo carrega os ids reais, e toda edição futura
   é obrigada a preservá-los pela regra acima.

Alternativa mais rápida, se preferir não exportar: pegar os ids das credenciais
na UI do n8n (aparecem na URL ao abrir a credencial, `/credentials/<id>`) e
substituir os `REPLACE_ME_*` no arquivo à mão, uma vez.

> Nota: os ids de credencial **não são segredos** — são identificadores locais
> da instância do n8n, não as chaves em si. Commitar eles é seguro; os valores
> secretos continuam só dentro do n8n e no `.env` do Docker.

## Fora de escopo (decisões já tomadas, não reabrir)

- Os nodes nativos de envio de WhatsApp (`n8n-nodes-base.whatsApp`) **ficam como
  estão**, usando Credential normal. Não converter para HTTP Request — já estão
  validados em produção e o risco não compensa o ganho.
- Segredos de Code node vêm de `$env` (`.env` do Docker), não de `$vars` /
  N8N Variables. Ver
  [gemini-supabase-storage-setup.md](gemini-supabase-storage-setup.md).
