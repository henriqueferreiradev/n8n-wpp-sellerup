-- =============================================================================
-- 002_seller_name.sql
-- Adiciona sellers.name — o nome que o vendedor informa na primeira conversa.
--
-- Por que foi preciso: o fluxo de mensagens passou a começar pedindo o nome do
-- vendedor ("como posso te chamar?") e a usá-lo na mensagem de boas-vindas
-- ("Prazer, {nome}!"). Não havia onde guardar isso — a tabela sellers não tinha
-- coluna de nome, e conversation_context não serve: ele é reescrito inteiro
-- (jsonb_build_object) em atualizar-estado-nome-produto e
-- atualizar-estado-aprovacao, então o nome se perderia no meio do fluxo.
--
-- Rodar contra o mesmo banco do 001:
--   psql "$DATABASE_URL" -f migrations/002_seller_name.sql
--
-- Idempotente: pode ser rodado mais de uma vez sem erro.
-- Aditivo: não altera nem remove nada existente.
-- =============================================================================

begin;

-- Nome informado pelo próprio vendedor no primeiro contato (estado
-- 'aguardando_nome_vendedor'). Fica null até ele responder — é o que distingue
-- um vendedor recém-liberado de um que já passou pela saudação.
alter table sellers
  add column if not exists name text;

comment on column sellers.name is
  'Nome que o vendedor informou na primeira conversa. Null = ainda não passou pela saudação.';

commit;

-- -----------------------------------------------------------------------------
-- NÃO incluído de propósito: listings.palavras_chave
-- -----------------------------------------------------------------------------
-- O node gerar-titulo-descricao passou a gerar também um campo palavras_chave
-- (string única de 12-18 termos separados por espaço), enviado ao vendedor na
-- mensagem *Palavras-chave*. Nesta rodada ele NÃO é persistido — só trafega na
-- execução, de montar-titulo-descricao-final até a mensagem do WhatsApp.
--
-- Se um dia valer a pena guardar, é só isto (mais incluir a coluna no UPDATE do
-- node atualizar-listing-titulo-descricao e no seu RETURNING):
--
--   alter table listings add column if not exists palavras_chave text;
