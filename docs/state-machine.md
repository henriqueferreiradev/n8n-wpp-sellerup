# Máquina de estados da conversa

O estado vive em `sellers.conversation_state` (text) e os dados temporários da
conversa em `sellers.conversation_context` (jsonb), como definido em
[docs/data-model.md](data-model.md).

> **Bloco (c): todas as transições abaixo até `aguardando_aprovacao` (e as 3
> saídas de `aguardando_aprovacao`) já existem de verdade.** O que ainda é
> placeholder: `aguardando_oauth_ml` e `publicando` (bloco d), e edição manual
> real do título/descrição.

## Diagrama

```mermaid
stateDiagram-v2
    [*] --> novo: seed / vendedor cadastrado à mão

    novo --> aguardando_nome_produto: recebe imagem ✅ bloco (c)
    novo --> novo: recebe texto (só pede a foto) ✅ bloco (b)

    aguardando_nome_produto --> aguardando_geracao: vendedor informa o nome ✅ bloco (c)
    aguardando_geracao --> aguardando_detalhes_produto: busca não achou nada confiável ✅ bloco (c)
    aguardando_detalhes_produto --> aguardando_geracao: vendedor informa detalhes ✅ bloco (c)
    aguardando_geracao --> aguardando_aprovacao: título/descrição/fotos prontos ✅ bloco (c)

    aguardando_aprovacao --> aguardando_aprovacao: botão "gerar de novo" (regera as 8 fotos, mesmo título/descrição) ✅ bloco (c)
    aguardando_aprovacao --> aguardando_oauth_ml: botão "aprovar" ✅ bloco (c) (placeholder de OAuth)
    aguardando_aprovacao --> aguardando_creditos: aprovado, sem saldo 🔜 bloco (e)
    aguardando_creditos --> aguardando_oauth_ml: crédito liberado 🔜 bloco (e)
    aguardando_oauth_ml --> publicando: OAuth concluído 🔜 bloco (d)
    aguardando_aprovacao --> publicando: aprovado, tudo pronto 🔜 bloco (d)
    publicando --> novo: anúncio publicado 🔜 bloco (d)
```

Legenda: ✅ implementado · 🔜 planejado

`aguardando_geracao` aparece duas vezes no diagrama (ida e volta) porque, na
prática, ele é só um estado de trânsito: o vendedor nunca fica "parado" nele
esperando alguém digitar algo — ou a execução segue direto pra
`aguardando_detalhes_produto` (se a busca não achou nada confiável) ou direto
pra `aguardando_aprovacao` (se achou, ou se o vendedor acabou de informar os
detalhes). Ver [README](../README.md), seção do bloco (c), pro fluxo completo
passo a passo.

## Estados

| Estado | O que significa | Entra quando | Sai quando | Bloco responsável | Hoje |
|---|---|---|---|---|---|
| `novo` | Ocioso. Sem anúncio em andamento; esperando uma foto. | Valor default do schema; volta aqui depois de publicar | Chega uma imagem | **(b)** | ✅ implementado |
| `aguardando_nome_produto` | Foto já baixada e salva; esperando o vendedor informar o nome do produto | Imagem recebida em `novo` | Vendedor responde com o nome | **(c)** | ✅ implementado |
| `aguardando_geracao` | Nome/detalhes recebidos; buscando informação real, gerando título/descrição/fotos | Nome ou detalhes do produto informados | Geração termina (→ `aguardando_aprovacao`) ou busca não confiável (→ `aguardando_detalhes_produto`) | **(c)** | ✅ implementado (é um estado de trânsito — ver nota acima) |
| `aguardando_detalhes_produto` | A busca não achou informação confiável sobre o produto; esperando o vendedor descrever as características | Busca sem `groundingChunks` / sem texto | Vendedor responde com os detalhes | **(c)** | ✅ implementado |
| `aguardando_aprovacao` | Anúncio (título + descrição + 8 fotos) enviado; esperando um dos 3 botões (aprovar / gerar de novo / editar) | Geração conclui | Usuário responde com um botão | **(c)** | ✅ implementado (as 3 transições respondem; "aprovar" e "editar" levam a placeholders dos blocos d/futuro) |
| `aguardando_creditos` | Aprovado, mas sem saldo para publicar | Aprovação sem `credit_balance` suficiente | Crédito liberado | **(e)** | placeholder |
| `aguardando_oauth_ml` | Falta ligar a conta do Mercado Livre | Botão "aprovar" em `aguardando_aprovacao` | Callback do OAuth grava os tokens | **(d)** | entra (placeholder), não sai ainda |
| `publicando` | Publicação no ML em andamento | Tudo pronto e aprovado | ML devolve o `ml_item_id` | **(d)** | placeholder |
| *(qualquer outro)* | Estado inesperado — bug ou schema em evolução | — | — | — | placeholder de "não reconheço" |

**`aguardando_oauth_ml` é um beco sem saída hoje**: a transição de entrada é
real (o botão "aprovar" grava e muda o estado), mas nada implementa a saída
até o bloco (d). Para destravar um vendedor de teste (de qualquer estado):

```sql
update sellers set conversation_state = 'novo' where whatsapp_number = '+55...';
```

## Notas de implementação

- **`aguardando_nome_produto` e `aguardando_detalhes_produto` são novos no
  bloco (c).** Como as demais, ficam de fora do comentário do schema em
  [001_initial_schema.sql](../migrations/001_initial_schema.sql) (lista os
  estados do bloco a) — coluna `text` livre, não precisa migration.
- **`conversation_context` passou a ser usado no bloco (c).** Guarda, ao longo
  da conversa: `listing_id`, `original_photo_storage_url` (setados assim que a
  foto é baixada e salva no Storage, antes até de perguntar o nome — ver
  próxima nota) e `nome_produto` (setado quando o vendedor responde). É o que
  permite a execução "pausar" esperando uma resposta de texto e, na próxima
  mensagem, continuar de onde parou sem perder o que já foi coletado — e o que
  permite o botão "gerar de novo" não pedir a foto nem o nome de volta.
- **A foto é baixada e salva no Storage assim que chega, antes de perguntar o
  nome do produto** — não no fim do fluxo. Motivo: a URL temporária que a Meta
  devolve pro binário da foto expira em poucos minutos, mas entre a foto
  chegar e o vendedor responder o nome do produto pode passar bem mais que
  isso (é uma pausa esperando resposta humana, sem tempo previsível). Uma URL
  do Supabase Storage não expira, então o download acontece uma vez só, cedo,
  e tudo depois disso (inclusive um eventual "gerar de novo") lê a foto do
  Storage, nunca da Meta de novo.
- **A transição não é atômica** em nenhum ponto do fluxo: cada etapa
  (criar listing, baixar/salvar foto, salvar nome, gerar título/descrição,
  gerar fotos, salvar no Storage) é um node Postgres/Code separado; se um
  falhar no meio, sobra estado parcial (ex: `listing` com título mas sem
  fotos). Aceitável no protótipo; vira transação só quando o fluxo passar a
  mexer em crédito.
- **Não há timeout de estado.** Um vendedor que trave em qualquer estado
  intermediário (ex: `aguardando_nome_produto`, se nunca responder) fica lá
  até alguém rodar o UPDATE acima.
