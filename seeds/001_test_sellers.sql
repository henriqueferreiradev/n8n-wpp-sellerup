-- =============================================================================
-- 001_test_sellers.sql
-- Seed mínima: 2 vendedores de teste (eu + um amigo) com crédito liberado
-- manualmente, mais o registro correspondente em credit_transactions.
--
-- Rodar depois da migration:
--   psql "$DATABASE_URL" -f seeds/001_test_sellers.sql
--
-- >>> ANTES DE RODAR: troque os números abaixo pelos números reais de WhatsApp,
-- >>> no formato E.164 (+55 + DDD + número). Os valores atuais são fictícios.
--
-- Idempotente: rodar mais de uma vez não duplica vendedor nem transação.
-- =============================================================================

begin;

insert into sellers (whatsapp_number, credit_balance, conversation_state)
values
  ('+5511999999999', 1000, 'novo'),  -- TROCAR: meu número
  ('+5511988888888', 1000, 'novo')   -- TROCAR: número do amigo de teste
on conflict (whatsapp_number) do nothing;

-- Documenta a liberação manual do crédito inicial.
-- amount_paid e pix_payment_id ficam null: não houve pagamento.
insert into credit_transactions (seller_id, amount_paid, credits_added, pix_payment_id, source, status)
select s.id, null::numeric(10,2), 1000, null::text, 'manual_test', 'completed'
from sellers s
where s.whatsapp_number in ('+5511999999999', '+5511988888888')
  and not exists (
    select 1
    from credit_transactions ct
    where ct.seller_id = s.id
      and ct.source = 'manual_test'
  );

commit;

-- Conferência rápida (o mesmo SELECT que o node Postgres do N8N vai rodar):
--   select whatsapp_number, credit_balance, conversation_state from sellers;
