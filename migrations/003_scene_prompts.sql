-- =============================================================================
-- 003_scene_prompts.sql
-- Adiciona listings.scene_prompts — os 8 prompts (um por cena) gerados pelo
-- GPT na hora da criação do anúncio.
--
-- Por que foi preciso: o recurso de "refazer 1 imagem específica" (lista
-- Imagem 1..8, botão 🔄 Refazer imagem) precisa do prompt_final daquela cena
-- pra chamar a Gemini de novo — sem guardar isso, teria que rechamar o GPT
-- (gerar-prompts-gpt) só pra recuperar um prompt que já foi gerado antes, o
-- que é mais caro e mais lento do que precisa ser.
--
-- Anúncios criados ANTES desta migration ficam com scene_prompts null — o
-- node buscar-scene-prompt não vai achar nada pra eles, e a regeneração de
-- imagem falha com um erro claro em vez de rechamar o GPT silenciosamente.
--
-- Rodar contra o mesmo banco do 001/002:
--   psql "$DATABASE_URL" -f migrations/003_scene_prompts.sql
--
-- Idempotente: pode ser rodado mais de uma vez sem erro.
-- Aditivo: não altera nem remove nada existente.
-- =============================================================================

begin;

-- { "1-foto-principal": "prompt final...", "2-problema-que-resolve": "...", ... }
-- Gravado por salvar-scene-prompts logo após gerar-prompts-gpt, na criação do
-- anúncio. Lido por buscar-scene-prompt (via scene_prompts ->> 'nome-da-cena')
-- quando o vendedor pede pra refazer uma imagem específica.
alter table listings
  add column if not exists scene_prompts jsonb;

comment on column listings.scene_prompts is
  'Prompt final por cena (chave = nome da cena, ex "3-beneficios-principais"), gerado pelo GPT na criação do anúncio. Usado para refazer 1 imagem sem rechamar o GPT. Null em anúncios criados antes desta coluna existir.';

commit;
