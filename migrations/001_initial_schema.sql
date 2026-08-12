-- =============================================================================
-- 001_initial_schema.sql
-- Schema inicial do protótipo (bloco a: camada de dados).
--
-- Rodar contra um Postgres/Supabase limpo:
--   psql "$DATABASE_URL" -f migrations/001_initial_schema.sql
--
-- Idempotente: pode ser rodado mais de uma vez sem erro.
-- =============================================================================

begin;

-- gen_random_uuid() é nativo no Postgres 13+, mas pgcrypto garante a função
-- em qualquer versão. No Supabase a extensão já vem disponível.
create extension if not exists pgcrypto;

-- -----------------------------------------------------------------------------
-- Trigger de updated_at
-- -----------------------------------------------------------------------------
create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- -----------------------------------------------------------------------------
-- sellers — vendedor/usuário de teste do bot
-- -----------------------------------------------------------------------------
create table if not exists sellers (
  id                    uuid primary key default gen_random_uuid(),

  -- Formato E.164, ex: +5511999999999
  whatsapp_number       text        not null unique,

  -- Preenchidos só depois do OAuth com o Mercado Livre (bloco d)
  ml_user_id            bigint,
  ml_access_token       text,
  ml_refresh_token      text,
  ml_token_expires_at   timestamptz,

  credit_balance        integer     not null default 0,

  -- Valores esperados nos próximos blocos: novo, aguardando_geracao,
  -- aguardando_aprovacao, aguardando_oauth_ml, publicando.
  -- Text simples de propósito: os estados ainda vão mudar durante o protótipo,
  -- e alterar um enum no Postgres é mais chato que alterar um check.
  conversation_state    text        not null default 'novo',

  -- Dados temporários da conversa em andamento (ex: url da última foto recebida)
  conversation_context  jsonb       not null default '{}'::jsonb,

  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),

  constraint sellers_credit_balance_non_negative check (credit_balance >= 0)
);

create index if not exists idx_sellers_whatsapp_number on sellers (whatsapp_number);

drop trigger if exists trg_sellers_updated_at on sellers;
create trigger trg_sellers_updated_at
  before update on sellers
  for each row
  execute function set_updated_at();

-- -----------------------------------------------------------------------------
-- listings — um anúncio sendo gerado/publicado
-- -----------------------------------------------------------------------------
create table if not exists listings (
  id                     uuid primary key default gen_random_uuid(),
  seller_id              uuid        not null references sellers (id) on delete cascade,

  original_photo_url     text,

  -- Array de objetos {url, scene, is_cover}
  generated_photos       jsonb       not null default '[]'::jsonb,

  generated_title        text,
  generated_description  text,
  ml_category_id         text,
  success_score          integer,

  -- Valores esperados: rascunho, aprovado, publicado
  status                 text        not null default 'rascunho',

  -- Preenchido depois da publicação no Mercado Livre (bloco d)
  ml_item_id             text,

  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),

  constraint listings_success_score_range check (
    success_score is null or (success_score between 0 and 100)
  )
);

create index if not exists idx_listings_seller_id on listings (seller_id);

drop trigger if exists trg_listings_updated_at on listings;
create trigger trg_listings_updated_at
  before update on listings
  for each row
  execute function set_updated_at();

-- -----------------------------------------------------------------------------
-- credit_transactions — histórico de crédito liberado
-- (manual agora; Pix numa fase futura)
-- -----------------------------------------------------------------------------
create table if not exists credit_transactions (
  id              uuid primary key default gen_random_uuid(),
  seller_id       uuid           not null references sellers (id) on delete cascade,

  -- Null quando a origem é manual/teste (não houve pagamento)
  amount_paid     numeric(10,2),

  credits_added   integer        not null,

  -- Reservado para a fase de cobrança via Pix; não usado no protótipo
  pix_payment_id  text,

  -- Valores esperados: manual_test, pix
  source          text           not null default 'manual_test',
  status          text           not null default 'completed',

  created_at      timestamptz    not null default now()
);

create index if not exists idx_credit_transactions_seller_id on credit_transactions (seller_id);

-- -----------------------------------------------------------------------------
-- market_analysis — resultado da análise de mercado + score, por anúncio
-- -----------------------------------------------------------------------------
create table if not exists market_analysis (
  id                     uuid primary key default gen_random_uuid(),
  listing_id             uuid        not null references listings (id) on delete cascade,

  trend_score            numeric,
  competition_level      text,

  -- ex: {"min": 10, "max": 20}
  suggested_price_range  jsonb,

  -- Explicação legível do score, mostrada ao usuário no WhatsApp
  rationale_text         text,

  created_at             timestamptz not null default now()
);

create index if not exists idx_market_analysis_listing_id on market_analysis (listing_id);

commit;
